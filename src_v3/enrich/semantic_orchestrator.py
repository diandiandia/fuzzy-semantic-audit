import os
from typing import List, Dict, Any
from src_v3.core.models import LanguageShard, IREdge, IRNode
from src_v3.providers.semantic.base import SemanticProvider
from src_v3.storage.ir_store import IRStore

def enrich_semantic_relations(
    workspace_dir: str, 
    repo_path: str, 
    shard: LanguageShard, 
    semantic_provider: SemanticProvider
) -> None:
    """
    Orchestrates SemanticProvider query results to build and save call graph edges.
    """
    ir_store = IRStore(workspace_dir)
    shard_files = set(shard.paths)
    
    new_edges = []
    
    # 1. Enrich calling relations (Callers & Callees)
    for sn in ir_store.iter_symbol_nodes():
        if sn.file not in shard_files:
            continue
            
        symbol_ref = {
            "symbol": sn.symbol,
            "file": sn.file,
            "span": sn.span
        }
        
        # A. Find callers
        try:
            callers = semantic_provider.find_callers(symbol_ref)
            for caller in callers:
                # Find matching node in IRStore
                caller_node = ir_store.get_node_by_id(
                    f"sym_{caller['file'].replace('/', '_')}_{caller['symbol']}_{caller['span']['start']}_{caller['span']['end']}"
                )
                if not caller_node:
                    # Fallback to search by symbol name and file
                    file_syms = ir_store.get_symbols_by_file(caller['file'])
                    for fs in file_syms:
                        if fs.symbol == caller['symbol']:
                            caller_node = fs
                            break
                            
                if caller_node:
                    edge_id = f"call_{caller_node.node_id}_{sn.node_id}"
                    confidence = semantic_provider.resolution_confidence()
                    res_kind = "exact" if confidence >= 0.7 else "fuzzy"
                    
                    new_edges.append(IREdge(
                        edge_id=edge_id,
                        kind="call",
                        src_node_id=caller_node.node_id,
                        dst_node_id=sn.node_id,
                        confidence=confidence,
                        resolution_kind=res_kind,
                        provider_trace=[semantic_provider.provider_name]
                    ))
        except Exception:
            pass
            
        # B. Find callees
        try:
            callees = semantic_provider.find_callees(symbol_ref)
            for callee in callees:
                callee_node = ir_store.get_node_by_id(
                    f"sym_{callee['file'].replace('/', '_')}_{callee['symbol']}_{callee['span']['start']}_{callee['span']['end']}"
                )
                if not callee_node:
                    file_syms = ir_store.get_symbols_by_file(callee['file'])
                    for fs in file_syms:
                        if fs.symbol == callee['symbol']:
                            callee_node = fs
                            break
                            
                if callee_node:
                    edge_id = f"call_{sn.node_id}_{callee_node.node_id}"
                    confidence = semantic_provider.resolution_confidence()
                    res_kind = "exact" if confidence >= 0.7 else "fuzzy"
                    
                    new_edges.append(IREdge(
                        edge_id=edge_id,
                        kind="call",
                        src_node_id=sn.node_id,
                        dst_node_id=callee_node.node_id,
                        confidence=confidence,
                        resolution_kind=res_kind,
                        provider_trace=[semantic_provider.provider_name]
                    ))
        except Exception:
            pass

    # 2. Resolve fuzzy imports
    # Let's read all edges and see if we can resolve 'import_xxx' targets to actual FileNodes
    existing_edges = ir_store.get_edges()
    resolved_import_edges = []
    
    file_nodes = ir_store.get_file_nodes()
    # Build maps for quick lookup
    file_by_name = {os.path.basename(fn.file).split('.')[0]: fn for fn in file_nodes}
    file_by_module = {fn.file.replace('/', '.').split('.')[0]: fn for fn in file_nodes}
    
    for edge in existing_edges:
        if edge.kind == "import" and edge.dst_node_id.startswith("import_"):
            import_name = edge.dst_node_id[len("import_"):]
            # Search if we can match this to any file
            target_fn = file_by_name.get(import_name)
            if not target_fn:
                target_fn = file_by_module.get(import_name)
                
            if target_fn:
                # Update import edge or create a resolved import edge
                resolved_import_edges.append(IREdge(
                    edge_id=f"resolved_{edge.edge_id}",
                    kind="import_resolved",
                    src_node_id=edge.src_node_id,
                    dst_node_id=target_fn.node_id,
                    confidence=1.0,
                    resolution_kind="exact",
                    provider_trace=["ImportResolver"]
                ))
                
    new_edges.extend(resolved_import_edges)
    
    # Save newly resolved edges to the IRStore
    if new_edges:
        ir_store.save([], new_edges, overwrite=False)
