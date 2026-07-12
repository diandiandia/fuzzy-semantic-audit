import os
from typing import List, Dict, Any, Optional
from src_v3.core.models import CandidateRecord, EvidenceBundle, IRNode
from src_v3.storage.ir_store import IRStore
from src_v3.evidence.completeness import calculate_completeness_score, determine_evidence_gaps

_file_lines_cache = {}

def _append_unique_trace(provider_trace: List[str], value: Any) -> None:
    if not value:
        return
    if isinstance(value, list):
        for item in value:
            _append_unique_trace(provider_trace, item)
        return
    if isinstance(value, dict):
        value = str(value)
    if value not in provider_trace:
        provider_trace.append(value)

def get_node_source(repo_path: str, node: IRNode) -> str:
    """
    Slices the source code of a node from the file on disk, with cache.
    """
    abs_path = os.path.join(repo_path, node.file)
    if not os.path.exists(abs_path):
        return ""
    if abs_path not in _file_lines_cache:
        try:
            with open(abs_path, 'r', encoding='utf-8', errors='ignore') as f:
                _file_lines_cache[abs_path] = f.readlines()
        except Exception:
            _file_lines_cache[abs_path] = []
    lines = _file_lines_cache[abs_path]
    start = max(0, node.span["start"] - 1)
    end = min(len(lines), node.span["end"])
    return "".join(lines[start:end])

def assemble_evidence(
    workspace_dir: str, 
    repo_path: str, 
    candidate: CandidateRecord, 
    ir_store: IRStore
) -> EvidenceBundle:
    """
    Assembles a complete, structured EvidenceBundle for a candidate.
    """
    provider_trace = list(candidate.provider_trace or [])

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
            provider_trace=provider_trace,
            evidence_completeness_score=10,
            evidence_gaps=["missing IR symbol node for candidate"]
        )
        
    symbol_body = get_node_source(repo_path, sn)
    for attr_name in ["framework_entrypoint", "framework_guard", "framework_resource", "framework_state_transition"]:
        attr = sn.attributes.get(attr_name, {})
        _append_unique_trace(provider_trace, attr.get("provider_name"))
        _append_unique_trace(provider_trace, attr.get("framework_trace"))
    
    # Load BFS depth limits from track configuration
    from src_v3.packs.tracks import load_track_pack
    track = candidate.source_tracks[0] if candidate.source_tracks else "generic"
    track_pack = load_track_pack(track)
    max_bfs_depth_up = track_pack.get("evidence_bfs_depth_up", 5)
    max_bfs_depth_down = track_pack.get("evidence_bfs_depth_down", 3)
    
    # Caller/Callee maps
    caller_map = ir_store.get_caller_map()
    callee_map = ir_store.get_callee_map()
    call_edge_trace = {}
    for edge in ir_store.iter_edges():
        if edge.kind == "call":
            call_edge_trace[(edge.src_node_id, edge.dst_node_id)] = edge.provider_trace
            
    # Gather immediate callers
    caller_chain = []
    immediate_caller_ids = caller_map.get(sn.node_id, [])
    for cid in immediate_caller_ids:
        c_node = ir_store.get_node_by_id(cid)
        if c_node:
            edge_trace = call_edge_trace.get((cid, sn.node_id), [])
            _append_unique_trace(provider_trace, edge_trace)
            caller_chain.append({
                "symbol": c_node.symbol,
                "file": c_node.file,
                "span": c_node.span,
                "provider_trace": edge_trace
            })
            
    # Gather immediate callees
    callee_chain = []
    immediate_callee_ids = callee_map.get(sn.node_id, [])
    for cid in immediate_callee_ids:
        c_node = ir_store.get_node_by_id(cid)
        if c_node:
            edge_trace = call_edge_trace.get((sn.node_id, cid), [])
            _append_unique_trace(provider_trace, edge_trace)
            callee_chain.append({
                "symbol": c_node.symbol,
                "file": c_node.file,
                "span": c_node.span,
                "provider_trace": edge_trace
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
            "code": symbol_body,
            "framework_trace": sn.attributes["framework_guard"].get("framework_trace", {})
        })
    if "framework_resource" in sn.attributes:
        resource_snippets.append({
            "symbol": sn.symbol,
            "file": sn.file,
            "resource_type": sn.attributes["framework_resource"]["resource_type"],
            "code": symbol_body,
            "framework_trace": sn.attributes["framework_resource"].get("framework_trace", {})
        })
    if "framework_state_transition" in sn.attributes:
        state_transition_snippets.append({
            "symbol": sn.symbol,
            "file": sn.file,
            "state_field": sn.attributes["framework_state_transition"]["state_field"],
            "framework_trace": sn.attributes["framework_state_transition"].get("framework_trace", {})
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
                    "code": get_node_source(repo_path, curr_node),
                    "framework_trace": ep_attr.get("framework_trace", {})
                })
                _append_unique_trace(provider_trace, ep_attr.get("provider_name"))
                _append_unique_trace(provider_trace, ep_attr.get("framework_trace"))
            # Check guards
            if "framework_guard" in curr_node.attributes:
                gd_attr = curr_node.attributes["framework_guard"]
                guard_snippets.append({
                    "symbol": curr_node.symbol,
                    "file": curr_node.file,
                    "guard_kind": gd_attr.get("guard_kind"),
                    "code": get_node_source(repo_path, curr_node),
                    "framework_trace": gd_attr.get("framework_trace", {})
                })
                _append_unique_trace(provider_trace, gd_attr.get("provider_name"))
                _append_unique_trace(provider_trace, gd_attr.get("framework_trace"))
            # Check state transitions
            if "framework_state_transition" in curr_node.attributes:
                st_attr = curr_node.attributes["framework_state_transition"]
                state_transition_snippets.append({
                    "symbol": curr_node.symbol,
                    "file": curr_node.file,
                    "state_field": st_attr.get("state_field"),
                    "framework_trace": st_attr.get("framework_trace", {})
                })
                _append_unique_trace(provider_trace, st_attr.get("provider_name"))
                _append_unique_trace(provider_trace, st_attr.get("framework_trace"))
                
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
                    "code": get_node_source(repo_path, curr_node),
                    "framework_trace": res_attr.get("framework_trace", {})
                })
                _append_unique_trace(provider_trace, res_attr.get("provider_name"))
                _append_unique_trace(provider_trace, res_attr.get("framework_trace"))
                
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
        "provider_trace": provider_trace
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
        provider_trace=provider_trace,
        evidence_completeness_score=score,
        evidence_gaps=gaps
    )
