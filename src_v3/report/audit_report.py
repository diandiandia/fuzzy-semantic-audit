import os
from typing import List, Dict, Any
from src_v3.core.models import CandidateRecord, VerificationResult

def compile_audit_report(workspace_dir: str, verified_cands: List[CandidateRecord], results_map: Dict[str, VerificationResult]) -> str:
    """
    Generates reports/audit_report.md listing confirmed vulnerabilities with premium markdown callouts and summary tables.
    """
    lines = [
        "# 🛡️ Fuzzy Semantic Audit - Findings Report",
        "",
        f"Total Verified Vulnerabilities: **{len(verified_cands)}**",
        ""
    ]
    
    if not verified_cands:
        lines.append("> [!NOTE]")
        lines.append("> No confirmed vulnerabilities were verified during this run.")
        return "\n".join(lines)
        
    # Summary Table
    lines.extend([
        "### 📊 Findings Summary",
        "",
        "| ID | Symbol | Vulnerability Track | Confidence | File Location |",
        "|---|---|---|---|---|"
    ])
    
    for idx, cand in enumerate(verified_cands):
        res = results_map.get(cand.candidate_id)
        conf = res.confidence if res else 0.0
        rel_link = f"../../{cand.file}#L{cand.span['start']}-L{cand.span['end']}"
        lines.append(f"| {idx + 1} | `{cand.symbol}` | `{', '.join(cand.source_tracks)}` | `{conf:.2f}` | [{cand.file}]({rel_link}) |")
        
    lines.extend([
        "",
        "---",
        "",
        "## 🔍 Detailed Vulnerability Traces",
        ""
    ])
    
    for idx, cand in enumerate(verified_cands):
        res = results_map.get(cand.candidate_id)
        reason = res.reason if res else "No verification details."
        conf = res.confidence if res else 0.0
        
        rel_link = f"../../{cand.file}#L{cand.span['start']}-L{cand.span['end']}"
        
        lines.extend([
            f"### 🚨 Finding {idx + 1}: `{cand.symbol}` in `{cand.file}`",
            "",
            "> [!CAUTION]",
            "> **Vulnerability Confirmed by Three-Lens Referees**",
            f"> - **Track**: `{', '.join(cand.source_tracks)}`",
            f"> - **Confidence Score**: `{conf:.2f}`",
            f"> - **Location**: [{cand.file} (Line {cand.span['start']}-{cand.span['end']})]({rel_link})",
            f"> - **Triage Verdict Reason**: {reason}",
            ""
        ])
        
    return "\n".join(lines)
