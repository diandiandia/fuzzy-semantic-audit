#!/usr/bin/env python3
import os
import re
import json
import argparse
import subprocess
import sys

# 忽略的目录
_IGNORE_DIRS = {".git", ".codegraph", "build", "dist", "node_modules",
                "vendor", "tests", "test", "mock", "__pycache__", ".venv", "venv", ".audit_workspace", ".audit_temp"}

# 文件扩展名到语言的映射
EXT_TO_LANG = {
    ".c": "c/cpp", ".h": "c/cpp", ".cpp": "c/cpp", ".hpp": "c/cpp", ".cc": "c/cpp", ".cxx": "c/cpp",
    ".go": "go",
    ".py": "python",
    ".java": "java",
    ".js": "javascript/typescript", ".ts": "javascript/typescript", ".jsx": "javascript/typescript", ".tsx": "javascript/typescript"
}

# 按语言划分的危险 sink 匹配规则
SINK_PATTERNS = {
    "c/cpp": re.compile(r"\b(strcpy|strcat|sprintf|vsprintf|gets|memcpy|memmove)\b"),
    "go": re.compile(r"\b(unsafe\.Pointer|reflect\.(ValueOf|TypeOf)|exec\.Command|os\.StartProcess)\b"),
    "python": re.compile(r"\b(eval|exec|os\.system|subprocess\.(run|Popen|call))\b"),
    "java": re.compile(r"\b(Runtime\.getRuntime\(\)\.exec|ProcessBuilder|Class\.forName|System\.loadLibrary)\b"),
    "javascript/typescript": re.compile(r"\b(eval|child_process\.(exec|spawn)|Function\b)"),
}

def _is_ignored_dir(root_dir):
    parts = root_dir.replace("\\", "/").split("/")
    return any(p in _IGNORE_DIRS for p in parts)

def detect_language(project_path):
    counts = {}
    for root_dir, _, files in os.walk(project_path):
        if _is_ignored_dir(root_dir):
            continue
        for file in files:
            ext = os.path.splitext(file)[1].lower()
            lang = EXT_TO_LANG.get(ext)
            if lang:
                counts[lang] = counts.get(lang, 0) + 1
    if not counts:
        return "c/cpp" # 默认兜底
    return max(counts, key=counts.get)

def get_file_symbols(project_path, file_path):
    """通过 CodeGraph 提取文件中的所有函数符号及其行号。"""
    cmd = ["codegraph", "node", "-p", project_path, "-f", file_path, "--symbols-only", file_path]
    res = subprocess.run(cmd, capture_output=True, text=True, cwd=project_path)
    symbols = []
    if res.returncode == 0:
        for line in res.stdout.splitlines():
            # 匹配格式: - `discover_primary_unref` (function) — :83
            m = re.match(r'^\s*-\s*`([^`]+)`\s*\((function|method)\)\s*—\s*:(.*)$', line)
            if m:
                name = m.group(1)
                line_num = m.group(3).strip()
                if line_num.isdigit():
                    symbols.append((name, int(line_num)))
    return sorted(symbols, key=lambda x: x[1])

def find_surrounding_function(symbols, line_num):
    """给定行号，反查所属的最邻近函数。"""
    if not symbols:
        return None
    # 查找最大的 func_line <= line_num
    candidate = None
    for name, f_line in symbols:
        if f_line <= line_num:
            candidate = name
        else:
            break
    return candidate

def main():
    parser = argparse.ArgumentParser(description="Recall Coverage Auditor")
    parser.add_argument("--cand-dir", required=True, help="Directory containing pending candidates")
    parser.add_argument("--project", required=True, help="Path to project root")
    parser.add_argument("--output", required=True, help="Path to write the markdown gap report")
    args = parser.parse_args()

    project_path = os.path.abspath(args.project)
    cand_dir = os.path.abspath(args.cand_dir)

    # 1. 加载所有已召回的候选函数
    recalled = set()
    if os.path.exists(cand_dir):
        for file in os.listdir(cand_dir):
            if file.startswith("cand-") and file.endswith(".json"):
                try:
                    with open(os.path.join(cand_dir, file), "r", encoding="utf-8") as f:
                        data = json.load(f)
                        rel_file = data.get("file")
                        func = data.get("function")
                        if rel_file and func:
                            # 统一格式化为 Unix 风格路径
                            recalled.add((rel_file.replace("\\", "/"), func))
                except Exception:
                    pass

    print(f"Loaded {len(recalled)} already-recalled candidate functions.")

    # 2. 检测项目语言并匹配规则
    lang = detect_language(project_path)
    pattern = SINK_PATTERNS.get(lang)
    print(f"Auto-detected language for audit: {lang}")

    gaps = []
    
    # 3. 扫描项目源文件
    for root_dir, _, files in os.walk(project_path):
        if _is_ignored_dir(root_dir):
            continue

        for file in files:
            ext = os.path.splitext(file)[1].lower()
            if EXT_TO_LANG.get(ext) != lang:
                continue

            filepath = os.path.join(root_dir, file)
            rel_file = os.path.relpath(filepath, project_path).replace("\\", "/")

            # 只有当该文件有匹配 SINK 的内容时，才提取 symbols
            try:
                with open(filepath, "r", encoding="utf-8", errors="ignore") as f:
                    lines = f.readlines()
            except Exception:
                continue

            matched_lines = []
            for idx, line in enumerate(lines, 1):
                if pattern.search(line):
                    matched_lines.append((idx, line.strip()))

            if not matched_lines:
                continue

            # 提取文件符号映射
            symbols = get_file_symbols(project_path, rel_file)
            if not symbols:
                continue

            for line_num, line_content in matched_lines:
                func_name = find_surrounding_function(symbols, line_num)
                if func_name:
                    if (rel_file, func_name) not in recalled:
                        gaps.append({
                            "file": rel_file,
                            "function": func_name,
                            "line": line_num,
                            "content": line_content
                        })

    # 4. 生成报告
    md = []
    md.append(f"# 🔍 Recall Coverage Audit Report")
    md.append(f"\n- **Project**: `{project_path}`")
    md.append(f"- **Detected Language**: `{lang}`")
    md.append(f"- **Total Potential Gaps**: **{len(gaps)}**")
    
    if not gaps:
        md.append("\n✅ **No recall gaps detected.** All scanned dangerous sinks are covered by candidates in the workflow.")
    else:
        md.append("\n⚠️ **The following functions contain dangerous sinks but are NOT covered by current candidate packages:**")
        md.append("\n| Function | File | Line | Trigger Content |")
        md.append("| :--- | :--- | :--- | :--- |")
        
        # 按文件分组排序
        gaps = sorted(gaps, key=lambda x: (x["file"], x["function"], x["line"]))
        for g in gaps:
            # 截断超长行内容
            content_preview = g["content"]
            if len(content_preview) > 80:
                content_preview = content_preview[:77] + "..."
            md.append(f"| `{g['function']}` | `{g['file']}` | {g['line']} | `{content_preview}` |")

    os.makedirs(os.path.dirname(os.path.abspath(args.output)), exist_ok=True)
    with open(args.output, "w", encoding="utf-8") as f:
        f.write("\n".join(md))

    print(f"Recall audit report compiled. {len(gaps)} potential gaps found. Saved to {args.output}")

if __name__ == "__main__":
    main()
