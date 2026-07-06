import os
import sys
import argparse
import json
from src_v2.core.plan_io import load_plan, save_plan
from src_v2.inventory.repo_profiler import profile_repo
from src_v2.inventory.language_sharder import generate_shards

def main():
    parser = argparse.ArgumentParser(description="Scan repository and build inventory (shards and profile).")
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

    # 1. Profile repo
    workspace_dir = os.path.dirname(plan_path)
    from src_v2.core.event_log import log_event
    log_event(workspace_dir, "inventory", "stage_start", {})

    try:
        profile = profile_repo(plan.repo_path)
    except Exception as e:
        print(json.dumps({"ok": False, "error": f"Failed to profile repo: {str(e)}"}))
        sys.exit(1)

    # 2. Save repo_profile.json
    workspace_dir = os.path.dirname(plan_path)
    profile_path = os.path.join(workspace_dir, "repo_profile.json")
    try:
        with open(profile_path, "w", encoding="utf-8") as f:
            f.write(profile.model_dump_json(indent=2))
    except Exception as e:
        print(json.dumps({"ok": False, "error": f"Failed to save repo profile: {str(e)}"}))
        sys.exit(1)

    # 3. Generate shards
    try:
        shards = generate_shards(profile)
    except Exception as e:
        print(json.dumps({"ok": False, "error": f"Failed to generate shards: {str(e)}"}))
        sys.exit(1)

    # 4. Update AuditPlan
    plan.repo_profile_path = os.path.relpath(profile_path, plan.repo_path)
    plan.repo_profile = profile
    plan.language_shards = shards
    plan.summary.shards_total = len(shards)
    
    try:
        save_plan(plan, plan_path)
    except Exception as e:
        print(json.dumps({"ok": False, "error": f"Failed to save plan: {str(e)}"}))
        sys.exit(1)

    # Get list of unique languages
    languages = sorted(list(set(shard.lang for shard in shards)))

    log_event(workspace_dir, "inventory", "stage_end", {"shards_total": len(shards)})

    result = {
        "ok": True,
        "repo_profile": profile_path,
        "shards_total": len(shards),
        "languages": languages
    }
    print(json.dumps(result))

if __name__ == "__main__":
    main()
