from typing import List, Dict, Any
from src_v3.providers.framework.base import FrameworkProvider
from src_v3.storage.ir_store import IRStore

class GinPack(FrameworkProvider):
    """
    Framework provider pack for Gin Web Framework (Go).
    """
    framework_name: str = "Gin"

    def detect(self, repo_profile: Dict[str, Any], files: List[str]) -> bool:
        for f in files:
            if f.endswith(".go"):
                return True
        return False

    def extract_entrypoints(self, ir_store: IRStore) -> List[Dict[str, Any]]:
        entrypoints = []
        for sn in ir_store.iter_symbol_nodes():
            content = sn.attributes.get("text", "")
            if ".GET(" in content or ".POST(" in content or ".Run(" in content:
                entrypoints.append({
                    "node_id": sn.node_id,
                    "route": "/api/gin",
                    "method": "GET",
                    "confidence": 0.9
                })
        return entrypoints

    def extract_guards(self, ir_store: IRStore) -> List[Dict[str, Any]]:
        return []

    def extract_resources(self, ir_store: IRStore) -> List[Dict[str, Any]]:
        return []

    def extract_state_transitions(self, ir_store: IRStore) -> List[Dict[str, Any]]:
        return []
