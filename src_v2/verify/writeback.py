import os
import json
import tempfile
from typing import List, Dict, Tuple
from datetime import datetime
from src_v2.core.models import CandidateRecord, VerificationResult, PlanSummary
from src_v2.core.plan_io import load_plan, update_plan_summary
from src_v2.core.candidate_registry import load_candidates, save_candidates
from src_v2.core.state_machine import transition

def writeback_verdicts(
    plan_path: str,
    verdicts: List[Dict]
) -> Tuple[int, int, int, int, int]:
    """
    Write verification verdicts back to registry and verification results log.
    Returns (consumed, verified_count, needs_review_count, false_positive_count, error_count)
    """
    workspace_dir = os.path.dirname(plan_path)
    registry_path = os.path.join(workspace_dir, "candidate_registry.jsonl")
    results_path = os.path.join(workspace_dir, "verification_results.jsonl")

    # Load candidates
    candidates = load_candidates(registry_path)
    candidates_map = {c.candidate_id: c for c in candidates}

    # Count updates
    consumed = 0
    verified_count = 0
    needs_review_count = 0
    false_positive_count = 0
    error_count = 0

    new_results: List[VerificationResult] = []

    for v in verdicts:
        cid = v["candidate_id"]
        referee_votes = v.get("referee_votes", [])
        evidence = v.get("evidence", [])

        # Enforce verdict_policy decisions if referee votes are present
        if referee_votes:
            from src_v2.verify.verdict_policy import decide
            verdict, reason = decide(referee_votes)
        else:
            requested_verdict = v.get("verdict", "needs_review")
            if requested_verdict == "error":
                verdict = "error"
                reason = v.get("reason", "Referee execution error reported.")
            else:
                verdict = "needs_review"
                reason = "Blocked: Referee votes omitted. Direct verdict injection is prohibited."

        if cid not in candidates_map:
            # Candidate not found in registry, skip or log
            continue

        cand = candidates_map[cid]
        
        # Transition status
        # In state machine, we transition through verifying -> verdict
        try:
            # First, set to verifying temporarily if it was queued
            if cand.status == "queued_for_verify":
                transition(cand, "verifying")
            # Then transition to final verdict
            transition(cand, verdict)
        except Exception as e:
            # If transition fails, record error status
            cand.status = "error"
            verdict = "error"

        # Update stats
        consumed += 1
        if verdict == "verified":
            verified_count += 1
        elif verdict == "needs_review":
            needs_review_count += 1
        elif verdict == "false_positive":
            false_positive_count += 1
        elif verdict == "error":
            error_count += 1

        # Create verification result
        vr = VerificationResult(
            candidate_id=cid,
            verdict=verdict,
            reason=reason,
            referee_votes=referee_votes,
            evidence=evidence,
            written_at=datetime.utcnow().isoformat() + "Z"
        )
        new_results.append(vr)

    # Save candidates registry
    save_candidates(registry_path, candidates)

    # Append verification results atomically
    if new_results:
        existing_results = []
        if os.path.exists(results_path):
            with open(results_path, "r", encoding="utf-8") as f:
                for line in f:
                    if line.strip():
                        try:
                            existing_results.append(VerificationResult.model_validate_json(line))
                        except:
                            pass
        
        # Merge, replacing old results for same candidate
        results_map = {r.candidate_id: r for r in existing_results}
        for r in new_results:
            results_map[r.candidate_id] = r
            
        # Atomic save
        fd, temp_path = tempfile.mkstemp(dir=workspace_dir)
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                for r in results_map.values():
                    f.write(r.model_dump_json() + "\n")
            os.replace(temp_path, results_path)
        except Exception as e:
            if os.path.exists(temp_path):
                os.remove(temp_path)
            raise e

    # Update manual_review queue dynamically based on needs_review candidates
    from src_v2.core.queue_store import load_queue, save_queue
    queue_dir = os.path.join(workspace_dir, "queues")
    manual_review_queue = load_queue(queue_dir, "manual_review")
    manual_review_set = set(manual_review_queue)
    for v in verdicts:
        cid = v["candidate_id"]
        if cid in candidates_map:
            cand = candidates_map[cid]
            if cand.status == "needs_review":
                manual_review_set.add(cid)
            else:
                if cid in manual_review_set:
                    manual_review_set.remove(cid)
    save_queue(queue_dir, "manual_review", list(manual_review_set))

    # Update plan summary
    update_plan_summary(plan_path, candidates)

    return consumed, verified_count, needs_review_count, false_positive_count, error_count
