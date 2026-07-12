#!/usr/bin/env python3
import argparse
import hashlib
import json
import os
import subprocess
import sys
import tempfile
import time
from typing import Any, Dict, List

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def run_cli(script_name: str, args: List[str]) -> Dict[str, Any]:
    script_path = os.path.join(PROJECT_ROOT, "src_v3", "cli", f"{script_name}.py")
    env = os.environ.copy()
    env["PYTHONPATH"] = PROJECT_ROOT
    proc = subprocess.run([sys.executable, script_path, *args], capture_output=True, text=True, env=env)
    if proc.returncode != 0:
        raise RuntimeError(f"{script_name} failed: {proc.stderr.strip()} {proc.stdout.strip()}")
    return json.loads(proc.stdout.strip())


def create_fixture_repo(root: str, files: int) -> str:
    repo_dir = os.path.join(root, "perf_fixture")
    os.makedirs(repo_dir, exist_ok=True)
    for idx in range(files):
        with open(os.path.join(repo_dir, f"service_{idx}.py"), "w", encoding="utf-8") as f:
            f.write(
                f"def authorize_{idx}(request):\n"
                f"    return request.user_id == {idx}\n\n"
                f"def route_{idx}(request):\n"
                f"    return authorize_{idx}(request)\n"
            )
    return repo_dir


def report_digest(workspace_dir: str) -> str:
    reports_dir = os.path.join(workspace_dir, "reports")
    digest = hashlib.sha256()
    for name in sorted(os.listdir(reports_dir)) if os.path.exists(reports_dir) else []:
        if not name.endswith(".md"):
            continue
        if name == "metrics_report.md":
            continue
        with open(os.path.join(reports_dir, name), "rb") as f:
            content = f.read()
        # Ignore volatile wall-clock metric lines while preserving report content.
        stable = b"\n".join(
            line for line in content.splitlines()
            if b"wall_clock_seconds" not in line and b"Generated at" not in line
        )
        digest.update(name.encode("utf-8") + b"\0" + stable)
    return digest.hexdigest()


def run_round(workspace_dir: str) -> Dict[str, Any]:
    started = time.time()
    ir = run_cli("build_ir", ["--workspace", workspace_dir])
    index = run_cli("build_index", ["--workspace", workspace_dir])
    reports = run_cli("compile_reports", ["--workspace", workspace_dir])
    return {
        "wall_clock_seconds": time.time() - started,
        "build_ir": ir.get("summary", {}),
        "build_index": index.get("summary", {}),
        "compile_reports": reports.get("summary", {}),
        "report_digest": report_digest(workspace_dir),
    }


def run_benchmark(files: int = 8, min_speedup: float = 1.05) -> Dict[str, Any]:
    with tempfile.TemporaryDirectory() as tmp:
        repo_dir = create_fixture_repo(tmp, files)
        run_cli("init_plan", ["--project", repo_dir])
        workspace_dir = os.path.join(repo_dir, ".audit_workspace_v3")
        run_cli("build_inventory", ["--workspace", workspace_dir])
        cold = run_round(workspace_dir)
        warm = run_round(workspace_dir)

        cold_time = max(0.0001, cold["wall_clock_seconds"])
        warm_time = max(0.0001, warm["wall_clock_seconds"])
        speedup = cold_time / warm_time
        cache_hits = warm["build_ir"].get("cache_hits", 0)
        cache_misses = warm["build_ir"].get("cache_misses", 0)
        reused_count = warm["build_index"].get("reused_count", 0)
        rebuilt_count = warm["build_index"].get("rebuilt_count", 0)
        reports_consistent = cold["report_digest"] == warm["report_digest"]
        cache_reuse_passed = cache_hits >= files and cache_misses == 0 and reused_count >= files and rebuilt_count == 0

        return {
            "ok": bool(cache_reuse_passed and reports_consistent and speedup >= min_speedup),
            "workspace_dir": workspace_dir,
            "files": files,
            "min_speedup": min_speedup,
            "speedup": speedup,
            "cold": cold,
            "warm": warm,
            "cache_reuse_passed": cache_reuse_passed,
            "reports_consistent": reports_consistent,
        }


def main():
    parser = argparse.ArgumentParser(description="Benchmark V3 incremental IR/index cache reuse")
    parser.add_argument("--files", type=int, default=8)
    parser.add_argument("--min-speedup", type=float, default=1.05)
    args = parser.parse_args()
    result = run_benchmark(files=args.files, min_speedup=args.min_speedup)
    print(json.dumps(result, indent=2, ensure_ascii=False))
    raise SystemExit(0 if result["ok"] else 1)


if __name__ == "__main__":
    main()
