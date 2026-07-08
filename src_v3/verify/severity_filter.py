from typing import List, Dict, Any
from src_v3.core.models import CandidateRecord

class SeverityFilter:
    """
    Classifies and prioritizes CandidateRecords based on priority score thresholds.
    """
    @staticmethod
    def get_severity(score: float) -> str:
        if score >= 80.0:
            return "critical"
        elif score >= 60.0:
            return "high"
        elif score >= 40.0:
            return "medium"
        else:
            return "low"

    @classmethod
    def filter_and_sort(cls, candidates: List[CandidateRecord], min_severity: str = "low") -> List[CandidateRecord]:
        severity_ranks = {"critical": 4, "high": 3, "medium": 2, "low": 1}
        min_rank = severity_ranks.get(min_severity.lower(), 1)
        
        filtered = []
        for cand in candidates:
            sev = cls.get_severity(cand.priority_score)
            if severity_ranks.get(sev, 1) >= min_rank:
                filtered.append(cand)
                
        # Sort by priority score desc
        filtered.sort(key=lambda x: x.priority_score, reverse=True)
        return filtered
