import os
from typing import Dict, Any
from src_v3.storage.candidate_store import CandidateStore
from src_v3.storage.evidence_store import EvidenceStore

def compile_metrics_report(workspace_dir: str, metrics: Dict[str, Any]) -> str:
    """
    Generates reports/metrics_report.md for performance/quality indicators,
    ensuring it contains key indicators like recall total, compression ratio,
    mean evidence score, and queue backlog.
    """
    candidate_store = CandidateStore(workspace_dir)
    evidence_store = EvidenceStore(workspace_dir)
    
    recalled_cands = candidate_store.get_candidates(pruned=False)
    pruned_cands = candidate_store.get_candidates(pruned=True)
    
    recall_total = len(recalled_cands)
    pruned_total = len(pruned_cands)
    compression_ratio = pruned_total / max(1, recall_total)
    
    # Calculate mean evidence score
    scores = []
    for cand in pruned_cands:
        bundle = evidence_store.get_evidence(cand.candidate_id)
        if bundle:
            scores.append(bundle.evidence_completeness_score)
    mean_evidence_score = sum(scores) / max(1, len(scores)) if scores else 0.0
    
    # Calculate queue backlog
    backlog_count = sum(1 for c in pruned_cands if c.status in [
        "discovered", "recalled", "normalized", "pruned", "evidence_ready", "queued_for_verify", "verifying"
    ])
    
    lines = [
        "# 📈 Fuzzy Semantic Audit - Metrics Summary Report",
        "",
        "### 🎯 Key Performance & Quality Indicators",
        "",
        f"- **Total Candidates Recalled (Recall Total)**: **{recall_total}**",
        f"- **Backlog Compression Ratio**: **{compression_ratio:.2%}** ({pruned_total}/{recall_total} candidates kept)",
        f"- **Mean Evidence Completeness Score**: **{mean_evidence_score:.1f} / 100**",
        f"- **Queue Backlog (Awaiting Triage/Verification)**: **{backlog_count}**",
        "",
        "---",
        "",
        "### 📊 Detailed Stage Metrics Execution Log",
        "",
        "| Stage | Metric Name | Metric Value |",
        "| --- | --- | --- |"
    ]
    
    for stage, stage_metrics in sorted(metrics.items()):
        for metric_name, value in sorted(stage_metrics.items()):
            val_str = f"{value:.4f}" if isinstance(value, float) else str(value)
            lines.append(f"| {stage} | {metric_name} | {val_str} |")
            
    return "\n".join(lines)
