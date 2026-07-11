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

from src_v3.core.boundary import WorkspaceBoundary

# Directory role signatures
ROLE_SIGNATURES = {
    "test": ["test", "tests", "spec", "specs", "__tests__"],
    "vendor": ["vendor", "node_modules", "venv", ".venv", "env", "third_party", "3rdparty"],
    "generated": ["gen", "generated", "dist", "build", "target", "out"]
}

def scan_repository(repo_path: str, workspace_dir: str = "") -> RepoProfile:
    """
    Scans the repository to identify languages, build systems, frameworks, 
    directory roles, risk directories, and entrypoint hints.
    """
    repo_path = os.path.abspath(repo_path)
    abs_workspace = os.path.abspath(workspace_dir) if workspace_dir else ""
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

    boundary = WorkspaceBoundary(workspace_dir)

    # Walk the repository
    for root, dirs, files in os.walk(repo_path):
        abs_root = os.path.abspath(root)
        if boundary.is_excluded(abs_root):
            dirs[:] = []
            continue

        # Determine roles for ALL subdirectories before filtering them out
        for d in dirs:
            d_abs_path = os.path.abspath(os.path.join(root, d))
            d_rel_path = os.path.relpath(d_abs_path, repo_path)
            
            is_workspace = boundary.is_excluded(d_abs_path) or os.path.exists(os.path.join(d_abs_path, "audit_plan.json")) or os.path.exists(os.path.join(d_abs_path, "run_manifest.json"))
                
            if is_workspace:
                directory_roles[d_rel_path] = "workspace_artifact"
                continue
                
            role = None
            d_lower = d.lower()
            if d_lower in {"vendor", "node_modules", "venv", ".venv", "env", "third_party", "3rdparty"}:
                role = "vendor"
            elif d_lower in {"gen", "generated", "dist", "build", "target", "out", "__pycache__"}:
                role = "generated"
            elif "audit_workspace" in d_lower or d_lower in WorkspaceBoundary.get_default_exclude_dirs():
                role = "workspace_artifact"
            elif d_lower in {"test", "tests", "spec", "specs", "__tests__"}:
                role = "test"
                
            if role:
                directory_roles[d_rel_path] = role

        # Modify dirs in-place to avoid walking ignored, hidden, audit workspace, dependency/vendor, and build/generated folders
        dirs[:] = [
            d for d in dirs 
            if not d.startswith(".") 
            and "audit_workspace" not in d 
            and d.lower() not in WorkspaceBoundary.get_default_exclude_dirs()
            and not boundary.is_excluded(os.path.join(root, d))
            and not os.path.exists(os.path.join(root, d, "audit_plan.json"))
            and not os.path.exists(os.path.join(root, d, "run_manifest.json"))
        ]
        
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
        else:
            directory_roles[rel_root] = "source"
            
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
