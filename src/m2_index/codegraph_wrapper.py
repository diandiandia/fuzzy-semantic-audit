import subprocess
import json
import os
import re

def get_source(symbol, project_path, file_path=None):
    cmd = ["codegraph", "node", "-p", project_path]
    if file_path:
        cmd.extend(["-f", file_path])
    cmd.append(symbol)
    result = subprocess.run(cmd, capture_output=True, text=True, cwd=project_path)
    if result.returncode == 0:
        return result.stdout
    return ""

def find_usages_enclosing_functions(pattern, project_path, limit=40, is_regex=False):
    """rg 搜 pattern 的所有 usages,反查每个命中所在的外层函数头,返回 [{name,file,line}]。
    与 get_callers_ripgrep_fallback 共享"向上找函数头"逻辑,但入参是任意 pattern
    (资源访问信号词/链式属性),不限于精确符号。给 explorer 第三路做语义无关的粗召回补强。
    """
    cmd = ["rg", "-n"]
    if not is_regex:
        cmd.append("-w")
    cmd.extend([pattern, project_path])
    
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        return []
        
    matches = []
    for line in result.stdout.splitlines():
        parts = line.split(":", 2)
        if len(parts) < 3:
            continue
        file_path = parts[0]
        try:
            line_num = int(parts[1])
        except ValueError:
            continue
        content_stripped = parts[2].strip()
        
        # 忽略定义/类名
        if any(pat in content_stripped for pat in ["def ", "func ", "function ", "class "]):
            continue
            
        matches.append((file_path, line_num))
        
    callers = []
    seen = set()
    
    func_regexes = [
        re.compile(r'^\s*def\s+([A-Za-z0-9_]+)\b'), # Python
        re.compile(r'^\s*func\s+(?:\([^)]+\)\s+)?([A-Za-z0-9_]+)\b'), # Go
        re.compile(r'^\s*function\s+([A-Za-z0-9_]+)\b'), # JS/TS
        re.compile(r'^\s*(?:const|let|var)\s+([A-Za-z0-9_]+)\s*=\s*(?:async\s*)?(?:\([^)]*\)|[A-Za-z0-9_]+)\s*=>'), # JS arrow
        re.compile(r'^\s*(?:[A-Za-z0-9_]+(?:\s*\*+)?\s+)+([A-Za-z0-9_]+)\s*\('), # C/C++ func
    ]
    
    for file_path, line_num in matches:
        if len(callers) >= limit:
            break
        enclosing_func = None
        try:
            with open(file_path, "r", encoding="utf-8", errors="ignore") as f:
                lines = f.readlines()
                start_idx = min(line_num - 1, len(lines) - 1)
                for idx in range(start_idx, -1, -1):
                    line_text = lines[idx]
                    for regex in func_regexes:
                        m = regex.match(line_text)
                        if m:
                            enclosing_func = m.group(1)
                            break
                    if enclosing_func:
                        break
        except Exception:
            pass
            
        rel_path = os.path.relpath(file_path, project_path)
        if not enclosing_func:
            enclosing_func = f"[module-level] {rel_path}:{line_num}"
            
        key = (enclosing_func, rel_path)
        if key not in seen:
            seen.add(key)
            callers.append({
                "name": enclosing_func,
                "file": rel_path,
                "line": line_num
            })
            
    return callers

def get_callers_ripgrep_fallback(symbol, project_path):
    """Fallback using ripgrep to find occurrences of the symbol name."""
    usages = find_usages_enclosing_functions(symbol, project_path, limit=10, is_regex=False)
    callers = []
    for u in usages:
        if u["name"] == symbol:
            continue
        callers.append({
            "name": u["name"],
            "filePath": u["file"],
            "line": u["line"],
            "is_fallback": True
        })
    return callers


def get_callers(symbol, project_path):
    cmd = ["codegraph", "callers", "-p", project_path, "-l", "10", "-j", symbol]
    result = subprocess.run(cmd, capture_output=True, text=True, cwd=project_path)
    callers = []
    if result.returncode == 0:
        try:
            callers = json.loads(result.stdout).get("callers", [])
        except Exception:
            pass
            
    if not callers:
        callers = get_callers_ripgrep_fallback(symbol, project_path)
    return callers


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
            caller_file = it.get("filePath") or it.get("file")
            src = get_source(it["name"], project_path, file_path=caller_file)
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
        
    high_reachable_folders = {
        "src", "lib", "main",                          # 通用/C/Java
        "views", "view", "routes", "route", "api",     # web 通用
        "controllers", "controller", "handlers", "handler",
        "endpoints", "endpoint", "resources", "resource",
        "blueprints", "blueprint",                     # flask
        "urls", "middleware", "web", "http", "rpc",
    }
    if any(part in high_reachable_folders for part in parts):
        return "high"
        
    return "medium"

