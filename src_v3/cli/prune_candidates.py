import argparse
import json
import os
import sys
import time

from src_v3.core.models import AuditPlan
from src_v3.core.plan_io import load_plan, save_plan
from src_v3.core.event_log import log_event
from src_v3.core.metrics import record_metric
from src_v3.storage.ir_store import IRStore
from src_v3.storage.candidate_store import CandidateStore
from src_v3.prune.feature_extractor import extract_features
from src_v3.prune.scorer import calculate_priority_score
from src_v3.prune.static_pruner import prune_candidates

def parse_args():
    parser = argparse.ArgumentParser(description="Extract features, score, and prune candidates")
    parser.add_argument("--workspace", required=True, help="Path to the V3 workspace directory")
    parser.add_argument("--threshold", type=float, default=45.0, help="Priority score threshold for pruning")
    return parser.parse_args()

def main():
    args = parse_args()
    workspace_dir = os.path.abspath(args.workspace)
    
    plan_path = os.path.join(workspace_dir, "audit_plan.json")
    if not os.path.exists(plan_path):
        print(json.dumps({
            "ok": False,
            "stage": "prune_candidates",
            "message": f"Audit plan not found: {plan_path}"
        }, ensure_ascii=False))
        sys.exit(1)
        
    start_time = time.time()
    
    try:
        plan = load_plan(plan_path)
        
        ir_store = IRStore(workspace_dir)
        candidate_store = CandidateStore(workspace_dir)
        
        # Load recalled candidates
        recalled = candidate_store.get_candidates(pruned=False)
        if not recalled:
            # Output empty JSON contract
            print(json.dumps({
                "ok": True,
                "stage": "prune_candidates",
                "workspace_dir": workspace_dir,
                "summary": {
                    "recalled_total": 0,
                    "pruned_total": 0,
                    "compression_ratio": 1.0,
                    "wall_clock_seconds": time.time() - start_time
                }
            }, ensure_ascii=False))
            sys.exit(0)
            
        config = plan.summary.get("config", {})
        
        # 1. Score all candidates
        for cand in recalled:
            features = extract_features(workspace_dir, cand, ir_store)
            cand.priority_score = calculate_priority_score(features, config)
            
        # 2. Perform static pruning
        kept, metrics = prune_candidates(recalled, threshold=args.threshold)
        
        # 3. Save kept candidates to pruned registry
        candidate_store.save_candidates(kept, pruned=True, overwrite=True)
        
        # Save plan updates
        save_plan(plan, plan_path)
        
        duration = time.time() - start_time
        
        # Log event and metrics
        log_event(workspace_dir, "prune_candidates", "info", f"Backlog compression completed: JIDs reduced from {metrics['recalled_total']} to {metrics['pruned_total']}", {
            "recalled_total": metrics["recalled_total"],
            "pruned_total": metrics["pruned_total"],
            "compression_ratio": metrics["compression_ratio"],
            "duration_seconds": duration
        })
        
        record_metric(workspace_dir, "prune_candidates", "recalled_total", metrics["recalled_total"])
        record_metric(workspace_dir, "prune_candidates", "pruned_total", metrics["pruned_total"])
        record_metric(workspace_dir, "prune_candidates", "compression_ratio", metrics["compression_ratio"])
        record_metric(workspace_dir, "prune_candidates", "wall_clock_seconds", duration)
        
        # Output JSON contract
        print(json.dumps({
            "ok": True,
            "stage": "prune_candidates",
            "workspace_dir": workspace_dir,
            "summary": {
                "recalled_total": metrics["recalled_total"],
                "pruned_total": metrics["pruned_total"],
                "compression_ratio": metrics["compression_ratio"],
                "wall_clock_seconds": duration
            }
        }, ensure_ascii=False))
        
    except Exception as e:
        import traceback
        print(json.dumps({
            "ok": False,
            "stage": "prune_candidates",
            "message": f"Error pruning candidates: {str(e)}",
            "traceback": traceback.format_exc()
        }, ensure_ascii=False))
        sys.exit(1)

if __name__ == "__main__":
    main()
