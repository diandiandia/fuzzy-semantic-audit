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

def _extract_code_preview(node_markdown, n_lines):
    """从 codegraph node 的 markdown 输出里抽出源码前 n_lines 行(去掉位置头/围栏/行号)。"""
    if not node_markdown:
        return ""
    parts = node_markdown.split("```")
    body = parts[1] if len(parts) >= 3 else node_markdown
    out = []
    for line in body.splitlines():
        s = line.strip()
        if s in ("c", "cpp", "python", "java", "go", "js", "ts", "javascript", "typescript"):
            continue  # 跳过围栏语言标签行
        # 去掉 "123\t" / "123 " 形式的行号前缀
        out.append(re.sub(r'^\s*\d+[\s\t]', '', line))
        if len(out) >= n_lines:
            break
    return "\n".join(out).strip()


def build_call_chain_context(symbol, project_path, max_len=6000, caller_src_depth=3, caller_src_lines=15):
    """为一个嫌疑函数拼出「调用链切片」供裁判做跨函数逻辑漏洞推理。

    上游 callers:除名字外,对前 caller_src_depth 个直接调用方**额外拉取其源码前
    caller_src_lines 行**——这样 Guard 裁判能真正看到"这条路径上有没有鉴权/校验"
    (越权判据),而不是只靠调用方函数名盲猜(评估 2.1 指出的"有骨无肉"缺陷)。
    下游 callees:仅名字(敏感 sink 判断看名字通常够用,且省 token)。
    整体截断到 max_len 控制注入裁判的 token。
    """
    callers = get_callers(symbol, project_path)
    callees = get_callees(symbol, project_path)

    def _name_line(it):
        name = it.get("name")
        fp = it.get("filePath") or it.get("file") or ""
        if not name:
            return None
        return f"{name} ({fp})" if fp else name

    # 上游:前 N 个拉源码,其余仅名字
    up_parts = []
    for i, it in enumerate(callers):
        label = _name_line(it)
        if not label:
            continue
        if i < caller_src_depth and it.get("name"):
            src = get_source(it["name"], project_path)
            preview = _extract_code_preview(src, caller_src_lines)
            if preview:
                up_parts.append(f"- {label}:\n```\n{preview}\n```")
                continue
        up_parts.append(f"- {label}")

    down = [n for n in (_name_line(it) for it in callees) if n]

    parts = []
    parts.append("== CALL CHAIN SLICE (for cross-function logic-flaw reasoning) ==")
    parts.append(f"UPSTREAM callers of `{symbol}` (check reachability from an external entry, and whether auth/ownership checks happen ON THIS PATH — source of the top callers is inlined below):")
    parts.append("\n".join(up_parts) if up_parts else "  (none found — may be an entrypoint, a callback, or unresolved)")
    parts.append(f"\nDOWNSTREAM callees of `{symbol}` (sensitive sinks? db write / file / exec / privileged op):")
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
