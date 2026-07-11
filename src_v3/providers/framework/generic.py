from typing import List, Dict, Any
from src_v3.providers.framework.base import FrameworkProvider

class GenericFrameworkProvider(FrameworkProvider):
    framework_name: str = "GenericFrameworkProvider"

    def detect(self, repo_profile: Dict[str, Any], files: List[str]) -> bool:
        return True # Always active as a fallback
