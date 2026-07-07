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

# Cache repository files listing globally to avoid walking large directory structures repeatedly
_repo_files_cache = {}

def get_repo_files(repo_path: str) -> List[str]:
    if repo_path not in _repo_files_cache:
        files_list = []
        for root, dirs, files in os.walk(repo_path):
            if ".git" in root or ".audit_workspace_v2" in root:
                continue
            for file in files:
                full_path = os.path.join(root, file)
                rel_path = os.path.relpath(full_path, repo_path)
                files_list.append(rel_path)
        _repo_files_cache[repo_path] = files_list
    return _repo_files_cache[repo_path]

def match_glob_patterns(repo_path: str, patterns: List[str]) -> List[str]:
    """Find all files in repo_path matching any glob pattern, supporting recursive **."""
    matched_files = []
    # Pre-compile regexes
    regexes = [glob_to_regex(p) for p in patterns]
    
    all_files = get_repo_files(repo_path)
    for rel_path in all_files:
        # Normalize path separators to forward slashes for matching
        match_path = rel_path.replace('\\', '/')
        for rx in regexes:
            if rx.match(match_path):
                matched_files.append(rel_path)
                break
    return matched_files

# Cache file contents globally to avoid reading files repeatedly across tracks
_file_lines_cache = {}

def get_file_lines(abs_path: str) -> List[str]:
    if abs_path not in _file_lines_cache:
        try:
            with open(abs_path, "r", encoding="utf-8", errors="ignore") as f:
                _file_lines_cache[abs_path] = f.readlines()
        except Exception:
            _file_lines_cache[abs_path] = []
    return _file_lines_cache[abs_path]

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
        f = s.get("file")
        if f:
            if f not in file_symbols:
                file_symbols[f] = []
            file_symbols[f].append(s)
            
    fallback_syms = [s for s in symbols if s.get("file") is None]
        
    # We will fetch file contents, check rule regexes, and match enclosing symbols.
    rules = plugin.build_track_rules(track.track_id)
    if not rules:
        return candidates

    for file in matched_files:
        abs_path = os.path.join(repo_path, file)
        if not os.path.exists(abs_path):
            continue
            
        lines = get_file_lines(abs_path)
        if not lines:
            continue

        # Get symbols for this file
        file_syms = file_symbols.get(file, [])
        if fallback_syms:
            file_syms = file_syms + fallback_syms

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
