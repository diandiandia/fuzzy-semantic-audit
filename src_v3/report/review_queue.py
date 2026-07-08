import os
from typing import List, Dict, Any
from src_v3.core.models import CandidateRecord, VerificationResult

def compile_audit_report(workspace_dir: str, verified_cands: List[CandidateRecord], results_map: Dict[str, VerificationResult]) -> str:
    """
    Generates reports/audit_report.md listing confirmed vulnerabilities with repo-relative links.
    """
    lines = [
        "# Audit Findings Report",
        f"Total Verified Vulnerabilities: **{len(verified_cands)}**",
        ""
    ]
    
    if not verified_cands:
        lines.append("No confirmed vulnerabilities were verified during this run.")
        return "\n".join(lines)
        
    for idx, cand in enumerate(verified_cands):
        res = results_map.get(cand.candidate_id)
        reason = res.reason if res else "No verification details."
        conf = res.confidence if res else 0.0
        
        # Portable relative link: reports is at .audit_workspace_v3/reports/, so repo root is ../../
        rel_link = f"../../{cand.file}#L{cand.span['start']}-L{cand.span['end']}"
        
        lines.extend([
            f"## {idx + 1}. [{cand.symbol} in {cand.file}]({rel_link})",
            f"- **Track**: `{', '.join(cand.source_tracks)}`",
            f"- **Confidence**: `{conf:.2f}`",
            f"- **Reason**: {reason}",
            ""
        ])
        
    return "\n".join(lines)

def compile_review_queue_report(workspace_dir: str, review_cands: List[CandidateRecord], results_map: Dict[str, VerificationResult]) -> str:
    """
    Generates reports/review_queue.md for manual review candidates with repo-relative links.
    """
    lines = [
        "# Manual Review Queue",
        f"Total Candidates Requiring Review: **{len(review_cands)}**",
        ""
    ]
    
    if not review_cands:
        lines.append("No candidates currently require manual review.")
        return "\n".join(lines)
        
    for idx, cand in enumerate(review_cands):
        res = results_map.get(cand.candidate_id)
        reason = res.reason if res else "Awaiting detailed triage."
        
        rel_link = f"../../{cand.file}#L{cand.span['start']}-L{cand.span['end']}"
        
        lines.extend([
            f"## {idx + 1}. [{cand.symbol} in {cand.file}]({rel_link})",
            f"- **Status**: `{cand.status.upper()}`",
            f"- **Track**: `{', '.join(cand.source_tracks)}`",
            f"- **Reason**: {reason}",
            ""
        ])
        
    return "\n".join(lines)
