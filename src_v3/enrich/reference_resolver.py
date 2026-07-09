from typing import List, Dict, Any
from src_v3.providers.semantic.base import SemanticProvider
from src_v3.storage.ir_store import IRStore

class ReferenceResolver:
    """
    Resolves symbol definitions and references across files.
    """
    def __init__(self, semantic_provider: SemanticProvider, ir_store: IRStore):
        self.provider = semantic_provider
        self.ir_store = ir_store

    def resolve_definitions(self, symbol: str, file_path: str, span: Dict[str, int]) -> List[Dict[str, Any]]:
        ref_query = {"symbol": symbol, "file": file_path, "span": span}
        return self.provider.find_definitions(ref_query)

    def resolve_references(self, symbol: str, file_path: str, span: Dict[str, int]) -> List[Dict[str, Any]]:
        ref_query = {"symbol": symbol, "file": file_path, "span": span}
        return self.provider.find_references(ref_query)
