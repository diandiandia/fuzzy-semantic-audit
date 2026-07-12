import os
import json
import re
from typing import List, Dict, Any
from src_v3.providers.embedding.base import EmbeddingProvider

class KeywordFallbackProvider(EmbeddingProvider):
    provider_name: str = "KeywordFallbackProvider"
    model_name: str = "jaccard-lexical"
    provider_version_string: str = "1.0.0"

    def _tokenize(self, text: str) -> Set:
        """
        Tokenizes text into a set of lowercase alphanumeric words.
        """
        return set(re.findall(r'\b[a-zA-Z0-9_]+\b', text.lower()))

    def build_index(self, records: List[Dict[str, Any]], out_dir: str) -> bool:
        """
        Builds Jaccard index and writes to index.json in out_dir.
        """
        os.makedirs(out_dir, exist_ok=True)
        index_path = os.path.join(out_dir, "index.json")
        
        indexed_records = []
        for r in records:
            text = r.get("text", "")
            indexed_records.append({
                "id": r.get("id"),
                "text": text,
                "metadata": r.get("metadata", {}),
                "tokens": list(self._tokenize(text))
            })
            
        with open(index_path, 'w', encoding='utf-8') as f:
            json.dump(indexed_records, f, indent=2, ensure_ascii=False)
        return True

    def search(self, query: str, out_dir: str, top_k: int) -> List[Dict[str, Any]]:
        """
        Loads Jaccard index and performs Jaccard similarity search.
        """
        index_path = os.path.join(out_dir, "index.json")
        if not os.path.exists(index_path):
            return []
            
        with open(index_path, 'r', encoding='utf-8') as f:
            records = json.load(f)
            
        query_tokens = self._tokenize(query)
        if not query_tokens:
            return []
            
        results = []
        for r in records:
            doc_tokens = set(r.get("tokens", []))
            intersection = query_tokens.intersection(doc_tokens)
            union = query_tokens.union(doc_tokens)
            
            # Jaccard score
            score = len(intersection) / len(union) if union else 0.0
            
            # Simple substring boost: if exact query exists in text, boost score
            if query.lower() in r.get("text", "").lower():
                score = max(score, 0.8) + 0.1 # Boost score
                
            if score > 0.0:
                results.append({
                    "id": r["id"],
                    "score": min(1.0, score),
                    "metadata": r["metadata"]
                })
                
        # Sort by score desc
        results.sort(key=lambda x: x["score"], reverse=True)
        return results[:top_k]
