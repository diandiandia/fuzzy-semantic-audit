#!/usr/bin/env python3
import json
import argparse
import sys
import os
import re
import subprocess

from src.common.lang_utils import markdown_tag, EXT_TO_LANG, all_source_extensions, DEFAULT_LANG

# 技术栈预扫描规则外置到 resources/prescan_rules.json(P0 去硬编码),
# 找不到文件时退回内置的 C/C++ 兜底集,保证脚本仍可运行。
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

def setup_args():
    parser = argparse.ArgumentParser(description="Audit Orchestrator & Plan Manager")
    subparsers = parser.add_subparsers(dest="command", required=True)
    
    # Init plan subcommand
    init_parser = subparsers.add_parser("init", help="Initialize audit plan from catalog")
    init_parser.add_argument("--catalog", required=True, help="Path to parsed cwe_699_catalog.json")
    init_parser.add_argument("--project", required=True, help="Path to target project codebase")
    init_parser.add_argument("--lang", default=None, help="Project programming language (auto-detected if omitted)")
    init_parser.add_argument("--output", required=True, help="Output audit_plan.json path")
    
    # Report compile subcommand
    report_parser = subparsers.add_parser("report", help="Compile verified findings into markdown report")
    report_parser.add_argument("--plan", required=True, help="Path to audit_plan.json")
    report_parser.add_argument("--output", required=True, help="Output markdown report path")
    
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
        # Ignore git and standard ignores
        if any(ignored in root_dir for ignored in [".git", ".codegraph", "build", "tests", "mock"]):
            continue
            
        for file in files:
            # Only scan source files
            if not file.endswith(_SOURCE_EXTS):
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
        if any(ignored in root_dir for ignored in [".git", ".codegraph", "build", "tests", "mock"]):
            continue
        for file in files:
            ext = os.path.splitext(file)[1].lower()
            lang = EXT_TO_LANG.get(ext)
            if lang:
                ext_counts[lang] = ext_counts.get(lang, 0) + 1

    if not ext_counts:
        return DEFAULT_LANG
    return max(ext_counts, key=ext_counts.get)

def cmd_init(args):
    project_path = os.path.abspath(args.project)
    
    # 1. Check and initialize CodeGraph index
    check_codegraph_index(project_path)
    
    if not os.path.exists(args.catalog):
        print(f"Error: Catalog file {args.catalog} does not exist", file=sys.stderr)
        sys.exit(1)
        
    with open(args.catalog, "r", encoding="utf-8") as f:
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
        
    with open(args.output, "w", encoding="utf-8") as f:
        json.dump(plan, f, indent=2, ensure_ascii=False)
    print(f"Initialized audit plan with {len(plan['tasks'])} tasks. Saved to: {args.output}")

def cmd_report(args):
    if not os.path.exists(args.plan):
        print(f"Error: Plan file {args.plan} does not exist", file=sys.stderr)
        sys.exit(1)
        
    with open(args.plan, "r", encoding="utf-8") as f:
        plan = json.load(f)

    code_tag = markdown_tag(plan.get("target_language"))
    print(f"Compiling report from audit plan: {args.plan}")
    
    findings = []
    total_candidates = 0
    false_positives = 0
    verified_vulnerabilities = 0
    
    for task in plan["tasks"]:
        for candidate in task.get("result_candidates", []):
            total_candidates += 1
            verdict = candidate.get("verdict")
            if verdict == "verified":
                verified_vulnerabilities += 1
                findings.append((task, candidate))
            elif verdict == "false_positive":
                false_positives += 1
                
    # Create Markdown report
    md = []
    md.append(f"# 🛡️ Code Security Audit Report: Fuzzy Semantic Audit Findings")
    md.append(f"\n- **Target Project**: `{plan.get('project_path')}`")
    md.append(f"- **Language**: `{plan.get('target_language')}`")
    md.append(f"- **Audit Status**: `{plan.get('status')}`")
    md.append(f"\n## 📊 Summary of Audit Run")
    md.append(f"| Metric | Count |")
    md.append(f"| :--- | :--- |")
    md.append(f"| Total CWE Weaknesses Scanned | {len(plan.get('tasks', []))} |")
    md.append(f"| Total Code Candidates Located | {total_candidates} |")
    md.append(f"| False Positives Dismissed | {false_positives} |")
    md.append(f"| **Verified Logic Vulnerabilities (0-Days)** | **{verified_vulnerabilities}** |")
    
    if verified_vulnerabilities == 0:
        md.append("\n🎉 **No logic vulnerabilities verified in this run.**")
    else:
        md.append("\n## 🚨 Detailed Vulnerability Records")
        for i, (task, cand) in enumerate(findings, 1):
            md.append(f"\n### {i}. [{cand['verdict'].upper()}] CWE-{task['cwe_id']}: {task['cwe_name']}")
            md.append(f"- **File Location**: `file://{cand['file']}`")
            md.append(f"- **Target Function**: `{cand['function']}`")
            md.append(f"- **Reachability Entrypoint**: `{cand.get('entrypoint', 'N/A')}`")
            
            md.append(f"\n#### 🔍 Vulnerability Explanation")
            md.append(f"{cand.get('triage_explanation', 'No detailed explanation provided.')}")
            
            md.append(f"\n#### 🧩 Target Source Code Snippet")
            md.append(f"```{code_tag}\n{cand.get('code_snippet', '// Code snippet missing')}\n```")

            if cand.get("struct_definitions"):
                md.append(f"\n#### 📦 Relevant Data Structure Definitions")
                md.append(f"```{code_tag}\n{cand.get('struct_definitions')}\n```")
                
            md.append("\n---")
            
    with open(args.output, "w", encoding="utf-8") as f:
        f.write("\n".join(md))
    print(f"Report compiled successfully. Saved to: {args.output}")

def main():
    args = setup_args()
    if args.command == "init":
        cmd_init(args)
    elif args.command == "report":
        cmd_report(args)

if __name__ == "__main__":
    main()
