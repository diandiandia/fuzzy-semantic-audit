import os
from typing import List, Dict, Any
from src_v3.core.models import AuditPlan, CandidateRecord
from src_v3.storage.candidate_store import CandidateStore

def compile_coverage_report(workspace_dir: str, plan: AuditPlan) -> str:
    """
    Generates reports/coverage_report.md summarizing language coverage, fallbacks,
    track statistics, candidate status counts, and queue backlogs.
    Uses premium GFM callout alerts, visual progress bars, and beautifully aligned summary tables.
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
    
    status_counts = {
        'verified': 0,
        'needs_review': 0,
        'false_positive': 0,
        'deferred': 0,
        'error': 0,
        'queued_for_verify': 0,
        'verifying': 0
    }
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
    
    # Build visual progress bar for degraded shards (fewer degraded is better/green, so bar represents healthy shards)
    healthy_shards = total_shards - degraded_shards
    bar_len = 15
    filled_len = int(round(bar_len * (healthy_shards / max(1, total_shards))))
    bar_str = "█" * filled_len + "░" * (bar_len - filled_len)
    
    lines = [
        "# 🛡️ Fuzzy Semantic Audit - Coverage & Degradation Report",
        "",
        "> [!IMPORTANT]",
        "> **V3 Execution Summary**",
        f"> - **Run Mode**: `{mode_str.upper()}`",
        f"> - **Run Capability**: `{cap_str}`",
        f"> - **System Integrity Profile**: `[{bar_str}] {healthy_shards}/{total_shards} Healthy Shards ({1.0 - degraded_ratio:.1%})`",
        ""
    ]
    
    if reasons:
        lines.extend([
            "> [!WARNING]",
            "> **Transparent Degradation Reasons Detected**"
        ])
        for r in sorted(reasons):
            lines.append(f"> - ⚠️ {r}")
        lines.append("")
        
    # Shards status table
    lines.extend([
        "## 📁 Language Shards Mapping & Effective Capabilities",
        "",
        "The project has been split into the following autonomous language shards for scanning and cross-referencing:",
        "",
        "| Shard ID | Language | Effective Cap | Status | Assigned Providers & Tooling |",
        "| :--- | :---: | :---: | :---: | :--- |"
    ])
    
    for shard in plan.language_shards:
        status_icon = "🟢"
        if shard.status == "indexed_fallback":
            status_icon = "🟡 fallback"
        elif shard.status == "failed":
            status_icon = "🔴 failed"
            
        providers_str = "<br>".join([f"**{k}**: `{v}`" for k, v in shard.provider_set.items()])
        lines.append(f"| `{shard.shard_id}` | {shard.lang} | `{shard.capability}` | {status_icon} | {providers_str} |")
    lines.append("")
    
    # Candidates statistics summary
    lines.extend([
        "## 📊 Candidate & Verification Queue Metrics",
        "",
        "| Metric | Count | Status Badge | Description / Triage Direction |",
        "| :--- | :---: | :---: | :--- |",
        f"| **Raw Recalled Candidates** | `{recalled_count}` | 📥 Recall | Total candidate matches collected by recall algorithms |",
        f"| **Pruned / Scored Candidates** | `{pruned_count}` | 🔍 Scored | Unique candidates passing static pruning thresholds |",
        f"| **Verified Vulnerabilities** | `{status_counts.get('verified', 0)}` | 🔴 **VULN** | Confirmed security defects by referee triage |",
        f"| **Needs Manual Review** | `{status_counts.get('needs_review', 0)}` | 🟡 **REVIEW** | Indeterminate status, sent to manual review queue |",
        f"| **False Positives** | `{status_counts.get('false_positive', 0)}` | 🟢 **FP** | Confirmed safe paths or blocked by guards |",
        f"| **Deferred Candidates** | `{status_counts.get('deferred', 0)}` | 🔵 **DEFER** | Mismatched capability level or missing backend |",
        f"| **Verification Errors** | `{status_counts.get('error', 0)}` | ⚠️ **ERROR** | Failed to triage due to API or connection issues |",
        f"| **Verification Backlog Queue** | `{status_counts.get('queued_for_verify', 0) + status_counts.get('verifying', 0)}` | ⏱️ Queue | Candidates currently in verification pipeline |",
        ""
    ])
    
    # Track statistics table
    lines.extend([
        "## 🎯 Security Tracks Recall Density",
        "",
        "Analysis of pruned candidates grouped by security audit tracks:",
        "",
        "| Security Track | Unique Candidates | Intensity Indicator |",
        "| :--- | :---: | :--- |"
    ])
    
    if track_counts:
        max_density = max(track_counts.values())
        for track in sorted(track_counts.keys()):
            count = track_counts[track]
            indicator_len = int(round(10 * (count / max_density)))
            indicator = "🔥" * max(1, indicator_len)
            lines.append(f"| `{track}` | `{count}` | {indicator} |")
    else:
        lines.append("| *No active tracks* | `0` | - |")
    lines.append("")
    
    # Capability definitions alert
    lines.extend([
        "> [!NOTE]",
        "> **V3 Capability Levels Definition**:",
        "> - `L0` (Text Only): Simple text search and regex matching (weakest).",
        "> - `L1` (AST Structure): Syntactic symbol definitions and imports.",
        "> - `L2` (Semantic Reference): Exact definitions, references, and callers/callees resolved.",
        "> - `L3` (Deep Audit): Complete multi-hop call graph reachability and guard verification.",
        ""
    ])
    
    return "\n".join(lines)
