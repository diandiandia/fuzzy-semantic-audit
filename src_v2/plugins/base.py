from typing import List, Dict, Any, Protocol, runtime_checkable

@runtime_checkable
class LanguagePlugin(Protocol):
    plugin_name: str
    lang_key: str
    capability_level: str  # L0, L1, L2 as described in System Design

    def match_files(self, repo_files: List[str]) -> List[str]:
        """Filter files list to only those this plugin handles."""
        ...

    def enumerate_symbols(self, repo_path: str, files: List[str]) -> List[Dict[str, Any]]:
        """Extract symbols/functions with start/end lines from files."""
        ...

    def detect_frameworks(self, repo_path: str, files: List[str]) -> List[str]:
        """Detect frameworks in the file list."""
        ...

    def build_track_rules(self, track_id: str) -> List[Dict[str, Any]]:
        """Return rules corresponding to this track."""
        ...

    def build_resource_signals(self) -> List[str]:
        """Return resource access indicators (regex/keywords) for resource recall."""
        ...

    def supports_callgraph(self) -> bool:
        """Returns True if this plugin can provide caller/callee graphs."""
        ...
