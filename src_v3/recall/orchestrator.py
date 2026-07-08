from typing import List, Dict, Any
from src_v3.core.models import LanguageShard, CandidateRecord
from src_v3.core.event_log import log_event
from src_v3.recall.rule_recall import recall_by_rules
from src_v3.recall.vector_recall import recall_by_vector
from src_v3.recall.graph_recall import expand_by_graph
from src_v3.recall.resource_recall import recall_by_resources
from src_v3.recall.framework_recall import recall_by_framework
from src_v3.recall.normalizer import normalize_candidates

def orchestrate_recall(
    workspace_dir: str, 
    shard: LanguageShard, 
    tracks: List[str], 
    config: Dict[str, Any]
) -> List[CandidateRecord]:
    """
    Coordinates execution of all 5 recall channels across the requested tracks.
    """
    all_raw_candidates: List[CandidateRecord] = []
    
    # Track stats
    stats = {
        "rule": 0,
        "vector": 0,
        "resource": 0,
        "framework": 0,
        "graph": 0
    }
    
    for track in tracks:
        track_seeds: List[CandidateRecord] = []
        
        # 1. Rule Recall
        rule_cands = recall_by_rules(workspace_dir, shard, track)
        stats["rule"] += len(rule_cands)
        track_seeds.extend(rule_cands)
        
        # 2. Vector Recall
        vec_cands = recall_by_vector(workspace_dir, shard, track, config)
        stats["vector"] += len(vec_cands)
        track_seeds.extend(vec_cands)
        
        # 3. Resource Recall
        res_cands = recall_by_resources(workspace_dir, shard, track)
        stats["resource"] += len(res_cands)
        track_seeds.extend(res_cands)
        
        # 4. Framework Recall
        fw_cands = recall_by_framework(workspace_dir, shard, track)
        stats["framework"] += len(fw_cands)
        track_seeds.extend(fw_cands)
        
        # 5. Graph Recall (using all track_seeds as JID seed points for expansion)
        graph_cands = expand_by_graph(workspace_dir, shard, track, track_seeds)
        stats["graph"] += len(graph_cands)
        
        track_all = track_seeds + graph_cands
        
        if not track_all:
            # Log event for zero-recall combination
            log_event(workspace_dir, "recall", "info", f"Zero recall for shard '{shard.shard_id}' on track '{track}'", {
                "shard_id": shard.shard_id,
                "track": track
            })
            
        all_raw_candidates.extend(track_all)
        
    # 6. Normalize and deduplicate JIDs
    normalized = normalize_candidates(all_raw_candidates)
    
    log_event(workspace_dir, "recall", "info", f"Recall completed for shard '{shard.shard_id}'", {
        "shard_id": shard.shard_id,
        "raw_count": len(all_raw_candidates),
        "normalized_count": len(normalized),
        "channel_stats": stats
    })
    
    return normalized
