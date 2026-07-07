import os
import sys
import json
import argparse
import time
from datetime import datetime, timezone
from src_v2.core.models import AuditPlan, LanguageShard
from src_v2.core.plan_io import load_plan, save_plan
from src_v2.recall.orchestrator import get_plugin
from src_v2.integrations import embedding_index
from src_v2.core.event_log import log_event

def main():
    parser = argparse.ArgumentParser(description="Build embedding index for all active shards.")
    parser.add_argument("--plan", required=True, help="Path to the audit plan JSON file.")
    args = parser.parse_args()

    plan_path = os.path.abspath(args.plan)
    if not os.path.exists(plan_path):
        sys.stderr.write(f"Error: Audit plan file not found at {plan_path}\n")
        sys.exit(1)

    plan = load_plan(plan_path)
    workspace_dir = os.path.dirname(plan_path)
    repo_path = plan.repo_path

    # Log stage start
    log_event(
        workspace_dir=workspace_dir,
        stage="index",
        event_type="stage_start",
        details={"timestamp": datetime.now(timezone.utc).isoformat() + "Z"}
    )

    indexed_count = 0
    t0 = time.time()

    for shard in plan.language_shards:
        if shard.status == "discovered":
            try:
                # 1. Enumerate all symbols in the shard files
                from src_v2.recall.rule_recall import match_glob_patterns
                matched_files = match_glob_patterns(repo_path, shard.paths)
                plugin = get_plugin(shard.lang)
                matched_files = plugin.match_files(matched_files)
                symbols = plugin.enumerate_symbols(repo_path, matched_files)

                # 2. Build records list
                records = []
                for sym in symbols:
                    abs_path = os.path.join(repo_path, sym["file"])
                    text_snippet = ""
                    start_line = sym.get("start", 1)
                    end_line = sym.get("end", start_line)
                    try:
                        with open(abs_path, "r", encoding="utf-8", errors="ignore") as f:
                            lines = f.readlines()
                            start = max(1, start_line)
                            end = min(len(lines), end_line)
                            text_snippet = "".join(lines[start-1:end])
                    except Exception:
                        pass

                    records.append({
                        "id": f"{sym['file']}:{sym['symbol']}:{start_line}:{end_line}",
                        "text": f"{sym['symbol']} in {sym['file']}\n{text_snippet}",
                        "file": sym["file"],
                        "symbol": sym["symbol"],
                        "span": {"start": start_line, "end": end_line}
                    })

                # 3. Build index
                success = embedding_index.build_index(shard.shard_id, workspace_dir, records)

                # 4. Advance status
                if success:
                    shard.status = "indexed"
                else:
                    shard.status = "indexed_fallback"
                indexed_count += 1
                
                log_event(
                    workspace_dir=workspace_dir,
                    stage="index",
                    event_type="shard_indexed",
                    details={"shard_id": shard.shard_id, "symbols_count": len(records)}
                )
            except Exception as e:
                log_event(
                    workspace_dir=workspace_dir,
                    stage="index",
                    event_type="shard_index_error",
                    details={"shard_id": shard.shard_id, "error": str(e)}
                )
                sys.stderr.write(f"Error indexing shard {shard.shard_id}: {str(e)}\n")

    # Save plan with updated shard statuses
    save_plan(plan, plan_path)

    # Log stage end
    elapsed = time.time() - t0
    log_event(
        workspace_dir=workspace_dir,
        stage="index",
        event_type="stage_end",
        details={
            "timestamp": datetime.now(timezone.utc).isoformat() + "Z",
            "duration_seconds": elapsed,
            "indexed_count": indexed_count
        }
    )

    result = {
        "ok": True,
        "indexed_shards": indexed_count,
        "duration_seconds": elapsed
    }
    print(json.dumps(result))

if __name__ == "__main__":
    main()
