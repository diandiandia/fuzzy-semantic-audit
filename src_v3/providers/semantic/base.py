from typing import List, Dict, Any

class SemanticProvider:
    """
    Base class / interface for semantic query providers.
    Supports resolving definition, reference, caller, and callee relations.
    """
    provider_name: str = "BaseSemanticProvider"

    def capability_level(self) -> str:
        """
        Returns the capability level (L0, L1, L2, L3) this provider supports.
        """
        raise NotImplementedError

    def resolution_confidence(self) -> float:
        """
        Returns a float between 0.0 and 1.0 indicating reference resolution confidence.
        """
        raise NotImplementedError

    def find_definitions(self, symbol_ref: Dict[str, Any]) -> List[Dict[str, Any]]:
        """
        Finds definition points of a given symbol reference.
        Input symbol_ref format: {"symbol": str, "file": str, "span": {"start": int, "end": int}}
        Returns a list of matching symbol nodes:
        {
            "symbol": str,
            "file": str,
            "span": {"start": int, "end": int},
            "kind": str
        }
        """
        raise NotImplementedError

    def find_references(self, symbol_ref: Dict[str, Any]) -> List[Dict[str, Any]]:
        """
        Finds call/reference sites of a symbol.
        """
        raise NotImplementedError

    def find_callers(self, symbol_ref: Dict[str, Any]) -> List[Dict[str, Any]]:
        """
        Finds immediate callers of a symbol.
        """
        raise NotImplementedError

    def find_callees(self, symbol_ref: Dict[str, Any]) -> List[Dict[str, Any]]:
        """
        Finds immediate callees of a symbol.
        """
        raise NotImplementedError
