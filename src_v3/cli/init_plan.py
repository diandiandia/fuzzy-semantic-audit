import argparse
import json
import os
import sys
import datetime
import uuid

from src_v3.core.models import AuditPlan, RunManifest, LanguageShard
from src_v3.core.plan_io import save_plan, save_run_manifest
from src_v3.core.event_log import log_event
from src_v3.core.metrics import record_metric
from src_v3.storage.sqlite import init_ir_cache_db, init_provider_cache_db

DEFAULT_TRACKS = [
    "authz",
    "state_machine",
    "resource_access",
    "injection",
    "input_validation",
    "deserialization",
    "memory_safety",
    "concurrency",
    "crypto",
    "filesystem_boundary"
]

def parse_args():
    parser = argparse.ArgumentParser(description="Initialize Fuzzy Semantic Audit V3 Workspace and Plan")
    parser.add_argument("--project", required=True, help="Path to the repository to audit")
    parser.add_argument("--workspace", help="Path to the workspace directory (default: <project>/.audit_workspace_v3)")
    parser.add_argument("--tracks", help="Comma-separated list of audit tracks to enable")
    return parser.parse_args()

def main():
    args = parse_args()
    
    project_path = os.path.abspath(args.project)
    if not os.path.exists(project_path):
        print(json.dumps({
            "ok": False,
            "stage": "init_plan",
            "message": f"Project path does not exist: {project_path}"
        }, ensure_ascii=False))
        sys.exit(1)
        
    workspace_dir = args.workspace
    if not workspace_dir:
        workspace_dir = os.path.join(project_path, ".audit_workspace_v3")
    workspace_dir = os.path.abspath(workspace_dir)
    
    # Enable tracks
    tracks = DEFAULT_TRACKS
    if args.tracks:
        tracks = [t.strip() for t in args.tracks.split(",") if t.strip()]
        
    try:
        # Create directory structure
        dirs = [
            os.path.join(workspace_dir, "ir"),
            os.path.join(workspace_dir, "indices", "lexical"),
            os.path.join(workspace_dir, "indices", "vector"),
            os.path.join(workspace_dir, "indices", "semantic"),
            os.path.join(workspace_dir, "candidates"),
            os.path.join(workspace_dir, "evidence", "packages"),
            os.path.join(workspace_dir, "queues"),
            os.path.join(workspace_dir, "reports"),
            os.path.join(workspace_dir, "metrics"),
            os.path.join(workspace_dir, "cache")
        ]
        
        for d in dirs:
            os.makedirs(d, exist_ok=True)
            
        # Initialize databases
        init_ir_cache_db(os.path.join(workspace_dir, "cache", "ir.sqlite"))
        init_provider_cache_db(os.path.join(workspace_dir, "cache", "provider.sqlite"))
        
        # Initialize queues as empty files
        queue_files = ["verify_now.json", "manual_review.json", "deferred.json"]
        for q in queue_files:
            qp = os.path.join(workspace_dir, "queues", q)
            if not os.path.exists(qp):
                with open(qp, "w", encoding="utf-8") as f:
                    json.dump([], f)
                    
        # Create AuditPlan
        plan_path = os.path.join(workspace_dir, "audit_plan.json")
        repo_profile_path = os.path.join(workspace_dir, "repo_profile.json")
        
        # Create empty profile if not exists
        if not os.path.exists(repo_profile_path):
            with open(repo_profile_path, "w", encoding="utf-8") as f:
                json.dump({
                    "languages": [],
                    "build_systems": [],
                    "frameworks": [],
                    "directory_roles": {},
                    "entrypoint_hints": [],
                    "risk_directories": []
                }, f, indent=2)
                
        plan = AuditPlan(
            version="3",
            repo_path=project_path,
            workspace_dir=workspace_dir,
            repo_profile_path="repo_profile.json",
            language_shards=[],
            audit_tracks=tracks,
            summary={},
            created_at=datetime.datetime.now(datetime.timezone.utc).isoformat(),
            updated_at=datetime.datetime.now(datetime.timezone.utc).isoformat()
        )
        
        # Create RunManifest
        run_manifest = RunManifest(
            run_id=str(uuid.uuid4()),
            run_mode="rule_only", # Default starting run mode
            run_capability="L0", # Default starting capability
            providers={},
            degradation_reasons=[]
        )
        plan.run_manifest = run_manifest
        
        # Save plan and manifest
        save_plan(plan, plan_path)
        manifest_path = os.path.join(workspace_dir, "run_manifest.json")
        save_run_manifest(run_manifest, manifest_path)
        
        # Log event and metric
        log_event(workspace_dir, "init_plan", "info", "Workspace and audit plan initialized successfully", {
            "project_path": project_path,
            "tracks": tracks
        })
        record_metric(workspace_dir, "init_plan", "initialized", True)
        
        # Print JSON contract to stdout
        contract = {
            "ok": True,
            "stage": "init_plan",
            "workspace_dir": workspace_dir,
            "summary": {
                "project_path": project_path,
                "tracks_count": len(tracks),
                "run_id": run_manifest.run_id
            }
        }
        print(json.dumps(contract, ensure_ascii=False))
        
    except Exception as e:
        import traceback
        print(json.dumps({
            "ok": False,
            "stage": "init_plan",
            "message": f"Error initializing workspace: {str(e)}",
            "traceback": traceback.format_exc()
        }, ensure_ascii=False))
        sys.exit(1)

if __name__ == "__main__":
    main()
