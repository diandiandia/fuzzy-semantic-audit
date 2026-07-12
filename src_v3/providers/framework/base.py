import json
import os
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

    def _repo_path_from_store(self, ir_store: IRStore) -> str:
        plan_path = os.path.join(ir_store.workspace_dir, "audit_plan.json")
        if not os.path.exists(plan_path):
            return ""
        try:
            with open(plan_path, "r", encoding="utf-8") as f:
                return os.path.abspath(json.load(f).get("repo_path", ""))
        except Exception:
            return ""

    def _symbol_context(self, ir_store: IRStore, symbol_node: Any, padding: int = 4) -> str:
        repo_path = self._repo_path_from_store(ir_store)
        if not repo_path or not symbol_node.file:
            return ""
        abs_path = os.path.join(repo_path, symbol_node.file)
        if not os.path.exists(abs_path):
            return ""
        try:
            with open(abs_path, "r", encoding="utf-8", errors="ignore") as f:
                lines = f.readlines()
        except Exception:
            return ""
        start = max(0, int(symbol_node.span.get("start", 1)) - 1 - padding)
        end = min(len(lines), int(symbol_node.span.get("end", 1)) + padding)
        return "".join(lines[start:end])

    def _matches_any(self, patterns: List[re.Pattern], symbol_node: Any, context: str) -> bool:
        haystacks = [symbol_node.symbol or "", symbol_node.file or "", context or ""]
        return any(rx.search(haystack) for rx in patterns for haystack in haystacks)

    def _infer_route_method(self, context: str) -> Dict[str, str]:
        route = f"{self.framework_name.lower()}://unknown"
        method = "ANY"

        method_match = re.search(
            r"(?:\b|\.)(get|post|put|delete|patch|head|options)\s*\(",
            context,
            re.IGNORECASE
        )
        spring_match = re.search(r"@(Get|Post|Put|Delete|Patch|Request)Mapping", context)
        api_view_match = re.search(r"@api_view\s*\(\s*\[\s*['\"]([A-Z]+)['\"]", context)
        gin_match = re.search(r"\b(GET|POST|PUT|DELETE|PATCH|HEAD|OPTIONS)\s*\(", context)
        if method_match:
            method = method_match.group(1).upper()
        elif spring_match and spring_match.group(1).lower() != "request":
            method = spring_match.group(1).upper()
        elif api_view_match:
            method = api_view_match.group(1).upper()
        elif gin_match:
            method = gin_match.group(1).upper()

        route_patterns = [
            r"(?:path|re_path|route|RequestMapping|GetMapping|PostMapping|PutMapping|DeleteMapping|PatchMapping)\s*\(\s*(?:value\s*=\s*)?['\"]([^'\"]+)['\"]",
            r"\.(?:get|post|put|delete|patch|use)\s*\(\s*['\"]([^'\"]+)['\"]",
            r"\b(?:GET|POST|PUT|DELETE|PATCH|HEAD|OPTIONS)\s*\(\s*['\"]([^'\"]+)['\"]"
        ]
        for pattern in route_patterns:
            route_match = re.search(pattern, context, re.IGNORECASE)
            if route_match:
                route = route_match.group(1)
                break
        return {"route": route, "method": method}

    def _trace(self, stage: str, symbol_node: Any, confidence: float, details: Dict[str, Any]) -> Dict[str, Any]:
        return {
            "framework": self.framework_name,
            "stage": stage,
            "symbol": symbol_node.symbol,
            "file": symbol_node.file,
            "confidence": confidence,
            "details": details
        }

    def detect(self, repo_profile: Dict[str, Any], files: List[str]) -> bool:
        """
        Determines if the project matches this framework.
        """
        raise NotImplementedError

    def extract_entrypoints(self, ir_store: IRStore) -> List[Dict[str, Any]]:
        entrypoints = []
        for sn in ir_store.iter_symbol_nodes():
            context = self._symbol_context(ir_store, sn)
            matched = self._matches_any(self.route_regex, sn, context)
            # Also check if the node is already flagged as entrypoint by parser
            if sn.kind == "entrypoint" or matched:
                route_info = self._infer_route_method(context)
                confidence = 0.9 if context and route_info["route"] != f"{self.framework_name.lower()}://unknown" else 0.8
                entrypoints.append({
                    "node_id": sn.node_id,
                    "route": route_info["route"] if route_info["route"] != f"{self.framework_name.lower()}://unknown" else f"{self.framework_name.lower()}://{sn.file}/{sn.symbol}",
                    "method": route_info["method"],
                    "confidence": confidence,
                    "framework_trace": self._trace("entrypoint", sn, confidence, route_info)
                })
        return entrypoints

    def extract_guards(self, ir_store: IRStore) -> List[Dict[str, Any]]:
        guards = []
        for sn in ir_store.iter_symbol_nodes():
            context = self._symbol_context(ir_store, sn)
            matched = self._matches_any(self.guard_regex, sn, context)
            if sn.kind == "guard_check" or matched:
                confidence = 0.9 if context else 0.8
                guards.append({
                    "node_id": sn.node_id,
                    "guard_kind": f"{self.framework_name.lower()}_auth_check",
                    "confidence": confidence,
                    "framework_trace": self._trace("guard", sn, confidence, {"matched_context": bool(context)})
                })
        return guards

    def extract_resources(self, ir_store: IRStore) -> List[Dict[str, Any]]:
        resources = []
        for sn in ir_store.iter_symbol_nodes():
            context = self._symbol_context(ir_store, sn)
            matched = self._matches_any(self.resource_regex, sn, context)
            if sn.kind == "resource_access" or matched:
                confidence = 0.9 if context else 0.8
                resources.append({
                    "node_id": sn.node_id,
                    "resource_type": f"{self.framework_name.lower()}_resource",
                    "resource_details": f"Resource interaction at {sn.symbol}",
                    "confidence": confidence,
                    "framework_trace": self._trace("resource", sn, confidence, {"matched_context": bool(context)})
                })
        return resources

    def extract_state_transitions(self, ir_store: IRStore) -> List[Dict[str, Any]]:
        transitions = []
        for sn in ir_store.iter_symbol_nodes():
            context = self._symbol_context(ir_store, sn)
            matched = self._matches_any(self.state_regex, sn, context)
            if sn.kind == "state_transition" or matched:
                confidence = 0.9 if context else 0.8
                transitions.append({
                    "node_id": sn.node_id,
                    "state_field": "status",
                    "from_state": "ANY",
                    "to_state": "ANY",
                    "confidence": confidence,
                    "framework_trace": self._trace("state_transition", sn, confidence, {"matched_context": bool(context)})
                })
        return transitions
