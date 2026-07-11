import os
import json
import hashlib
from pathlib import Path
from typing import Dict, Any, Optional

class IndexCache:
    """
    Handles file-level indexing cache and fingerprint validation.
    """
    def __init__(self, cache_dir: Path):
        self.cache_dir = Path(cache_dir)
        os.makedirs(self.cache_dir, exist_ok=True)
        self.manifest_path = self.cache_dir / "index_cache_manifest.json"
        self.records_dir = self.cache_dir / "records"
        os.makedirs(self.records_dir, exist_ok=True)
        self.manifest = self.load_manifest()

    def load_manifest(self) -> dict:
        if self.manifest_path.exists():
            try:
                with open(self.manifest_path, 'r', encoding='utf-8') as f:
                    return json.load(f)
            except Exception:
                pass
        return {
            "files": {}  # rel_path -> fingerprint dict
        }

    def save_manifest(self, manifest: Optional[dict] = None) -> None:
        if manifest is not None:
            self.manifest = manifest
        with open(self.manifest_path, 'w', encoding='utf-8') as f:
            json.dump(self.manifest, f, indent=2, ensure_ascii=False)

    def _get_record_path(self, rel_path: str) -> Path:
        # Sanitize rel_path to make it a safe filename
        sanitized = rel_path.replace("/", "_").replace("\\", "_").replace("..", "_")
        # Add hash of the original rel_path to prevent collisions
        path_hash = hashlib.md5(rel_path.encode('utf-8')).hexdigest()
        return self.records_dir / f"{sanitized}_{path_hash}.json"

    def get_file_record(self, rel_path: str) -> Optional[dict]:
        path = self._get_record_path(rel_path)
        if path.exists():
            try:
                with open(path, 'r', encoding='utf-8') as f:
                    return json.load(f)
            except Exception:
                pass
        return None

    def put_file_record(self, rel_path: str, record: dict) -> None:
        path = self._get_record_path(rel_path)
        os.makedirs(path.parent, exist_ok=True)
        with open(path, 'w', encoding='utf-8') as f:
            json.dump(record, f, indent=2, ensure_ascii=False)

    def delete_file_record(self, rel_path: str) -> None:
        path = self._get_record_path(rel_path)
        if path.exists():
            try:
                path.unlink()
            except Exception:
                pass
        if rel_path in self.manifest.get("files", {}):
            del self.manifest["files"][rel_path]

    def is_valid(self, rel_path: str, fingerprint: dict) -> bool:
        # Check if the file fingerprint matches
        cached_files = self.manifest.get("files", {})
        if rel_path not in cached_files:
            return False
            
        cached_fp = cached_files[rel_path]
        for k in ["parser_version", "schema_version", "embedding_model", "embedding_config_hash", "chunking_config_hash", "content_hash"]:
            if cached_fp.get(k) != fingerprint.get(k):
                return False
        return True
