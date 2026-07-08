import os
from typing import Dict, Any, Optional

class QueryLoader:
    def __init__(self, query_packs_dir: Optional[str] = None):
        if not query_packs_dir:
            # Default to src_v3/packs/languages
            base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
            query_packs_dir = os.path.join(base_dir, "packs", "languages")
        self.query_packs_dir = query_packs_dir

    def load_query_pack(self, lang: str) -> Dict[str, Any]:
        """
        Loads all tree-sitter query patterns (.scm files) for a given language.
        Returns a dict: {"queries": dict of name to scm string, "version": str}
        """
        lang_dir = os.path.join(self.query_packs_dir, lang)
        queries = {}
        version = "1.0.0-default"
        
        if os.path.exists(lang_dir):
            # Check for version file
            version_path = os.path.join(lang_dir, "version.txt")
            if os.path.exists(version_path):
                try:
                    with open(version_path, 'r', encoding='utf-8') as f:
                        version = f.read().strip()
                except Exception:
                    pass
            
            # Load all .scm files
            for file in os.listdir(lang_dir):
                if file.endswith(".scm"):
                    name = os.path.splitext(file)[0]
                    file_path = os.path.join(lang_dir, file)
                    try:
                        with open(file_path, 'r', encoding='utf-8') as f:
                            queries[name] = f.read()
                    except Exception:
                        pass
                        
        return {
            "queries": queries,
            "version": version
        }
