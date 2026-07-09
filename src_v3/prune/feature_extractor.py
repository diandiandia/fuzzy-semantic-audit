import os
import re
from typing import Dict, Any, List
from src_v3.core.models import CandidateRecord, IRNode
from src_v3.storage.ir_store import IRStore

def extract_features(
    workspace_dir: str, 
    candidate: CandidateRecord, 
    ir_store: IRStore
) -> Dict[str, float]:
    """
    Extracts characteristic characteristic scores (range 0.0 - 1.0) for a candidate,
    satisfying V3 static pruning requirements.
    """
    features = {
        "signal_score": 0.5,
        "semantic_similarity_score": min(1.0, candidate.priority_score / 100.0),
        "reachability_score": 0.1,
        "guard_conflict_score": 1.0,
        "framework_risk_score": 0.3,
        "code_quality_score": 0.8,
        "path_relevance_score": 0.5,
        "parameter_propagation_score": 0.2,
        "path_decay_factor": 1.0
    }
    
    # 1. Vendor/Docs/Generated/Test/Mock path decay factor calculation
    path_lower = candidate.file.lower()
    decay_factor = 1.0
    decay_patterns = {
        "vendor": 0.2,
        "node_modules": 0.1,
        "docs": 0.3,
        "generated": 0.3,
        "test": 0.4,
        "mock": 0.4,
        "fixture": 0.3,
        "setup": 0.5
    }
    for pattern, weight in decay_patterns.items():
        if pattern in path_lower:
            decay_factor = min(decay_factor, weight)
    features["path_decay_factor"] = decay_factor
    
    # 2. Path relevance based on high-risk folders
    is_risk_path = False
    risk_patterns = ["api", "auth", "controller", "route", "security", "core", "main", "src"]
    for rp in risk_patterns:
        if rp in path_lower:
            is_risk_path = True
            break
    features["path_relevance_score"] = 1.0 if is_risk_path else 0.5

    # 3. Recall signal intensity
    if "framework" in candidate.recall_sources or "rule" in candidate.recall_sources:
        features["signal_score"] = 1.0
    elif "vector" in candidate.recall_sources:
        features["signal_score"] = max(0.5, features["semantic_similarity_score"])
        
    # Locate target symbol node in call graph
    node_id = f"sym_{candidate.file.replace('/', '_')}_{candidate.symbol}_{candidate.span['start']}_{candidate.span['end']}"
    sn = ir_store.get_node_by_id(node_id)
    
    if not sn:
        for fs in ir_store.get_symbols_by_file(candidate.file):
            if fs.symbol == candidate.symbol:
                sn = fs
                break
                
    if sn:
        # A. Code quality score
        features["code_quality_score"] = sn.attributes.get("code_density", 0.8)
        
        # B. Call graph BFS for reachability and framework relevance
        edges = ir_store.get_edges()
        caller_map = {}
        for edge in edges:
            if edge.kind == "call":
                caller_map.setdefault(edge.dst_node_id, []).append(edge.src_node_id)
                
        queue = [(sn.node_id, 0)]
        visited = {sn.node_id}
        
        reached_entrypoint = False
        min_depth = 999
        resource_count = 0
        guard_count = 0
        state_count = 0
        
        # Direct check on candidate itself
        if "framework_entrypoint" in sn.attributes:
            reached_entrypoint = True
            min_depth = 0
        if "framework_resource" in sn.attributes:
            resource_count += 2
        if "framework_guard" in sn.attributes:
            guard_count += 2
        if "framework_state_transition" in sn.attributes:
            state_count += 2
            
        while queue:
            curr_id, depth = queue.pop(0)
            if depth >= 3:
                continue
                
            curr_node = ir_store.get_node_by_id(curr_id)
            if curr_node:
                if "framework_entrypoint" in curr_node.attributes:
                    reached_entrypoint = True
                    min_depth = min(min_depth, depth)
                if "framework_resource" in curr_node.attributes:
                    resource_count += 1
                if "framework_guard" in curr_node.attributes:
                    guard_count += 1
                if "framework_state_transition" in curr_node.attributes:
                    state_count += 1
                    
            callers = caller_map.get(curr_id, [])
            for c_id in callers:
                if c_id not in visited:
                    visited.add(c_id)
                    queue.append((c_id, depth + 1))
                    
        # Reachability from public entrypoint
        if reached_entrypoint:
            features["reachability_score"] = 1.0 / (min_depth + 1)
            
        # Transitive framework relevance
        features["framework_risk_score"] = min(1.0, 0.3 + 0.2 * resource_count + 0.2 * state_count)
        
        # Guard conflict score: unguarded represents high risk (1.0), guarded represents low risk (0.0)
        features["guard_conflict_score"] = max(0.0, 1.0 - 0.3 * guard_count)
        
        # C. Parameter propagation approximation
        # Check if parameter signature or method body uses common input identifiers
        symbol_body = sn.attributes.get("symbol_body", "").lower()
        input_keywords = ["req", "request", "param", "body", "arg", "data", "payload", "input", "user_id", "query"]
        param_score = 0.2
        for kw in input_keywords:
            if kw in symbol_body[:200]:
                param_score += 0.2
            if kw in candidate.symbol.lower():
                param_score += 0.3
        features["parameter_propagation_score"] = min(1.0, param_score)
        
    return features
