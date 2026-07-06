import os
import re
import fnmatch
from typing import List, Dict, Any
from src_v2.core.models import LanguageShard, AuditTrack, CandidateRecord, Span
from src_v2.plugins.base import LanguagePlugin
from src_v2.core.candidate_registry import make_identity_key, make_candidate_id

def glob_to_regex(pattern: str) -> re.Pattern:
    """Translate a glob pattern to a compiled regex pattern, supporting recursive **."""
    regex_parts = []
    i, n = 0, len(pattern)
    while i < n:
        char = pattern[i]
        if char == '*':
            if i + 1 < n and pattern[i+1] == '*':
                regex_parts.append('.*')
                i += 2
                if i < n and pattern[i] == '/':
                    regex_parts.append('/?')
                    i += 1
            else:
                regex_parts.append('[^/]*')
                i += 1
        elif char == '?':
            regex_parts.append('[^/]')
            i += 1
        elif char in ('.', '^', '$', '+', '(', ')', '{', '}', '|', '\\'):
            regex_parts.append('\\' + char)
            i += 1
        else:
            regex_parts.append(char)
            i += 1
    return re.compile('^' + ''.join(regex_parts) + '$')

def match_glob_patterns(repo_path: str, patterns: List[str]) -> List[str]:
    """Find all files in repo_path matching any glob pattern, supporting recursive **."""
    matched_files = []
    # Pre-compile regexes
    regexes = [glob_to_regex(p) for p in patterns]
    
    for root, dirs, files in os.walk(repo_path):
        if ".git" in root or ".audit_workspace_v2" in root:
            continue
            
        for file in files:
            full_path = os.path.join(root, file)
            rel_path = os.path.relpath(full_path, repo_path)
            # Normalize path separators to forward slashes for matching
            match_path = rel_path.replace('\\', '/')
            
            for rx in regexes:
                if rx.match(match_path):
                    matched_files.append(rel_path)
                    break
    return matched_files

def run(
    repo_path: str,
    shard: LanguageShard,
    track: AuditTrack,
    plugin: LanguagePlugin
) -> List[CandidateRecord]:
    """Run rule-based recall on shard for track."""
    candidates = []
    
    # 1. Match files
    all_files = match_glob_patterns(repo_path, shard.paths)
    matched_files = plugin.match_files(all_files)
    if not matched_files:
        return candidates

    # 2. Get symbols
    symbols = plugin.enumerate_symbols(repo_path, matched_files)
    # Group symbols by file for quick lookup
    file_symbols: Dict[str, List[Dict[str, Any]]] = {}
    for s in symbols:
        # We need the file name, wait, enumerate_symbols can return file or we can map it
        # Let's assume plugin.enumerate_symbols returns dicts with 'symbol', 'start', 'end' AND 'file' if multi-file
        # Wait, if not, we should have plugin return 'file' in symbol dict.
        # Let's assume symbols are annotated with 'file' or we do it. Let's make sure our plugins return 'file' or we map.
        # In generic plugin, we added symbol to symbols list per file, but did we add 'file'? Let's check!
        # Ah, in generic.py line 78:
        # symbols.append({"symbol": name, "start": line_num, "end": end_line})
        # Wait, we missed adding 'file' in generic.py! Let's check:
        # Ah, yes. It was:
        # symbols.append({"symbol": name, "start": line_num, "end": end_line})
        # Let's make sure it contains "file": file in generic.py as well. We'll fix generic.py.
        # But first, let's write rule_recall.py assuming it has "file".
        pass
        
    # We will fetch file contents, check rule regexes, and match enclosing symbols.
    rules = plugin.build_track_rules(track.track_id)
    if not rules:
        return candidates

    for file in matched_files:
        abs_path = os.path.join(repo_path, file)
        if not os.path.exists(abs_path):
            continue
            
        try:
            with open(abs_path, "r", encoding="utf-8", errors="ignore") as f:
                lines = f.readlines()
        except Exception:
            continue

        # Get symbols for this file
        file_syms = [s for s in symbols if s.get("file") == file or s.get("file") is None] # fallback

        for idx, line in enumerate(lines):
            line_no = idx + 1
            for rule in rules:
                pat = rule.get("pattern")
                if not pat:
                    continue
                    
                # Search pattern
                if re.search(pat, line):
                    # Found a match! Locate enclosing symbol
                    enclosing_sym = None
                    for s in file_syms:
                        if s["start"] <= line_no <= s["end"]:
                            enclosing_sym = s
                            break
                            
                    symbol_name = enclosing_sym["symbol"] if enclosing_sym else "file_level_global"
                    start_line = enclosing_sym["start"] if enclosing_sym else max(1, line_no - 10)
                    end_line = enclosing_sym["end"] if enclosing_sym else min(len(lines), line_no + 10)
                    
                    # Create CandidateRecord
                    priority = rule.get("priority", 20)
                    
                    identity_key = make_identity_key(shard.shard_id, file, symbol_name, start_line, end_line)
                    cand_id = make_candidate_id(shard.shard_id, file, symbol_name, start_line, end_line)
                    
                    cand = CandidateRecord(
                        candidate_id=cand_id,
                        identity_key=identity_key,
                        shard_id=shard.shard_id,
                        lang=shard.lang,
                        file=file,
                        symbol=symbol_name,
                        span=Span(start=start_line, end=end_line),
                        source_tracks=[track.track_id],
                        matched_rules=[rule["rule_id"]],
                        recall_sources=["rule"],
                        priority=priority,
                        status="recalled"
                    )
                    candidates.append(cand)
                    
    return candidates
