import os
import json
from typing import List, Dict, Any
from src_v3.providers.embedding.base import EmbeddingProvider, cosine_similarity

class FastEmbedProvider(EmbeddingProvider):
    provider_name: str = "FastEmbedProvider"

    def __init__(self):
        self.available = False
        self.model = None
        try:
            from fastembed import TextEmbedding
            self.model = TextEmbedding()
            self.available = True
        except ImportError:
            self.available = False

    def build_index(self, records: List[Dict[str, Any]], out_dir: str) -> bool:
        if not self.available or not self.model:
            return False
            
        try:
            os.makedirs(out_dir, exist_ok=True)
            index_path = os.path.join(out_dir, "index_vector.json")
            
            texts = [r.get("text", "") for r in records]
            # model.embed returns a generator of numpy arrays
            embeddings_gen = self.model.embed(texts)
            
            indexed_records = []
            for idx, embedding in enumerate(embeddings_gen):
                r = records[idx]
                indexed_records.append({
                    "id": r.get("id"),
                    "text": r.get("text"),
                    "metadata": r.get("metadata", {}),
                    "embedding": embedding.tolist()
                })
                
            with open(index_path, 'w', encoding='utf-8') as f:
                json.dump(indexed_records, f, indent=2, ensure_ascii=False)
            return True
        except Exception:
            return False

    def search(self, query: str, out_dir: str, top_k: int) -> List[Dict[str, Any]]:
        if not self.available or not self.model:
            return []
            
        index_path = os.path.join(out_dir, "index_vector.json")
        if not os.path.exists(index_path):
            return []
            
        try:
            # model.embed takes list of texts
            query_embedding = list(self.model.embed([query]))[0].tolist()
            
            with open(index_path, 'r', encoding='utf-8') as f:
                records = json.load(f)
                
            results = []
            for r in records:
                doc_embedding = r.get("embedding")
                if doc_embedding:
                    score = cosine_similarity(query_embedding, doc_embedding)
                    if score > 0.0:
                        results.append({
                            "id": r["id"],
                            "score": score,
                            "metadata": r["metadata"]
                        })
                        
            results.sort(key=lambda x: x["score"], reverse=True)
            return results[:top_k]
        except Exception:
            return []
