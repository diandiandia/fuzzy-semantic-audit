#!/usr/bin/env python3
import json
import argparse
import sys
import os
import re
import subprocess

from src.common.lang_utils import EXT_TO_LANG, all_source_extensions, DEFAULT_LANG
from src.common import paths

# 技术栈预扫描规则外置到 resources/prescan_rules.json(P0 去硬编码),
# 找不到文件时退回内置的通用多语言兜底集,保证脚本仍可运行。
_PRESCAN_RULES_PATH = os.path.join(
    os.path.dirname(__file__), "..", "..", "resources", "prescan_rules.json"
)
_FALLBACK_PRESCAN = {
    "memory": {
        "patterns": [r"malloc", r"free", r"calloc", r"realloc", r"memcpy", r"memmove", r"memset", r"delete", r"new\s", r"pointer", r"dereference"],
        "cwes": ["119", "120", "121", "122", "125", "415", "416", "476", "787", "824"]
    },
    "concurrency": {
        "patterns": [r"thread", r"mutex", r"lock", r"synchronized", r"concurrent", r"go func"],
        "cwes": ["362", "413", "543", "567", "662", "663", "820", "821", "833", "1038", "1058"]
    },
    "network": {
        "patterns": [r"socket", r"connect", r"recv", r"send", r"http", r"requests", r"fetch"],
        "cwes": ["252", "295", "406", "601", "611", "918", "1007"]
    },
    "authz": {
        "patterns": [r"auth", r"permission", r"role", r"user", r"session", r"login"],
        "cwes": ["285", "639", "862", "863", "266", "306"]
    },
    "injection": {
        "patterns": [r"exec", r"system", r"eval", r"subprocess", r"query", r"execute"],
        "cwes": ["77", "78", "79", "89", "90", "94"]
    }
}

def load_prescan_keywords():
    try:
        with open(os.path.abspath(_PRESCAN_RULES_PATH), "r", encoding="utf-8") as f:
            data = json.load(f)
        # 去掉注释键(以 _ 开头),只保留真正的技术栈规则
        return {k: v for k, v in data.items() if not k.startswith("_")}
    except Exception as e:
        print(f"Warning: failed to load prescan rules ({e}); using built-in fallback.", file=sys.stderr)
        return dict(_FALLBACK_PRESCAN)

PRE_SCAN_KEYWORDS = load_prescan_keywords()

# 所有已知源文件扩展名(供预扫描 / 语言探测遍历复用)
_SOURCE_EXTS = tuple(sorted(all_source_extensions()))

# 预扫描 / 语言探测时忽略的目录:VCS、索引、构建产物、依赖、前端打包目录、测试。
# 实测教训(walle):不忽略 fe/dist 会把 webpack 打包的 vendor.*.js(第三方库 minified)
# 扫进来 → 技术栈误判(什么都命中)、语言误判(前端 js 盖过后端 py)。
_IGNORE_DIRS = (".git", ".codegraph", "build", "dist", "node_modules",
                "vendor", "tests", "test", "mock", "__pycache__", ".venv", "venv")

def _is_ignored_dir(root_dir):
    parts = root_dir.replace("\\", "/").split("/")
    return any(p in _IGNORE_DIRS for p in parts)

def _is_generated_file(filename):
    # minified / source-map / 打包产物:纯噪声,跳过
    low = filename.lower()
    return low.endswith((".min.js", ".min.css", ".map", ".bundle.js")) or ".min." in low

def setup_args():
    parser = argparse.ArgumentParser(description="Audit Orchestrator & Plan Manager")
    subparsers = parser.add_subparsers(dest="command", required=True)
    
    # Init plan subcommand. 产物默认落在 <project>/.audit_workspace/(见 common/paths.py);
    # --catalog/--output 可选,不传则用 workspace 默认路径。
    init_parser = subparsers.add_parser("init", help="Initialize audit plan from catalog")
    init_parser.add_argument("--catalog", default=None, help="Path to CWE catalog JSON (default: <project>/.audit_workspace/catalog.json)")
    init_parser.add_argument("--project", required=True, help="Path to target project codebase")
    init_parser.add_argument("--lang", default=None, help="Project programming language (auto-detected if omitted)")
    init_parser.add_argument("--output", default=None, help="Output audit_plan.json path (default: <project>/.audit_workspace/audit_plan.json)")

    # Report compile subcommand
    report_parser = subparsers.add_parser("report", help="Compile verified findings into markdown report")
    report_parser.add_argument("--project", default=None, help="Target project (to derive default workspace paths)")
    report_parser.add_argument("--plan", default=None, help="Path to audit_plan.json (default: <project>/.audit_workspace/audit_plan.json)")
    report_parser.add_argument("--output", default=None, help="Output report path (default: <project>/.audit_workspace/audit_report.md)")
    
    return parser.parse_args()

def perform_pre_scan(project_path):
    print(f"Pre-scanning target project: {project_path} for active technology stacks...")
    found_tags = set()
    
    # Compile regex patterns
    compiled_patterns = {}
    for tag, config in PRE_SCAN_KEYWORDS.items():
        compiled_patterns[tag] = [re.compile(p, re.IGNORECASE) for p in config["patterns"]]
        
    # Walk the directory
    for root_dir, _, files in os.walk(project_path):
        if _is_ignored_dir(root_dir):
            continue

        for file in files:
            # Only scan source files; skip generated/minified bundles
            if not file.endswith(_SOURCE_EXTS) or _is_generated_file(file):
                continue
                
            filepath = os.path.join(root_dir, file)
            try:
                with open(filepath, "r", encoding="utf-8", errors="ignore") as f:
                    content = f.read()
                    for tag, patterns in compiled_patterns.items():
                        if tag in found_tags:
                            continue
                        for pattern in patterns:
                            if pattern.search(content):
                                found_tags.add(tag)
                                print(f"  [+] Match found for category '{tag}' in file: {file}")
                                break
            except Exception as e:
                pass # Ignore reading errors
                
    print(f"Pre-scan complete. Detected technology categories: {list(found_tags)}")
    return found_tags

def calculate_pruned_cwes(catalog, found_tags):
    # Determine which CWEs should be pruned
    all_prune_candidates = set()
    for tag, config in PRE_SCAN_KEYWORDS.items():
        if tag not in found_tags:
            # We didn't find keywords for this category, so we can prune its associated CWEs
            all_prune_candidates.update(config["cwes"])
            
    pruned_catalog = {}
    pruned_count = 0
    for w_id, info in catalog.items():
        if w_id in all_prune_candidates:
            pruned_count += 1
            continue
        pruned_catalog[w_id] = info
        
    print(f"Pruning: Discarded {pruned_count} CWEs due to lack of corresponding keyword signatures in codebase.")
    print(f"Retained {len(pruned_catalog)} CWEs for active auditing.")
    return pruned_catalog

def check_codegraph_index(project_path):
    print("Checking CodeGraph index status...")
    status_cmd = ["codegraph", "status", project_path]
    result = subprocess.run(status_cmd, capture_output=True, text=True)
    if result.returncode != 0:
        print(f"CodeGraph index not found or uninitialized in {project_path}. Initializing...")
        init_cmd = ["codegraph", "init", project_path]
        init_res = subprocess.run(init_cmd, capture_output=True, text=True)
        if init_res.returncode != 0:
            print(f"Error initializing CodeGraph index: {init_res.stderr}", file=sys.stderr)
            sys.exit(1)
        print("CodeGraph index successfully initialized.")
    else:
        print("CodeGraph index verified and active.")

def detect_language(project_path):
    ext_counts = {}
    for root_dir, _, files in os.walk(project_path):
        if _is_ignored_dir(root_dir):
            continue
        for file in files:
            if _is_generated_file(file):
                continue
            ext = os.path.splitext(file)[1].lower()
            lang = EXT_TO_LANG.get(ext)
            if lang:
                ext_counts[lang] = ext_counts.get(lang, 0) + 1

    if not ext_counts:
        return DEFAULT_LANG
    return max(ext_counts, key=ext_counts.get)

def cmd_init(args):
    project_path = os.path.abspath(args.project)

    # 产物统一到 <project>/.audit_workspace/;未显式指定则用默认路径
    paths.ensure_workspace(project_path)
    catalog_file = args.catalog or paths.catalog_path(project_path)
    output_plan = args.output or paths.plan_path(project_path)

    # 1. Check and initialize CodeGraph index
    check_codegraph_index(project_path)

    if not os.path.exists(catalog_file):
        print(f"Error: Catalog file {catalog_file} does not exist", file=sys.stderr)
        sys.exit(1)
        
    with open(catalog_file, "r", encoding="utf-8") as f:
        catalog = json.load(f)
        
    # 2. Auto-detect programming language if not specified
    target_lang = args.lang
    if not target_lang:
        target_lang = detect_language(project_path)
        print(f"Auto-detected project programming language: {target_lang}")
        
    # Pre-scan targets
    found_tags = perform_pre_scan(project_path)
    active_catalog = calculate_pruned_cwes(catalog, found_tags)
    
    # Build the initial JSON audit plan
    plan = {
        "project_path": project_path,
        "target_language": target_lang,
        "status": "initialized",
        "tasks": []
    }
    
    for w_id, cwe_info in active_catalog.items():
        plan["tasks"].append({
            "id": f"task-cwe-{w_id}",
            "type": "explore",
            "cwe_id": w_id,
            "cwe_name": cwe_info["name"],
            "description": cwe_info["description"],
            "query_intents": [], # Will be populated by explorer / synthesizers
            "vulnerability_prompt": "", # Will be populated by intents generator
            "status": "pending",
            "result_candidates": [] # Will store candidate symbols and functions
        })
        
    with open(output_plan, "w", encoding="utf-8") as f:
        json.dump(plan, f, indent=2, ensure_ascii=False)
    print(f"Initialized audit plan with {len(plan['tasks'])} tasks. Saved to: {output_plan}")

def cmd_report(args):
    # 三桶报告的唯一实现在 m5_report.reporter(verified / needs_review / false_positive)。
    # orchestrator 的 report 子命令保留为兼容入口,直接委托给 reporter,避免维护两份
    # 且防止旧的两桶实现与 §13 三桶设计漂移(此前它只渲染 verified/false_positive)。
    from src.m5_report import reporter
    plan_file = args.plan
    output_file = args.output
    if (not plan_file or not output_file):
        if not args.project:
            print("Error: report needs --plan+--output, or --project to derive workspace defaults.", file=sys.stderr)
            sys.exit(1)
        plan_file = plan_file or paths.plan_path(args.project)
        output_file = output_file or paths.report_path(args.project)
    reporter.compile_report(plan_file, output_file)

def main():
    args = setup_args()
    if args.command == "init":
        cmd_init(args)
    elif args.command == "report":
        cmd_report(args)

if __name__ == "__main__":
    main()
