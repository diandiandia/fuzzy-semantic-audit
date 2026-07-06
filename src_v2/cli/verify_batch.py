import os
import sys
import argparse
import json
from src_v2.core.plan_io import load_plan, update_plan_summary
from src_v2.core.candidate_registry import load_candidates, save_candidates, get_candidate
from src_v2.core.queue_store import dequeue, enqueue, load_queue, save_queue
from src_v2.verify.writeback import writeback_verdicts
from src_v2.core.state_machine import transition
from src_v2.verify.package_builder import build_candidate_package
from datetime import datetime, timezone

def parse_utc_timestamp(ts_str: str) -> datetime:
    """Parse UTC timestamp string in ISO 8601 format."""
    clean_ts = ts_str.replace("Z", "+00:00")
    return datetime.fromisoformat(clean_ts)

def check_lease_expiry(candidates, registry_path, queue_dir, plan_path, timeout_seconds=1800):
    """Check for expired verifying leases (e.g. timeout > timeout_seconds) and transition them to deferred."""
    now = datetime.now(timezone.utc)
    expired_count = 0
    deferred_ids = []
    
    for c in candidates:
        if c.status == "verifying":
            try:
                updated_at_dt = parse_utc_timestamp(c.updated_at)
                if updated_at_dt.tzinfo is None:
                    updated_at_dt = updated_at_dt.replace(tzinfo=timezone.utc)
                
                age = (now - updated_at_dt).total_seconds()
                if age > timeout_seconds: # configurable lease timeout
                    transition(c, "deferred")
                    deferred_ids.append(c.candidate_id)
                    expired_count += 1
            except Exception:
                pass
                
    if expired_count > 0:
        save_candidates(registry_path, candidates)
        # Move expired from verify_now to deferred queue
        verify_now = load_queue(queue_dir, "verify_now")
        remaining = [cid for cid in verify_now if cid not in deferred_ids]
        save_queue(queue_dir, "verify_now", remaining)
        enqueue(queue_dir, "deferred", deferred_ids)
        update_plan_summary(plan_path, candidates)
    return expired_count

def main():
    parser = argparse.ArgumentParser(description="Get verify batches and writeback verdicts.")
    parser.add_argument("--plan", required=True, help="Path to the audit_plan.json file.")
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--get-batch", action="store_true", help="Get a batch of candidates to verify.")
    group.add_argument("--writeback", help="Path to the json file containing verdicts to write back.")
    group.add_argument("--renew-lease", help="Candidate ID to renew lease (heartbeat).")
    parser.add_argument("--limit", type=int, default=10, help="Batch limit (only for --get-batch).")
    parser.add_argument("--lease-timeout", type=int, default=1800, help="Lease timeout in seconds (default: 1800).")
    args = parser.parse_args()

    plan_path = os.path.abspath(args.plan)
    if not os.path.exists(plan_path):
        print(json.dumps({"ok": False, "error": f"Plan file not found: {plan_path}"}))
        sys.exit(1)

    workspace_dir = os.path.dirname(plan_path)
    registry_path = os.path.join(workspace_dir, "candidate_registry.jsonl")
    queue_dir = os.path.join(workspace_dir, "queues")

    # Load plan
    try:
        plan = load_plan(plan_path)
    except Exception as e:
        print(json.dumps({"ok": False, "error": f"Failed to load plan: {str(e)}"}))
        sys.exit(1)

    tracks_map = {track.track_id: track for track in plan.audit_tracks}

    if args.get_batch:
        # Log stage start if not yet logged in event log
        log_path = os.path.join(workspace_dir, "event_log.jsonl")
        has_triage_start = False
        if os.path.exists(log_path):
            try:
                with open(log_path, "r", encoding="utf-8") as lf:
                    for line in lf:
                        if '"stage": "triage"' in line and '"event_type": "stage_start"' in line:
                            has_triage_start = True
                            break
            except:
                pass
        if not has_triage_start:
            from src_v2.core.event_log import log_event
            log_event(workspace_dir, "triage", "stage_start", {})

        # Load registry
        candidates = load_candidates(registry_path)
        
        # Check and handle expired leases first using configured lease timeout
        check_lease_expiry(candidates, registry_path, queue_dir, plan_path, args.lease_timeout)
        
        # Reload candidates after lease expiry updates
        candidates = load_candidates(registry_path)
        candidates_map = {c.candidate_id: c for c in candidates}

        # Read verify_now queue without dequeuing destructively
        verify_now = load_queue(queue_dir, "verify_now")
        
        # Find candidates in verify_now that are currently in queued_for_verify status
        cand_ids_to_process = []
        for cid in verify_now:
            if cid in candidates_map:
                cand = candidates_map[cid]
                if cand.status == "queued_for_verify":
                    cand_ids_to_process.append(cid)
                    if len(cand_ids_to_process) >= args.limit:
                        break
                        
        batch = []
        failed_ids = []
        for cid in cand_ids_to_process:
            cand = candidates_map[cid]
            # Build context package
            try:
                pkg_path = build_candidate_package(plan.repo_path, workspace_dir, cand, tracks_map)
                
                # Transition to verifying
                transition(cand, "verifying")
                
                # Find mapped CWE for packaging details
                cwe_id = "Unknown"
                for track_id in cand.source_tracks:
                    track = tracks_map.get(track_id)
                    if track and track.mapped_cwes:
                        cwe_id = track.mapped_cwes[0]
                        break
                        
                batch.append({
                    "candidate_id": cand.candidate_id,
                    "pkg_path": pkg_path,
                    "cwe_id": cwe_id,
                    "file": cand.file,
                    "symbol": cand.symbol
                })
            except Exception as e:
                # Mark as error if packaging fails
                cand.status = "error"
                failed_ids.append(cid)
                
        # Save updated candidates status
        save_candidates(registry_path, candidates)
        
        # Immediate removal of failed packaging candidates from verify_now to prevent residue
        if failed_ids:
            remaining_verify_now = [cid for cid in verify_now if cid not in failed_ids]
            save_queue(queue_dir, "verify_now", remaining_verify_now)
            
        update_plan_summary(plan_path, candidates)

        print(json.dumps({"ok": True, "batch": batch}))

    elif args.writeback:
        # Load verdicts from file
        verdicts_path = os.path.abspath(args.writeback)
        if not os.path.exists(verdicts_path):
            print(json.dumps({"ok": False, "error": f"Verdicts file not found: {verdicts_path}"}))
            sys.exit(1)

        try:
            with open(verdicts_path, "r", encoding="utf-8") as f:
                verdicts = json.load(f)
        except Exception as e:
            print(json.dumps({"ok": False, "error": f"Failed to load verdicts: {str(e)}"}))
            sys.exit(1)

        # Writeback verdicts
        try:
            consumed, verified, needs_review, false_positive, error = writeback_verdicts(plan_path, verdicts)
        except Exception as e:
            print(json.dumps({"ok": False, "error": f"Failed to writeback verdicts: {str(e)}"}))
            sys.exit(1)

        # Manage verify_now queue and deferred queue
        verify_now = load_queue(queue_dir, "verify_now")
        
        candidates = load_candidates(registry_path)
        candidates_map = {c.candidate_id: c for c in candidates}
        
        remaining_verify_now = []
        
        for cid in verify_now:
            if cid in candidates_map:
                cand = candidates_map[cid]
                # If it has been processed and is in a final status, remove it from queue
                if cand.status in {"verified", "needs_review", "false_positive", "error"}:
                    continue
                # If it is stuck in "verifying" status but was not written back in this batch,
                # we leave it in "verifying" status so other concurrent/long workers can complete it!
                else:
                    remaining_verify_now.append(cid)
            else:
                continue
                
        # Save updated verify_now queue
        save_queue(queue_dir, "verify_now", remaining_verify_now)
        
        # Run lease expiry check to cleanly handle actual timeouts
        deferred_count = check_lease_expiry(candidates, registry_path, queue_dir, plan_path, args.lease_timeout)

        # Log stage end if verify_now queue is completely empty
        final_verify_now = load_queue(queue_dir, "verify_now")
        if not final_verify_now:
            from src_v2.core.event_log import log_event
            log_event(workspace_dir, "triage", "stage_end", {})

        # Return status
        print(json.dumps({
            "ok": True,
            "consumed": consumed,
            "verified": verified,
            "needs_review": needs_review,
            "false_positive": false_positive,
            "deferred": deferred_count
        }))

    elif args.renew_lease:
        # Load registry
        candidates = load_candidates(registry_path)
        candidates_map = {c.candidate_id: c for c in candidates}
        
        cid = args.renew_lease
        if cid not in candidates_map:
            print(json.dumps({"ok": False, "error": f"Candidate not found: {cid}"}))
            sys.exit(1)
            
        cand = candidates_map[cid]
        if cand.status != "verifying":
            print(json.dumps({"ok": False, "error": f"Candidate {cid} is not in verifying status (current: {cand.status})"}))
            sys.exit(1)
            
        # Update timestamp to renew lease (heartbeat)
        cand.updated_at = datetime.now(timezone.utc).isoformat() + "Z"
        save_candidates(registry_path, candidates)
        
        print(json.dumps({"ok": True, "candidate_id": cid, "updated_at": cand.updated_at}))

if __name__ == "__main__":
    main()
