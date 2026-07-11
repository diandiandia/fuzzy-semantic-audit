#!/usr/bin/env python3
import os
import sys
import json
import argparse
import tempfile
import shutil
import subprocess
import yaml

def parse_args():
    parser = argparse.ArgumentParser(description="Evaluate baseline recall and compression metrics")
    parser.add_argument("--case-file", help="Path to case YAML file")
    parser.add_argument("--repo-dir", help="Path to the repository directory to audit")
    return parser.parse_args()

def main():
    args = parse_args()
    
    # 1. Determine case file
    case_file = args.case_file
    if not case_file:
        # Default to synthetic fixture
        base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        case_file = os.path.join(base_dir, "baselines", "cases", "synthetic_fixture.yaml")
        
    if not os.path.exists(case_file):
        print(json.dumps({
            "ok": False,
            "message": f"Case file not found: {case_file}"
        }))
        sys.exit(1)
        
    with open(case_file, 'r', encoding='utf-8') as f:
        case_data = yaml.safe_load(f)
        
    repo_id = case_data.get("repo_id")
    
    temp_dir = None
    repo_dir = args.repo_dir
    
    # 2. Create synthetic fixture if repo_dir not specified and repo_id is synthetic_fixture
    if not repo_dir and repo_id == "synthetic_fixture":
        temp_dir = tempfile.mkdtemp()
        repo_dir = os.path.join(temp_dir, "synthetic_project")
        os.makedirs(repo_dir, exist_ok=True)
        
        # Write views.py
        views_code = """
def delete_user(request):
    # Sensitive operation containing authz pattern
    return True
"""
        permissions_code = """
def require_admin(user):
    # Critical security guard authz check
    pass
"""
        with open(os.path.join(repo_dir, "views.py"), "w") as f:
            f.write(views_code)
        with open(os.path.join(repo_dir, "permissions.py"), "w") as f:
            f.write(permissions_code)
        # Create package.json to trigger framework detectors
        with open(os.path.join(repo_dir, "package.json"), "w") as f:
            f.write('{"dependencies": {"express": "4.18.2"}}')
            
    if not repo_dir or not os.path.exists(repo_dir):
        print(json.dumps({
            "ok": False,
            "message": f"Repository directory not found or not specified for repo_id '{repo_id}'"
        }))
        if temp_dir:
            shutil.rmtree(temp_dir)
        sys.exit(1)
        
    try:
        # 3. Run V3 orchestrated pipeline
        project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        orchestrate_script = os.path.join(project_root, "src_v3", "cli", "orchestrate_audit.py")
        
        env = os.environ.copy()
        env["PYTHONPATH"] = project_root
        
        proc = subprocess.run([
            sys.executable, orchestrate_script,
            "--project", repo_dir
        ], capture_output=True, text=True, env=env)
        
        if proc.returncode != 0:
            print(json.dumps({
                "ok": False,
                "message": f"Pipeline execution failed: {proc.stderr}"
            }))
            sys.exit(1)
            
        # 4. Load candidates
        workspace_dir = os.path.join(repo_dir, ".audit_workspace_v3")
        registry_path = os.path.join(workspace_dir, "candidates", "candidate_registry.jsonl")
        pruned_path = os.path.join(workspace_dir, "candidates", "pruned_registry.jsonl")
        
        candidates = []
        if os.path.exists(registry_path):
            with open(registry_path, "r", encoding="utf-8") as f:
                candidates = [json.loads(line.strip()) for line in f if line.strip()]
                
        pruned_candidates = []
        if os.path.exists(pruned_path):
            with open(pruned_path, "r", encoding="utf-8") as f:
                pruned_candidates = [json.loads(line.strip()) for line in f if line.strip()]
                
        # 5. Evaluate Expected Targets
        expected = case_data.get("expected", {})
        must_retrieve = expected.get("must_retrieve", [])
        
        # Sort candidates by score descending
        candidates.sort(key=lambda x: x.get("priority_score", 0.0), reverse=True)
        top_20_cands = candidates[:20]
        
        retrieved_must = 0
        failures = []
        
        for target in must_retrieve:
            target_path = target.get("path")
            target_symbol = target.get("symbol")
            
            # Check if this target is retrieved anywhere in candidate registry
            found = False
            for cand in candidates:
                if cand.get("file") == target_path and cand.get("symbol") == target_symbol:
                    found = True
                    break
            
            if not found:
                failures.append(f"Missing expected symbol: '{target_symbol}' in file '{target_path}'")
            else:
                # Check if it was in the top 20
                in_top_20 = False
                for cand in top_20_cands:
                    if cand.get("file") == target_path and cand.get("symbol") == target_symbol:
                        in_top_20 = True
                        break
                if in_top_20:
                    retrieved_must += 1
                else:
                    failures.append(f"Expected symbol '{target_symbol}' was retrieved but not in top-k 20.")
                    
        total_must = len(must_retrieve)
        recall_at_20 = retrieved_must / total_must if total_must > 0 else 1.0
        
        passed = 1 if len(failures) == 0 else 0
        failed = 1 - passed
        
        # Output evaluation JSON
        output = {
            "baseline_id": repo_id,
            "cases": 1,
            "passed": passed,
            "failed": failed,
            "recall_at_20": recall_at_20,
            "avg_candidates_before_prune": len(candidates),
            "avg_candidates_after_prune": len(pruned_candidates),
            "failures": failures
        }
        
        print(json.dumps(output, indent=2, ensure_ascii=False))
        
    finally:
        if temp_dir:
            shutil.rmtree(temp_dir)

if __name__ == "__main__":
    main()
