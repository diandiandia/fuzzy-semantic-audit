from typing import List, Dict, Any
from src_v3.providers.framework.base import FrameworkProvider

class ExpressPack(FrameworkProvider):
    framework_name: str = "ExpressPack"

    def detect(self, repo_profile: Dict[str, Any], files: List[str]) -> bool:
        return "express" in repo_profile.get("frameworks", [])
