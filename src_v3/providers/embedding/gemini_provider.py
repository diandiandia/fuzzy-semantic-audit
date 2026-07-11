import os
import json
from typing import List, Dict, Any
from src_v3.providers.embedding.base import EmbeddingProvider, cosine_similarity

class GeminiProvider(EmbeddingProvider):
    provider_name: str = "GeminiProvider"

    def __init__(self, api_key: str = ""):
        self.api_key = api_key
        self.configured = False
        if api_key:
            try:
                import google.generativeai as genai
                genai.configure(api_key=api_key)
                self.configured = True
            except ImportError:
                pass

    def build_index(self, records: List[Dict[str, Any]], out_dir: str) -> bool:
        if not self.configured:
            return False
            
        try:
            import google.generativeai as genai
            os.makedirs(out_dir, exist_ok=True)
            index_path = os.path.join(out_dir, "index_vector.json")
            
            indexed_records = []
            # Batch size of 100
            batch_size = 100
            for i in range(0, len(records), batch_size):
                batch = records[i:i+batch_size]
                texts = [r.get("text", "") for r in batch]
                
                response = genai.embed_content(
                    model="models/embedding-001",
                    content=texts,
                    task_type="retrieval_document"
                )
                
                # embed_content returns a dict/object with 'embedding' list of lists
                embeddings = response.get("embedding", [])
                for idx, embedding in enumerate(embeddings):
                    r = batch[idx]
                    indexed_records.append({
                        "id": r.get("id"),
                        "text": r.get("text"),
                        "metadata": r.get("metadata", {}),
                        "embedding": embedding
                    })
                    
            with open(index_path, 'w', encoding='utf-8') as f:
                json.dump(indexed_records, f, indent=2, ensure_ascii=False)
            return True
        except Exception:
            return False

    def search(self, query: str, out_dir: str, top_k: int) -> List[Dict[str, Any]]:
        if not self.configured:
            return []
            
        index_path = os.path.join(out_dir, "index_vector.json")
        if not os.path.exists(index_path):
            return []
            
        try:
            import google.generativeai as genai
            response = genai.embed_content(
                model="models/embedding-001",
                content=query,
                task_type="retrieval_query"
            )
            query_embedding = response.get("embedding", [])
            if not query_embedding:
                return []
                
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
