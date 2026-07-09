import os
from typing import Dict, Any

class FileClassifier:
    """
    Classifies file paths and extensions to map them to target languages.
    """
    EXT_TO_LANG = {
        ".py": "python",
        ".js": "javascript",
        ".jsx": "javascript",
        ".ts": "typescript",
        ".tsx": "typescript",
        ".go": "go",
        ".java": "java",
        ".rs": "rust",
        ".cpp": "cpp",
        ".c": "c",
        ".h": "c",
        ".hpp": "cpp",
        ".cs": "csharp",
        ".rb": "ruby",
        ".php": "php"
    }

    @classmethod
    def classify(cls, file_path: str) -> str:
        ext = os.path.splitext(file_path)[1].lower()
        return cls.EXT_TO_LANG.get(ext, "unsupported")
