from typing import List, Dict, Any
from src_v3.providers.framework.base import FrameworkProvider

class AndroidPack(FrameworkProvider):
    framework_name: str = "AndroidPack"

    def detect(self, repo_profile: Dict[str, Any], files: List[str]) -> bool:
        return "android" in repo_profile.get("frameworks", [])
