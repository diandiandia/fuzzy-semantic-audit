from typing import List, Dict, Any
from src_v3.providers.framework.base import FrameworkProvider

class SpringPack(FrameworkProvider):
    framework_name: str = "SpringPack"

    def detect(self, repo_profile: Dict[str, Any], files: List[str]) -> bool:
        return "spring" in repo_profile.get("frameworks", [])
