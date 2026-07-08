import os
from typing import List, Dict, Set
from src_v3.core.models import RepoProfile

# Map extensions to languages
EXT_TO_LANG = {
    ".py": "python",
    ".js": "javascript",
    ".jsx": "javascript",
    ".ts": "typescript",
    ".tsx": "typescript",
    ".go": "go",
    ".java": "java",
    ".kt": "kotlin",
    ".rs": "rust",
    ".cpp": "cpp",
    ".c": "c",
    ".h": "c",
    ".hpp": "cpp",
    ".cs": "csharp",
    ".rb": "ruby",
    ".php": "php"
}

# Directories to ignore entirely
IGNORE_DIRS = {".git", ".audit_workspace_v3", ".gemini"}

# Directory role signatures
ROLE_SIGNATURES = {
    "test": ["test", "tests", "spec", "specs", "__tests__"],
    "vendor": ["vendor", "node_modules", "venv", ".venv", "env", "third_party", "3rdparty"],
    "generated": ["gen", "generated", "dist", "build", "target", "out"]
}

def scan_repository(repo_path: str) -> RepoProfile:
    """
    Scans the repository to identify languages, build systems, frameworks, 
    directory roles, risk directories, and entrypoint hints.
    """
    repo_path = os.path.abspath(repo_path)
    languages: Set[str] = set()
    build_systems: Set[str] = set()
    frameworks: Set[str] = set()
    directory_roles: Dict[str, str] = {}
    entrypoint_hints: List[str] = []
    risk_directories: List[str] = []

    # Common build files detection
    build_files = {
        "package.json": "npm",
        "requirements.txt": "pip",
        "Pipfile": "pipenv",
        "pyproject.toml": "poetry",
        "go.mod": "go-modules",
        "pom.xml": "maven",
        "build.gradle": "gradle",
        "build.gradle.kts": "gradle",
        "Cargo.toml": "cargo",
        "CMakeLists.txt": "cmake",
        "Makefile": "make"
    }

    # Walk the repository
    for root, dirs, files in os.walk(repo_path):
        # Modify dirs in-place to avoid walking ignored directories
        dirs[:] = [d for d in dirs if d not in IGNORE_DIRS]
        
        # Calculate relative path
        rel_root = os.path.relpath(root, repo_path)
        if rel_root == ".":
            rel_root = ""
            
        # Determine directory role
        role = None
        for r_name, signatures in ROLE_SIGNATURES.items():
            # Check if any folder segment matches signatures
            parts = rel_root.split(os.sep) if rel_root else []
            if any(p.lower() in signatures for p in parts):
                role = r_name
                break
        
        if role:
            directory_roles[rel_root] = role
            
        for file in files:
            file_path = os.path.join(root, file)
            rel_file_path = os.path.relpath(file_path, repo_path)
            ext = os.path.splitext(file)[1].lower()
            
            # 1. Identify languages
            if ext in EXT_TO_LANG:
                languages.add(EXT_TO_LANG[ext])
                
            # 2. Identify build systems
            if file in build_files:
                build_systems.add(build_files[file])
                
            # 3. Identify entrypoint hints
            # Common main/app files
            name_lower = os.path.splitext(file)[0].lower()
            if name_lower in ["main", "app", "index", "server", "application", "wsgi", "asgi"]:
                if ext in EXT_TO_LANG:
                    entrypoint_hints.append(rel_file_path)

            # 4. Identify risk directories
            # Directories named api, controllers, routers, handlers, auth, middleware
            parts = rel_root.split(os.sep) if rel_root else []
            risk_words = ["api", "controller", "controllers", "router", "routers", "handler", "handlers", "auth", "middleware", "middlewares"]
            if any(p.lower() in risk_words for p in parts):
                if rel_root not in risk_directories:
                    risk_directories.append(rel_root)

    return RepoProfile(
        languages=sorted(list(languages)),
        build_systems=sorted(list(build_systems)),
        frameworks=sorted(list(frameworks)), # Frameworks will be supplemented by framework detector
        directory_roles=directory_roles,
        entrypoint_hints=sorted(entrypoint_hints),
        risk_directories=sorted(risk_directories)
    )
