import os
import json
import time
import sys
from typing import List, Dict, Any

from src_v4.inventory.language_sharder import LanguageDiscoverer
from src_v4.packs.dynamic_packer import AIDynamicPacker
from src_v4.filter.coarse_scanner import ASTCoarseScanner
from src_v4.filter.severity_scorer import SeverityScorer
from src_v4.verify.tools import AgentTools
from src_v4.verify.agentic_triage import VerifierAgent

class AuditOrchestrator:
    """系统工作流引擎控制器，作为串行队列的执行保障"""
    
    def execute(self, workspace_path: str):
        """
        控制流次序：
        1. 启动 LanguageDiscoverer -> 产出 repo_profile.json
        2. 启动 AIDynamicPacker -> 产出 scan_pack.json
        3. 运行 ASTCoarseScanner & Scorer -> 产出 verify_queue.json
        4. 循环从队列中 pop 高危 Candidate -> 拉起 VerifierAgent 验证 -> 串行回写报告
        """
        workspace_path = os.path.abspath(workspace_path)
        print(f"=== Starting Fuzzy Semantic Audit V4 for workspace: {workspace_path} ===")
        
        # 1. 启动语言发现器
        print("\n--- Phase 1: Discovering Languages ---")
        discoverer = LanguageDiscoverer()
        profile = discoverer.discover(workspace_path)
        detected_langs = list(profile["languages"].keys())
        print(f"Detected languages: {detected_langs}")
        print(f"Saved profile to: repo_profile.json")
        
        if not detected_langs:
            print("No supported programming languages detected. Audit aborting.")
            return
            
        # 2. 启动 AI 动态画像生成器
        print("\n--- Phase 2: Generating Security Scan Pack ---")
        packer = AIDynamicPacker()
        pack = packer.generate_pack(detected_langs, workspace_path)
        print("Saved dynamic scan rules to: scan_pack.json")
        
        # 3. 运行 AST/正则粗筛器与打分器
        print("\n--- Phase 3: Coarse AST & Regex Filtering ---")
        # 收集所有登记的源文件
        all_files = []
        for lang_files in profile["languages"].values():
            all_files.extend(lang_files)
            
        scanner = ASTCoarseScanner()
        candidates = scanner.scan(all_files, pack, workspace_path)
        print(f"Found {len(candidates)} candidate sinks during coarse filtering.")
        
        scorer = SeverityScorer()
        scored_queue = scorer.score_and_queue(candidates, workspace_path)
        print(f"Saved prioritized queue to: verify_queue.json")
        
        # 4. 串行循环验证
        print("\n--- Phase 4: Sequential Agentic Verification ---")
        tools = AgentTools(workspace_path, profile)
        verifier = VerifierAgent()
        
        reports_dir = os.path.join(workspace_path, "reports")
        os.makedirs(reports_dir, exist_ok=True)
        report_path = os.path.join(reports_dir, "review_queue.md")
        
        # 初始化报告内容
        report_content = [
            "# Fuzzy Semantic Audit V4 — Audit Findings Report\n",
            f"**Audit executed at**: {time.strftime('%Y-%m-%d %H:%M:%S')}\n",
            f"**Target Workspace**: `{workspace_path}`\n",
            "## 📌 Executive Summary\n",
            "This report lists the verified security findings and their corresponding reachability call paths.\n",
            "## 🔍 Findings Details\n"
        ]
        
        # 加载待审队列
        queue_path = os.path.join(workspace_path, "verify_queue.json")
        if not os.path.exists(queue_path):
            print("No verify queue found. Workflow terminated.")
            return
            
        with open(queue_path, "r", encoding="utf-8") as f:
            queue = json.load(f)
            
        pending_candidates = [c for c in queue if c.get("status") == "PENDING"]
        print(f"Total candidates to verify: {len(pending_candidates)}")
        
        for cand in queue:
            if cand.get("status") != "PENDING":
                continue
                
            cand_id = cand["candidate_id"]
            print(f"\n[Verifying] candidate {cand_id}: {cand['symbol']} in {cand['file_path']}:{cand['line_number']} (Severity: {cand['severity']}, Score: {cand['score']})")
            
            # 状态流转锁：锁定为研判中，并立即持久化存盘
            cand["status"] = "VERIFYING"
            self._save_queue(queue, queue_path)
            
            # 拉起 Verifier Agent 研判
            result = verifier.verify_candidate(cand, tools)
            verdict = result.get("verdict", "NEEDS_REVIEW")
            reasoning_path = result.get("reasoning_path", [])
            summary = result.get("summary", "")
            
            print(f"[Result] Candidate {cand_id} Verdict: {verdict}")
            
            # 更新状态
            if verdict == "YES":
                cand["status"] = "DONE"
                # 记录到报告
                findings_md = f"""
### 🚨 Candidate {cand_id}: {cand['symbol']} ({cand['severity']})
- **File**: `{cand['file_path']}:{cand['line_number']}`
- **Language**: {cand['language']}
- **Verification Verdict**: `YES` (Reachable)
- **Taint Call Chain Path**:
  ```
  {" -> ".join(reasoning_path)}
  ```
- **Agent Analysis Summary**:
  {summary}
---
"""
                report_content.append(findings_md)
            elif verdict == "NO":
                cand["status"] = "DONE"
            else:
                cand["status"] = "ERROR_NEEDS_REVIEW"
                
            # 回写最终状态
            self._save_queue(queue, queue_path)
            
        # 写入最终 Markdown 报告
        with open(report_path, "w", encoding="utf-8") as f:
            f.writelines(report_content)
            
        print(f"\n=== Audit Workflow Completed. Report written to {report_path} ===")

    def _save_queue(self, queue: list, path: str):
        with open(path, "w", encoding="utf-8") as f:
            json.dump(queue, f, indent=2, ensure_ascii=False)

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python orchestrate_audit.py <workspace_path>")
        sys.exit(1)
        
    orchestrator = AuditOrchestrator()
    orchestrator.execute(sys.argv[1])
