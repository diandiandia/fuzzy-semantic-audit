import os
import sys
import argparse
import json
from src_v2.core.models import AuditPlan, AuditTrack, PlanSummary
from src_v2.core.plan_io import save_plan, load_plan

def load_tracks_from_config() -> list:
    """Load standard default tracks and overlay custom configurations from resources_v2/tracks/*.json."""
    default_tracks = [
        AuditTrack(track_id="authz", title="Authorization and Ownership", mapped_cwes=["285", "639", "862", "863"]),
        AuditTrack(track_id="state_machine", title="State Machine Logic", mapped_cwes=["841"]),
        AuditTrack(track_id="resource_access", title="Resource Access Control", mapped_cwes=["22", "73", "552", "668"]),
        AuditTrack(track_id="injection", title="Code and Command Injection", mapped_cwes=["77", "78", "89", "94"]),
        AuditTrack(track_id="input_validation", title="Input Validation and Sanitization", mapped_cwes=["20"]),
        AuditTrack(track_id="deserialization", title="Unsafe Deserialization", mapped_cwes=["502"]),
        AuditTrack(track_id="memory_safety", title="Memory Safety", mapped_cwes=["119", "416", "787"]),
        AuditTrack(track_id="concurrency", title="Concurrency and Race Conditions", mapped_cwes=["362", "367"]),
        AuditTrack(track_id="crypto", title="Cryptographic Weaknesses", mapped_cwes=["327", "328", "338"]),
        AuditTrack(track_id="filesystem_boundary", title="Filesystem Boundary Bypass", mapped_cwes=["23", "36"])
    ]
    tracks_map = {t.track_id: t for t in default_tracks}
    
    base_dir = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    tracks_dir = os.path.join(base_dir, "resources_v2", "tracks")
    
    if os.path.exists(tracks_dir):
        try:
            for file in sorted(os.listdir(tracks_dir)):
                if file.endswith(".json"):
                    fp = os.path.join(tracks_dir, file)
                    with open(fp, "r", encoding="utf-8") as f:
                        data = json.load(f)
                        track_id = data["track_id"]
                        track = AuditTrack(
                            track_id=track_id,
                            title=data["title"],
                            mapped_cwes=data.get("mapped_cwes", [])
                        )
                        tracks_map[track_id] = track
        except Exception:
            pass
            
    return list(tracks_map.values())

def main():
    parser = argparse.ArgumentParser(description="Initialize audit workspace and plan.")
    parser.add_argument("--project", required=True, help="Absolute path to the repository to audit.")
    args = parser.parse_args()

    project_path = os.path.abspath(args.project)
    workspace_dir = os.path.join(project_path, ".audit_workspace_v2")
    queues_dir = os.path.join(workspace_dir, "queues")
    registry_path = os.path.join(workspace_dir, "candidate_registry.jsonl")
    plan_path = os.path.join(workspace_dir, "audit_plan.json")

    # Load tracks from config dynamically
    standard_tracks = load_tracks_from_config()

    # Create directories
    os.makedirs(workspace_dir, exist_ok=True)
    os.makedirs(queues_dir, exist_ok=True)

    # Touch registry file
    with open(registry_path, "a", encoding="utf-8") as f:
        pass

    # Create empty queues files if they don't exist
    for q_name in ["verify_now", "deferred", "manual_review"]:
        q_path = os.path.join(queues_dir, f"{q_name}.json")
        if not os.path.exists(q_path):
            with open(q_path, "w", encoding="utf-8") as f:
                json.dump({
                    "queue_name": q_name,
                    "candidate_ids": [],
                    "updated_at": "1970-01-01T00:00:00Z"
                }, f, indent=2)

    # Initialize or load AuditPlan
    if os.path.exists(plan_path):
        try:
            plan = load_plan(plan_path)
            # Ensure standard tracks are present and active
            existing_track_ids = {t.track_id for t in plan.audit_tracks}
            for t in standard_tracks:
                if t.track_id not in existing_track_ids:
                    plan.audit_tracks.append(t)
            plan.summary.tracks_total = len(plan.audit_tracks)
        except Exception:
            plan = AuditPlan(
                repo_path=project_path,
                repo_profile_path=os.path.relpath(os.path.join(workspace_dir, "repo_profile.json"), project_path),
                audit_tracks=standard_tracks,
                summary=PlanSummary(tracks_total=len(standard_tracks))
            )
    else:
        plan = AuditPlan(
            repo_path=project_path,
            repo_profile_path=os.path.relpath(os.path.join(workspace_dir, "repo_profile.json"), project_path),
            audit_tracks=standard_tracks,
            summary=PlanSummary(tracks_total=len(standard_tracks))
        )
    
    save_plan(plan, plan_path)

    # Output JSON contract
    result = {
        "ok": True,
        "workspace": workspace_dir,
        "plan": plan_path
    }
    print(json.dumps(result))

if __name__ == "__main__":
    main()
