import argparse
import json
import os
import sys
import time

from src_v3.core.models import AuditPlan
from src_v3.core.plan_io import load_plan, save_plan
from src_v3.core.event_log import log_event
from src_v3.core.metrics import record_metric
from src_v3.core.enums import CandidateStatus
from src_v3.core.state_machine import transition
from src_v3.storage.ir_store import IRStore
from src_v3.storage.candidate_store import CandidateStore
from src_v3.storage.evidence_store import EvidenceStore
from src_v3.evidence.assembler import assemble_evidence

def parse_args():
    parser = argparse.ArgumentParser(description="Assemble standardized evidence packages for pruned candidates")
    parser.add_argument("--workspace", required=True, help="Path to the V3 workspace directory")
    return parser.parse_args()

def main():
    args = parse_args()
    workspace_dir = os.path.abspath(args.workspace)
    
    plan_path = os.path.join(workspace_dir, "audit_plan.json")
    if not os.path.exists(plan_path):
        print(json.dumps({
            "ok": False,
            "stage": "build_evidence",
            "message": f"Audit plan not found: {plan_path}"
        }, ensure_ascii=False))
        sys.exit(1)
        
    start_time = time.time()
    
    try:
        plan = load_plan(plan_path)
        repo_path = plan.repo_path
        
        ir_store = IRStore(workspace_dir)
        candidate_store = CandidateStore(workspace_dir)
        evidence_store = EvidenceStore(workspace_dir)
        
        # Load pruned candidates
        pruned = candidate_store.get_candidates(pruned=True)
        if not pruned:
            # Output empty JSON contract
            print(json.dumps({
                "ok": True,
                "stage": "build_evidence",
                "workspace_dir": workspace_dir,
                "summary": {
                    "evidence_built_count": 0,
                    "mean_evidence_score": 0.0,
                    "wall_clock_seconds": time.time() - start_time
                }
            }, ensure_ascii=False))
            sys.exit(0)
            
        total_score = 0
        built_count = 0
        
        from src_v3.evidence.package_builder import PackageBuilder
        package_builder = PackageBuilder(workspace_dir)
        
        for cand in pruned:
            # Assemble evidence package
            bundle = assemble_evidence(workspace_dir, repo_path, cand, ir_store)
            rel_path = package_builder.save_package(cand.candidate_id, bundle)
            
            # Transition candidate status based on strict structural and contextual evidence
            has_context = (
                len(bundle.upstream_entrypoints) > 0 
                or len(bundle.guard_snippets) > 0 
                or len(bundle.resource_snippets) > 0 
                or len(bundle.state_transition_snippets) > 0
            )
            # Explicitly associate candidate with its evidence package relative path
            cand.evidence_refs = [rel_path]
            
            if bundle.symbol_body.strip() and has_context:
                transition(cand, CandidateStatus.EVIDENCE_READY.value, workspace_dir=workspace_dir)
                built_count += 1
            else:
                # Evidence is insufficient (bare candidate); route to needs_review/deferred
                transition(cand, CandidateStatus.NEEDS_REVIEW.value, workspace_dir=workspace_dir)
            
            total_score += bundle.evidence_completeness_score
            
        # Update pruned candidates with new status
        candidate_store.save_candidates(pruned, pruned=True, overwrite=True)
        
        mean_score = total_score / max(1, len(pruned))
        
        save_plan(plan, plan_path)
        
        duration = time.time() - start_time
        
        # Log event and metrics
        log_event(workspace_dir, "build_evidence", "info", f"Assembled {built_count} evidence packages. Mean completeness: {mean_score:.1f}", {
            "evidence_built_count": built_count,
            "mean_evidence_score": mean_score,
            "duration_seconds": duration
        })
        
        record_metric(workspace_dir, "build_evidence", "evidence_built_count", built_count)
        record_metric(workspace_dir, "build_evidence", "mean_evidence_score", mean_score)
        record_metric(workspace_dir, "build_evidence", "wall_clock_seconds", duration)
        
        # Output JSON contract
        print(json.dumps({
            "ok": True,
            "stage": "build_evidence",
            "workspace_dir": workspace_dir,
            "summary": {
                "evidence_built_count": built_count,
                "mean_evidence_score": mean_score,
                "wall_clock_seconds": duration
            }
        }, ensure_ascii=False))
        
    except Exception as e:
        import traceback
        print(json.dumps({
            "ok": False,
            "stage": "build_evidence",
            "message": f"Error building evidence: {str(e)}",
            "traceback": traceback.format_exc()
        }, ensure_ascii=False))
        sys.exit(1)

if __name__ == "__main__":
    main()
