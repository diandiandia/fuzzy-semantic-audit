import os
from typing import List, Dict, Any
from src_v3.core.models import LanguageShard, CandidateRecord
from src_v3.core.provider_registry import resolve_embedding
from src_v3.storage.ir_store import IRStore

TRACK_INTENTS = {
    "authz": "check permission, check user auth, verify ownership, role permission check",
    "state_machine": "change state, transition status, update state machine, state check",
    "resource_access": "read file, write db, query database, connect socket, network connection",
    "injection": "execute system command, subprocess shell, sql query command execution",
    "input_validation": "sanitize parameter, input check validator, regex filter check",
    "deserialization": "deserialize object stream, load json pickle dump, unpack package",
    "memory_safety": "free pointer malloc buffer allocation, pointer write unsafe",
    "concurrency": "mutex lock, lock thread synchronization, race condition concurrent",
    "crypto": "encrypt message, decrypt key, generate random cipher, password hash",
    "filesystem_boundary": "join path verify path boundary directory traversal check"
}

def recall_by_vector(
    workspace_dir: str, 
    shard: LanguageShard, 
    track: str, 
    config: Dict[str, Any]
) -> List[CandidateRecord]:
    """
    Recalls candidates by Jaccard lexical or vector search indexing.
    """
    workspace_dir = os.path.abspath(workspace_dir)
    ir_store = IRStore(workspace_dir)
    
    # 1. Resolve embedding provider
    embedding_provider = resolve_embedding(config)
    provider_trace = [embedding_provider.provider_name]
    if embedding_provider.provider_name == "KeywordFallbackProvider":
        provider_trace.append("embedding_fallback: lexical keyword search")
    
    # Locate index path
    index_type = "lexical" if embedding_provider.provider_name == "KeywordFallbackProvider" else "vector"
    index_dir = os.path.join(workspace_dir, "indices", index_type, shard.shard_id)
    
    if not os.path.exists(index_dir):
        return []
        
    from src_v3.packs.tracks import load_track_pack
    track_pack = load_track_pack(track)
    query = track_pack.get("vector_intent") or TRACK_INTENTS.get(track, track)
    top_k = track_pack.get("top_k", 10)
    
    # 2. Query the index
    try:
        search_results = embedding_provider.search(query, index_dir, top_k=top_k)
    except Exception:
        return []
        
    candidates = []
    for match in search_results:
        node_id = match["id"]
        score = match["score"]
        
        # Load the actual symbol node
        sn = ir_store.get_node_by_id(node_id)
        if sn:
            candidates.append(CandidateRecord(
                candidate_id="",
                identity_key="",
                shard_id=shard.shard_id,
                lang=shard.lang,
                file=sn.file,
                symbol=sn.symbol,
                span=sn.span,
                source_tracks=[track],
                matched_rules=[f"vector.{track}.similarity_match"],
                recall_sources=["vector"],
                provider_trace=provider_trace,
                priority_score=score * 100.0, # Scale Jaccard/cosine score to 100
                candidate_capability=shard.capability,
                status="discovered"
            ))
            
    return candidates
