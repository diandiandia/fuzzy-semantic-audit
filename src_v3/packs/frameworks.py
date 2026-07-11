import os
import json
from typing import Dict, Any

FRAMEWORK_PACKS = {}

base_dir = os.path.dirname(os.path.abspath(__file__))
frameworks_dir = os.path.join(base_dir, "frameworks")

def load_framework_pack(fw: str) -> Dict[str, Any]:
    """
    Loads a versioned framework pack config for the given framework.
    """
    fw_dir = os.path.join(frameworks_dir, fw)
    if not os.path.exists(fw_dir):
        return {
            "version": "1.0.0-default",
            "route_patterns": [],
            "guard_patterns": [],
            "resource_patterns": [],
            "state_machine_patterns": []
        }
        
    version = "1.0.0"
    version_path = os.path.join(fw_dir, "version.txt")
    if os.path.exists(version_path):
        try:
            with open(version_path, 'r', encoding='utf-8') as f:
                version = f.read().strip()
        except Exception:
            pass
            
    config_path = os.path.join(fw_dir, "config.json")
    config = {}
    if os.path.exists(config_path):
        try:
            with open(config_path, 'r', encoding='utf-8') as f:
                config = json.load(f)
        except Exception:
            pass
            
    return {
        "version": version,
        "route_patterns": config.get("route_patterns", []),
        "guard_patterns": config.get("guard_patterns", []),
        "resource_patterns": config.get("resource_patterns", []),
        "state_machine_patterns": config.get("state_machine_patterns", [])
    }

# Populate legacy FRAMEWORK_PACKS for backward compatibility
if os.path.exists(frameworks_dir):
    for fw in os.listdir(frameworks_dir):
        if os.path.isdir(os.path.join(frameworks_dir, fw)):
            mapping = {
                "django": "DjangoPack",
                "express": "ExpressPack",
                "spring": "SpringPack",
                "gin": "GinPack",
                "android": "AndroidPack",
                "generic": "GenericFrameworkProvider"
            }
            FRAMEWORK_PACKS[fw] = mapping.get(fw, "GenericFrameworkProvider")
else:
    FRAMEWORK_PACKS = {
        "django": "DjangoPack",
        "express": "ExpressPack",
        "spring": "SpringPack",
        "gin": "GinPack",
        "android": "AndroidPack",
        "generic": "GenericFrameworkProvider"
    }
