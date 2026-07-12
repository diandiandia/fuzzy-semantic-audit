import os
from typing import Set

class WorkspaceBoundary:
    """
    Unified workspace boundary contract defining paths that should be excluded
    from source code scans (workspace, cache, report, history).
    """
    def __init__(self, workspace_dir: str):
        self.workspace_dir = os.path.abspath(workspace_dir) if workspace_dir else ""
        if self.workspace_dir:
            self.cache_dir = os.path.join(self.workspace_dir, "cache")
            self.reports_dir = os.path.join(self.workspace_dir, "reports")
            self.candidates_dir = os.path.join(self.workspace_dir, "candidates")
            self.evidence_dir = os.path.join(self.workspace_dir, "evidence")
            self.history_dir = os.path.join(self.workspace_dir, "history")
        else:
            self.cache_dir = ""
            self.reports_dir = ""
            self.candidates_dir = ""
            self.evidence_dir = ""
            self.history_dir = ""

    def is_excluded(self, path: str) -> bool:
        """
        Returns True if the path is inside the workspace boundary (workspace, cache, report, history, etc.).
        """
        if not self.workspace_dir:
            return False
        abs_path = os.path.abspath(path)
        # Check if it is the workspace directory itself or a child of it
        if abs_path == self.workspace_dir or abs_path.startswith(self.workspace_dir + os.sep):
            return True
        return False

    @classmethod
    def has_workspace_marker(cls, path: str) -> bool:
        """
        Detect historical audit workspaces even when they are not the currently
        configured workspace directory.
        """
        return (
            os.path.exists(os.path.join(path, "audit_plan.json"))
            or os.path.exists(os.path.join(path, "run_manifest.json"))
        )

    def is_repository_artifact_dir(self, path: str) -> bool:
        """
        Returns True for the active workspace, historical audit workspaces, or
        common generated/cache/vendor directories that must not enter source
        inventory, sharding, or recall.
        """
        abs_path = os.path.abspath(path)
        name = os.path.basename(abs_path).lower()
        if self.is_excluded(abs_path):
            return True
        if self.has_workspace_marker(abs_path):
            return True
        if "audit_workspace" in name:
            return True
        return name in self.get_default_exclude_dirs()
        
    @staticmethod
    def get_default_exclude_dirs() -> Set[str]:
        """
        Returns standard system directory names to exclude.
        """
        return {
            ".git", ".audit_workspace", ".audit_workspace_v2", ".audit_workspace_v3",
            ".gemini", ".codex", ".agents", ".cache", ".pytest_cache", ".mypy_cache",
            ".ruff_cache", ".tox", ".nox", "node_modules", "venv",
            ".venv", "env", "vendor", "third_party", "3rdparty",
            "gen", "generated", "dist", "build", "target", "out", "__pycache__",
            "coverage", "htmlcov"
        }
