import os
from typing import List, Dict, Any
from src_v2.core.models import LanguageShard, AuditTrack, CandidateRecord, Span
from src_v2.plugins.base import LanguagePlugin
from src_v2.integrations.codegraph_client import find_usages_enclosing_functions
from src_v2.core.candidate_registry import make_candidate_id

TRACK_SENSITIVE_SYMBOLS: Dict[str, List[str]] = {
    "injection": ["eval", "system", "subprocess", "exec", "popen", "sh"],
    "authz": ["login", "authorize", "authenticate", "permission", "isAdmin", "roles"],
    "resource_access": ["db", "query", "database", "select", "connect", "cursor", "execute"],
    "filesystem_boundary": ["open", "read_file", "write_file", "file_path", "path"]
}

def run(
    repo_path: str,
    shard: LanguageShard,
    track: AuditTrack,
    plugin: LanguagePlugin
) -> List[CandidateRecord]:
    """Run callgraph-based recall scanner by looking up callers of track-sensitive APIs."""
    candidates = []
    symbols = TRACK_SENSITIVE_SYMBOLS.get(track.track_id, [])
    if not symbols:
        return candidates
        
    for sym in symbols:
        try:
            usages = find_usages_enclosing_functions(sym, repo_path, limit=20)
            for u in usages:
                file_rel = u["file"]
                
                # Check if file belongs to this shard
                from src_v2.recall.rule_recall import glob_to_regex
                regexes = [glob_to_regex(p) for p in shard.paths]
                match_path = file_rel.replace('\\', '/')
                is_in_shard = False
                for rx in regexes:
                    if rx.match(match_path):
                        is_in_shard = True
                        break
                if not is_in_shard:
                    continue
                    
                symbol_name = u["name"]
                start_line = u["line"]
                end_line = u["line"]
                
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
                    matched_rules=[f"graph.callchain.{sym}"],
                    recall_sources=["graph"],
                    priority=75,
                    status="recalled"
                )
                candidates.append(cand)
        except Exception:
            pass
            
    return candidates
