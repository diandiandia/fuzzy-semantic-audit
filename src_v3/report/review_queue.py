import os
from typing import List, Dict, Any
from src_v3.core.models import CandidateRecord, VerificationResult

def compile_review_queue_report(workspace_dir: str, review_cands: List[CandidateRecord], results_map: Dict[str, VerificationResult]) -> str:
    """
    Generates reports/review_queue.md for manual review candidates with repo-relative links.
    """
    lines = [
        "# 📋 Manual Review Queue",
        "",
        f"Total Candidates Requiring Review: **{len(review_cands)}**",
        ""
    ]
    
    if not review_cands:
        lines.append("> [!NOTE]")
        lines.append("> No candidates currently require manual review.")
        return "\n".join(lines)
        
    # Summary Table
    lines.extend([
        "### 📊 Review Backlog Summary",
        "",
        "| ID | Symbol | Track | Target Status | File Location |",
        "|---|---|---|---|---|"
    ])
    
    for idx, cand in enumerate(review_cands):
        rel_link = f"../../{cand.file}#L{cand.span['start']}-L{cand.span['end']}"
        lines.append(f"| {idx + 1} | `{cand.symbol}` | `{', '.join(cand.source_tracks)}` | **{cand.status.upper()}** | [{cand.file}]({rel_link}) |")
        
    lines.extend([
        "",
        "---",
        "",
        "## 🔍 Detailed Backlog Traces",
        ""
    ])
    
    for idx, cand in enumerate(review_cands):
        res = results_map.get(cand.candidate_id)
        reason = res.reason if res else "Awaiting detailed triage."
        rel_link = f"../../{cand.file}#L{cand.span['start']}-L{cand.span['end']}"
        
        alert_type = "[!WARNING]" if cand.status == "needs_review" else "[!NOTE]"
        
        lines.extend([
            f"### {idx + 1}. `{cand.symbol}` in `{cand.file}`",
            "",
            f"> {alert_type}",
            f"> **Manual Review Required ({cand.status.upper()})**",
            f"> - **Track**: `{', '.join(cand.source_tracks)}`",
            f"> - **Location**: [{cand.file} (Line {cand.span['start']}-{cand.span['end']})]({rel_link})",
            f"> - **Verification Feedback**: {reason}",
            ""
        ])
        
    return "\n".join(lines)
