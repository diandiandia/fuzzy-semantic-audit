import os
import json
from typing import List, Dict, Any

class SeverityScorer:
    """对初筛节点进行严重性特征打分并排序"""
    
    ENTRYPOINTS = ["onTransact", "onCommand", "handleShellCommand", "main"]
    PRIVILEGES = ["AttributionSource", "Binder", "UserHandle", "Context"]
    HIGH_RISK_KEYS = ["remove", "delete", "permission", "enable", "disable"]

    def calculate_score(self, candidate: Dict[str, Any]) -> float:
        """
        根据评分矩阵计算单个候选点的风险分数
        """
        score = 0.0
        symbol = candidate.get("symbol", "")
        clues = candidate.get("clues", {})
        line_content = clues.get("line_content", "")
        
        # 1. 控制流入口 (Entrypoint) 匹配 (+30)
        has_entrypoint = False
        for ep in self.ENTRYPOINTS:
            if ep.lower() in symbol.lower() or ep.lower() in line_content.lower():
                has_entrypoint = True
                break
        if has_entrypoint:
            score += 30.0
            
        # 2. 参数特权性 (Privilege) 匹配 (+30)
        has_privilege = False
        for priv in self.PRIVILEGES:
            if priv.lower() in symbol.lower() or priv.lower() in line_content.lower():
                has_privilege = True
                break
        if has_privilege:
            score += 30.0
            
        # 3. 高危敏感词 (High Risk Key) 匹配 (+20)
        has_risk_key = False
        for rk in self.HIGH_RISK_KEYS:
            if rk.lower() in symbol.lower() or rk.lower() in line_content.lower():
                has_risk_key = True
                break
        if has_risk_key:
            score += 20.0
            
        # 4. 规则匹配密度 (Density) 匹配 (+20)
        # 如果同时匹配了关键字和正则表达式，或者匹配到了特定的 AST Query 标签
        has_density = False
        if clues.get("matched_keyword") is not None and clues.get("trigger_regex") is not None:
            has_density = True
        elif clues.get("matched_tag") is not None:
            # 如果是 AST 匹配，比如 matched_tag 非空
            has_density = True
            
        if has_density:
            score += 20.0
            
        return score

    def score_and_queue(self, candidates: List[Dict[str, Any]], repo_path: str = "") -> List[Dict[str, Any]]:
        """
        计算每个 Candidate 严重分，标注等级，并写入 verify_queue.json 待验证队列。
        按分值降序排列。
        """
        scored_candidates = []
        for cand in candidates:
            score = self.calculate_score(cand)
            cand["score"] = score
            
            # 严重性评定标准
            if score >= 80.0:
                cand["severity"] = "Critical"
            elif score >= 60.0:
                cand["severity"] = "High"
            elif score >= 40.0:
                cand["severity"] = "Medium"
            else:
                cand["severity"] = "Low"
                
            scored_candidates.append(cand)
            
        # 按分数进行降序排列，分数相同按 ID 排序保证稳定性
        scored_candidates.sort(key=lambda x: (-x["score"], x.get("candidate_id", "")))
        
        # 如果提供了 repo_path，则持久化写入 verify_queue.json
        if repo_path:
            queue_path = os.path.join(repo_path, "verify_queue.json")
            with open(queue_path, "w", encoding="utf-8") as f:
                json.dump(scored_candidates, f, indent=2, ensure_ascii=False)
                
        return scored_candidates
