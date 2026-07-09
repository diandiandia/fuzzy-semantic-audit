from typing import List, Dict, Any, Optional
from src_v3.providers.semantic.base import SemanticProvider
from src_v3.storage.index_store import IndexStore

class CachedSemanticProvider(SemanticProvider):
    """
    Wraps an underlying SemanticProvider and intercepts queries using a pre-compiled semantic index.
    """
    def __init__(self, fallback_provider: SemanticProvider, workspace_dir: str, shard_id: str):
        self.fallback = fallback_provider
        self.provider_name = f"Cached({fallback_provider.provider_name})"
        
        # Load compiled semantic index from IndexStore
        index_store = IndexStore(workspace_dir)
        self.index_data = index_store.load_semantic_index(shard_id)

    def capability_level(self) -> str:
        return self.fallback.capability_level()

    def resolution_confidence(self) -> float:
        return self.fallback.resolution_confidence()

    def _get_node_key(self, symbol_ref: Dict[str, Any]) -> str:
        symbol = symbol_ref.get("symbol")
        file = symbol_ref.get("file")
        span = symbol_ref.get("span", {})
        
        if not self.index_data:
            return ""
            
        for nid, data in self.index_data.items():
            if data.get("symbol") == symbol and data.get("file") == file:
                n_span = data.get("span", {})
                if not span or not n_span or (span.get("start") == n_span.get("start")):
                    return nid
        return ""

    def find_definitions(self, symbol_ref: Dict[str, Any]) -> List[Dict[str, Any]]:
        nid = self._get_node_key(symbol_ref)
        if nid and nid in self.index_data:
            return self.index_data[nid].get("definitions", [])
        return self.fallback.find_definitions(symbol_ref)

    def find_references(self, symbol_ref: Dict[str, Any]) -> List[Dict[str, Any]]:
        nid = self._get_node_key(symbol_ref)
        if nid and nid in self.index_data:
            return self.index_data[nid].get("references", [])
        return self.fallback.find_references(symbol_ref)

    def find_callers(self, symbol_ref: Dict[str, Any]) -> List[Dict[str, Any]]:
        nid = self._get_node_key(symbol_ref)
        if nid and nid in self.index_data:
            return self.index_data[nid].get("callers", [])
        return self.fallback.find_callers(symbol_ref)

    def find_callees(self, symbol_ref: Dict[str, Any]) -> List[Dict[str, Any]]:
        nid = self._get_node_key(symbol_ref)
        if nid and nid in self.index_data:
            return self.index_data[nid].get("callees", [])
        return self.fallback.find_callees(symbol_ref)
