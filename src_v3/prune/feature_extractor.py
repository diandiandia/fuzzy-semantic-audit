import os
from typing import Dict, Any, List
from src_v3.core.models import CandidateRecord, IRNode
from src_v3.storage.ir_store import IRStore

def extract_features(
    workspace_dir: str, 
    candidate: CandidateRecord, 
    ir_store: IRStore
) -> Dict[str, float]:
    """
    Extracts 6 characteristic scores (range 0.0 - 1.0) for a candidate.
    """
    features = {
        "signal_score": 0.5,
        "semantic_similarity_score": min(1.0, candidate.priority_score / 100.0),
        "reachability_score": 0.2,
        "guard_conflict_score": 1.0,
        "framework_risk_score": 0.5,
        "code_quality_score": 0.8
    }
    
    # 1. Signal score based on recall channels
    if "framework" in candidate.recall_sources or "rule" in candidate.recall_sources:
        features["signal_score"] = 1.0
    elif "vector" in candidate.recall_sources:
        features["signal_score"] = max(0.5, features["semantic_similarity_score"])
        
    # Locate target symbol node
    node_id = f"sym_{candidate.file.replace('/', '_')}_{candidate.symbol}_{candidate.span['start']}_{candidate.span['end']}"
    sn = ir_store.get_node_by_id(node_id)
    
    if not sn:
        # Fallback search by symbol and file
        for fs in ir_store.get_symbols_by_file(candidate.file):
            if fs.symbol == candidate.symbol:
                sn = fs
                break
                
    if sn:
        # A. Code quality score from code density
        features["code_quality_score"] = sn.attributes.get("code_density", 0.8)
        
        # B. Framework risk score from tags
        if "framework_resource" in sn.attributes:
            features["framework_risk_score"] = 1.0
        elif "framework_entrypoint" in sn.attributes:
            features["framework_risk_score"] = 0.9
            
        # C. Reachability & Guard checks via Call Graph BFS
        # Find paths of caller calling callee up to depth 3
        # We want to see if any caller reaches an entrypoint, or if there is a guard
        edges = ir_store.get_edges()
        
        # Build Caller map: callee_id -> list of caller_ids
        caller_map = {}
        for edge in edges:
            if edge.kind == "call":
                caller_map.setdefault(edge.dst_node_id, []).append(edge.src_node_id)
                
        # BFS up
        queue = [(sn.node_id, 0)]
        visited = {sn.node_id}
        
        reached_entrypoint = False
        guarded = False
        min_depth = 999
        
        # Direct check on candidate itself
        if "framework_entrypoint" in sn.attributes:
            reached_entrypoint = True
            min_depth = 0
        if "framework_guard" in sn.attributes:
            guarded = True
            
        while queue:
            curr_id, depth = queue.pop(0)
            if depth >= 3:
                continue
                
            curr_node = ir_store.get_node_by_id(curr_id)
            if curr_node:
                if "framework_entrypoint" in curr_node.attributes:
                    reached_entrypoint = True
                    min_depth = min(min_depth, depth)
                if "framework_guard" in curr_node.attributes:
                    guarded = True
                    
            callers = caller_map.get(curr_id, [])
            for c_id in callers:
                if c_id not in visited:
                    visited.add(c_id)
                    queue.append((c_id, depth + 1))
                    
        if reached_entrypoint:
            features["reachability_score"] = 1.0 / (min_depth + 1)
        if guarded:
            features["guard_conflict_score"] = 0.2 # Guarded, so less likely to be vulnerable
            
    return features
