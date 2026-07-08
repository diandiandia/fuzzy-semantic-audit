from typing import List, Dict, Any
from src_v3.providers.embedding.base import EmbeddingProvider

class FastEmbedProvider(EmbeddingProvider):
    provider_name: str = "FastEmbedProvider"

    def __init__(self):
        self.available = False
        try:
            import fastembed
            self.available = True
        except ImportError:
            self.available = False

    def build_index(self, records: List[Dict[str, Any]], out_dir: str) -> bool:
        return False # Fall back if not loaded/supported in this env

    def search(self, query: str, out_dir: str, top_k: int) -> List[Dict[str, Any]]:
        return []
