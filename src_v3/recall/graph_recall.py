from typing import List, Set, Dict, Any
from src_v3.core.models import LanguageShard, CandidateRecord, IREdge
from src_v3.storage.ir_store import IRStore

def expand_by_graph(
    workspace_dir: str, 
    shard: LanguageShard, 
    track: str, 
    seed_candidates: List[CandidateRecord]
) -> List[CandidateRecord]:
    """
    Expands candidate lists by following CallEdges in the IRStore recursively (multi-hop callers and callees).
    """
    if not seed_candidates:
        return []
        
    ir_store = IRStore(workspace_dir)
    shard_files = set(shard.paths)
    
    from src_v3.packs.tracks import load_track_pack
    track_pack = load_track_pack(track)
    max_hops = track_pack.get("graph_recall_max_hops", 3)
    
    # Map seed symbol names or node IDs
    seed_nodes = set()
    for sc in seed_candidates:
        node_id = f"sym_{sc.file.replace('/', '_')}_{sc.symbol}_{sc.span['start']}_{sc.span['end']}"
        seed_nodes.add(node_id)
        
    # Get all call edges
    edges = ir_store.get_edges()
    call_edges = [e for e in edges if e.kind == "call"]
    
    # Build adjacency list
    adj: Dict[str, List[tuple]] = {}
    for edge in call_edges:
        src = edge.src_node_id
        dst = edge.dst_node_id
        if src not in adj:
            adj[src] = []
        if dst not in adj:
            adj[dst] = []
        adj[src].append((dst, "callee"))
        adj[dst].append((src, "caller"))
        
    # Multi-hop BFS
    current_frontier = set(seed_nodes)
    visited_nodes = set(seed_nodes)
    new_candidates = []
    
    for hop in range(max_hops):
        next_frontier = set()
        for node in current_frontier:
            if node in adj:
                for neighbor, direction in adj[node]:
                    if neighbor not in visited_nodes:
                        visited_nodes.add(neighbor)
                        next_frontier.add(neighbor)
                        
                        sn = ir_store.get_node_by_id(neighbor)
                        if sn and sn.file in shard_files:
                            new_candidates.append(CandidateRecord(
                                candidate_id="",
                                identity_key="",
                                shard_id=shard.shard_id,
                                lang=shard.lang,
                                file=sn.file,
                                symbol=sn.symbol,
                                span=sn.span,
                                source_tracks=[track],
                                matched_rules=[f"graph.hop{hop+1}.{direction}"],
                                recall_sources=["graph"],
                                provider_trace=list(set(trace for edge in call_edges if (edge.src_node_id == node and edge.dst_node_id == neighbor) or (edge.src_node_id == neighbor and edge.dst_node_id == node) for trace in edge.provider_trace)),
                                priority_score=max(30.0, 60.0 - (hop * 10)),
                                candidate_capability=shard.capability,
                                status="discovered"
                            ))
        current_frontier = next_frontier
        if not current_frontier:
            break
            
    return new_candidates
