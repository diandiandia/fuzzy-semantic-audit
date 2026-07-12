import os
import json
from typing import List, Dict, Any
from src_v3.providers.embedding.base import EmbeddingProvider, cosine_similarity

class OpenAIProvider(EmbeddingProvider):
    provider_name: str = "OpenAIProvider"
    provider_version_string: str = "openai-python"

    def __init__(self, api_key: str = "", model: str = "text-embedding-3-small"):
        self.api_key = api_key
        self.model_name = model
        self.client = None
        if api_key:
            try:
                import openai
                self.client = openai.OpenAI(api_key=api_key)
            except ImportError:
                pass

    def build_index(self, records: List[Dict[str, Any]], out_dir: str) -> bool:
        if not self.client:
            return False
            
        try:
            os.makedirs(out_dir, exist_ok=True)
            index_path = os.path.join(out_dir, "index_vector.json")
            
            indexed_records = []
            # Batch size of 100
            batch_size = 100
            for i in range(0, len(records), batch_size):
                batch = records[i:i+batch_size]
                texts = [r.get("text", "") for r in batch]
                
                response = self.client.embeddings.create(
                    input=texts,
                    model=self.model_name
                )
                
                for idx, item in enumerate(response.data):
                    r = batch[idx]
                    indexed_records.append({
                        "id": r.get("id"),
                        "text": r.get("text"),
                        "metadata": r.get("metadata", {}),
                        "embedding": item.embedding
                    })
                    
            with open(index_path, 'w', encoding='utf-8') as f:
                json.dump(indexed_records, f, indent=2, ensure_ascii=False)
            return True
        except Exception:
            return False

    def search(self, query: str, out_dir: str, top_k: int) -> List[Dict[str, Any]]:
        if not self.client:
            return []
            
        index_path = os.path.join(out_dir, "index_vector.json")
        if not os.path.exists(index_path):
            return []
            
        try:
            # Get query embedding
            response = self.client.embeddings.create(
                input=[query],
                model=self.model_name
            )
            query_embedding = response.data[0].embedding
            
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
