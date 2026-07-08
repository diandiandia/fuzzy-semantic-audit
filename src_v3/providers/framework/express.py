import re
from typing import List, Dict, Any
from src_v3.providers.framework.base import FrameworkProvider
from src_v3.storage.ir_store import IRStore

class ExpressPack(FrameworkProvider):
    framework_name: str = "ExpressPack"

    def detect(self, repo_profile: Dict[str, Any], files: List[str]) -> bool:
        return "express" in repo_profile.get("frameworks", [])

    def extract_entrypoints(self, ir_store: IRStore) -> List[Dict[str, Any]]:
        entrypoints = []
        for sn in ir_store.iter_symbol_nodes():
            if re.search(r'(?i)(req|res|next|app\.(get|post|put|delete|use)|router\.)', sn.symbol):
                entrypoints.append({
                    "node_id": sn.node_id,
                    "route": f"express://{sn.file}/{sn.symbol}",
                    "method": "ANY",
                    "confidence": 0.8
                })
        return entrypoints

    def extract_guards(self, ir_store: IRStore) -> List[Dict[str, Any]]:
        guards = []
        for sn in ir_store.iter_symbol_nodes():
            if re.search(r'(?i)(auth|passport|jwt|session|cookie|authorize)', sn.symbol):
                guards.append({
                    "node_id": sn.node_id,
                    "guard_kind": "express_auth_middleware",
                    "confidence": 0.8
                })
        return guards

    def extract_resources(self, ir_store: IRStore) -> List[Dict[str, Any]]:
        resources = []
        for sn in ir_store.iter_symbol_nodes():
            if re.search(r'(?i)(db|query|find|save|findone|insert|mongoose|sequelize|pg|knex)', sn.symbol):
                resources.append({
                    "node_id": sn.node_id,
                    "resource_type": "express_db_query",
                    "resource_details": f"Database query at {sn.symbol}"
                })
        return resources

    def extract_state_transitions(self, ir_store: IRStore) -> List[Dict[str, Any]]:
        transitions = []
        for sn in ir_store.iter_symbol_nodes():
            if re.search(r'(?i)(status|state|update)', sn.symbol):
                transitions.append({
                    "node_id": sn.node_id,
                    "state_field": "status",
                    "from_state": "ANY",
                    "to_state": "ANY"
                })
        return transitions
