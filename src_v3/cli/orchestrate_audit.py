import argparse
import json
import os
import sys
import subprocess


def run_stage(stage_name: str, args: list) -> dict:
    cli_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), f"{stage_name}.py")
    cmd = [sys.executable, cli_path] + args
    
    # Set PYTHONPATH
    env = os.environ.copy()
    env["PYTHONPATH"] = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    
    try:
        proc = subprocess.run(cmd, capture_output=True, text=True, env=env)
        if proc.returncode != 0:
            return {
                "ok": False,
                "stage": stage_name,
                "message": f"CLI exited with code {proc.returncode}. Stderr: {proc.stderr.strip()}"
            }
        try:
            return json.loads(proc.stdout.strip())
        except json.JSONDecodeError:
            return {
                "ok": False,
                "stage": stage_name,
                "message": f"CLI output was not valid JSON. Stdout: {proc.stdout.strip()}"
            }
    except Exception as e:
        return {
            "ok": False,
            "stage": stage_name,
            "message": f"Failed to run stage process: {str(e)}"
        }

def main():
    parser = argparse.ArgumentParser(description="Python E2E orchestrator for Fuzzy Semantic Audit V3")
    parser.add_argument("--project", required=True, help="Path to the repository to audit")
    parser.add_argument("--workspace", help="Path to the workspace directory")
    args = parser.parse_args()
    
    project_path = os.path.abspath(args.project)
    
    print(json.dumps({
        "ok": True,
        "stage": "orchestrate_audit_start",
        "message": "Starting V3 E2E Orchestrated Audit (Python native)"
    }))
    
    # 1. Init Plan
    init_args = ["--project", project_path]
    if args.workspace:
        init_args += ["--workspace", os.path.abspath(args.workspace)]
    
    res = run_stage("init_plan", init_args)
    if not res.get("ok"):
        print(json.dumps(res, ensure_ascii=False))
        sys.exit(1)
        
    workspace_dir = res["workspace_dir"]
    print(json.dumps(res, ensure_ascii=False))
    
    # 2. Sequential Execution of other core stages
    core_stages = [
        "build_inventory",
        "build_ir",
        "build_index",
        "recall_candidates",
        "prune_candidates",
        "build_evidence",
        "compile_reports"
    ]
    
    for stage in core_stages:
        res = run_stage(stage, ["--workspace", workspace_dir])
        if not res.get("ok"):
            print(json.dumps(res, ensure_ascii=False))
            sys.exit(1)
        print(json.dumps(res, ensure_ascii=False))
        
    print(json.dumps({
        "ok": True,
        "stage": "orchestrate_audit_complete",
        "workspace_dir": workspace_dir,
        "summary": {
            "message": "All pipeline stages completed successfully"
        }
    }, ensure_ascii=False))

if __name__ == "__main__":
    main()
