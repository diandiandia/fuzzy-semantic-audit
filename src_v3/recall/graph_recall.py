from typing import List, Set
from src_v3.core.models import LanguageShard, CandidateRecord, IREdge
from src_v3.storage.ir_store import IRStore

def expand_by_graph(
    workspace_dir: str, 
    shard: LanguageShard, 
    track: str, 
    seed_candidates: List[CandidateRecord]
) -> List[CandidateRecord]:
    """
    Expands candidate lists by following CallEdges in the IRStore (1-hop callers and callees).
    """
    if not seed_candidates:
        return []
        
    ir_store = IRStore(workspace_dir)
    shard_files = set(shard.paths)
    
    # Map seed symbol names or node IDs to quickly check if they are already in seeds
    seed_nodes = set()
    for sc in seed_candidates:
        # Since candidate IDs aren't fully normalized yet, we can locate their node_id in IRStore
        # by building the ID matching what build_file_ir does
        node_id = f"sym_{sc.file.replace('/', '_')}_{sc.symbol}_{sc.span['start']}_{sc.span['end']}"
        seed_nodes.add(node_id)
        
    new_candidates = []
    visited_nodes = seed_nodes.copy()
    
    # Load all edges
    edges = ir_store.get_edges()
    
    for edge in edges:
        # We only follow call graph edges
        if edge.kind != "call":
            continue
            
        target_node_id = None
        # Caller expansion: if callee is a seed, recall the caller
        if edge.dst_node_id in seed_nodes and edge.src_node_id not in visited_nodes:
            target_node_id = edge.src_node_id
        # Callee expansion: if caller is a seed, recall the callee
        elif edge.src_node_id in seed_nodes and edge.dst_node_id not in visited_nodes:
            target_node_id = edge.dst_node_id
            
        if target_node_id:
            visited_nodes.add(target_node_id)
            sn = ir_store.get_node_by_id(target_node_id)
            
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
                    matched_rules=[f"graph.{track}.neighborhood_match"],
                    recall_sources=["graph"],
                    provider_trace=edge.provider_trace,
                    priority_score=50.0, # Baseline graph expansion score
                    candidate_capability=shard.capability,
                    status="discovered"
                ))
                
    return new_candidates
