from typing import List, Dict, Any
from src_v3.providers.embedding.base import EmbeddingProvider

class CohereProvider(EmbeddingProvider):
    provider_name: str = "CohereProvider"

    def __init__(self, api_key: str = ""):
        self.api_key = api_key

    def build_index(self, records: List[Dict[str, Any]], out_dir: str) -> bool:
        return False

    def search(self, query: str, out_dir: str, top_k: int) -> List[Dict[str, Any]]:
        return []
