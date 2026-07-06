import os
import json
from typing import List, Dict, Any, Optional

try:
    from fastembed import TextEmbedding
except ImportError:
    TextEmbedding = None

def is_embedding_available() -> bool:
    """Check if fastembed package and embedding capability is available."""
    return TextEmbedding is not None

def build_index(shard_id: str, workspace_dir: str, records: List[Dict[str, Any]]) -> bool:
    """Build and save an embedding index for a shard."""
    if not is_embedding_available():
        # Fallback: write a stub to verify we went through the step
        out_dir = os.path.join(workspace_dir, "indices", shard_id)
        os.makedirs(out_dir, exist_ok=True)
        with open(os.path.join(out_dir, "metadata.json"), "w", encoding="utf-8") as f:
            json.dump(records, f, indent=2)
        return False

    try:
        import numpy as np
        out_dir = os.path.join(workspace_dir, "indices", shard_id)
        os.makedirs(out_dir, exist_ok=True)
        
        texts = [r.get("text", f"{r.get('name', '')} {r.get('file', '')}") for r in records]
        
        model = TextEmbedding(model_name="BAAI/bge-small-en-v1.5")
        vectors = np.array(list(model.embed(texts)))
        
        # Save metadata and vectors
        with open(os.path.join(out_dir, "metadata.json"), "w", encoding="utf-8") as f:
            json.dump(records, f, indent=2)
        np.save(os.path.join(out_dir, "vectors.npy"), vectors)
        return True
    except Exception:
        return False

def search(shard_id: str, workspace_dir: str, query: str, top_k: int = 10) -> List[Dict[str, Any]]:
    """Search for matching records using cosine similarity or simple keyword fallback."""
    out_dir = os.path.join(workspace_dir, "indices", shard_id)
    meta_path = os.path.join(out_dir, "metadata.json")
    vec_path = os.path.join(out_dir, "vectors.npy")

    if not os.path.exists(meta_path):
        return []

    try:
        with open(meta_path, "r", encoding="utf-8") as f:
            metadata = json.load(f)
    except Exception:
        return []

    # If fastembed/vectors are not available, use keyword overlap fallback
    if not is_embedding_available() or not os.path.exists(vec_path):
        # Fallback: simple keyword matching in 'text' field
        query_words = set(query.lower().split())
        scored_results = []
        for meta in metadata:
            text = meta.get("text", f"{meta.get('name', '')} {meta.get('file', '')}").lower()
            # Calculate Jaccard similarity or simple overlap
            overlap = sum(1 for w in query_words if w in text)
            if overlap > 0:
                score = overlap / max(1, len(query_words))
                scored_results.append((meta, score))
        scored_results.sort(key=lambda x: x[1], reverse=True)
        if not scored_results:
            return []
        # Return full metadata dict with score key
        return [dict(r[0], score=r[1]) for r in scored_results[:top_k]]

    try:
        import numpy as np
        vectors = np.load(vec_path)
        model = TextEmbedding(model_name="BAAI/bge-small-en-v1.5")
        ivec = np.array(list(model.embed([query])))[0]
        
        norms = np.linalg.norm(vectors, axis=1) * np.linalg.norm(ivec) + 1e-9
        sims = vectors @ ivec / norms
        
        top_indices = np.argsort(-sims)[:top_k]
        results = []
        for idx in top_indices:
            score = float(sims[idx])
            meta = metadata[idx]
            results.append(dict(meta, score=score))
        return results
    except Exception as e:
        try:
            from src_v2.core.event_log import log_event
            log_event(
                workspace_dir=workspace_dir,
                stage="recall",
                event_type="vector_search_error",
                details={"shard_id": shard_id, "error": str(e)}
            )
        except:
            pass
        return []
