from typing import List, Dict, Any
from src_v3.storage.ir_store import IRStore

class FrameworkProvider:
    """
    Base class / interface for framework semantics extraction.
    Identifies HTTP routes, middleware authentication/authorization checks,
    database/file/network resources, and state machine transitions.
    """
    framework_name: str = "BaseFrameworkProvider"

    def detect(self, repo_profile: Dict[str, Any], files: List[str]) -> bool:
        """
        Determines if the project matches this framework.
        """
        raise NotImplementedError

    def extract_entrypoints(self, ir_store: IRStore) -> List[Dict[str, Any]]:
        """
        Extracts entrypoint annotations, routes, or handlers.
        Returns: list of dict, e.g. [{"node_id": str, "route": str, "method": str, "confidence": float}]
        """
        raise NotImplementedError

    def extract_guards(self, ir_store: IRStore) -> List[Dict[str, Any]]:
        """
        Extracts middleware checks, guards, decorators (e.g. auth required, admin check).
        Returns: list of dict, e.g. [{"node_id": str, "guard_kind": str, "confidence": float}]
        """
        raise NotImplementedError

    def extract_resources(self, ir_store: IRStore) -> List[Dict[str, Any]]:
        """
        Extracts external resource access points (DB queries, file reads/writes, network calls).
        Returns: list of dict, e.g. [{"node_id": str, "resource_type": str, "resource_details": str}]
        """
        raise NotImplementedError

    def extract_state_transitions(self, ir_store: IRStore) -> List[Dict[str, Any]]:
        """
        Extracts state machine modifications (status updates, db updates to state).
        Returns: list of dict, e.g. [{"node_id": str, "state_field": str, "from_state": str, "to_state": str}]
        """
        raise NotImplementedError
