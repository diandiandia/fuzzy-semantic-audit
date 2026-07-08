import re
from typing import List, Dict, Any
from src_v3.providers.framework.base import FrameworkProvider
from src_v3.storage.ir_store import IRStore

class GenericFrameworkProvider(FrameworkProvider):
    framework_name: str = "GenericFrameworkProvider"

    def detect(self, repo_profile: Dict[str, Any], files: List[str]) -> bool:
        return True # Always active as a fallback

    def extract_entrypoints(self, ir_store: IRStore) -> List[Dict[str, Any]]:
        """
        Locates entrypoints by inspecting function names for HTTP/API indicators.
        """
        entrypoints = []
        pattern = re.compile(r'(?i)(handler|route|controller|api|get_|post_|put_|delete_|serve)')
        
        for sn in ir_store.iter_symbol_nodes():
            if sn.attributes.get("symbol_kind") == "function":
                if pattern.search(sn.symbol):
                    entrypoints.append({
                        "node_id": sn.node_id,
                        "route": f"generic://{sn.file}/{sn.symbol}",
                        "method": "ANY",
                        "confidence": 0.5
                    })
        return entrypoints

    def extract_guards(self, ir_store: IRStore) -> List[Dict[str, Any]]:
        """
        Locates security guards by identifying verification and authorization keywords.
        """
        guards = []
        pattern = re.compile(r'(?i)(auth|guard|check|verify|login|permission|validate|require|session)')
        
        for sn in ir_store.iter_symbol_nodes():
            if sn.attributes.get("symbol_kind") == "function":
                if pattern.search(sn.symbol):
                    guards.append({
                        "node_id": sn.node_id,
                        "guard_kind": "generic_auth_check",
                        "confidence": 0.5
                    })
        return guards

    def extract_resources(self, ir_store: IRStore) -> List[Dict[str, Any]]:
        """
        Locates database, network, and file system interactions.
        """
        resources = []
        pattern = re.compile(r'(?i)(db|sql|query|save|insert|delete|update|select|file|read|write|connect|send|recv|publish|consume)')
        
        for sn in ir_store.iter_symbol_nodes():
            if sn.attributes.get("symbol_kind") == "function":
                if pattern.search(sn.symbol):
                    resources.append({
                        "node_id": sn.node_id,
                        "resource_type": "generic_io",
                        "resource_details": f"Symbol {sn.symbol} hints resource access"
                    })
        return resources

    def extract_state_transitions(self, ir_store: IRStore) -> List[Dict[str, Any]]:
        """
        Locates state updates and transitions.
        """
        transitions = []
        pattern = re.compile(r'(?i)(status|state|transition|step|phase|stage|progress)')
        
        for sn in ir_store.iter_symbol_nodes():
            if sn.attributes.get("symbol_kind") == "function":
                if pattern.search(sn.symbol):
                    transitions.append({
                        "node_id": sn.node_id,
                        "state_field": "status",
                        "from_state": "ANY",
                        "to_state": "ANY"
                    })
        return transitions
