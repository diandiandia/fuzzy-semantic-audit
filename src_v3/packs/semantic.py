import os
import json
from typing import Dict, Any, List

# Standard provider preference fallback registry
SEMANTIC_PACKS = {}

base_dir = os.path.dirname(os.path.abspath(__file__))
semantic_dir = os.path.join(base_dir, "semantic")

def load_semantic_pack(lang: str) -> Dict[str, Any]:
    """
    Loads a versioned semantic pack config for the given language.
    """
    lang_dir = os.path.join(semantic_dir, lang)
    if not os.path.exists(lang_dir):
        return {
            "version": "1.0.0-default",
            "provider_preference": ["lsp", "lsif", "ctags"] if lang not in ["cpp", "c"] else ["lsp", "ctags"],
            "fuzzy_resolution_policy": "enclosing_function",
            "edge_normalization": {}
        }
        
    version = "1.0.0"
    version_path = os.path.join(lang_dir, "version.txt")
    if os.path.exists(version_path):
        try:
            with open(version_path, 'r', encoding='utf-8') as f:
                version = f.read().strip()
        except Exception:
            pass
            
    config_path = os.path.join(lang_dir, "config.json")
    config = {}
    if os.path.exists(config_path):
        try:
            with open(config_path, 'r', encoding='utf-8') as f:
                config = json.load(f)
        except Exception:
            pass
            
    return {
        "version": version,
        "provider_preference": config.get("provider_preference", ["lsp", "lsif", "ctags"]),
        "fuzzy_resolution_policy": config.get("fuzzy_resolution_policy", "enclosing_function"),
        "edge_normalization": config.get("edge_normalization", {})
    }

# Populate legacy SEMANTIC_PACKS for backward compatibility
if os.path.exists(semantic_dir):
    for lang in os.listdir(semantic_dir):
        if os.path.isdir(os.path.join(semantic_dir, lang)):
            pack = load_semantic_pack(lang)
            SEMANTIC_PACKS[lang] = pack["provider_preference"]
else:
    SEMANTIC_PACKS = {
        "python": ["lsp", "lsif", "ctags"],
        "javascript": ["lsp", "lsif", "ctags"],
        "go": ["lsp", "lsif", "ctags"],
        "java": ["lsp", "lsif", "ctags"],
        "cpp": ["lsp", "ctags"],
        "c": ["lsp", "ctags"]
    }
