import math
from typing import List, Dict, Any

def cosine_similarity(v1: List[float], v2: List[float]) -> float:
    if not v1 or not v2 or len(v1) != len(v2):
        return 0.0
    dot_product = sum(x * y for x, y in zip(v1, v2))
    norm_v1 = math.sqrt(sum(x * x for x in v1))
    norm_v2 = math.sqrt(sum(x * x for x in v2))
    if norm_v1 == 0.0 or norm_v2 == 0.0:
        return 0.0
    return dot_product / (norm_v1 * norm_v2)

class EmbeddingProvider:
    """
    Base class / interface for building vector or lexical indices and searching them.
    """
    provider_name: str = "BaseEmbeddingProvider"

    def build_index(self, records: List[Dict[str, Any]], out_dir: str) -> bool:
        """
        Builds an index from list of records and writes it to out_dir.
        records: list of dict, e.g. [{"id": str, "text": str, "metadata": dict}]
        """
        raise NotImplementedError

    def search(self, query: str, out_dir: str, top_k: int) -> List[Dict[str, Any]]:
        """
        Searches the index and returns list of matching records with similarity score.
        Returns: list of dict, e.g. [{"id": str, "score": float, "metadata": dict}]
        """
        raise NotImplementedError
