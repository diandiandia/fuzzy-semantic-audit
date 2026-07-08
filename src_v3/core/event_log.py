import json
import os
import datetime
from typing import Dict, Any, Optional

def log_event(workspace_dir: str, stage: str, event_type: str, message: str, metadata: Optional[Dict[str, Any]] = None) -> None:
    """
    Logs an event to event_log.jsonl in the workspace directory.
    """
    log_dir = os.path.abspath(workspace_dir)
    os.makedirs(log_dir, exist_ok=True)
    log_path = os.path.join(log_dir, "event_log.jsonl")
    
    event = {
        "timestamp": datetime.datetime.now(datetime.timezone.utc).isoformat(),
        "stage": stage,
        "event_type": event_type,
        "message": message,
        "metadata": metadata or {}
    }
    
    # Use append mode to write to the jsonl file
    with open(log_path, 'a', encoding='utf-8') as f:
        f.write(json.dumps(event, ensure_ascii=False) + "\n")
