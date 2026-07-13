import argparse
import json
import os
import sys
import time
import datetime

from src_v3.core.models import AuditPlan, VerificationResult, CandidateRecord
from src_v3.core.plan_io import load_plan, save_plan
from src_v3.core.event_log import log_event
from src_v3.core.metrics import record_metric
from src_v3.core.enums import CandidateStatus
from src_v3.storage.candidate_store import CandidateStore
from src_v3.storage.evidence_store import EvidenceStore
from src_v3.verify.verdict_policy import evaluate_verdict

def parse_args():
    parser = argparse.ArgumentParser(description="Coordinate batch verification and verdict writeback")
    parser.add_argument("--workspace", required=True, help="Path to the V3 workspace directory")
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--get-batch", action="store_true", help="Fetch evidence-ready candidates into verify_now.json")
    group.add_argument("--writeback", action="store_true", help="Evaluate votes and write back final verdicts")
    return parser.parse_args()

def main():
    args = parse_args()
    workspace_dir = os.path.abspath(args.workspace)
    
    plan_path = os.path.join(workspace_dir, "audit_plan.json")
    if not os.path.exists(plan_path):
        print(json.dumps({
            "ok": False,
            "stage": "verify_batch",
            "message": f"Audit plan not found: {plan_path}"
        }, ensure_ascii=False))
        sys.exit(1)
        
    start_time = time.time()
    
    try:
        plan = load_plan(plan_path)
        from src_v3.storage.queue_store import QueueStore
        candidate_store = CandidateStore(workspace_dir)
        evidence_store = EvidenceStore(workspace_dir)
        queue_store = QueueStore(workspace_dir)
        
        results_path = os.path.join(workspace_dir, "evidence", "verification_results.jsonl")
        
        if args.get_batch:
            # 1. Fetch evidence_ready candidates
            ready_cands = candidate_store.get_candidates_by_status(CandidateStatus.EVIDENCE_READY.value, pruned=True)
            
            # Sort and prioritize candidates using the SeverityFilter module
            from src_v3.verify.severity_filter import SeverityFilter
            ready_cands = SeverityFilter.filter_and_sort(ready_cands, min_severity="low")
            
            batch_data = []
            valid_ready_cands = []
            
            # Load existing manual review queue to append rejected candidates
            manual_review_list = queue_store.load_manual_review()
            
            for cand in ready_cands:
                # Fetch evidence bundle
                bundle = evidence_store.get_evidence(cand.candidate_id)
                has_context = (
                    bundle
                    and (
                        len(bundle.upstream_entrypoints) > 0 
                        or len(bundle.guard_snippets) > 0 
                        or len(bundle.resource_snippets) > 0 
                        or len(bundle.state_transition_snippets) > 0
                    )
                )
                from src_v3.core.state_machine import transition
                if not bundle or not bundle.symbol_body.strip() or not has_context:
                    # Double-lock rejection
                    log_event(workspace_dir, "verify_batch", "warning", f"Candidate '{cand.symbol}' rejected from verify batch due to insufficient contextual evidence. Score: {bundle.evidence_completeness_score if bundle else 'N/A'}")
                    transition(cand, CandidateStatus.NEEDS_REVIEW.value, workspace_dir=workspace_dir)
                    candidate_store.upsert_candidates([cand], pruned=True)
                    # Add candidate to manual review queue
                    manual_review_list.append(cand.to_dict())
                    continue
                    
                transition(cand, CandidateStatus.QUEUED_FOR_VERIFY.value, workspace_dir=workspace_dir)
                valid_ready_cands.append(cand)
                batch_data.append({
                    "candidate": cand.to_dict(),
                    "votes": {
                        "reachability": "MAYBE",
                        "guarded": "MAYBE",
                        "exploitability": "MAYBE"
                    }
                })
                
            # Update candidate store with queued status
            candidate_store.upsert_candidates(valid_ready_cands, pruned=True)
            
            # Write to verify_now.json queue
            queue_store.save_verify_now(batch_data)
            
            # Save updated manual review queue
            def deduplicate_queue(q_list):
                seen = set()
                deduped = []
                for item in q_list:
                    cid = item.get("candidate_id")
                    if cid not in seen:
                        seen.add(cid)
                        deduped.append(item)
                return deduped
            queue_store.save_manual_review(deduplicate_queue(manual_review_list))
                
            duration = time.time() - start_time
            
            # Log event and metrics
            log_event(workspace_dir, "verify_batch", "info", f"Fetched {len(batch_data)} candidates into verify_now.json queue", {
                "fetched_count": len(batch_data),
                "duration_seconds": duration
            })
            
            print(json.dumps({
                "ok": True,
                "stage": "verify_batch_get_batch",
                "workspace_dir": workspace_dir,
                "summary": {
                    "fetched_count": len(batch_data),
                    "wall_clock_seconds": duration
                }
            }, ensure_ascii=False))
            
        elif args.writeback:
            # 2. Read verify_now.json and evaluate
            config = plan.summary.get("config", {})
            batch_data = queue_store.load_verify_now()
            if not batch_data:
                # If queue is empty, print empty writeback summary gracefully
                pass
                
            verified_count = 0
            fp_count = 0
            needs_review_count = 0
            deferred_count = 0
            error_count = 0
            
            updated_candidates = []
            new_results = []
            
            # Load existing queues for writeback updates
            manual_review_list = queue_store.load_manual_review()
            deferred_list = queue_store.load_deferred()
            
            from concurrent.futures import ThreadPoolExecutor
            from src_v3.verify.llm_triage import run_three_lens_referee

            # Pre-fetch LLM votes concurrently for all candidates with default votes
            candidates_to_query = []
            for item in batch_data:
                cand_dict = item["candidate"]
                cand = CandidateRecord.from_dict(cand_dict)
                existing_cand = candidate_store.get_candidate_by_id(cand.candidate_id, pruned=True)
                if existing_cand and existing_cand.status in ["verified", "false_positive", "needs_review", "deferred", "error"]:
                    continue
                votes = item.get("votes", {})
                if votes.get("reachability") == "MAYBE" and votes.get("guarded") == "MAYBE":
                    candidates_to_query.append((cand, item))

            def run_triage_worker(cand_item):
                cand, item = cand_item
                try:
                    bundle = evidence_store.get_evidence(cand.candidate_id)
                    llm_votes, warnings = run_three_lens_referee(cand, bundle, config)
                    return cand.candidate_id, llm_votes, warnings
                except Exception as e:
                    return cand.candidate_id, {"reachability": "ERROR", "guarded": "ERROR", "exploitability": "ERROR", "error": True}, [str(e)]

            prefetched_votes = {}
            if candidates_to_query:
                max_workers = min(10, len(candidates_to_query))
                with ThreadPoolExecutor(max_workers=max_workers) as executor:
                    for cid, llm_votes, warnings in executor.map(run_triage_worker, candidates_to_query):
                        prefetched_votes[cid] = (llm_votes, warnings)

            for item in batch_data:
                cand_dict = item["candidate"]
                cand = CandidateRecord.from_dict(cand_dict)
                
                # Interruption recovery: check if candidate is already processed
                existing_cand = candidate_store.get_candidate_by_id(cand.candidate_id, pruned=True)
                if existing_cand and existing_cand.status in ["verified", "false_positive", "needs_review", "deferred", "error"]:
                    verdict = existing_cand.status
                    reason = "Already verified (restored from previous run)."
                    cand.status = verdict
                    
                    if verdict == "verified":
                        verified_count += 1
                    elif verdict == "false_positive":
                        fp_count += 1
                    elif verdict == "deferred":
                        deferred_count += 1
                    elif verdict == "error":
                        error_count += 1
                    else:
                        needs_review_count += 1
                        
                    results_path = os.path.join(workspace_dir, "evidence", "verification_results.jsonl")
                    already_logged = False
                    if os.path.exists(results_path):
                        with open(results_path, 'r', encoding='utf-8') as f:
                            for line in f:
                                if line.strip():
                                    res_dict = json.loads(line.strip())
                                    if res_dict.get("candidate_id") == cand.candidate_id:
                                        already_logged = True
                                        break
                    
                    if not already_logged:
                        res = VerificationResult(
                            candidate_id=cand.candidate_id,
                            verdict=verdict,
                            reason=reason,
                            confidence=cand.priority_score / 100.0,
                            referee_votes=[item.get("votes", {})],
                            evidence=[],
                            written_at=datetime.datetime.now(datetime.timezone.utc).isoformat()
                        )
                        new_results.append(res)
                        
                    updated_candidates.append(cand)
                    continue

                votes = item.get("votes", {})
                
                # Check if votes are default/unfilled
                if votes.get("reachability") == "MAYBE" and votes.get("guarded") == "MAYBE":
                    if cand.candidate_id in prefetched_votes:
                        llm_votes, warnings = prefetched_votes[cand.candidate_id]
                        if warnings:
                            # Log warning about LLM degradation
                            log_event(workspace_dir, "verify_batch", "warning", f"LLM triage degraded for candidate {cand.candidate_id}: {', '.join(warnings)}")
                            if plan.run_manifest and "LLM Triage degraded: api keys missing or query failed" not in plan.run_manifest.degradation_reasons:
                                plan.run_manifest.degradation_reasons.append("LLM Triage degraded: api keys missing or query failed")
                                
                        # Use LLM votes
                        votes = llm_votes

                            
                from src_v3.core.state_machine import transition
                # Transition candidate from queued_for_verify to verifying
                transition(cand, CandidateStatus.VERIFYING.value, workspace_dir=workspace_dir)
                
                verdict, reason = evaluate_verdict(votes, cand.candidate_capability, plan.run_manifest.run_capability if plan.run_manifest else None)
                # Transition candidate from verifying to the final verdict status
                transition(cand, verdict, workspace_dir=workspace_dir)
                
                if verdict == "verified":
                    verified_count += 1
                elif verdict == "false_positive":
                    fp_count += 1
                elif verdict == "deferred":
                    deferred_count += 1
                    deferred_list.append(cand.to_dict())
                elif verdict == "error":
                    error_count += 1
                    manual_review_list.append(cand.to_dict())
                else:
                    needs_review_count += 1
                    manual_review_list.append(cand.to_dict())
                    
                updated_candidates.append(cand)
                
                # Build VerificationResult
                res = VerificationResult(
                    candidate_id=cand.candidate_id,
                    verdict=verdict,
                    reason=reason,
                    confidence=cand.priority_score / 100.0,
                    referee_votes=[votes],
                    evidence=[],
                    written_at=datetime.datetime.now(datetime.timezone.utc).isoformat()
                )
                new_results.append(res)
                
            # Overwrite registry, save results, and update queues via VerificationWriteback
            from src_v3.verify.writeback import VerificationWriteback
            writeback_helper = VerificationWriteback(workspace_dir)
            writeback_helper.perform_writeback(
                updated_candidates=updated_candidates,
                new_results=new_results,
                manual_review_list=manual_review_list,
                deferred_list=deferred_list
            )
                
            duration = time.time() - start_time
            
            # Log event and metrics
            log_event(workspace_dir, "verify_batch", "info", f"Writeback completed: verified={verified_count}, fp={fp_count}, review={needs_review_count}, deferred={deferred_count}, error={error_count}", {
                "verified": verified_count,
                "false_positive": fp_count,
                "needs_review": needs_review_count,
                "deferred": deferred_count,
                "error": error_count,
                "duration_seconds": duration
            })
            
            record_metric(workspace_dir, "verify_batch", "verified_count", verified_count)
            record_metric(workspace_dir, "verify_batch", "false_positive_count", fp_count)
            record_metric(workspace_dir, "verify_batch", "needs_review_count", needs_review_count)
            record_metric(workspace_dir, "verify_batch", "deferred_count", deferred_count)
            record_metric(workspace_dir, "verify_batch", "error_count", error_count)
            record_metric(workspace_dir, "verify_batch", "wall_clock_seconds", duration)
            
            # Save plan and manifest updates
            from src_v3.core.plan_io import save_plan, save_run_manifest
            save_plan(plan, plan_path)
            if plan.run_manifest:
                save_run_manifest(plan.run_manifest, os.path.join(workspace_dir, "run_manifest.json"))
                
            print(json.dumps({
                "ok": True,
                "stage": "verify_batch_writeback",
                "workspace_dir": workspace_dir,
                "summary": {
                    "verified": verified_count,
                    "false_positive": fp_count,
                    "needs_review": needs_review_count,
                    "deferred": deferred_count,
                    "error": error_count,
                    "wall_clock_seconds": duration
                }
            }, ensure_ascii=False))
            
    except Exception as e:
        import traceback
        print(json.dumps({
            "ok": False,
            "stage": "verify_batch",
            "message": f"Error running batch verification: {str(e)}",
            "traceback": traceback.format_exc()
        }, ensure_ascii=False))
        sys.exit(1)

if __name__ == "__main__":
    main()
