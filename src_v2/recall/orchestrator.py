from typing import List, Dict, Tuple
from src_v2.core.models import AuditPlan, CandidateRecord, LanguageShard, AuditTrack
from src_v2.plugins.base import LanguagePlugin
from src_v2.plugins.generic import GenericPlugin
from src_v2.recall import rule_recall, graph_recall, vector_recall, resource_recall
from src_v2.recall.normalizer import normalize_candidates
from src_v2.recall.priority_ranker import rank_candidates

# Plugin cache / registry
_PLUGINS: Dict[str, LanguagePlugin] = {}

def get_plugin(lang: str) -> LanguagePlugin:
    """Get or load plugin instance for language."""
    if lang in _PLUGINS:
        return _PLUGINS[lang]
        
    # Dynamically load specialized plugins if they exist, fallback to generic
    plugin = None
    try:
        if lang == "python":
            from src_v2.plugins.python import PythonPlugin
            plugin = PythonPlugin()
        elif lang in {"javascript", "typescript"}:
            from src_v2.plugins.javascript import JavaScriptPlugin
            plugin = JavaScriptPlugin()
        elif lang == "go":
            from src_v2.plugins.go import GoPlugin
            plugin = GoPlugin()
        elif lang == "java":
            from src_v2.plugins.java import JavaPlugin
            plugin = JavaPlugin()
        elif lang in {"c", "cpp"}:
            # C and C++ can use same plugin
            from src_v2.plugins.cpp import CppPlugin
            plugin = CppPlugin()
    except ImportError:
        # Specialized plugin file not implemented/imported yet, fallback
        pass
        
    if plugin is None:
        plugin = GenericPlugin()
        
    _PLUGINS[lang] = plugin
    return plugin

def run_recall(plan: AuditPlan) -> Tuple[List[CandidateRecord], List[Tuple[str, str]]]:
    """
    Run the full recall phase. 
    Returns:
      - list of normalized, prioritized candidates.
      - list of (shard_id, track_id) pairs with zero recall.
    """
    raw_candidates: List[CandidateRecord] = []
    zero_recall_pairs: List[Tuple[str, str]] = []
    
    repo_path = plan.repo_path

    # Iterate over every shard and track
    for shard in plan.language_shards:
        plugin = get_plugin(shard.lang)
        
        for track in plan.audit_tracks:
            if track.status != "active":
                continue
                
            shard_track_candidates: List[CandidateRecord] = []
            
            # Run multi-channel recall
            import os, sys
            workspace_dir = os.path.join(repo_path, ".audit_workspace_v2")
            from src_v2.core.event_log import log_event
            
            # 1. Rule recall (primary for L0/L1)
            try:
                rule_cands = rule_recall.run(repo_path, shard, track, plugin)
                shard_track_candidates.extend(rule_cands)
            except Exception as e:
                log_event(
                    workspace_dir=workspace_dir,
                    stage="recall",
                    event_type="channel_error",
                    details={"shard": shard.shard_id, "track": track.track_id, "channel": "rule", "error": str(e)}
                )
                sys.stderr.write(f"Error in rule recall channel: {str(e)}\n")
                
            # 2. Graph recall
            try:
                graph_cands = graph_recall.run(repo_path, shard, track, plugin)
                shard_track_candidates.extend(graph_cands)
            except Exception as e:
                log_event(
                    workspace_dir=workspace_dir,
                    stage="recall",
                    event_type="channel_error",
                    details={"shard": shard.shard_id, "track": track.track_id, "channel": "graph", "error": str(e)}
                )
                sys.stderr.write(f"Error in graph recall channel: {str(e)}\n")
                
            # 3. Vector recall
            try:
                vector_cands = vector_recall.run(repo_path, shard, track, plugin)
                shard_track_candidates.extend(vector_cands)
            except Exception as e:
                log_event(
                    workspace_dir=workspace_dir,
                    stage="recall",
                    event_type="channel_error",
                    details={"shard": shard.shard_id, "track": track.track_id, "channel": "vector", "error": str(e)}
                )
                sys.stderr.write(f"Error in vector recall channel: {str(e)}\n")
                
            # 4. Resource recall
            try:
                resource_cands = resource_recall.run(repo_path, shard, track, plugin)
                shard_track_candidates.extend(resource_cands)
            except Exception as e:
                log_event(
                    workspace_dir=workspace_dir,
                    stage="recall",
                    event_type="channel_error",
                    details={"shard": shard.shard_id, "track": track.track_id, "channel": "resource", "error": str(e)}
                )
                sys.stderr.write(f"Error in resource recall channel: {str(e)}\n")
                
            if not shard_track_candidates:
                # Zero recall event
                zero_recall_pairs.append((shard.shard_id, track.track_id))
                log_event(
                    workspace_dir=workspace_dir,
                    stage="recall",
                    event_type="zero_recall",
                    details={"shard_id": shard.shard_id, "track_id": track.track_id}
                )
            else:
                raw_candidates.extend(shard_track_candidates)
                
    # Normalize candidates (deduplicate and merge tracks/rules/recall_sources)
    normalized = normalize_candidates(raw_candidates)
    
    # Prioritize candidates
    ranked = rank_candidates(normalized, plan.repo_profile)
    
    return ranked, zero_recall_pairs
