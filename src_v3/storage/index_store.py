import os
import json
from typing import Dict, Any, Optional

class IndexStore:
    """
    Handles storage of indexing metadata (lexical, vector, semantic) for language shards.
    Keeps a registry file under .audit_workspace_v3/indices/index_registry.json.
    """
    def __init__(self, workspace_dir: str):
        self.workspace_dir = os.path.abspath(workspace_dir)
        self.indices_dir = os.path.join(self.workspace_dir, "indices")
        os.makedirs(self.indices_dir, exist_ok=True)
        self.registry_path = os.path.join(self.indices_dir, "index_registry.json")
        
        self.registry = self._load()

    def _load(self) -> Dict[str, Any]:
        if os.path.exists(self.registry_path):
            try:
                with open(self.registry_path, 'r', encoding='utf-8') as f:
                    return json.load(f)
            except Exception:
                return {}
        return {}

    def save(self) -> None:
        with open(self.registry_path, 'w', encoding='utf-8') as f:
            json.dump(self.registry, f, indent=2, ensure_ascii=False)

    def register_index(
        self, 
        shard_id: str, 
        index_type: str, 
        status: str, 
        path: str, 
        metadata: Optional[Dict[str, Any]] = None
    ) -> None:
        """
        Registers or updates index status for a shard.
        index_type: e.g. "lexical", "vector", "semantic"
        status: e.g. "indexed", "indexed_fallback", "failed"
        """
        if shard_id not in self.registry:
            self.registry[shard_id] = {}
            
        self.registry[shard_id][index_type] = {
            "status": status,
            "path": os.path.relpath(path, self.workspace_dir) if os.path.isabs(path) else path,
            "metadata": metadata or {}
        }
        self.save()

    def get_index_status(self, shard_id: str) -> Dict[str, Any]:
        """
        Returns indexing status for all types under a shard.
        """
        return self.registry.get(shard_id, {})

    def load_semantic_index(self, shard_id: str) -> Dict[str, Any]:
        """
        Loads the compiled semantic index data for a shard if available.
        """
        shard_info = self.registry.get(shard_id, {})
        sem_info = shard_info.get("semantic", {})
        if sem_info and sem_info.get("status") in ["indexed", "indexed_fallback"]:
            idx_rel = sem_info.get("path")
            if idx_rel:
                idx_path = os.path.join(self.workspace_dir, idx_rel, "semantic_index.json")
                if os.path.exists(idx_path):
                    try:
                        with open(idx_path, 'r', encoding='utf-8') as f:
                            return json.load(f)
                    except Exception:
                        return {}
        return {}
