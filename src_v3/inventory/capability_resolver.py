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
    framework_provider = providers.get("framework")
    
    # No parser -> L0
    if not parser_provider or parser_provider == "NullProvider":
        return CapabilityLevel.L0.value
        
    # Has parser, but no semantic provider -> L1
    if not semantic_provider or semantic_provider == "NullProvider":
        return CapabilityLevel.L1.value
        
    # If framework provider is active with strong semantic provider -> L3, else L2
    if framework_provider and framework_provider != "GenericFrameworkProvider":
        if semantic_provider in ["LSPProvider", "LSIFProvider", "CodeGraphProvider"]:
            return CapabilityLevel.L3.value
        return CapabilityLevel.L2.value
        
    return CapabilityLevel.L2.value

def resolve_effective_capability(shard: LanguageShard, ir_store: IRStore, semantic_index: Dict[str, Any]) -> str:
    """
    Resolves the effective capability level achieved by a shard, mapping it 
    directly to the actual structure and cross-reference outputs produced.
    """
    # Start at L0 (Text-based)
    effective_cap = CapabilityLevel.L0.value
    
    # 1. L1 Structural: Must have successfully extracted symbol nodes in the shard files
    shard_paths_set = set(shard.paths)
    all_syms = [s for s in ir_store.get_symbol_nodes() if s.file in shard_paths_set and s.kind == "symbol"]
    if not all_syms:
        return CapabilityLevel.L0.value
        
    effective_cap = CapabilityLevel.L1.value
    
    # 2. L2 Semantic: Must have successfully resolved definitions/references in the semantic index
    has_semantic = False
    if semantic_index:
        for node_id, data in semantic_index.items():
            if data.get("definitions") or data.get("references"):
                has_semantic = True
                break
                
    if has_semantic:
        effective_cap = CapabilityLevel.L2.value
        
    # 3. L3 Deep Audit: Must have call graph edges or framework entrypoints successfully resolved
    has_deep = False
    all_edges = ir_store.get_edges()
    call_edges = [e for e in all_edges if e.kind == "call" and ir_store.get_node_by_id(e.src_node_id) and ir_store.get_node_by_id(e.src_node_id).file in shard_paths_set]
    if call_edges:
        has_deep = True
        
    entrypoint_nodes = [n for n in ir_store.get_symbol_nodes() if n.kind == "entrypoint" and n.file in shard_paths_set]
    if entrypoint_nodes:
        has_deep = True
        
    if has_deep:
        effective_cap = CapabilityLevel.L3.value
            
    return effective_cap
