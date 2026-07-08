import os
import json
from src_v3.core.plan_io import load_plan
from src_v3.core.metrics import load_metrics
from src_v3.core.models import VerificationResult
from src_v3.storage.candidate_store import CandidateStore

# Import functions from decomposed module files
from src_v3.report.coverage_report import compile_coverage_report
from src_v3.report.review_queue import compile_audit_report, compile_review_queue_report
from src_v3.report.metrics_report import compile_metrics_report

def write_all_reports(workspace_dir: str) -> None:
    """
    Compiles all four reports and saves them to reports/ directory.
    """
    plan = load_plan(os.path.join(workspace_dir, "audit_plan.json"))
    candidate_store = CandidateStore(workspace_dir)
    
    # Load all verification results
    results_map = {}
    results_path = os.path.join(workspace_dir, "evidence", "verification_results.jsonl")
    if os.path.exists(results_path):
        with open(results_path, 'r', encoding='utf-8') as f:
            for line in f:
                if line.strip():
                    res = VerificationResult.from_dict(json.loads(line.strip()))
                    results_map[res.candidate_id] = res
                    
    # Load candidates
    pruned = candidate_store.get_candidates(pruned=True)
    
    verified = [c for c in pruned if c.status == "verified"]
    review = [c for c in pruned if c.status in ["needs_review", "deferred", "error"]]
    
    reports_dir = os.path.join(workspace_dir, "reports")
    os.makedirs(reports_dir, exist_ok=True)
    
    # Coverage report
    coverage_md = compile_coverage_report(workspace_dir, plan)
    with open(os.path.join(reports_dir, "coverage_report.md"), 'w', encoding='utf-8') as f:
        f.write(coverage_md)
        
    # Audit report
    audit_md = compile_audit_report(workspace_dir, verified, results_map)
    with open(os.path.join(reports_dir, "audit_report.md"), 'w', encoding='utf-8') as f:
        f.write(audit_md)
        
    # Review queue report
    review_md = compile_review_queue_report(workspace_dir, review, results_map)
    with open(os.path.join(reports_dir, "review_queue.md"), 'w', encoding='utf-8') as f:
        f.write(review_md)
        
    # Metrics report
    metrics = load_metrics(workspace_dir)
    metrics_md = compile_metrics_report(workspace_dir, metrics)
    with open(os.path.join(reports_dir, "metrics_report.md"), 'w', encoding='utf-8') as f:
        f.write(metrics_md)
