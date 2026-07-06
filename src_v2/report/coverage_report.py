import os
import json
from datetime import datetime, timezone
from typing import List, Dict, Tuple
from src_v2.core.models import AuditPlan, CandidateRecord
from src_v2.core.plan_io import load_plan
from src_v2.core.candidate_registry import load_candidates
from src_v2.core.queue_store import load_queue

def generate_coverage_report(
    plan_path: str, 
    registry_path: str, 
    queue_dir: str, 
    output_path: str
) -> str:
    """Generate coverage_report.md based on plan, registry, and queues."""
    plan = load_plan(plan_path)
    candidates = load_candidates(registry_path)
    
    # 1. Run Summary
    total_shards = len(plan.language_shards)
    total_tracks = len(plan.audit_tracks)
    total_candidates = len(candidates)
    
    # Status breakdown
    status_counts = {
        "verified": 0,
        "needs_review": 0,
        "false_positive": 0,
        "deferred": 0,
        "error": 0,
        "discovered": 0,
        "indexed": 0,
        "recalled": 0,
        "normalized": 0,
        "queued_for_verify": 0,
        "verifying": 0
    }
    for c in candidates:
        status_counts[c.status] = status_counts.get(c.status, 0) + 1
        
    unfinished_candidates = sum(
        status_counts[s] for s in [
            "discovered", "indexed", "recalled", "normalized", 
            "queued_for_verify", "verifying", "deferred", "error"
        ]
    )

    # 2. Shard Coverage
    shard_counts: Dict[str, int] = {shard.shard_id: 0 for shard in plan.language_shards}
    shard_languages = {shard.shard_id: shard.lang for shard in plan.language_shards}
    for c in candidates:
        if c.shard_id in shard_counts:
            shard_counts[c.shard_id] += 1
        else:
            shard_counts[c.shard_id] = 1

    # 3. Track Coverage
    track_counts: Dict[str, int] = {track.track_id: 0 for track in plan.audit_tracks}
    track_titles = {track.track_id: track.title for track in plan.audit_tracks}
    for c in candidates:
        for track in c.source_tracks:
            if track in track_counts:
                track_counts[track] += 1
            else:
                track_counts[track] = 1

    # 4. Zero Recall Pairs
    # Any combination of shard and track with 0 candidates is a zero recall pair
    zero_recall_pairs: List[Tuple[str, str]] = []
    # Build maps
    shard_track_candidates: Dict[Tuple[str, str], int] = {}
    for c in candidates:
        for track in c.source_tracks:
            pair = (c.shard_id, track)
            shard_track_candidates[pair] = shard_track_candidates.get(pair, 0) + 1

    for shard in plan.language_shards:
        for track in plan.audit_tracks:
            pair = (shard.shard_id, track.track_id)
            if shard_track_candidates.get(pair, 0) == 0:
                zero_recall_pairs.append((shard.shard_id, track.track_id))

    # 5. Queue Status
    verify_now_queue = load_queue(queue_dir, "verify_now")
    deferred_queue = load_queue(queue_dir, "deferred")
    manual_review_queue = load_queue(queue_dir, "manual_review")

    # Load and parse event log for phase durations
    workspace_dir = os.path.dirname(plan_path)
    event_log_path = os.path.join(workspace_dir, "event_log.jsonl")
    stage_durations = {}
    stage_starts = {}
    
    if os.path.exists(event_log_path):
        try:
            with open(event_log_path, "r", encoding="utf-8") as f:
                for line in f:
                    if line.strip():
                        event = json.loads(line)
                        stage = event.get("stage")
                        ev_type = event.get("event_type")
                        ts_str = event.get("timestamp")
                        
                        if not stage or not ts_str:
                            continue
                            
                        ts = datetime.fromisoformat(ts_str.replace("Z", "+00:00"))
                        
                        if ev_type == "stage_start":
                            stage_starts[stage] = ts
                        elif ev_type == "stage_end":
                            start_ts = stage_starts.get(stage)
                            if start_ts:
                                diff = (ts - start_ts).total_seconds()
                                stage_durations[stage] = diff
        except Exception:
            pass

    # 6. Errors list
    error_candidates = [c for c in candidates if c.status == "error"]

    # Generate Markdown
    md = []
    md.append("# Coverage Report\n")
    
    md.append("## Run Summary\n")
    md.append(f"- **Total Shards**: {total_shards}")
    md.append(f"- **Total Tracks**: {total_tracks}")
    md.append(f"- **Total Candidates Recalled**: {total_candidates}")
    md.append(f"- **Unfinished Candidates**: {unfinished_candidates}")
    md.append("\n### Candidate Status Breakdown")
    md.append("| Status | Count | Description |")
    md.append("|---|---|---|")
    md.append(f"| `verified` | {status_counts['verified']} | Confirmed vulnerabilities with reachability and exploitability |")
    md.append(f"| `needs_review` | {status_counts['needs_review']} | Suspicious findings requiring manual review |")
    md.append(f"| `false_positive` | {status_counts['false_positive']} | Explicitly disproven candidates |")
    md.append(f"| `deferred` | {status_counts['deferred']} | Postponed due to budget or schedule |")
    md.append(f"| `error` | {status_counts['error']} | Verification or processing failures |")
    md.append(f"| `queued_for_verify` | {status_counts['queued_for_verify']} | Waiting in verify queue |")
    md.append(f"| `verifying` | {status_counts['verifying']} | Currently being processed |")
    md.append(f"| Other Intermediate | {sum(status_counts[s] for s in ['discovered', 'indexed', 'recalled', 'normalized'])} | Discovered, indexed, recalled, or normalized candidates |")
    md.append("\n")

    md.append("## Shard Coverage\n")
    md.append("| Shard ID | Language | Candidates Recalled |")
    md.append("|---|---|---|")
    for shard in plan.language_shards:
        md.append(f"| `{shard.shard_id}` | {shard.lang} | {shard_counts.get(shard.shard_id, 0)} |")
    md.append("\n")

    md.append("## Track Coverage\n")
    md.append("| Track ID | Track Name | Candidates Recalled |")
    md.append("|---|---|---|")
    for track in plan.audit_tracks:
        md.append(f"| `{track.track_id}` | {track.title} | {track_counts.get(track.track_id, 0)} |")
    md.append("\n")

    md.append("## Candidate Status\n")
    md.append(f"- **Verified**: {status_counts['verified']}")
    md.append(f"- **Needs Review**: {status_counts['needs_review']}")
    md.append(f"- **False Positive**: {status_counts['false_positive']}")
    md.append(f"- **Deferred**: {status_counts['deferred']}")
    md.append(f"- **Error**: {status_counts['error']}")
    md.append("\n")

    md.append("## Zero Recall Pairs\n")
    if zero_recall_pairs:
        md.append("The following shard and track combinations did not recall any candidates:")
        md.append("| Shard ID | Track ID |")
        md.append("|---|---|")
        for shard_id, track_id in zero_recall_pairs:
            md.append(f"| `{shard_id}` | `{track_id}` |")
    else:
        md.append("No zero-recall pairs! All shards and tracks had at least one candidate recalled.")
    md.append("\n")

    md.append("## Queue Backlogs\n")
    md.append(f"- **Verify Now Queue (`verify_now`) Backlog**: {len(verify_now_queue)} candidate(s)")
    md.append(f"- **Deferred Queue (`deferred`) Backlog**: {len(deferred_queue)} candidate(s)")
    md.append(f"- **Manual Review Queue (`manual_review`) Backlog**: {len(manual_review_queue)} candidate(s)")
    md.append("\n")

    md.append("## Deferred Queue Details\n")
    md.append(f"- **Total Candidates Deferred**: {len(deferred_queue)}")
    if deferred_queue:
        md.append("\nList of deferred candidate IDs:")
        for cid in deferred_queue:
            md.append(f"- `{cid}`")
    md.append("\n")

    md.append("## Phase Execution Durations\n")
    md.append("| Phase | Duration (seconds) | Status |")
    md.append("|---|---|---|")
    stages_list = ["inventory", "index", "recall", "triage", "report"]
    for s in stages_list:
        dur = stage_durations.get(s)
        if dur is not None:
            md.append(f"| `{s}` | {dur:.2f}s | Completed |")
        elif s in stage_starts:
            if s == "report":
                diff = (datetime.now(timezone.utc) - stage_starts[s]).total_seconds()
                md.append(f"| `{s}` | {diff:.2f}s | Completed |")
            else:
                md.append(f"| `{s}` | N/A | In Progress / Interrupted |")
        else:
            md.append(f"| `{s}` | N/A | Not Started |")
    md.append("\n")

    md.append("## Language Shards Status\n")
    md.append("| Shard ID | Language | Status | Paths / Match Patterns |")
    md.append("|---|---|---|---|")
    for shard in plan.language_shards:
        paths_str = ", ".join(shard.paths[:3]) + ("..." if len(shard.paths) > 3 else "")
        md.append(f"| `{shard.shard_id}` | `{shard.lang}` | `{shard.status}` | `{paths_str}` |")
    md.append("\n")

    md.append("## Errors\n")
    md.append(f"- **Total Candidate Errors**: {len(error_candidates)}")
    if error_candidates:
        md.append("\n| Candidate ID | File | Symbol |")
        md.append("|---|---|---|")
        for ec in error_candidates:
            md.append(f"| `{ec.candidate_id}` | `{ec.file}` | `{ec.symbol}` |")
    md.append("\n")

    report_content = "\n".join(md)
    
    dir_name = os.path.dirname(output_path)
    if dir_name:
        os.makedirs(dir_name, exist_ok=True)
        
    with open(output_path, "w", encoding="utf-8") as f:
        f.write(report_content)
        
    return report_content
