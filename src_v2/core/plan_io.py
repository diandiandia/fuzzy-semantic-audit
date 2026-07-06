import os
import tempfile
from datetime import datetime
from typing import List
from src_v2.core.models import AuditPlan, CandidateRecord, PlanSummary

def load_plan(plan_path: str) -> AuditPlan:
    """Load AuditPlan from plan_path."""
    if not os.path.exists(plan_path):
        raise FileNotFoundError(f"Audit plan file not found at {plan_path}")
    with open(plan_path, "r", encoding="utf-8") as f:
        content = f.read()
    return AuditPlan.model_validate_json(content)

def save_plan(plan: AuditPlan, plan_path: str) -> None:
    """Atomically save AuditPlan to plan_path."""
    plan.updated_at = datetime.utcnow().isoformat() + "Z"
    
    dir_name = os.path.dirname(plan_path)
    if dir_name:
        os.makedirs(dir_name, exist_ok=True)
        
    # Atomic write pattern
    fd, temp_path = tempfile.mkstemp(dir=dir_name)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            f.write(plan.model_dump_json(indent=2))
        os.replace(temp_path, plan_path)
    except Exception as e:
        if os.path.exists(temp_path):
            os.remove(temp_path)
        raise e

def update_plan_summary(plan_path: str, candidates: List[CandidateRecord]) -> AuditPlan:
    """Update summary of AuditPlan based on candidates and save it."""
    plan = load_plan(plan_path)
    
    # Update shard statuses based on candidate finality
    from collections import defaultdict
    shard_cands = defaultdict(list)
    for c in candidates:
        shard_cands[c.shard_id].append(c)
        
    for shard in plan.language_shards:
        cands = shard_cands[shard.shard_id]
        if cands:
            all_final = all(c.status in {"verified", "needs_review", "false_positive", "error"} for c in cands)
            if all_final:
                shard.status = "verified"
                
    shards_total = len(plan.language_shards)
    tracks_total = len(plan.audit_tracks)
    
    summary = PlanSummary(
        shards_total=shards_total,
        tracks_total=tracks_total,
        candidates_total=len(candidates),
        verified=sum(1 for c in candidates if c.status == "verified"),
        needs_review=sum(1 for c in candidates if c.status == "needs_review"),
        false_positive=sum(1 for c in candidates if c.status == "false_positive"),
        deferred=sum(1 for c in candidates if c.status == "deferred"),
        error=sum(1 for c in candidates if c.status == "error")
    )
    
    plan.summary = summary
    save_plan(plan, plan_path)
    return plan
