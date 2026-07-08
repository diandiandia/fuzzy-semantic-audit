import argparse
import json
import os
import sys
import time

from src_v3.core.event_log import log_event
from src_v3.core.metrics import record_metric
from src_v3.report.report_compiler import write_all_reports

def parse_args():
    parser = argparse.ArgumentParser(description="Compile all 4 markdown reports")
    parser.add_argument("--workspace", required=True, help="Path to the V3 workspace directory")
    return parser.parse_args()

def main():
    args = parse_args()
    workspace_dir = os.path.abspath(args.workspace)
    
    plan_path = os.path.join(workspace_dir, "audit_plan.json")
    if not os.path.exists(plan_path):
        print(json.dumps({
            "ok": False,
            "stage": "compile_reports",
            "message": f"Audit plan not found: {plan_path}"
        }, ensure_ascii=False))
        sys.exit(1)
        
    start_time = time.time()
    
    try:
        write_all_reports(workspace_dir)
        
        duration = time.time() - start_time
        
        # Log event and metrics
        log_event(workspace_dir, "compile_reports", "info", "Markdown reports compiled successfully", {
            "duration_seconds": duration
        })
        record_metric(workspace_dir, "compile_reports", "wall_clock_seconds", duration)
        
        # Output JSON contract
        print(json.dumps({
            "ok": True,
            "stage": "compile_reports",
            "workspace_dir": workspace_dir,
            "summary": {
                "coverage_report": "coverage_report.md",
                "audit_report": "audit_report.md",
                "review_queue": "review_queue.md",
                "metrics_report": "metrics_report.md",
                "wall_clock_seconds": duration
            }
        }, ensure_ascii=False))
        
    except Exception as e:
        import traceback
        print(json.dumps({
            "ok": False,
            "stage": "compile_reports",
            "message": f"Error compiling reports: {str(e)}",
            "traceback": traceback.format_exc()
        }, ensure_ascii=False))
        sys.exit(1)

if __name__ == "__main__":
    main()
