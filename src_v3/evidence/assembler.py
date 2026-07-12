import os
from typing import List, Dict, Any, Optional
from src_v3.core.models import CandidateRecord, EvidenceBundle, IRNode
from src_v3.storage.ir_store import IRStore
from src_v3.evidence.completeness import calculate_completeness_score, determine_evidence_gaps

def get_node_source(repo_path: str, node: IRNode) -> str:
    """
    Slices the source code of a node from the file on disk.
    """
    abs_path = os.path.join(repo_path, node.file)
    if not os.path.exists(abs_path):
        return ""
    try:
        with open(abs_path, 'r', encoding='utf-8', errors='ignore') as f:
            lines = f.readlines()
        start = max(0, node.span["start"] - 1)
        end = min(len(lines), node.span["end"])
        return "".join(lines[start:end])
    except Exception:
        return ""

def assemble_evidence(
    workspace_dir: str, 
    repo_path: str, 
    candidate: CandidateRecord, 
    ir_store: IRStore
) -> EvidenceBundle:
    """
    Assembles a complete, structured EvidenceBundle for a candidate.
    """
    # 1. Locate candidate node in IR
    node_id = f"sym_{candidate.file.replace('/', '_')}_{candidate.symbol}_{candidate.span['start']}_{candidate.span['end']}"
    sn = ir_store.get_node_by_id(node_id)
    if not sn:
        for fs in ir_store.get_symbols_by_file(candidate.file):
            if fs.symbol == candidate.symbol:
                sn = fs
                break
                
    if not sn:
        # Return base bundle if symbol node isn't found
        return EvidenceBundle(
            candidate_id=candidate.candidate_id,
            symbol_body="",
            evidence_completeness_score=10
        )
        
    symbol_body = get_node_source(repo_path, sn)
    
    # Load BFS depth limits from track configuration
    from src_v3.packs.tracks import load_track_pack
    track = candidate.source_tracks[0] if candidate.source_tracks else "generic"
    track_pack = load_track_pack(track)
    max_bfs_depth_up = track_pack.get("evidence_bfs_depth_up", 5)
    max_bfs_depth_down = track_pack.get("evidence_bfs_depth_down", 3)
    
    # Caller/Callee maps
    caller_map = ir_store.get_caller_map()
    callee_map = ir_store.get_callee_map()
            
    # Gather immediate callers
    caller_chain = []
    immediate_caller_ids = caller_map.get(sn.node_id, [])
    for cid in immediate_caller_ids:
        c_node = ir_store.get_node_by_id(cid)
        if c_node:
            caller_chain.append({
                "symbol": c_node.symbol,
                "file": c_node.file,
                "span": c_node.span
            })
            
    # Gather immediate callees
    callee_chain = []
    immediate_callee_ids = callee_map.get(sn.node_id, [])
    for cid in immediate_callee_ids:
        c_node = ir_store.get_node_by_id(cid)
        if c_node:
            callee_chain.append({
                "symbol": c_node.symbol,
                "file": c_node.file,
                "span": c_node.span
            })
            
    # BFS up to find entrypoints, guards, and transitions
    upstream_entrypoints = []
    guard_snippets = []
    state_transition_snippets = []
    resource_snippets = []
    
    # Check if candidate itself has guard/resource
    if "framework_guard" in sn.attributes:
        guard_snippets.append({
            "symbol": sn.symbol,
            "file": sn.file,
            "guard_kind": sn.attributes["framework_guard"]["guard_kind"],
            "code": symbol_body
        })
    if "framework_resource" in sn.attributes:
        resource_snippets.append({
            "symbol": sn.symbol,
            "file": sn.file,
            "resource_type": sn.attributes["framework_resource"]["resource_type"],
            "code": symbol_body
        })
    if "framework_state_transition" in sn.attributes:
        state_transition_snippets.append({
            "symbol": sn.symbol,
            "file": sn.file,
            "state_field": sn.attributes["framework_state_transition"]["state_field"]
        })
        
    # BFS up
    queue = [(sn.node_id, 0)]
    visited = {sn.node_id}
    
    while queue:
        curr_id, depth = queue.pop(0)
        if depth >= max_bfs_depth_up:
            continue
            
        curr_node = ir_store.get_node_by_id(curr_id)
        if curr_node and curr_id != sn.node_id:
            # Check entrypoints
            if "framework_entrypoint" in curr_node.attributes:
                ep_attr = curr_node.attributes["framework_entrypoint"]
                upstream_entrypoints.append({
                    "node_id": curr_node.node_id,
                    "symbol": curr_node.symbol,
                    "file": curr_node.file,
                    "route": ep_attr.get("route"),
                    "code": get_node_source(repo_path, curr_node)
                })
            # Check guards
            if "framework_guard" in curr_node.attributes:
                gd_attr = curr_node.attributes["framework_guard"]
                guard_snippets.append({
                    "symbol": curr_node.symbol,
                    "file": curr_node.file,
                    "guard_kind": gd_attr.get("guard_kind"),
                    "code": get_node_source(repo_path, curr_node)
                })
            # Check state transitions
            if "framework_state_transition" in curr_node.attributes:
                st_attr = curr_node.attributes["framework_state_transition"]
                state_transition_snippets.append({
                    "symbol": curr_node.symbol,
                    "file": curr_node.file,
                    "state_field": st_attr.get("state_field")
                })
                
        # Move up the call graph
        callers = caller_map.get(curr_id, [])
        for c_id in callers:
            if c_id not in visited:
                visited.add(c_id)
                queue.append((c_id, depth + 1))
                
    # BFS down to find resource accesses (databases, files) called by this candidate
    queue_down = [(sn.node_id, 0)]
    visited_down = {sn.node_id}
    while queue_down:
        curr_id, depth = queue_down.pop(0)
        if depth >= max_bfs_depth_down:
            continue
            
        curr_node = ir_store.get_node_by_id(curr_id)
        if curr_node and curr_id != sn.node_id:
            if "framework_resource" in curr_node.attributes:
                res_attr = curr_node.attributes["framework_resource"]
                resource_snippets.append({
                    "symbol": curr_node.symbol,
                    "file": curr_node.file,
                    "resource_type": res_attr.get("resource_type"),
                    "code": get_node_source(repo_path, curr_node)
                })
                
        callees = callee_map.get(curr_id, [])
        for c_id in callees:
            if c_id not in visited_down:
                visited_down.add(c_id)
                queue_down.append((c_id, depth + 1))
                
    # Extract real type and class definitions in the same file for type_or_model_context
    type_or_model_context = []
    for node in ir_store.get_symbols_by_file(candidate.file):
        if node.kind == "type_hint" or (node.kind == "symbol" and node.attributes.get("symbol_kind") == "class"):
                type_or_model_context.append({
                    "symbol": node.symbol,
                    "kind": node.kind if node.kind != "symbol" else "class",
                    "span": node.span,
                    "code": get_node_source(repo_path, node)
                })
                
    bundle_dict = {
        "candidate_id": candidate.candidate_id,
        "symbol_body": symbol_body,
        "upstream_entrypoints": upstream_entrypoints,
        "caller_chain": caller_chain,
        "callee_chain": callee_chain,
        "guard_snippets": guard_snippets,
        "resource_snippets": resource_snippets,
        "state_transition_snippets": state_transition_snippets,
        "type_or_model_context": type_or_model_context,
        "provider_trace": candidate.provider_trace
    }
    
    score = calculate_completeness_score(bundle_dict, candidate.source_tracks)
    gaps = determine_evidence_gaps(bundle_dict, candidate.source_tracks)
    
    return EvidenceBundle(
        candidate_id=candidate.candidate_id,
        symbol_body=symbol_body,
        upstream_entrypoints=upstream_entrypoints,
        caller_chain=caller_chain,
        callee_chain=callee_chain,
        guard_snippets=guard_snippets,
        resource_snippets=resource_snippets,
        state_transition_snippets=state_transition_snippets,
        type_or_model_context=type_or_model_context,
        provider_trace=candidate.provider_trace,
        evidence_completeness_score=score,
        evidence_gaps=gaps
    )
