import os
import sys
import argparse
import json
from src_v2.core.plan_io import load_plan
from src_v2.report.coverage_report import generate_coverage_report
from src_v2.report.audit_report import generate_audit_report
from src_v2.report.review_queue import generate_review_queue_report

def main():
    parser = argparse.ArgumentParser(description="Compile audit, coverage, and review reports.")
    parser.add_argument("--plan", required=True, help="Path to the audit_plan.json file.")
    args = parser.parse_args()

    plan_path = os.path.abspath(args.plan)
    if not os.path.exists(plan_path):
        print(json.dumps({"ok": False, "error": f"Plan file not found: {plan_path}"}))
        sys.exit(1)

    workspace_dir = os.path.dirname(plan_path)
    registry_path = os.path.join(workspace_dir, "candidate_registry.jsonl")
    results_path = os.path.join(workspace_dir, "verification_results.jsonl")
    queue_dir = os.path.join(workspace_dir, "queues")
    reports_dir = os.path.join(workspace_dir, "reports")
    
    os.makedirs(reports_dir, exist_ok=True)

    from src_v2.core.event_log import log_event
    log_event(workspace_dir, "report", "stage_start", {})

    audit_report_path = os.path.join(reports_dir, "audit_report.md")
    coverage_report_path = os.path.join(reports_dir, "coverage_report.md")
    review_queue_path = os.path.join(reports_dir, "review_queue.md")

    # Generate coverage report
    try:
        generate_coverage_report(plan_path, registry_path, queue_dir, coverage_report_path)
    except Exception as e:
        print(json.dumps({"ok": False, "error": f"Failed to generate coverage report: {str(e)}"}))
        sys.exit(1)

    # Generate audit report
    try:
        generate_audit_report(plan_path, registry_path, results_path, audit_report_path)
    except Exception as e:
        print(json.dumps({"ok": False, "error": f"Failed to generate audit report: {str(e)}"}))
        sys.exit(1)

    # Generate review queue report
    try:
        generate_review_queue_report(plan_path, registry_path, results_path, review_queue_path)
    except Exception as e:
        print(json.dumps({"ok": False, "error": f"Failed to generate review queue report: {str(e)}"}))
        sys.exit(1)

    log_event(workspace_dir, "report", "stage_end", {})

    # Output JSON contract
    result = {
        "ok": True,
        "audit_report": audit_report_path,
        "coverage_report": coverage_report_path,
        "review_queue": review_queue_path
    }
    print(json.dumps(result))

if __name__ == "__main__":
    main()
