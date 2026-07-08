import os
import json
from typing import List, Dict, Any

class QueueStore:
    """
    Handles read, write, and clear operations for the verification queues:
    verify_now.json, manual_review.json, deferred.json under .audit_workspace_v3/queues/.
    """
    def __init__(self, workspace_dir: str):
        self.workspace_dir = os.path.abspath(workspace_dir)
        self.queues_dir = os.path.join(self.workspace_dir, "queues")
        os.makedirs(self.queues_dir, exist_ok=True)
        
        self.verify_now_path = os.path.join(self.queues_dir, "verify_now.json")
        self.manual_review_path = os.path.join(self.queues_dir, "manual_review.json")
        self.deferred_path = os.path.join(self.queues_dir, "deferred.json")

    def load_verify_now(self) -> List[Dict[str, Any]]:
        if not os.path.exists(self.verify_now_path):
            return []
        try:
            with open(self.verify_now_path, 'r', encoding='utf-8') as f:
                return json.load(f)
        except Exception:
            return []

    def save_verify_now(self, data: List[Dict[str, Any]]) -> None:
        with open(self.verify_now_path, 'w', encoding='utf-8') as f:
            json.dump(data, f, indent=2, ensure_ascii=False)

    def clear_verify_now(self) -> None:
        self.save_verify_now([])

    def load_manual_review(self) -> List[Dict[str, Any]]:
        if not os.path.exists(self.manual_review_path):
            return []
        try:
            with open(self.manual_review_path, 'r', encoding='utf-8') as f:
                return json.load(f)
        except Exception:
            return []

    def save_manual_review(self, data: List[Dict[str, Any]]) -> None:
        with open(self.manual_review_path, 'w', encoding='utf-8') as f:
            json.dump(data, f, indent=2, ensure_ascii=False)

    def load_deferred(self) -> List[Dict[str, Any]]:
        if not os.path.exists(self.deferred_path):
            return []
        try:
            with open(self.deferred_path, 'r', encoding='utf-8') as f:
                return json.load(f)
        except Exception:
            return []

    def save_deferred(self, data: List[Dict[str, Any]]) -> None:
        with open(self.deferred_path, 'w', encoding='utf-8') as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
