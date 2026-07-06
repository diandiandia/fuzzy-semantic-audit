import os
import json
import tempfile
from datetime import datetime
from typing import Dict, Any

def log_event(
    workspace_dir: str,
    stage: str,
    event_type: str,
    details: Dict[str, Any]
) -> None:
    """Log an event atomically to event_log.jsonl in the workspace."""
    os.makedirs(workspace_dir, exist_ok=True)
    log_path = os.path.join(workspace_dir, "event_log.jsonl")
    
    event = {
        "timestamp": datetime.utcnow().isoformat() + "Z",
        "stage": stage,
        "event_type": event_type,
        "details": details
    }
    
    # We can append directly to the file
    try:
        with open(log_path, "a", encoding="utf-8") as f:
            f.write(json.dumps(event) + "\n")
    except Exception:
        # Ignore logging errors to avoid blocking primary execution
        pass
