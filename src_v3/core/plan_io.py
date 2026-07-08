import json
import os
import datetime
from typing import Dict, Any
from src_v3.core.models import AuditPlan, RunManifest

def load_plan(plan_path: str) -> AuditPlan:
    """
    Loads an AuditPlan from a JSON file.
    """
    if not os.path.exists(plan_path):
        raise FileNotFoundError(f"Audit plan file not found: {plan_path}")
    with open(plan_path, 'r', encoding='utf-8') as f:
        data = json.load(f)
    return AuditPlan.from_dict(data)

def save_plan(plan: AuditPlan, plan_path: str) -> None:
    """
    Saves an AuditPlan to a JSON file, updating the updated_at timestamp.
    """
    # Ensure parent directory exists
    os.makedirs(os.path.dirname(os.path.abspath(plan_path)), exist_ok=True)
    
    current_time = datetime.datetime.now(datetime.timezone.utc).isoformat()
    if not plan.created_at:
        plan.created_at = current_time
    plan.updated_at = current_time
    
    data = plan.to_dict()
    with open(plan_path, 'w', encoding='utf-8') as f:
        json.dump(data, f, indent=2, ensure_ascii=False)

def load_run_manifest(manifest_path: str) -> RunManifest:
    """
    Loads a RunManifest from a JSON file.
    """
    if not os.path.exists(manifest_path):
        raise FileNotFoundError(f"Run manifest file not found: {manifest_path}")
    with open(manifest_path, 'r', encoding='utf-8') as f:
        data = json.load(f)
    return RunManifest.from_dict(data)

def save_run_manifest(manifest: RunManifest, manifest_path: str) -> None:
    """
    Saves a RunManifest to a JSON file.
    """
    os.makedirs(os.path.dirname(os.path.abspath(manifest_path)), exist_ok=True)
    data = manifest.to_dict()
    with open(manifest_path, 'w', encoding='utf-8') as f:
        json.dump(data, f, indent=2, ensure_ascii=False)

def update_plan_summary(plan_path: str, summary_updates: Dict[str, Any]) -> None:
    """
    Updates the summary section of an existing audit plan.
    """
    plan = load_plan(plan_path)
    plan.summary.update(summary_updates)
    save_plan(plan, plan_path)
