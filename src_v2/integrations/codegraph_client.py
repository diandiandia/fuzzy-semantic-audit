import subprocess
import json
import os
import re
from typing import List, Dict, Any, Optional

def is_codegraph_available() -> bool:
    """Check if codegraph CLI is installed in PATH."""
    try:
        subprocess.run(["codegraph", "--help"], capture_output=True)
        return True
    except FileNotFoundError:
        return False

def get_source(symbol: str, project_path: str, file_path: Optional[str] = None) -> str:
    """Retrieve source code of a symbol using codegraph, or empty string."""
    if not is_codegraph_available():
        # Fallback: if file_path is provided, try reading it
        if file_path:
            abs_path = os.path.join(project_path, file_path)
            if os.path.exists(abs_path):
                try:
                    with open(abs_path, "r", encoding="utf-8", errors="ignore") as f:
                        return f.read()
                except:
                    pass
        return ""

    cmd = ["codegraph", "node", "-p", project_path]
    if file_path:
        cmd.extend(["-f", file_path])
    cmd.append(symbol)
    
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, cwd=project_path, timeout=5)
        if result.returncode == 0:
            return result.stdout
    except Exception:
        pass
    return ""

def find_usages_enclosing_functions(
    pattern: str, 
    project_path: str, 
    limit: int = 40, 
    is_regex: bool = False, 
    exclude_name: Optional[str] = None
) -> List[Dict[str, Any]]:
    """Search pattern occurrences (using pure python to avoid rg binary dependency), trace back to enclosing functions, and return details."""
    func_regexes = [
        # Python: def func_name(...)
        re.compile(r'^\s*def\s+([A-Za-z0-9_]+)\b'),
        
        # Go: func func_name(...) or func (recv) func_name(...)
        re.compile(r'^\s*func\s+(?:\([^)]+\)\s+)?([A-Za-z0-9_]+)\b'),
        
        # JS/TS: function name(...) or async function name(...) or export default function name(...)
        re.compile(r'(?:^|\s)(?:export\s+)?(?:default\s+)?(?:async\s+)?function\s+([A-Za-z0-9_]+)\b'),
        
        # JS/TS arrow/expression assignment: const name = ... or let name = function...
        re.compile(r'(?:^|\s)(?:export\s+)?(?:const|let|var)\s+([A-Za-z0-9_]+)\s*=\s*(?:async\s*)?(?:\([^)]*\)|[A-Za-z0-9_]+)?\s*=>'),
        re.compile(r'(?:^|\s)(?:export\s+)?(?:const|let|var)\s+([A-Za-z0-9_]+)\s*=\s*(?:async\s*)?function\b'),
        
        # JS/TS object property assignment or class shorthand method: name(...) { or async name(...) {
        re.compile(r'^\s*(?:async\s+)?([A-Za-z0-9_]+)\s*\([^)]*\)\s*(?:\{|$)'),
        re.compile(r'^\s*([A-Za-z0-9_]+)\s*:\s*(?:async\s*)?(?:function\b|(?:\([^)]*\)|[A-Za-z0-9_]+)?\s*=>)'),
        
        # Java/C++/C#: type name(...) { or public type name(...)
        re.compile(r'(?:public|private|protected|static|final|synchronized|synchronized\s+)?\s*[\w<>\s\[\]]+\s+([A-Za-z0-9_]+)\s*\([^)]*\)\s*(?:throws\s+[\w,\s]+)?\s*(?:\{|$)'),
        
        # C/C++ global functions
        re.compile(r'^\s*(?:[A-Za-z0-9_]+(?:\s*\*+)?\s+)+([A-Za-z0-9_]+)\s*\('),
    ]

    matches = []
    
    # Pure python search
    pat_regex = re.compile(pattern if is_regex else r'\b' + re.escape(pattern) + r'\b')
    for root, dirs, files in os.walk(project_path):
        dirs[:] = [d for d in dirs if not d.startswith('.')]
        for f in files:
            _, ext = os.path.splitext(f)
            if ext.lower() in {
                ".png", ".jpg", ".jpeg", ".gif", ".ico", ".svg", ".pdf", ".zip", ".tar",
                ".gz", ".mp3", ".mp4", ".wav", ".exe", ".dll", ".so", ".bin", ".db",
                ".woff", ".woff2", ".eot", ".ttf", ".jsonl", ".json", ".md"
            }:
                continue
                
            file_path = os.path.join(root, f)
            try:
                with open(file_path, "r", encoding="utf-8", errors="ignore") as file_obj:
                    for line_idx, line_text in enumerate(file_obj, 1):
                        if pat_regex.search(line_text):
                            is_self_def = False
                            for regex in func_regexes:
                                m = regex.search(line_text)
                                if m:
                                    defined_name = m.group(1)
                                    if defined_name == pattern or (not is_regex and defined_name in pattern):
                                        is_self_def = True
                                    break
                            if is_self_def:
                                continue
                            matches.append((file_path, line_idx))
            except Exception:
                pass

    callers = []
    seen = set()
    
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
                    trimmed_line = line_text.strip()
                    if trimmed_line.endswith((';', ',')):
                        continue
                    for regex in func_regexes:
                        m = regex.search(line_text)
                        if m:
                            name = m.group(1)
                            if name in {
                                "if", "for", "while", "switch", "catch", "with", "function", "class", 
                                "const", "let", "var", "return", "import", "export", "default", "from", 
                                "as", "async", "await", "try", "finally", "throw", "new", "delete", 
                                "typeof", "instanceof", "in", "of", "void"
                            }:
                                continue
                            enclosing_func = name
                            break
                    if enclosing_func:
                        if exclude_name and enclosing_func == exclude_name:
                            enclosing_func = None
                            continue
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

def get_callers_ripgrep_fallback(symbol: str, project_path: str) -> List[Dict[str, Any]]:
    """Fallback using ripgrep to find occurrences of the symbol name."""
    usages = find_usages_enclosing_functions(symbol, project_path, limit=10, is_regex=False, exclude_name=symbol)
    callers = []
    for u in usages:
        callers.append({
            "name": u["name"],
            "filePath": u["file"],
            "line": u["line"],
            "is_fallback": True
        })
    return callers

def get_callers(symbol: str, project_path: str) -> List[Dict[str, Any]]:
    """Retrieve callers of a symbol."""
    if not is_codegraph_available():
        return get_callers_ripgrep_fallback(symbol, project_path)

    cmd = ["codegraph", "callers", "-p", project_path, "-l", "10", "-j", symbol]
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, cwd=project_path, timeout=5)
        if result.returncode == 0:
            return json.loads(result.stdout).get("callers", [])
    except Exception:
        pass
    
    return get_callers_ripgrep_fallback(symbol, project_path)

def get_callees(symbol: str, project_path: str) -> List[Dict[str, Any]]:
    """Retrieve callees of a symbol."""
    if not is_codegraph_available():
        return []

    cmd = ["codegraph", "callees", "-p", project_path, "-l", "10", "-j", symbol]
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, cwd=project_path, timeout=5)
        if result.returncode == 0:
            return json.loads(result.stdout).get("callees", [])
    except Exception:
        pass
    return []

def explore(query: str, project_path: str) -> str:
    """Retrieve explore path outputs."""
    if not is_codegraph_available():
        return ""

    cmd = ["codegraph", "explore", "-p", project_path, query]
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, cwd=project_path, timeout=5)
        if result.returncode == 0:
            return result.stdout
    except Exception:
        pass
    return ""

def _extract_code_preview(node_markdown: str, n_lines: int) -> str:
    """Extract code preview from codegraph node markdown output."""
    if not node_markdown:
        return ""
    parts = node_markdown.split("```")
    body = parts[1] if len(parts) >= 3 else node_markdown
    out = []
    for line in body.splitlines():
        s = line.strip()
        if s in ("c", "cpp", "python", "java", "go", "js", "ts", "javascript", "typescript"):
            continue
        out.append(re.sub(r'^\s*\d+[\s\t]', '', line))
        if len(out) >= n_lines:
            break
    return "\n".join(out).strip()

def build_call_chain_context(
    symbol: str, 
    project_path: str, 
    max_len: int = 6000, 
    caller_src_depth: int = 3, 
    caller_src_lines: int = 15
) -> str:
    """Build a call chain slice for a suspect function to help verification reasoning."""
    callers = get_callers(symbol, project_path)
    callees = get_callees(symbol, project_path)

    def _name_line(it):
        name = it.get("name")
        fp = it.get("filePath") or it.get("file") or ""
        if not name:
            return None
        return f"{name} ({fp})" if fp else name

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

def reachability_hint(file_path: str) -> str:
    """Determine routing reachability based on file path."""
    path_lower = file_path.lower().replace('\\', '/')
    parts = path_lower.split('/')
    
    low_reachable_folders = {"monitor", "tools", "client", "unit", "emulator", "test", "tests", "mock", "mocks", "benchmark", "benchmarks", "gtest"}
    if any(part in low_reachable_folders for part in parts):
        return "low"
        
    high_reachable_folders = {
        "src", "lib", "main",
        "views", "view", "routes", "route", "api",
        "controllers", "controller", "handlers", "handler",
        "endpoints", "endpoint", "resources", "resource",
        "blueprints", "blueprint",
        "urls", "middleware", "web", "http", "rpc",
    }
    if any(part in high_reachable_folders for part in parts):
        return "high"
        
    return "medium"
