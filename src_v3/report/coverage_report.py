import os
from typing import List, Dict, Any
from src_v3.core.models import AuditPlan, CandidateRecord
from src_v3.storage.candidate_store import CandidateStore

def compile_coverage_report(workspace_dir: str, plan: AuditPlan) -> str:
    """
    Generates reports/coverage_report.md summarizing language coverage, fallbacks,
    track statistics, candidate status counts, and queue backlogs.
    """
    manifest = plan.run_manifest
    mode_str = manifest.run_mode if manifest else "unknown"
    cap_str = manifest.run_capability if manifest else "unknown"
    reasons = manifest.degradation_reasons if manifest else []
    
    # Calculate candidate counts
    candidate_store = CandidateStore(workspace_dir)
    all_cands = candidate_store.get_candidates(pruned=False)
    pruned_cands = candidate_store.get_candidates(pruned=True)
    
    recalled_count = len(all_cands)
    pruned_count = len(pruned_cands)
    
    status_counts = {}
    track_counts = {}
    
    for c in pruned_cands:
        status_counts[c.status] = status_counts.get(c.status, 0) + 1
        for track in c.source_tracks:
            track_counts[track] = track_counts.get(track, 0) + 1
            
    # Degradation ratio
    total_shards = len(plan.language_shards)
    degraded_shards = sum(
        1 for s in plan.language_shards 
        if s.status in ["indexed_fallback", "recalled_fallback", "failed"]
    )
    degraded_ratio = degraded_shards / max(1, total_shards)
    
    lines = [
        "# Coverage & Degradation Report",
        f"**Run Mode**: `{mode_str}`",
        f"**Run Capability Level**: `{cap_str}`",
        f"**Degraded Shards Ratio**: `{degraded_ratio:.1%} ({degraded_shards}/{total_shards})`",
        ""
    ]
    
    if reasons:
        lines.append("### Transparent Degradation Reasons")
        for r in reasons:
            lines.append(f"- {r}")
        lines.append("")
        
    # Shards status table
    lines.extend([
        "### Language Shards Status",
        "| Shard ID | Language | Capability | Status | Assigned Providers |",
        "| --- | --- | --- | --- | --- |"
    ])
    
    for shard in plan.language_shards:
        providers_str = ", ".join([f"{k}: {v}" for k, v in shard.provider_set.items()])
        lines.append(f"| {shard.shard_id} | {shard.lang} | {shard.capability} | {shard.status} | {providers_str} |")
    lines.append("")
    
    # Candidates statistics summary
    lines.extend([
        "### Candidate & Queue Backlog Summary",
        f"- **Total Candidates Recalled (Raw)**: {recalled_count}",
        f"- **Total Candidates Kept (Pruned)**: {pruned_count}",
        f"- **Verified Vulnerabilities**: {status_counts.get('verified', 0)}",
        f"- **Needs Manual Review**: {status_counts.get('needs_review', 0)}",
        f"- **False Positives**: {status_counts.get('false_positive', 0)}",
        f"- **Deferred Candidates**: {status_counts.get('deferred', 0)}",
        f"- **Verification Errors**: {status_counts.get('error', 0)}",
        f"- **Queued for Verify Backlog**: {status_counts.get('queued_for_verify', 0) + status_counts.get('verifying', 0)}",
        ""
    ])
    
    # Track statistics table
    lines.extend([
        "### Enabled Tracks Coverage",
        "| Track Name | Candidates Found (Pruned) |",
        "| --- | --- |"
    ])
    for track in plan.audit_tracks:
        count = track_counts.get(track, 0)
        lines.append(f"| {track} | {count} |")
        
    return "\n".join(lines)
