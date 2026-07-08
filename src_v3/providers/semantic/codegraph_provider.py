from typing import List, Dict, Any
from src_v3.providers.semantic.base import SemanticProvider
from src_v3.core.enums import CapabilityLevel

class CodeGraphProvider(SemanticProvider):
    provider_name: str = "CodeGraphProvider"

    def __init__(self, endpoint: str = ""):
        self.endpoint = endpoint

    def capability_level(self) -> str:
        return CapabilityLevel.L3

    def resolution_confidence(self) -> float:
        return 0.9 if self.endpoint else 0.0

    def find_definitions(self, symbol_ref: Dict[str, Any]) -> List[Dict[str, Any]]:
        return []

    def find_references(self, symbol_ref: Dict[str, Any]) -> List[Dict[str, Any]]:
        return []

    def find_callers(self, symbol_ref: Dict[str, Any]) -> List[Dict[str, Any]]:
        return []

    def find_callees(self, symbol_ref: Dict[str, Any]) -> List[Dict[str, Any]]:
        return []
