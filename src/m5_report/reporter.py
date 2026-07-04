import os
import json
import argparse
import sys
from src.common.plan_manager import load_plan
from src.common.lang_utils import markdown_tag

def setup_args():
    parser = argparse.ArgumentParser(description="Audit Report Compiler")
    parser.add_argument("--plan", required=True, help="Path to audit_plan.json")
    parser.add_argument("--output", required=True, help="Output markdown report path")
    return parser.parse_args()

def file_url(plan, cand):
    """返回本地绝对路径的 file:// URL,确保编辑器中可直接点击。"""
    project_path = plan.get("project_path", "")
    rel_path = cand.get("file", "")
    abs_path = os.path.abspath(os.path.join(project_path, rel_path))
    # Linux 绝对路径以 / 开头,file:// + /path... = file:///path...
    return f"file://{abs_path}" if abs_path.startswith("/") else f"file:///{abs_path}"

def cwe_label(task, cand):
    """去重后一个候选可命中多个 CWE:优先用候选的 matched_cwes,回退到 task 的单 CWE。"""
    matched = cand.get("matched_cwes")
    if matched:
        return "CWE-" + " / CWE-".join(matched)
    return f"CWE-{task.get('cwe_id', '?')}: {task.get('cwe_name', '')}"

def compile_report(plan_path, output_path):
    plan = load_plan(plan_path)

    code_tag = markdown_tag(plan.get("target_language"))
    print(f"Compiling three-bucket report from plan: {plan_path}")
    
    # Track statistics
    scanned_cwe_ids = plan.get("scanned_cwe_ids", [])
    if not scanned_cwe_ids:
        # 兼容未去重或未记录时从候选包的 matched_cwes 反推
        cwe_set = set()
        for task in plan.get("tasks", []):
            for cand in task.get("result_candidates", []):
                matched = cand.get("matched_cwes", [])
                if matched:
                    cwe_set.update(matched)
                elif cand.get("cwe_id") and cand.get("cwe_id") != "MULTI":
                    cwe_set.add(cand.get("cwe_id"))
        scanned_cwe_ids = list(cwe_set)
    total_scanned_cwes = len(scanned_cwe_ids) if scanned_cwe_ids else len(plan.get("tasks", []))
    total_candidates = 0
    verified = []
    needs_review = []
    false_positive = []
    pending = []
    
    for task in plan.get("tasks", []):
        for cand in task.get("result_candidates", []):
            total_candidates += 1
            verdict = cand.get("verdict", "pending")
            if verdict == "verified":
                verified.append((task, cand))
            elif verdict == "needs_review":
                needs_review.append((task, cand))
            elif verdict == "false_positive":
                false_positive.append((task, cand))
            else:
                pending.append((task, cand))
                
    # Build Markdown report
    md = []
    md.append(f"# 🛡️ Code Security Audit Report: Fuzzy Semantic Audit Findings")
    md.append(f"\n- **Target Project**: `{plan.get('project_path')}`")
    md.append(f"- **Language**: `{plan.get('target_language')}`")
    md.append(f"- **Audit Status**: `{plan.get('status')}`")
    
    md.append(f"\n## 📊 Summary of Audit Run")
    md.append(f"| Metric | Count |")
    md.append(f"| :--- | :--- |")
    md.append(f"| Total CWE Weaknesses Scanned | {total_scanned_cwes} |")
    md.append(f"| Total Code Candidates Located | {total_candidates} |")
    md.append(f"| **Verified Logic Vulnerabilities (0-Days)** | **{len(verified)}** |")
    md.append(f"| **Requires Manual Review (Needs Review)** | **{len(needs_review)}** |")
    md.append(f"| False Positives Dismissed | {len(false_positive)} |")
    md.append(f"| Unverified / Pending Candidates | {len(pending)} |")
    
    # Honest boundaries log (Section 7 and Section 5.3)
    md.append(f"\n## 🔍 Audit Completeness & Budget Limits")
    if len(pending) > 0:
        md.append(f"⚠️ **Notice**: There are **{len(pending)}** candidates that were truncated or remain unverified due to budget/token limits or execution constraints.")
    else:
        md.append("✅ All identified candidates were fully processed and verified.")
        
    # Verified section
    md.append(f"\n## 🚨 Verified Logic Vulnerabilities (verified)")
    if not verified:
        md.append("🎉 **No logic vulnerabilities verified in this run.**")
    else:
        for i, (task, cand) in enumerate(verified, 1):
            md.append(f"\n### {i}. {cwe_label(task, cand)}")
            md.append(f"- **File Location**: `{file_url(plan, cand)}`")
            md.append(f"- **Target Function**: `{cand['function']}`")
            md.append(f"- **Reachability Entrypoint**: `{cand.get('entrypoint', 'N/A')}`")
            md.append(f"- **Recall Source**: `{cand.get('recall_source', 'unknown')}`")
            
            md.append(f"\n#### 🔍 Vulnerability Explanation")
            md.append(f"{cand.get('triage_explanation', 'No detailed explanation provided.')}")
            
            votes = cand.get("votes", [])
            if votes:
                md.append(f"\n#### 🗳️ Verification Votes")
                for vote in votes:
                    md.append(f"- **{vote.get('lens', 'unknown')}**: isReal={vote.get('isReal')}, confidence={vote.get('confidence')}")
                    md.append(f"  - Reason: {vote.get('reason')}")
                    if vote.get("attackPath") and vote.get("attackPath") != "None":
                        md.append(f"  - Attack Path: `{vote.get('attackPath')}`")
            
            if cand.get("call_chain_context"):
                md.append(f"\n#### 🔗 Call Chain Slice (cross-function data flow)")
                md.append(f"```\n{cand.get('call_chain_context')}\n```")

            md.append(f"\n#### 🧩 Target Source Code Snippet")
            md.append(f"```{code_tag}\n{cand.get('code_snippet', '// Code snippet missing')}\n```")

            if cand.get("struct_definitions"):
                md.append(f"\n#### 📦 Relevant Data Structure Definitions")
                md.append(f"```{code_tag}\n{cand.get('struct_definitions')}\n```")
            md.append("\n---")
            
    # Needs review section
    md.append(f"\n## ⚠️ Candidates Requiring Manual Review (needs_review)")
    if not needs_review:
        md.append("No candidates required manual review.")
    else:
        for i, (task, cand) in enumerate(needs_review, 1):
            md.append(f"\n### {i}. {cwe_label(task, cand)}")
            md.append(f"- **File Location**: `{file_url(plan, cand)}`")
            md.append(f"- **Target Function**: `{cand['function']}`")
            md.append(f"- **Reachability Entrypoint**: `{cand.get('entrypoint', 'N/A')}`")
            md.append(f"- **Recall Source**: `{cand.get('recall_source', 'unknown')}`")
            
            md.append(f"\n#### 🔍 Review Rationale")
            md.append(f"{cand.get('triage_explanation', 'No detailed explanation provided.')}")
            
            votes = cand.get("votes", [])
            if votes:
                md.append(f"\n#### 🗳️ Verification Votes & Missing Evidence")
                for vote in votes:
                    md.append(f"- **{vote.get('lens', 'unknown')}**: isReal={vote.get('isReal')}, confidence={vote.get('confidence')}")
                    md.append(f"  - Reason: {vote.get('reason')}")
                    if vote.get("missingEvidence") and vote.get("missingEvidence") != "None":
                        md.append(f"  - Missing Evidence: *{vote.get('missingEvidence')}*")

            if cand.get("call_chain_context"):
                md.append(f"\n#### 🔗 Call Chain Slice (cross-function data flow)")
                md.append(f"```\n{cand.get('call_chain_context')}\n```")

            md.append(f"\n#### 🧩 Target Source Code Snippet")
            md.append(f"```{code_tag}\n{cand.get('code_snippet', '// Code snippet missing')}\n```")
            md.append("\n---")
            
    # False positives appendix
    md.append(f"\n## ❌ Appendix: False Positives Dismissed (false_positive)")
    if not false_positive:
        md.append("No false positives were dismissed in this run.")
    else:
        for i, (task, cand) in enumerate(false_positive, 1):
            md.append(f"\n### {i}. {cwe_label(task, cand)} (Function: `{cand['function']}`)")
            md.append(f"- **File Location**: `{file_url(plan, cand)}`")
            md.append(f"- **Recall Source**: `{cand.get('recall_source', 'unknown')}`")
            md.append(f"- **Dismissal Explanation**: {cand.get('triage_explanation', 'No detailed explanation provided.')}")
            
    # Write report
    with open(output_path, "w", encoding="utf-8") as f:
        f.write("\n".join(md))

    print(f"Report compiled successfully. Saved to: {output_path}")

def main():
    args = setup_args()
    compile_report(args.plan, args.output)

if __name__ == "__main__":
    main()
