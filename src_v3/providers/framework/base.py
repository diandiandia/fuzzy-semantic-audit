import re
from typing import List, Dict, Any
from src_v3.storage.ir_store import IRStore

class FrameworkProvider:
    """
    Base class / interface for framework semantics extraction.
    Identifies HTTP routes, middleware authentication/authorization checks,
    database/file/network resources, and state machine transitions.
    """
    framework_name: str = "BaseFrameworkProvider"

    def __init__(self):
        # Dynamically determine framework name lower (e.g. DjangoPack -> django)
        fw_name = self.framework_name.replace("Pack", "").replace("Provider", "").lower()
        from src_v3.packs.frameworks import load_framework_pack
        self.pack = load_framework_pack(fw_name)
        
        # Compile patterns for route, guard, resource, state
        self.route_regex = [re.compile(p, re.IGNORECASE) for p in self.pack.get("route_patterns", []) if p]
        self.guard_regex = [re.compile(p, re.IGNORECASE) for p in self.pack.get("guard_patterns", []) if p]
        self.resource_regex = [re.compile(p, re.IGNORECASE) for p in self.pack.get("resource_patterns", []) if p]
        self.state_regex = [re.compile(p, re.IGNORECASE) for p in self.pack.get("state_machine_patterns", []) if p]

    def detect(self, repo_profile: Dict[str, Any], files: List[str]) -> bool:
        """
        Determines if the project matches this framework.
        """
        raise NotImplementedError

    def extract_entrypoints(self, ir_store: IRStore) -> List[Dict[str, Any]]:
        entrypoints = []
        for sn in ir_store.iter_symbol_nodes():
            matched = False
            for rx in self.route_regex:
                if rx.search(sn.symbol) or rx.search(sn.file):
                    matched = True
                    break
            # Also check if the node is already flagged as entrypoint by parser
            if sn.kind == "entrypoint" or matched:
                entrypoints.append({
                    "node_id": sn.node_id,
                    "route": f"{self.framework_name.lower()}://{sn.file}/{sn.symbol}",
                    "method": "ANY",
                    "confidence": 0.8
                })
        return entrypoints

    def extract_guards(self, ir_store: IRStore) -> List[Dict[str, Any]]:
        guards = []
        for sn in ir_store.iter_symbol_nodes():
            matched = False
            for rx in self.guard_regex:
                if rx.search(sn.symbol) or rx.search(sn.file):
                    matched = True
                    break
            if sn.kind == "guard_check" or matched:
                guards.append({
                    "node_id": sn.node_id,
                    "guard_kind": f"{self.framework_name.lower()}_auth_check",
                    "confidence": 0.8
                })
        return guards

    def extract_resources(self, ir_store: IRStore) -> List[Dict[str, Any]]:
        resources = []
        for sn in ir_store.iter_symbol_nodes():
            matched = False
            for rx in self.resource_regex:
                if rx.search(sn.symbol) or rx.search(sn.file):
                    matched = True
                    break
            if sn.kind == "resource_access" or matched:
                resources.append({
                    "node_id": sn.node_id,
                    "resource_type": f"{self.framework_name.lower()}_resource",
                    "resource_details": f"Resource interaction at {sn.symbol}"
                })
        return resources

    def extract_state_transitions(self, ir_store: IRStore) -> List[Dict[str, Any]]:
        transitions = []
        for sn in ir_store.iter_symbol_nodes():
            matched = False
            for rx in self.state_regex:
                if rx.search(sn.symbol) or rx.search(sn.file):
                    matched = True
                    break
            if sn.kind == "state_transition" or matched:
                transitions.append({
                    "node_id": sn.node_id,
                    "state_field": "status",
                    "from_state": "ANY",
                    "to_state": "ANY"
                })
        return transitions
