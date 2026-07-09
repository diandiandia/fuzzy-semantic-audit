from typing import Any, Dict, Optional
import datetime
from src_v3.core.enums import ShardStatus, CandidateStatus
from src_v3.core.models import LanguageShard, CandidateRecord

# Valid shard transitions
SHARD_TRANSITIONS = {
    ShardStatus.DISCOVERED: {ShardStatus.PARSED, ShardStatus.PARSED_FALLBACK, ShardStatus.FAILED},
    ShardStatus.PARSED: {ShardStatus.INDEXED, ShardStatus.INDEXED_FALLBACK, ShardStatus.FAILED},
    ShardStatus.PARSED_FALLBACK: {ShardStatus.INDEXED, ShardStatus.INDEXED_FALLBACK, ShardStatus.FAILED},
    ShardStatus.INDEXED: {ShardStatus.RECALLED, ShardStatus.RECALLED_FALLBACK, ShardStatus.PARSED, ShardStatus.FAILED},
    ShardStatus.INDEXED_FALLBACK: {ShardStatus.RECALLED, ShardStatus.RECALLED_FALLBACK, ShardStatus.PARSED, ShardStatus.FAILED},
    ShardStatus.RECALLED: {ShardStatus.DISCOVERED, ShardStatus.PARSED, ShardStatus.PARSED_FALLBACK},
    ShardStatus.RECALLED_FALLBACK: {ShardStatus.DISCOVERED, ShardStatus.PARSED, ShardStatus.PARSED_FALLBACK},
    ShardStatus.FAILED: {ShardStatus.DISCOVERED, ShardStatus.PARSED, ShardStatus.PARSED_FALLBACK}
}

# Valid candidate transitions
CANDIDATE_TRANSITIONS = {
    CandidateStatus.DISCOVERED: {CandidateStatus.RECALLED, CandidateStatus.ERROR},
    CandidateStatus.RECALLED: {CandidateStatus.NORMALIZED, CandidateStatus.ERROR},
    CandidateStatus.NORMALIZED: {CandidateStatus.PRUNED, CandidateStatus.ERROR},
    CandidateStatus.PRUNED: {CandidateStatus.EVIDENCE_READY, CandidateStatus.NEEDS_REVIEW, CandidateStatus.DEFERRED, CandidateStatus.ERROR},
    CandidateStatus.EVIDENCE_READY: {CandidateStatus.QUEUED_FOR_VERIFY, CandidateStatus.NEEDS_REVIEW, CandidateStatus.DEFERRED, CandidateStatus.ERROR},
    CandidateStatus.QUEUED_FOR_VERIFY: {CandidateStatus.VERIFYING, CandidateStatus.ERROR},
    CandidateStatus.VERIFYING: {
        CandidateStatus.VERIFIED,
        CandidateStatus.NEEDS_REVIEW,
        CandidateStatus.FALSE_POSITIVE,
        CandidateStatus.DEFERRED,
        CandidateStatus.ERROR
    },
    CandidateStatus.DEFERRED: {CandidateStatus.QUEUED_FOR_VERIFY, CandidateStatus.ERROR},
    CandidateStatus.NEEDS_REVIEW: {CandidateStatus.QUEUED_FOR_VERIFY, CandidateStatus.ERROR},
    CandidateStatus.FALSE_POSITIVE: {CandidateStatus.QUEUED_FOR_VERIFY, CandidateStatus.ERROR},
    CandidateStatus.VERIFIED: {CandidateStatus.QUEUED_FOR_VERIFY, CandidateStatus.ERROR},
    CandidateStatus.ERROR: {CandidateStatus.DISCOVERED, CandidateStatus.QUEUED_FOR_VERIFY}
}

def can_transition(kind: str, from_status: str, to_status: str) -> bool:
    """
    Checks if a status transition is valid.
    """
    if from_status == to_status:
        return True
        
    if kind == "shard":
        # Standardize strings to enums if they are strings
        try:
            from_enum = ShardStatus(from_status)
            to_enum = ShardStatus(to_status)
        except ValueError:
            return False
        allowed = SHARD_TRANSITIONS.get(from_enum, set())
        return to_enum in allowed
        
    elif kind == "candidate":
        try:
            from_enum = CandidateStatus(from_status)
            to_enum = CandidateStatus(to_status)
        except ValueError:
            return False
            
        # DoD Constraint: deferred cannot directly transition to verified
        if from_enum == CandidateStatus.DEFERRED and to_enum == CandidateStatus.VERIFIED:
            return False
            
        allowed = CANDIDATE_TRANSITIONS.get(from_enum, set())
        return to_enum in allowed
        
    return False

def transition(obj: Any, to_status: str, metadata: Optional[Dict[str, Any]] = None, workspace_dir: Optional[str] = None) -> Any:
    """
    Transitions the object status if allowed, and returns the modified object.
    Raises ValueError if transition is invalid.
    """
    kind = ""
    if isinstance(obj, LanguageShard):
        kind = "shard"
    elif isinstance(obj, CandidateRecord):
        kind = "candidate"
    else:
        # Also support dicts with 'status' key
        if isinstance(obj, dict) and "status" in obj:
            if "shard_id" in obj:
                kind = "shard"
            elif "candidate_id" in obj:
                kind = "candidate"
                
    if not kind:
        raise ValueError(f"Unknown object type for transition: {type(obj)}")
        
    current_status = obj.status if not isinstance(obj, dict) else obj["status"]
    
    if not can_transition(kind, current_status, to_status):
        raise ValueError(f"Invalid transition for {kind}: {current_status} -> {to_status}")
        
    import datetime
    now_str = datetime.datetime.now(datetime.timezone.utc).isoformat()
    
    if isinstance(obj, dict):
        obj["status"] = to_status
        obj["updated_at"] = now_str
        if metadata:
            obj.setdefault("metadata", {}).update(metadata)
    else:
        obj.status = to_status
        # Dynamically set updated_at attribute if it exists or add it
        obj.updated_at = now_str
        
    # Trigger critical state transition event logging
    from src_v3.core.event_log import log_event
    log_event(
        workspace_dir or ".",
        "state_machine",
        "info",
        f"State transitioned for {kind}: {current_status} -> {to_status}",
        {
            "kind": kind,
            "from": current_status,
            "to": to_status,
            "updated_at": now_str,
            "metadata": metadata
        }
    )
    return obj
