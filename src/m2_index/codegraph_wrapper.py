import subprocess
import json
import os
import re

def get_source(symbol, project_path):
    cmd = ["codegraph", "node", "-p", project_path, symbol]
    result = subprocess.run(cmd, capture_output=True, text=True, cwd=project_path)
    if result.returncode == 0:
        return result.stdout
    return ""

def get_callers(symbol, project_path):
    cmd = ["codegraph", "callers", "-p", project_path, "-l", "10", "-j", symbol]
    result = subprocess.run(cmd, capture_output=True, text=True, cwd=project_path)
    if result.returncode == 0:
        try:
            return json.loads(result.stdout).get("callers", [])
        except Exception:
            pass
    return []

def reachability_hint(file_path):
    # Determine reachability by path routing (System Design Section 10 / Architecture Section 2)
    path_lower = file_path.lower().replace('\\', '/')
    parts = path_lower.split('/')
    
    low_reachable_folders = {"monitor", "tools", "client", "unit", "emulator", "test", "tests", "mock", "mocks", "benchmark", "benchmarks", "gtest"}
    if any(part in low_reachable_folders for part in parts):
        return "low"
        
    high_reachable_folders = {"src", "lib", "main"}
    if any(part in high_reachable_folders for part in parts) or path_lower.startswith("src/") or path_lower.startswith("lib/"):
        return "high"
        
    return "medium"
