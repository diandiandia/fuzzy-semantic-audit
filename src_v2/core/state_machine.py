from src_v2.core.models import CandidateRecord
from datetime import datetime

# Allowed state transition map
ALLOWED_TRANSITIONS = {
    "discovered": {"indexed"},
    "indexed": {"recalled"},
    "recalled": {"normalized"},
    "normalized": {"queued_for_verify"},
    "queued_for_verify": {"verifying"},
    "verifying": {"verified", "needs_review", "false_positive", "deferred", "error"},
    "deferred": {"queued_for_verify"},
    "error": {"queued_for_verify"},
}

def can_transition(from_status: str, to_status: str) -> bool:
    """Check if transition from from_status to to_status is allowed."""
    if from_status == to_status:
        return True
    return to_status in ALLOWED_TRANSITIONS.get(from_status, set())

def transition(candidate: CandidateRecord, to_status: str) -> CandidateRecord:
    """Transition candidate to a new status. Raises ValueError if disallowed."""
    if not can_transition(candidate.status, to_status):
        raise ValueError(f"Disallowed state transition from '{candidate.status}' to '{to_status}'")
    
    candidate.status = to_status
    candidate.updated_at = datetime.utcnow().isoformat() + "Z"
    return candidate
