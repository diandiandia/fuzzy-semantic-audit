import argparse
import json
import os
import sys
import time

from src_v3.core.models import AuditPlan, RepoProfile, CandidateRecord
from src_v3.core.plan_io import load_plan, save_plan
from src_v3.core.event_log import log_event
from src_v3.core.metrics import record_metric
from src_v3.core.enums import ShardStatus, ShardStatus
from src_v3.core.provider_registry import resolve_semantic
from src_v3.storage.ir_store import IRStore
from src_v3.storage.candidate_store import CandidateStore
from src_v3.enrich.semantic_orchestrator import enrich_semantic_relations
from src_v3.enrich.framework_semantics import enrich_framework_semantics
from src_v3.providers.framework.generic import GenericFrameworkProvider
from src_v3.providers.framework.django import DjangoPack
from src_v3.providers.framework.express import ExpressPack
from src_v3.recall.orchestrator import orchestrate_recall

def parse_args():
    parser = argparse.ArgumentParser(description="Orchestrate candidate recall across all shards and tracks")
    parser.add_argument("--workspace", required=True, help="Path to the V3 workspace directory")
    return parser.parse_args()

def main():
    args = parse_args()
    workspace_dir = os.path.abspath(args.workspace)
    
    plan_path = os.path.join(workspace_dir, "audit_plan.json")
    if not os.path.exists(plan_path):
        print(json.dumps({
            "ok": False,
            "stage": "recall_candidates",
            "message": f"Audit plan not found: {plan_path}"
        }, ensure_ascii=False))
        sys.exit(1)
        
    start_time = time.time()
    
    try:
        plan = load_plan(plan_path)
        repo_path = plan.repo_path
        
        ir_store = IRStore(workspace_dir)
        candidate_store = CandidateStore(workspace_dir)
        
        # Load repo profile
        profile_path = os.path.join(workspace_dir, plan.repo_profile_path)
        if os.path.exists(profile_path):
            with open(profile_path, 'r', encoding='utf-8') as f:
                profile_data = json.load(f)
            profile = RepoProfile.from_dict(profile_data)
        else:
            profile = RepoProfile()
            
        config = plan.summary.get("config", {})
        
        all_candidates = []
        
        for shard in plan.language_shards:
            # Skip if shard index / parser failed
            if shard.status == ShardStatus.FAILED.value:
                continue
                
            # 1. Resolve semantic provider from the saved provider_set (inheriting fallback state)
            from src_v3.core.provider_registry import resolve_provider_by_name
            semantic_provider_name = shard.provider_set.get("semantic", "NullProvider")
            raw_provider = resolve_provider_by_name(semantic_provider_name, config, repo_path, ir_store)
            if not raw_provider:
                from src_v3.providers.semantic.null_provider import NullProvider
                raw_provider = NullProvider()
            from src_v3.providers.semantic.cached_provider import CachedSemanticProvider
            semantic_provider = CachedSemanticProvider(raw_provider, workspace_dir, shard.shard_id)
            
            # 2. Enrich semantic calling relations
            enrich_semantic_relations(workspace_dir, repo_path, shard, semantic_provider)
            
            # 3. Enrich framework annotations based on saved provider_set
            fw_provider_name = shard.provider_set.get("framework", "GenericFrameworkProvider")
            fw_provider = resolve_provider_by_name(fw_provider_name, config, repo_path, ir_store)
            if fw_provider:
                enrich_framework_semantics(workspace_dir, shard, [fw_provider])
            
            # 4. Perform multi-channel recall
            shard_candidates = orchestrate_recall(workspace_dir, shard, plan.audit_tracks, config)
            all_candidates.extend(shard_candidates)
            
            # 5. Set shard recalled status
            from src_v3.core.state_machine import transition
            if shard.status == ShardStatus.INDEXED_FALLBACK.value or shard.capability in ["L0", "L1"]:
                transition(shard, ShardStatus.RECALLED_FALLBACK.value, workspace_dir=workspace_dir)
            else:
                transition(shard, ShardStatus.RECALLED.value, workspace_dir=workspace_dir)
                
        # 6. Deduplicate & save candidates globally
        candidate_store.save_candidates(all_candidates, pruned=False, overwrite=True)
        
        save_plan(plan, plan_path)
        
        duration = time.time() - start_time
        
        # Log event and metrics
        log_event(workspace_dir, "recall_candidates", "info", f"Total of {len(all_candidates)} candidates recalled", {
            "recalled_count": len(all_candidates),
            "duration_seconds": duration
        })
        
        record_metric(workspace_dir, "recall_candidates", "recalled_count", len(all_candidates))
        record_metric(workspace_dir, "recall_candidates", "wall_clock_seconds", duration)
        
        # Output JSON contract
        print(json.dumps({
            "ok": True,
            "stage": "recall_candidates",
            "workspace_dir": workspace_dir,
            "summary": {
                "recalled_count": len(all_candidates),
                "wall_clock_seconds": duration
            }
        }, ensure_ascii=False))
        
    except Exception as e:
        import traceback
        print(json.dumps({
            "ok": False,
            "stage": "recall_candidates",
            "message": f"Error recalling candidates: {str(e)}",
            "traceback": traceback.format_exc()
        }, ensure_ascii=False))
        sys.exit(1)

if __name__ == "__main__":
    main()
