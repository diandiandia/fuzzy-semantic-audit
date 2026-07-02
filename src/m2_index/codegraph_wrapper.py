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

def get_callees(symbol, project_path):
    cmd = ["codegraph", "callees", "-p", project_path, "-l", "10", "-j", symbol]
    result = subprocess.run(cmd, capture_output=True, text=True, cwd=project_path)
    if result.returncode == 0:
        try:
            return json.loads(result.stdout).get("callees", [])
        except Exception:
            pass
    return []

def explore(query, project_path):
    """codegraph explore:一次返回相关符号源码 + 调用路径(用于逻辑漏洞的调用链重建)。

    这是 P1 的关键能力:逻辑漏洞(越权/状态机/信任边界)必须看 entry→guard→sink
    的完整数据流,而非单函数。explore 的调用路径正是这条链的原料。
    """
    cmd = ["codegraph", "explore", "-p", project_path, query]
    result = subprocess.run(cmd, capture_output=True, text=True, cwd=project_path)
    if result.returncode == 0:
        return result.stdout
    return ""

def build_call_chain_context(symbol, project_path, max_len=4000):
    """为一个嫌疑函数拼出「调用链切片」:上游 callers(谁能到达/是否经过校验)
    + 下游 callees(把数据交给了谁/是否是敏感 sink)。供裁判判断跨函数的逻辑漏洞。

    返回一段结构化文本,已截断到 max_len 以控制注入给裁判的 token。
    """
    callers = get_callers(symbol, project_path)
    callees = get_callees(symbol, project_path)

    def _names(items):
        out = []
        for it in items:
            name = it.get("name")
            fp = it.get("filePath") or it.get("file") or ""
            if name:
                out.append(f"{name} ({fp})" if fp else name)
        return out

    up = _names(callers)
    down = _names(callees)

    parts = []
    parts.append("== CALL CHAIN SLICE (for cross-function logic-flaw reasoning) ==")
    parts.append(f"UPSTREAM callers (who can reach `{symbol}` — check if any is an external entry / whether auth happens here):")
    parts.append("  " + (", ".join(up) if up else "(none found — may be an entrypoint, a callback, or unresolved)"))
    parts.append(f"DOWNSTREAM callees (what `{symbol}` hands data to — check for sensitive sinks: db write / file / exec / privileged op):")
    parts.append("  " + (", ".join(down) if down else "(none found)"))

    text = "\n".join(parts)
    if len(text) > max_len:
        text = text[:max_len] + "\n... (truncated)"
    return text

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
