import os
import json
import re
from typing import Optional
from src_v3.core.models import EvidenceBundle

class EvidenceStore:
    """
    Handles storage of EvidenceBundles under .audit_workspace_v3/evidence/packages/.
    Each bundle is saved as a separate JSON file named after the candidate ID.
    """
    def __init__(self, workspace_dir: str):
        self.workspace_dir = os.path.abspath(workspace_dir)
        self.packages_dir = os.path.join(self.workspace_dir, "evidence", "packages")
        os.makedirs(self.packages_dir, exist_ok=True)

    def _safe_filename(self, candidate_id: str) -> str:
        # Sanitize candidate_id to be safe as a filename
        return re.sub(r'[^a-zA-Z0-9_\-\.]', '_', candidate_id) + ".json"

    def get_evidence_relative_path(self, candidate_id: str) -> str:
        """
        Returns the workspace-relative path of the evidence bundle for a candidate.
        """
        filename = self._safe_filename(candidate_id)
        return os.path.join("evidence", "packages", filename)

    def save_evidence(self, bundle: EvidenceBundle) -> None:
        """
        Saves an EvidenceBundle to its own JSON file.
        """
        filename = self._safe_filename(bundle.candidate_id)
        filepath = os.path.join(self.packages_dir, filename)
        
        with open(filepath, 'w', encoding='utf-8') as f:
            json.dump(bundle.to_dict(), f, indent=2, ensure_ascii=False)

    def get_evidence(self, candidate_id: str) -> Optional[EvidenceBundle]:
        """
        Loads and returns the EvidenceBundle for a candidate, or None if not found.
        """
        filename = self._safe_filename(candidate_id)
        filepath = os.path.join(self.packages_dir, filename)
        
        if not os.path.exists(filepath):
            return None
            
        try:
            with open(filepath, 'r', encoding='utf-8') as f:
                data = json.load(f)
            return EvidenceBundle.from_dict(data)
        except Exception:
            return None
