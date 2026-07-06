import os
import json
from typing import List, Dict, Any
from src_v2.core.models import LanguageShard, AuditTrack, CandidateRecord, Span
from src_v2.plugins.base import LanguagePlugin
from src_v2.integrations import embedding_index
from src_v2.core.candidate_registry import make_candidate_id

def run(
    repo_path: str,
    shard: LanguageShard,
    track: AuditTrack,
    plugin: LanguagePlugin
) -> List[CandidateRecord]:
    """Run vector semantic recall scanner with automatic index construction."""
    candidates = []
    workspace_dir = os.path.join(repo_path, ".audit_workspace_v2")
    
    # 1. Check if index already exists
    out_dir = os.path.join(workspace_dir, "indices", shard.shard_id)
    meta_path = os.path.join(out_dir, "metadata.json")
    
    if not os.path.exists(meta_path):
        import sys
        sys.stderr.write(f"Warning: Index for shard {shard.shard_id} not found. Returning empty list.\n")
        return []

    # 2. Search index
    # We query the index with track description and title keywords
    query_text = f"{track.title} {track.track_id}"
    results = embedding_index.search(shard.shard_id, workspace_dir, query_text, top_k=5)
    
    # 3. Build CandidateRecords from results
    for r in results:
        file_rel = r["file"]
        symbol_name = r["symbol"]
        span_data = r["span"]
        start_line = span_data["start"]
        end_line = span_data["end"]
        
        cand_id = make_candidate_id(shard.shard_id, file_rel, symbol_name, start_line, end_line)
        cand = CandidateRecord(
            candidate_id=cand_id,
            identity_key=f"{shard.shard_id}|{file_rel}|{symbol_name}|{start_line}|{end_line}",
            shard_id=shard.shard_id,
            lang=shard.lang,
            file=file_rel,
            symbol=symbol_name,
            span=Span(start=start_line, end=end_line),
            source_tracks=[track.track_id],
            matched_rules=["vector.semantic.match"],
            recall_sources=["vector"],
            priority=80, # Vector default priority
            status="recalled"
        )
        candidates.append(cand)
        
    return candidates
