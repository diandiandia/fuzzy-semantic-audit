import os
import tempfile
import json
from typing import List, Optional, Dict
from datetime import datetime
from src_v2.core.models import CandidateRecord, Span
from src_v2.core.state_machine import transition

def make_identity_key(shard_id: str, file_path: str, symbol: str, start: int, end: int) -> str:
    """Generate stable identity key."""
    return f"{shard_id}|{file_path}|{symbol}|{start}|{end}"

def make_candidate_id(shard_id: str, file_path: str, symbol: str, start: int, end: int) -> str:
    """Generate stable candidate ID."""
    return f"cand_{shard_id}_{file_path}_{symbol}_{start}_{end}"

def load_candidates(registry_path: str, status: Optional[str] = None) -> List[CandidateRecord]:
    """Load candidates from JSONL registry."""
    candidates = []
    if not os.path.exists(registry_path):
        return candidates
        
    with open(registry_path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                candidate = CandidateRecord.model_validate_json(line)
                if status is None or candidate.status == status:
                    candidates.append(candidate)
            except Exception as e:
                from src_v2.core.event_log import log_event
                workspace_dir = os.path.dirname(registry_path)
                log_event(
                    workspace_dir=workspace_dir,
                    stage="core",
                    event_type="corrupt_registry_line",
                    details={"line": line, "error": str(e)}
                )
                raise ValueError(f"Corrupt registry line: {line}. Error: {str(e)}")
    return candidates

def save_candidates(registry_path: str, candidates: List[CandidateRecord]) -> None:
    """Atomically save all candidates to JSONL registry."""
    dir_name = os.path.dirname(registry_path)
    if dir_name:
        os.makedirs(dir_name, exist_ok=True)
        
    fd, temp_path = tempfile.mkstemp(dir=dir_name)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            for c in candidates:
                f.write(c.model_dump_json() + "\n")
        os.replace(temp_path, registry_path)
    except Exception as e:
        if os.path.exists(temp_path):
            os.remove(temp_path)
        raise e

def upsert_candidates(registry_path: str, new_records: List[CandidateRecord]) -> int:
    """Upsert candidates into JSONL registry. Returns number of records added or updated."""
    existing = load_candidates(registry_path)
    existing_map: Dict[str, CandidateRecord] = {c.identity_key: c for c in existing}
    
    updated_count = 0
    for new_rec in new_records:
        key = new_rec.identity_key
        if key in existing_map:
            old_rec = existing_map[key]
            # Merge fields
            merged_tracks = sorted(list(set(old_rec.source_tracks + new_rec.source_tracks)))
            merged_rules = sorted(list(set(old_rec.matched_rules + new_rec.matched_rules)))
            merged_sources = sorted(list(set(old_rec.recall_sources + new_rec.recall_sources)))
            
            # Update only if fields changed or priority changed
            has_changes = (
                old_rec.source_tracks != merged_tracks or
                old_rec.matched_rules != merged_rules or
                old_rec.recall_sources != merged_sources or
                old_rec.priority != max(old_rec.priority, new_rec.priority)
            )
            
            if has_changes:
                old_rec.source_tracks = merged_tracks
                old_rec.matched_rules = merged_rules
                old_rec.recall_sources = merged_sources
                old_rec.priority = max(old_rec.priority, new_rec.priority)
                old_rec.updated_at = datetime.utcnow().isoformat() + "Z"
                updated_count += 1
        else:
            existing_map[key] = new_rec
            updated_count += 1
            
    save_candidates(registry_path, list(existing_map.values()))
    return updated_count

def get_candidate(registry_path: str, candidate_id: str) -> Optional[CandidateRecord]:
    """Get candidate by ID."""
    candidates = load_candidates(registry_path)
    for c in candidates:
        if c.candidate_id == candidate_id:
            return c
    return None

def update_candidate_status(registry_path: str, candidate_id: str, new_status: str) -> Optional[CandidateRecord]:
    """Transition candidate status and save back to registry."""
    candidates = load_candidates(registry_path)
    target = None
    for c in candidates:
        if c.candidate_id == candidate_id:
            transition(c, new_status)
            target = c
            break
            
    if target:
        save_candidates(registry_path, candidates)
    return target
