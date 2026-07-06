import os
import re
from typing import List, Dict, Any
from src_v2.core.models import LanguageShard, AuditTrack, CandidateRecord, Span
from src_v2.plugins.base import LanguagePlugin
from src_v2.core.candidate_registry import make_identity_key, make_candidate_id
from src_v2.recall.rule_recall import match_glob_patterns

RESOURCE_RELATED_TRACKS = {"authz", "state_machine", "resource_access", "filesystem_boundary"}

def run(
    repo_path: str,
    shard: LanguageShard,
    track: AuditTrack,
    plugin: LanguagePlugin
) -> List[CandidateRecord]:
    """Run resource-access based recall by matching code patterns accessing key resources."""
    candidates = []
    
    # Resource recall only makes sense for resource-related tracks
    if track.track_id not in RESOURCE_RELATED_TRACKS:
        return candidates

    # 1. Match files
    all_files = match_glob_patterns(repo_path, shard.paths)
    matched_files = plugin.match_files(all_files)
    if not matched_files:
        return candidates

    # 2. Get symbols
    symbols = plugin.enumerate_symbols(repo_path, matched_files)
    if not symbols:
        return candidates

    # 3. Get resource signals patterns
    signals = plugin.build_resource_signals()
    if not signals:
        return candidates

    # Compile regexes
    compiled_signals = [re.compile(s) for s in signals]

    for file in matched_files:
        abs_path = os.path.join(repo_path, file)
        if not os.path.exists(abs_path):
            continue
            
        try:
            with open(abs_path, "r", encoding="utf-8", errors="ignore") as f:
                lines = f.readlines()
        except Exception:
            continue

        file_syms = [s for s in symbols if s.get("file") == file or s.get("file") is None]

        for sym in file_syms:
            start = max(1, sym["start"])
            end = min(len(lines), sym["end"])
            
            # Combine lines of this symbol's body
            body_text = "".join(lines[start-1:end])
            
            # Check if it matches any resource signals
            matched_sigs = []
            for sig in compiled_signals:
                if sig.search(body_text):
                    matched_sigs.append(sig.pattern)
            
            if matched_sigs:
                symbol_name = sym["symbol"]
                identity_key = make_identity_key(shard.shard_id, file, symbol_name, start, end)
                cand_id = make_candidate_id(shard.shard_id, file, symbol_name, start, end)
                
                cand = CandidateRecord(
                    candidate_id=cand_id,
                    identity_key=identity_key,
                    shard_id=shard.shard_id,
                    lang=shard.lang,
                    file=file,
                    symbol=symbol_name,
                    span=Span(start=start, end=end),
                    source_tracks=[track.track_id],
                    matched_rules=["generic.resource.access"],
                    recall_sources=["resource"],
                    priority=25, # baseline resource priority
                    status="recalled"
                )
                candidates.append(cand)
                
    return candidates
