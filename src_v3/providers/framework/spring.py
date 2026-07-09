from typing import List, Dict, Any
from src_v3.providers.framework.base import FrameworkProvider
from src_v3.storage.ir_store import IRStore

class SpringPack(FrameworkProvider):
    """
    Framework provider pack for Spring Boot / Spring MVC (Java).
    """
    framework_name: str = "Spring"

    def detect(self, repo_profile: Dict[str, Any], files: List[str]) -> bool:
        # Detect Spring Boot applications (pom.xml dependency or @SpringBootApplication)
        for f in files:
            if "pom.xml" in f or "build.gradle" in f:
                return True
        return False

    def extract_entrypoints(self, ir_store: IRStore) -> List[Dict[str, Any]]:
        entrypoints = []
        for sn in ir_store.iter_symbol_nodes():
            # Match annotations like @RestController, @GetMapping, @PostMapping, etc.
            content = sn.attributes.get("text", "")
            if "@RequestMapping" in content or "@GetMapping" in content or "@PostMapping" in content:
                entrypoints.append({
                    "node_id": sn.node_id,
                    "route": sn.attributes.get("route", "/api/spring"),
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
