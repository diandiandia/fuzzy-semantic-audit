from typing import List, Dict, Any
from src_v3.providers.framework.base import FrameworkProvider
from src_v3.storage.ir_store import IRStore

class AndroidPack(FrameworkProvider):
    """
    Framework provider pack for Android Application Framework (Kotlin/Java).
    """
    framework_name: str = "Android"

    def detect(self, repo_profile: Dict[str, Any], files: List[str]) -> bool:
        for f in files:
            if "AndroidManifest.xml" in f:
                return True
        return False

    def extract_entrypoints(self, ir_store: IRStore) -> List[Dict[str, Any]]:
        entrypoints = []
        for sn in ir_store.iter_symbol_nodes():
            content = sn.attributes.get("text", "")
            if "onCreate" in content or "Activity" in sn.symbol:
                entrypoints.append({
                    "node_id": sn.node_id,
                    "route": f"android://{sn.symbol}",
                    "method": "LIFECYCLE",
                    "confidence": 0.95
                })
        return entrypoints

    def extract_guards(self, ir_store: IRStore) -> List[Dict[str, Any]]:
        return []

    def extract_resources(self, ir_store: IRStore) -> List[Dict[str, Any]]:
        return []

    def extract_state_transitions(self, ir_store: IRStore) -> List[Dict[str, Any]]:
        return []
