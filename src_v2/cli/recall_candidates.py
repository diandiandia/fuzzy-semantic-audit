import os
import sys
import argparse
import json
from src_v2.core.plan_io import load_plan, save_plan, update_plan_summary
from src_v2.core.candidate_registry import load_candidates, upsert_candidates, save_candidates
from src_v2.core.queue_store import enqueue
from src_v2.recall.orchestrator import run_recall
from src_v2.core.state_machine import transition

def main():
    parser = argparse.ArgumentParser(description="Run multi-channel candidate recall.")
    parser.add_argument("--project", help="Absolute path to the repository.")
    parser.add_argument("--plan", help="Path to the audit_plan.json file.")
    args = parser.parse_args()

    if not args.project and not args.plan:
        print(json.dumps({"ok": False, "error": "Either --project or --plan must be provided."}))
        sys.exit(1)

    plan_path = None
    if args.plan:
        plan_path = os.path.abspath(args.plan)
    elif args.project:
        project_path = os.path.abspath(args.project)
        plan_path = os.path.join(project_path, ".audit_workspace_v2", "audit_plan.json")

    try:
        plan = load_plan(plan_path)
    except Exception as e:
        print(json.dumps({"ok": False, "error": f"Failed to load plan: {str(e)}"}))
        sys.exit(1)

    workspace_dir = os.path.dirname(plan_path)
    registry_path = os.path.join(workspace_dir, "candidate_registry.jsonl")
    queue_dir = os.path.join(workspace_dir, "queues")

    # 1. Run recall
    from src_v2.core.event_log import log_event
    log_event(workspace_dir, "recall", "stage_start", {})
    try:
        candidates, zero_recall_pairs = run_recall(plan)
    except Exception as e:
        print(json.dumps({"ok": False, "error": f"Failed to run recall: {str(e)}"}))
        sys.exit(1)

    # 2. Upsert candidates into registry
    try:
        upsert_candidates(registry_path, candidates)
    except Exception as e:
        print(json.dumps({"ok": False, "error": f"Failed to upsert candidates: {str(e)}"}))
        sys.exit(1)

    # 3. Transition newly recalled candidates to queued_for_verify and collect them
    all_candidates = load_candidates(registry_path)
    to_enqueue = []
    
    for c in all_candidates:
        try:
            if c.status == "discovered":
                transition(c, "indexed")
            if c.status == "indexed":
                transition(c, "recalled")
            if c.status == "recalled":
                transition(c, "normalized")
            if c.status == "normalized":
                transition(c, "queued_for_verify")
                to_enqueue.append(c.candidate_id)
        except Exception as e:
            pass
                
    # Save the transitioned statuses
    save_candidates(registry_path, all_candidates)

    # 4. Enqueue into verify_now
    if to_enqueue:
        try:
            enqueue(queue_dir, "verify_now", to_enqueue)
        except Exception as e:
            print(json.dumps({"ok": False, "error": f"Failed to enqueue candidates: {str(e)}"}))
            sys.exit(1)

    # 5. Update plan summary and shard statuses
    try:
        for shard in plan.language_shards:
            if shard.status in {"indexed", "indexed_fallback", "discovered"}:
                shard.status = "recalled" if shard.status != "indexed_fallback" else "recalled_fallback"
        save_plan(plan, plan_path)
        update_plan_summary(plan_path, all_candidates)
    except Exception as e:
        print(json.dumps({"ok": False, "error": f"Failed to update plan summary and shard statuses: {str(e)}"}))
        sys.exit(1)

    log_event(workspace_dir, "recall", "stage_end", {
        "candidates_total": len(all_candidates),
        "queued_for_verify": len(to_enqueue)
    })

    # Output JSON contract
    result = {
        "ok": True,
        "candidates_total": len(all_candidates),
        "queued_for_verify": len(to_enqueue),
        "zero_recall_pairs": zero_recall_pairs
    }
    print(json.dumps(result))

if __name__ == "__main__":
    main()
