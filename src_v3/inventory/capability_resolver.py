from typing import Any, Dict
from src_v3.core.models import LanguageShard
from src_v3.core.enums import CapabilityLevel
from src_v3.storage.ir_store import IRStore

def resolve_shard_capability(shard: LanguageShard) -> str:
    """
    Resolves the nominal capability level of a language shard 
    based on the assigned provider_set.
    """
    providers = shard.provider_set or {}
    parser_provider = providers.get("parser")
    semantic_provider = providers.get("semantic")
    
    # No parser -> L0
    if not parser_provider or parser_provider == "NullProvider":
        return CapabilityLevel.L0.value
        
    # Has parser, but no semantic provider -> L1
    if not semantic_provider or semantic_provider == "NullProvider":
        return CapabilityLevel.L1.value
        
    # Nominal capability is at most L2. L3 represents deep call-graph path verification
    # which can only be achieved effectively if confirmed by the actual execution environment.
    return CapabilityLevel.L2.value

def resolve_effective_capability(shard: LanguageShard, ir_store: IRStore, semantic_index: Dict[str, Any], semantic_provider: Any = None) -> str:
    """
    Resolves the effective capability level achieved by a shard, mapping it 
    directly to the actual structure and cross-reference outputs produced.
    """
    # Start at L0 (Text-based)
    effective_cap = CapabilityLevel.L0.value
    
    # 1. L1 Structural: Must have successfully extracted symbol nodes using a structured parser (not regex/failed)
    shard_paths_set = set(shard.paths)
    file_nodes = [n for n in ir_store.get_file_nodes() if n.file in shard_paths_set]
    
    has_structure = False
    for fn in file_nodes:
        p_mode = fn.attributes.get("parse_mode")
        if p_mode not in ["regex", "failed"]:
            has_structure = True
            break
            
    if not has_structure:
        return CapabilityLevel.L0.value
        
    effective_cap = CapabilityLevel.L1.value
    
    # 2. L2 Semantic: heuristic/text fallback results are never semantic evidence.
    if semantic_provider is None or getattr(semantic_provider, "use_fallback", True):
        return effective_cap

    # Must have successfully resolved definitions/references in the semantic index.
    has_semantic = False
    if semantic_index:
        for node_id, data in semantic_index.items():
            if data.get("definitions") or data.get("references"):
                has_semantic = True
                break
                
    if has_semantic:
        effective_cap = CapabilityLevel.L2.value
        
    # 3. L3 Deep Audit: Require real, exact semantic call edges in addition to
    # non-fallback definition/reference results. Parser-created fuzzy call edges
    # and text-derived provider output are insufficient.
    has_deep = False
    all_edges = ir_store.get_edges()
    call_edges = [
        e for e in all_edges
        if e.kind == "call"
        and e.resolution_kind == "exact"
        and getattr(semantic_provider, "provider_name", "") in e.provider_trace
        and ir_store.get_node_by_id(e.src_node_id)
        and ir_store.get_node_by_id(e.src_node_id).file in shard_paths_set
    ]
    if call_edges:
        has_deep = True
        
    entrypoint_nodes = [n for n in ir_store.get_symbol_nodes() if n.kind == "entrypoint" and n.file in shard_paths_set]
    if entrypoint_nodes:
        has_deep = True
        
    if has_deep:
        effective_cap = CapabilityLevel.L3.value
            
    return effective_cap
