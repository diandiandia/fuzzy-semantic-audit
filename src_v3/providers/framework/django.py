import os
from typing import List, Dict, Any
from src_v3.providers.framework.base import FrameworkProvider

class DjangoPack(FrameworkProvider):
    framework_name: str = "DjangoPack"

    def detect(self, repo_profile: Dict[str, Any], files: List[str]) -> bool:
        return "django" in repo_profile.get("frameworks", [])
