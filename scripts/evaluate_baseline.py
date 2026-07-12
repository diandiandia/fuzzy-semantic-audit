#!/usr/bin/env python3
import argparse
import glob
import json
import os
import shutil
import subprocess
import sys
import tempfile
import hashlib
from typing import Any, Dict, List, Optional, Tuple

import yaml


PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DEFAULT_CASE = os.path.join(PROJECT_ROOT, "baselines", "cases", "synthetic_fixture.yaml")
DEFAULT_CASES_DIR = os.path.join(PROJECT_ROOT, "baselines", "cases")
DEFAULT_REPOS_FILE = os.path.join(PROJECT_ROOT, "baselines", "repos.yaml")


def parse_args():
    parser = argparse.ArgumentParser(description="Evaluate V3 baseline recall and compression metrics")
    parser.add_argument("--case-file", help="Path to a case YAML file")
    parser.add_argument("--repo-dir", help="Path to the repository directory for a single case")
    parser.add_argument("--all", action="store_true", help="Evaluate all baseline cases under --cases-dir")
    parser.add_argument("--cases-dir", default=DEFAULT_CASES_DIR, help="Directory containing baseline case YAML files")
    parser.add_argument("--repos-file", default=DEFAULT_REPOS_FILE, help="Repository registry YAML for real baselines")
    parser.add_argument("--include-disabled", action="store_true", help="Include disabled repos from repos.yaml")
    parser.add_argument("--fail-on-skipped", action="store_true", help="Exit non-zero if any enabled real baseline is skipped")
    return parser.parse_args()


def load_yaml(path: str) -> Dict[str, Any]:
    with open(path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f) or {}


def load_repo_registry(path: str) -> Dict[str, Dict[str, Any]]:
    if not os.path.exists(path):
        return {}
    data = load_yaml(path)
    return {repo.get("id"): repo for repo in data.get("repos", []) if repo.get("id")}


def discover_case_files(cases_dir: str) -> List[str]:
    return sorted(glob.glob(os.path.join(cases_dir, "*.yaml")))


def create_synthetic_fixture() -> Tuple[str, str]:
    temp_dir = tempfile.mkdtemp()
    repo_dir = os.path.join(temp_dir, "synthetic_project")
    os.makedirs(repo_dir, exist_ok=True)

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
    with open(os.path.join(repo_dir, "views.py"), "w", encoding="utf-8") as f:
        f.write(views_code)
    with open(os.path.join(repo_dir, "permissions.py"), "w", encoding="utf-8") as f:
        f.write(permissions_code)
    with open(os.path.join(repo_dir, "package.json"), "w", encoding="utf-8") as f:
        f.write('{"dependencies": {"express": "4.18.2"}}')
    return repo_dir, temp_dir


def resolve_repo_dir(repo_id: str, repo_config: Optional[Dict[str, Any]], explicit_repo_dir: str = "") -> Tuple[Optional[str], str]:
    if explicit_repo_dir:
        return os.path.abspath(explicit_repo_dir), "explicit --repo-dir"

    if repo_id == "synthetic_fixture":
        repo_dir, temp_dir = create_synthetic_fixture()
        return repo_dir, temp_dir

    repo_config = repo_config or {}
    env_var = repo_config.get("local_path_env") or f"FSA_BASELINE_{repo_id.upper()}_DIR"
    env_path = os.environ.get(env_var)
    if env_path:
        return os.path.abspath(env_path), f"env:{env_var}"

    local_path = repo_config.get("local_path")
    if local_path:
        return os.path.abspath(os.path.expanduser(local_path)), "repos.yaml:local_path"

    root = os.environ.get("FSA_BASELINE_REPO_ROOT")
    checkout = repo_config.get("checkout_dir") or repo_config.get("name", "").split("/")[-1]
    if root and checkout:
        return os.path.abspath(os.path.join(root, checkout)), "env:FSA_BASELINE_REPO_ROOT"

    return None, f"missing local repo path; set {env_var}, local_path, or FSA_BASELINE_REPO_ROOT"


def run_pipeline(repo_dir: str) -> Tuple[bool, str]:
    orchestrate_script = os.path.join(PROJECT_ROOT, "src_v3", "cli", "orchestrate_audit.py")
    env = os.environ.copy()
    env["PYTHONPATH"] = PROJECT_ROOT
    proc = subprocess.run(
        [sys.executable, orchestrate_script, "--project", repo_dir],
        capture_output=True,
        text=True,
        env=env,
    )
    if proc.returncode != 0:
        return False, f"Pipeline execution failed: {proc.stderr.strip()} {proc.stdout.strip()}".strip()
    return True, ""


def load_candidates(repo_dir: str) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
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

    return candidates, pruned_candidates


def load_json(path: str) -> Dict[str, Any]:
    if not os.path.exists(path):
        return {}
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def stable_report_digest(path: str) -> str:
    if not os.path.exists(path):
        return ""
    digest = hashlib.sha256()
    with open(path, "rb") as f:
        for line in f:
            if b"wall_clock_seconds" in line or b"Generated at" in line:
                continue
            digest.update(line)
    return digest.hexdigest()


def load_baseline_observability(repo_dir: str) -> Dict[str, Any]:
    workspace_dir = os.path.join(repo_dir, ".audit_workspace_v3")
    plan = load_json(os.path.join(workspace_dir, "audit_plan.json"))
    shards = plan.get("language_shards", [])
    degraded = [
        shard for shard in shards
        if shard.get("status") in ["indexed_fallback", "recalled_fallback", "failed"]
    ]
    coverage_report = os.path.join(workspace_dir, "reports", "coverage_report.md")
    coverage_text = ""
    if os.path.exists(coverage_report):
        with open(coverage_report, "r", encoding="utf-8") as f:
            coverage_text = f.read()
    return {
        "fallback_ratio": len(degraded) / max(1, len(shards)),
        "coverage_report_digest": stable_report_digest(coverage_report),
        "coverage_report_text": coverage_text,
    }


def evaluate_case(case_file: str, repo_dir: str) -> Dict[str, Any]:
    case_data = load_yaml(case_file)
    ok, message = run_pipeline(repo_dir)
    if not ok:
        return {
            "case_id": case_data.get("case_id"),
            "repo_id": case_data.get("repo_id"),
            "passed": 0,
            "failed": 1,
            "recall_at_20": 0.0,
            "avg_candidates_before_prune": 0,
            "avg_candidates_after_prune": 0,
            "failures": [message],
        }

    candidates, pruned_candidates = load_candidates(repo_dir)
    observability = load_baseline_observability(repo_dir)
    expected = case_data.get("expected", {})
    must_retrieve = expected.get("must_retrieve", [])
    top_k = int(expected.get("should_rank_top_k", 20))
    metrics = case_data.get("metrics", {})
    min_recall = float(metrics.get("min_recall_at_20", 0.0))
    max_after_prune = int(metrics.get("max_candidates_after_prune", 10**9))
    max_fallback_ratio = metrics.get("max_fallback_ratio")
    min_candidate_total = metrics.get("min_candidate_total")
    report_must_contain = metrics.get("report_must_contain", [])

    candidates.sort(key=lambda x: x.get("priority_score", 0.0), reverse=True)
    top_candidates = candidates[:top_k]

    retrieved_must = 0
    failures = []
    for target in must_retrieve:
        target_path = target.get("path")
        target_symbol = target.get("symbol")
        found = any(c.get("file") == target_path and c.get("symbol") == target_symbol for c in candidates)
        if not found:
            failures.append(f"Missing expected symbol: '{target_symbol}' in file '{target_path}'")
            continue
        in_top_k = any(c.get("file") == target_path and c.get("symbol") == target_symbol for c in top_candidates)
        if in_top_k:
            retrieved_must += 1
        else:
            failures.append(f"Expected symbol '{target_symbol}' was retrieved but not in top-k {top_k}.")

    recall_at_20 = retrieved_must / len(must_retrieve) if must_retrieve else 1.0
    if recall_at_20 < min_recall:
        failures.append(f"Recall {recall_at_20:.2f} below required minimum {min_recall:.2f}")
    if len(pruned_candidates) > max_after_prune:
        failures.append(f"Pruned candidates {len(pruned_candidates)} exceeds maximum {max_after_prune}")
    if max_fallback_ratio is not None and observability["fallback_ratio"] > float(max_fallback_ratio):
        failures.append(f"Fallback ratio {observability['fallback_ratio']:.2f} exceeds maximum {float(max_fallback_ratio):.2f}")
    if min_candidate_total is not None and len(candidates) < int(min_candidate_total):
        failures.append(f"Candidate total {len(candidates)} below minimum {int(min_candidate_total)}")
    for needle in report_must_contain:
        if needle not in observability["coverage_report_text"]:
            failures.append(f"Coverage report missing required content: {needle}")

    passed = 1 if not failures else 0
    return {
        "case_id": case_data.get("case_id"),
        "repo_id": case_data.get("repo_id"),
        "passed": passed,
        "failed": 1 - passed,
        "recall_at_20": recall_at_20,
        "candidate_total": len(candidates),
        "fallback_ratio": observability["fallback_ratio"],
        "coverage_report_digest": observability["coverage_report_digest"],
        "avg_candidates_before_prune": len(candidates),
        "avg_candidates_after_prune": len(pruned_candidates),
        "failures": failures,
    }


def summarize(results: List[Dict[str, Any]], skipped: List[Dict[str, Any]], baseline_id: str = "") -> Dict[str, Any]:
    cases = len(results)
    passed = sum(r.get("passed", 0) for r in results)
    failed = sum(r.get("failed", 0) for r in results)
    recall_vals = [r.get("recall_at_20", 0.0) for r in results]
    before_vals = [r.get("avg_candidates_before_prune", 0) for r in results]
    after_vals = [r.get("avg_candidates_after_prune", 0) for r in results]
    candidate_totals = [r.get("candidate_total", 0) for r in results]
    fallback_ratios = [r.get("fallback_ratio", 0.0) for r in results]
    failures = []
    for r in results:
        for failure in r.get("failures", []):
            failures.append(f"{r.get('case_id')}: {failure}")

    return {
        "baseline_id": baseline_id or ("all" if cases != 1 else results[0].get("repo_id")),
        "cases": cases,
        "passed": passed,
        "failed": failed,
        "skipped": len(skipped),
        "recall_at_20": sum(recall_vals) / len(recall_vals) if recall_vals else 0.0,
        "candidate_total": sum(candidate_totals),
        "fallback_ratio": sum(fallback_ratios) / len(fallback_ratios) if fallback_ratios else 0.0,
        "avg_candidates_before_prune": sum(before_vals) / len(before_vals) if before_vals else 0.0,
        "avg_candidates_after_prune": sum(after_vals) / len(after_vals) if after_vals else 0.0,
        "failures": failures,
        "skipped_cases": skipped,
        "results": results,
    }


def run_single_case(args) -> Dict[str, Any]:
    case_file = args.case_file or DEFAULT_CASE
    if not os.path.exists(case_file):
        print(json.dumps({"ok": False, "message": f"Case file not found: {case_file}"}))
        sys.exit(1)

    case_data = load_yaml(case_file)
    repo_id = case_data.get("repo_id")
    repo_registry = load_repo_registry(args.repos_file)
    repo_dir, source = resolve_repo_dir(repo_id, repo_registry.get(repo_id), args.repo_dir or "")
    cleanup_dir = source if repo_id == "synthetic_fixture" and source and source.startswith(tempfile.gettempdir()) else None
    try:
        if not repo_dir or not os.path.exists(repo_dir):
            return summarize([], [{
                "case_id": case_data.get("case_id"),
                "repo_id": repo_id,
                "reason": source,
            }], baseline_id=repo_id)
        return summarize([evaluate_case(case_file, repo_dir)], [], baseline_id=repo_id)
    finally:
        if cleanup_dir:
            shutil.rmtree(cleanup_dir)


def run_all_cases(args) -> Dict[str, Any]:
    repo_registry = load_repo_registry(args.repos_file)
    case_files = discover_case_files(args.cases_dir)
    results = []
    skipped = []

    for case_file in case_files:
        case_data = load_yaml(case_file)
        repo_id = case_data.get("repo_id")
        repo_config = repo_registry.get(repo_id, {})
        if repo_id != "synthetic_fixture" and not args.include_disabled and repo_config.get("enabled") is False:
            skipped.append({
                "case_id": case_data.get("case_id"),
                "repo_id": repo_id,
                "reason": "repo disabled in repos.yaml",
            })
            continue

        repo_dir, source = resolve_repo_dir(repo_id, repo_config)
        cleanup_dir = source if repo_id == "synthetic_fixture" and source and source.startswith(tempfile.gettempdir()) else None
        try:
            if not repo_dir or not os.path.exists(repo_dir):
                skipped.append({
                    "case_id": case_data.get("case_id"),
                    "repo_id": repo_id,
                    "reason": source,
                })
                continue
            results.append(evaluate_case(case_file, repo_dir))
        finally:
            if cleanup_dir:
                shutil.rmtree(cleanup_dir)

    return summarize(results, skipped, baseline_id="all")


def main():
    args = parse_args()
    output = run_all_cases(args) if args.all else run_single_case(args)
    print(json.dumps(output, indent=2, ensure_ascii=False))
    if output["failed"] or (args.fail_on_skipped and output["skipped"]):
        sys.exit(1)


if __name__ == "__main__":
    main()
