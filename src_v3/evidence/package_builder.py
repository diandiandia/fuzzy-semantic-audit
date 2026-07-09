import os
from typing import Dict, Any
from src_v3.core.models import EvidenceBundle
from src_v3.storage.evidence_store import EvidenceStore

class PackageBuilder:
    """
    Coordinates building and storing of EvidenceBundles.
    """
    def __init__(self, workspace_dir: str):
        self.workspace_dir = os.path.abspath(workspace_dir)
        self.evidence_store = EvidenceStore(self.workspace_dir)

    def save_package(self, candidate_id: str, bundle: EvidenceBundle) -> str:
        """
        Saves the EvidenceBundle package to the EvidenceStore.
        """
        self.evidence_store.save_evidence(bundle)
        return self.evidence_store.get_evidence_relative_path(candidate_id)
