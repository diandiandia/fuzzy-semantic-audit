import os
from typing import List, Dict, Any
from src_v3.core.models import LanguageShard, IREdge, IRNode, CallEdge
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

    existing_edges = ir_store.get_edges()
    call_edges_exist = any(e.kind == "call" for e in existing_edges)

    # 1. Enrich calling relations (Callers & Callees)
    if not call_edges_exist:
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
                        from src_v3.enrich.call_edge_builder import CallEdgeBuilder
                        new_edges.append(CallEdgeBuilder.build_call_edge(caller_node, sn, semantic_provider))
            except Exception as e:
                from src_v3.core.event_log import log_event
                log_event(workspace_dir, "semantic_orchestrator", "error", f"Failed to find callers for symbol {sn.symbol} in file {sn.file}: {str(e)}")
                from src_v3.core.plan_io import load_plan, save_plan
                plan_path = os.path.join(workspace_dir, "audit_plan.json")
                if os.path.exists(plan_path):
                    try:
                        plan = load_plan(plan_path)
                        reason = f"Enrichment error (callers) on {sn.symbol} in {sn.file}: {str(e)}"
                        if plan.run_manifest and reason not in plan.run_manifest.degradation_reasons:
                            plan.run_manifest.degradation_reasons.append(reason)
                            save_plan(plan, plan_path)
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
                        from src_v3.enrich.call_edge_builder import CallEdgeBuilder
                        new_edges.append(CallEdgeBuilder.build_call_edge(sn, callee_node, semantic_provider))
            except Exception as e:
                from src_v3.core.event_log import log_event
                log_event(workspace_dir, "semantic_orchestrator", "error", f"Failed to find callees for symbol {sn.symbol} in file {sn.file}: {str(e)}")
                from src_v3.core.plan_io import load_plan, save_plan
                plan_path = os.path.join(workspace_dir, "audit_plan.json")
                if os.path.exists(plan_path):
                    try:
                        plan = load_plan(plan_path)
                        reason = f"Enrichment error (callees) on {sn.symbol} in {sn.file}: {str(e)}"
                        if plan.run_manifest and reason not in plan.run_manifest.degradation_reasons:
                            plan.run_manifest.degradation_reasons.append(reason)
                            save_plan(plan, plan_path)
                    except Exception:
                        pass

    # 2. Resolve fuzzy imports
    # Let's read all edges and see if we can resolve 'import_xxx' targets to actual FileNodes
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
