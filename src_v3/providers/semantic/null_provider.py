from typing import List, Dict, Any
from src_v3.providers.semantic.base import SemanticProvider
from src_v3.core.enums import CapabilityLevel

class NullProvider(SemanticProvider):
    provider_name: str = "NullProvider"

    def capability_level(self) -> str:
        return CapabilityLevel.L0.value

    def resolution_confidence(self) -> float:
        return 0.0

    def find_definitions(self, symbol_ref: Dict[str, Any]) -> List[Dict[str, Any]]:
        return []

    def find_references(self, symbol_ref: Dict[str, Any]) -> List[Dict[str, Any]]:
        return []

    def find_callers(self, symbol_ref: Dict[str, Any]) -> List[Dict[str, Any]]:
        return []

    def find_callees(self, symbol_ref: Dict[str, Any]) -> List[Dict[str, Any]]:
        return []
