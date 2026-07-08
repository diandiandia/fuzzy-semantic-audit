import os
import re
from typing import List, Dict, Any
from src_v3.providers.framework.base import FrameworkProvider
from src_v3.storage.ir_store import IRStore

class DjangoPack(FrameworkProvider):
    framework_name: str = "DjangoPack"

    def detect(self, repo_profile: Dict[str, Any], files: List[str]) -> bool:
        return "django" in repo_profile.get("frameworks", [])

    def extract_entrypoints(self, ir_store: IRStore) -> List[Dict[str, Any]]:
        """
        Locates Django views and REST API endpoints.
        """
        entrypoints = []
        # Typically Django views reside in views.py or are named View/ViewSet
        for sn in ir_store.iter_symbol_nodes():
            if "views.py" in sn.file.lower() or "view" in sn.symbol.lower():
                if sn.attributes.get("symbol_kind") == "function" or sn.attributes.get("symbol_kind") == "class":
                    entrypoints.append({
                        "node_id": sn.node_id,
                        "route": f"django://{sn.file}/{sn.symbol}",
                        "method": "ANY",
                        "confidence": 0.8
                    })
        return entrypoints

    def extract_guards(self, ir_store: IRStore) -> List[Dict[str, Any]]:
        """
        Locates Django authentication and permission checks.
        """
        guards = []
        for sn in ir_store.iter_symbol_nodes():
            # Check for decorator annotations or common permission checking methods
            if "login_required" in sn.symbol.lower() or "has_perm" in sn.symbol.lower() or "is_authenticated" in sn.symbol.lower():
                guards.append({
                    "node_id": sn.node_id,
                    "guard_kind": "django_auth_check",
                    "confidence": 0.8
                })
        return guards

    def extract_resources(self, ir_store: IRStore) -> List[Dict[str, Any]]:
        """
        Locates Django ORM / database access.
        """
        resources = []
        # Django models or symbols querying model managers
        for sn in ir_store.iter_symbol_nodes():
            if "models.py" in sn.file.lower() or "objects" in sn.symbol.lower():
                resources.append({
                    "node_id": sn.node_id,
                    "resource_type": "django_orm",
                    "resource_details": f"ORM interaction at {sn.symbol}"
                })
        return resources

    def extract_state_transitions(self, ir_store: IRStore) -> List[Dict[str, Any]]:
        """
        Locates state changes on Django models.
        """
        transitions = []
        for sn in ir_store.iter_symbol_nodes():
            if ("status" in sn.symbol.lower() or "state" in sn.symbol.lower()) and "save" in sn.symbol.lower():
                transitions.append({
                    "node_id": sn.node_id,
                    "state_field": "status",
                    "from_state": "ANY",
                    "to_state": "ANY"
                })
        return transitions
