import os
import re
import yaml
from typing import List, Dict, Any
from src_v3.core.models import LanguageShard, CandidateRecord
from src_v3.storage.ir_store import IRStore
from src_v3.core.plan_io import load_plan
from src_v3.core.provider_registry import resolve_parser

TRACK_KEYWORDS = {
    "authz": ["auth", "login", "permission", "role", "allow", "deny", "check_access", "privilege", "owner"],
    "state_machine": ["status", "state", "transition", "update_status", "step", "phase", "stage"],
    "resource_access": ["db", "query", "file", "read", "write", "socket", "connection", "http"],
    "injection": ["exec", "eval", "system", "command", "sql", "query", "run", "subprocess"],
    "input_validation": ["validate", "check", "sanitize", "clean", "parse", "filter", "regex"],
    "deserialization": ["serialize", "deserialize", "load", "dump", "pickle", "marshal", "xml"],
    "memory_safety": ["malloc", "free", "alloc", "pointer", "buffer", "unsafe", "overflow"],
    "concurrency": ["thread", "lock", "mutex", "sync", "race", "concurrent", "parallel", "atomic"],
    "crypto": ["encrypt", "decrypt", "cipher", "hash", "md5", "sha", "aes", "key", "password"],
    "filesystem_boundary": ["path", "filepath", "directory", "dir", "join", "open", "absolute", "relative"]
}

def load_declarative_rules(rules_dir: str, track: str) -> List[Dict[str, Any]]:
    """
    Loads declarative YAML rules for a given track from the rules directory.
    """
    rules_path = os.path.join(rules_dir, "rules.yaml")
    if not os.path.exists(rules_path):
        rules_path = os.path.join(rules_dir, f"{track}.yaml")
        
    if not os.path.exists(rules_path):
        return []
        
    try:
        with open(rules_path, 'r', encoding='utf-8') as f:
            data = yaml.safe_load(f)
            return data.get("rules", [])
    except Exception:
        return []

def recall_by_rules(workspace_dir: str, shard: LanguageShard, track: str) -> List[CandidateRecord]:
    """
    Recalls candidates using declarative YAML rules (supporting AST queries)
    and falls back to keyword matching.
    """
    ir_store = IRStore(workspace_dir)
    candidates = []
    
    # Load plan configurations and resolve the true repository root path
    plan = load_plan(os.path.join(workspace_dir, "audit_plan.json"))
    if not plan or not plan.repo_path:
        raise ValueError("Cannot resolve repository root: audit plan missing or invalid repo_path")
    config = plan.summary.get("config", {})
    repo_root = os.path.abspath(plan.repo_path)
        
    # 1. Resolve tool-bundled rules directory (from versioned tracks pack)
    from src_v3.packs.tracks import AUDIT_TRACKS
    tool_rules_dir = AUDIT_TRACKS.get(track, "")
    
    # 2. Resolve project-specific rules directory
    repo_rules_dir = os.path.join(repo_root, "rules")
    
    # Load rules from both locations and combine them (deduplicated by rule ID)
    rules_list = []
    seen_rule_ids = set()
    for r_dir in [tool_rules_dir, repo_rules_dir]:
        if os.path.exists(r_dir):
            for r in load_declarative_rules(r_dir, track):
                r_id = r.get("id")
                if r_id and r_id not in seen_rule_ids:
                    seen_rule_ids.add(r_id)
                    rules_list.append(r)
                    
    rules = rules_list
    shard_files = set(shard.paths)
        
    parser_prov = resolve_parser(shard.lang, config)
    
    if rules:
        is_ts = (not parser_prov.use_fallback)
        
        for rule in rules:
            rule_id = rule.get("id")
            pattern_str = rule.get("pattern")
            required_kind = rule.get("kind")
            ast_query_str = rule.get("ast_query")
            
            if is_ts and ast_query_str:
                # 1. Use real Tree-sitter AST queries over raw files
                for rel_file in shard.paths:
                    abs_file = os.path.join(repo_root, rel_file)
                    if not os.path.exists(abs_file):
                        continue
                    try:
                        parsed = parser_prov.parse_file(abs_file, shard.lang)
                        if parsed.get("mode") == "tree_sitter":
                            tree = parsed["tree"]
                            ts_lang = parsed["ts_lang"]
                            content = parsed["content"]
                            query = ts_lang.query(ast_query_str)
                            captures = query.captures(tree.root_node)
                            for node, tag in captures:
                                start_line = node.start_point[0] + 1
                                end_line = node.end_point[0] + 1
                                name_bytes = content.encode('utf-8')[node.start_byte:node.end_byte]
                                symbol_name = name_bytes.decode('utf-8', errors='ignore')
                                
                                # Apply name pattern filter
                                if pattern_str and not re.search(pattern_str, symbol_name):
                                    continue
                                    
                                candidates.append(CandidateRecord(
                                    candidate_id="",
                                    identity_key="",
                                    shard_id=shard.shard_id,
                                    lang=shard.lang,
                                    file=rel_file,
                                    symbol=symbol_name,
                                    span={"start": start_line, "end": end_line},
                                    source_tracks=[track],
                                    matched_rules=[rule_id],
                                    recall_sources=["rule"],
                                    provider_trace=[parser_prov.provider_name],
                                    priority_score=70.0,
                                    candidate_capability=shard.capability,
                                    status="discovered"
                                ))
                    except Exception:
                        pass
            else:
                # 2. Use Symbol index based AST queries (AST symbol kind + Name Pattern matching)
                for sn in ir_store.iter_symbol_nodes():
                    if sn.file not in shard_files:
                        continue
                        
                    if required_kind and sn.attributes.get("symbol_kind") != required_kind:
                        continue
                        
                    if pattern_str and re.search(pattern_str, sn.symbol):
                        candidates.append(CandidateRecord(
                            candidate_id="",
                            identity_key="",
                            shard_id=shard.shard_id,
                            lang=shard.lang,
                            file=sn.file,
                            symbol=sn.symbol,
                            span=sn.span,
                            source_tracks=[track],
                            matched_rules=[rule_id],
                            recall_sources=["rule"],
                            provider_trace=[parser_prov.provider_name],
                            priority_score=65.0,
                            candidate_capability=shard.capability,
                            status="discovered"
                        ))
    else:
        # 3. Keyword Fallback
        keywords = TRACK_KEYWORDS.get(track, [])
        if not keywords:
            return []
            
        pattern = re.compile(r'(?i)(' + '|'.join(keywords) + ')')
        for sn in ir_store.iter_symbol_nodes():
            if sn.file not in shard_files:
                continue
                
            if pattern.search(sn.symbol):
                candidates.append(CandidateRecord(
                    candidate_id="",
                    identity_key="",
                    shard_id=shard.shard_id,
                    lang=shard.lang,
                    file=sn.file,
                    symbol=sn.symbol,
                    span=sn.span,
                    source_tracks=[track],
                    matched_rules=[f"rule.{track}.keyword_match"],
                    recall_sources=["rule"],
                    provider_trace=[parser_prov.provider_name],
                    priority_score=60.0,
                    candidate_capability=shard.capability,
                    status="discovered"
                ))
                
    return candidates
