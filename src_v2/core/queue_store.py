import os
import json
import tempfile
from typing import List
from datetime import datetime, timezone

def _get_queue_path(queue_dir: str, queue_name: str) -> str:
    """Get path to the queue file."""
    return os.path.join(queue_dir, f"{queue_name}.json")

def load_queue(queue_dir: str, queue_name: str) -> List[str]:
    """Load candidate IDs from the queue."""
    path = _get_queue_path(queue_dir, queue_name)
    if not os.path.exists(path):
        return []
        
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
            return data.get("candidate_ids", [])
    except Exception:
        return []

def save_queue(queue_dir: str, queue_name: str, candidate_ids: List[str]) -> None:
    """Atomically save candidate IDs to the queue."""
    os.makedirs(queue_dir, exist_ok=True)
    path = _get_queue_path(queue_dir, queue_name)
    
    data = {
        "queue_name": queue_name,
        "candidate_ids": candidate_ids,
        "updated_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
    }
    
    # Atomic write
    fd, temp_path = tempfile.mkstemp(dir=queue_dir)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)
        os.replace(temp_path, path)
    except Exception as e:
        if os.path.exists(temp_path):
            os.remove(temp_path)
        raise e

def enqueue(queue_dir: str, queue_name: str, candidate_ids: List[str]) -> None:
    """Add candidate IDs to the end of the queue, avoiding duplicates."""
    existing = load_queue(queue_dir, queue_name)
    existing_set = set(existing)
    
    added = []
    for cid in candidate_ids:
        if cid not in existing_set:
            added.append(cid)
            existing_set.add(cid)
            
    save_queue(queue_dir, queue_name, existing + added)

def dequeue(queue_dir: str, queue_name: str, limit: int) -> List[str]:
    """Remove and return up to `limit` candidate IDs from the front of the queue."""
    existing = load_queue(queue_dir, queue_name)
    if not existing:
        return []
        
    dequeued = existing[:limit]
    remaining = existing[limit:]
    save_queue(queue_dir, queue_name, remaining)
    return dequeued

def requeue(queue_dir: str, queue_name: str, candidate_ids: List[str]) -> None:
    """Prepend candidate IDs to the front of the queue, avoiding duplicates."""
    existing = load_queue(queue_dir, queue_name)
    existing_set = set(existing)
    
    prepended = []
    for cid in candidate_ids:
        if cid not in existing_set:
            prepended.append(cid)
            existing_set.add(cid)
            
    # Remove from remaining list if they were already there, to avoid duplicates
    clean_existing = [cid for cid in existing if cid not in set(candidate_ids)]
    save_queue(queue_dir, queue_name, prepended + clean_existing)

def peek(queue_dir: str, queue_name: str, limit: int = 10) -> List[str]:
    """Peek at the first few items of the queue without removing them."""
    existing = load_queue(queue_dir, queue_name)
    return existing[:limit]
