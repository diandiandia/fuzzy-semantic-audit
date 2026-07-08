from typing import List, Dict, Any

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
