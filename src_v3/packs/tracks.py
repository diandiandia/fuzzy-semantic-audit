import os
import yaml
from typing import Dict, Any, List

AUDIT_TRACKS = {}

base_dir = os.path.dirname(os.path.abspath(__file__))
tracks_dir = os.path.join(base_dir, "tracks")

def load_track_pack(track: str) -> Dict[str, Any]:
    """
    Loads a versioned track pack for the given track.
    """
    track_dir = os.path.join(tracks_dir, track)
    if not os.path.exists(track_dir):
        return {
            "version": "1.0.0-default",
            "rules": []
        }
        
    version = "1.0.0"
    version_path = os.path.join(track_dir, "version.txt")
    if os.path.exists(version_path):
        try:
            with open(version_path, 'r', encoding='utf-8') as f:
                version = f.read().strip()
        except Exception:
            pass
            
    rules_path = os.path.join(track_dir, "rules.yaml")
    rules = []
    if os.path.exists(rules_path):
        try:
            with open(rules_path, 'r', encoding='utf-8') as f:
                data = yaml.safe_load(f)
                rules = data.get("rules", [])
        except Exception:
            pass
            
    return {
        "version": version,
        "rules": rules
    }

# Populate legacy AUDIT_TRACKS for backward compatibility
if os.path.exists(tracks_dir):
    for track in os.listdir(tracks_dir):
        if os.path.isdir(os.path.join(tracks_dir, track)):
            AUDIT_TRACKS[track] = os.path.join(tracks_dir, track)
else:
    # Fallback to default mapping
    for track in [
        "authz", "state_machine", "resource_access", "injection", "input_validation",
        "deserialization", "memory_safety", "concurrency", "crypto", "filesystem_boundary"
    ]:
        AUDIT_TRACKS[track] = os.path.join(base_dir, "tracks", track)
