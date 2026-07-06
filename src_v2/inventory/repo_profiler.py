import os
from typing import List, Dict, Tuple
from src_v2.core.models import RepoProfile, RepoLanguage, RepoDirectories

# Extension to language mapping
LANG_EXT_MAP = {
    ".py": "python",
    ".js": "javascript",
    ".jsx": "javascript",
    ".ts": "typescript",
    ".tsx": "typescript",
    ".go": "go",
    ".java": "java",
    ".c": "c",
    ".h": "c",
    ".cpp": "cpp",
    ".cc": "cpp",
    ".cxx": "cpp",
    ".hpp": "cpp"
}

IGNORED_DIRS = {
    ".git", ".audit_workspace_v2", "node_modules", "vendor", "venv", 
    ".venv", "dist", "build", "target", "bin", "obj", "__pycache__",
    ".idea", ".vscode"
}

TEST_DIR_KEYWORDS = {"test", "tests", "__tests__", "spec", "specs"}

def profile_repo(repo_path: str) -> RepoProfile:
    """Scan directory and generate RepoProfile."""
    repo_path = os.path.abspath(repo_path)
    
    file_counts: Dict[str, int] = {}
    frameworks = set()
    source_dirs = set()
    test_dirs = set()
    generated_dirs = set()
    entrypoints = []

    # Look for files like package.json, go.mod, requirements.txt, manage.py, pom.xml to detect frameworks
    for root, dirs, files in os.walk(repo_path):
        # Filter directories to avoid scanning ignored ones
        rel_root = os.path.relpath(root, repo_path)
        path_parts = rel_root.split(os.sep) if rel_root != "." else []
        
        # If any part of the path is in IGNORED_DIRS, skip
        if any(p in IGNORED_DIRS for p in path_parts):
            continue
            
        # Determine directory category
        if rel_root != ".":
            top_dir = path_parts[0]
            if any(kw in top_dir.lower() for kw in TEST_DIR_KEYWORDS):
                test_dirs.add(top_dir)
            else:
                source_dirs.add(top_dir)
        
        for file in files:
            file_path = os.path.join(root, file)
            rel_file_path = os.path.relpath(file_path, repo_path)
            _, ext = os.path.splitext(file)
            ext = ext.lower()
            
            # Count language files
            if ext in LANG_EXT_MAP:
                lang = LANG_EXT_MAP[ext]
                # Normalize javascript/typescript if needed or keep separate as per design
                # Let's keep them separate as defined
                file_counts[lang] = file_counts.get(lang, 0) + 1
            else:
                # Add to generic file count if it's code/config but not primary language
                # e.g., html, css, json, yaml, etc.
                if ext in {".html", ".css", ".json", ".yaml", ".yml", ".sh", ".bash", ".sql"}:
                    file_counts["generic"] = file_counts.get("generic", 0) + 1
            
            # Framework signals
            if file == "package.json":
                frameworks.add("nodejs")
                try:
                    with open(file_path, "r", errors="ignore") as f:
                        content = f.read()
                        if "express" in content:
                            frameworks.add("express")
                        if "react" in content:
                            frameworks.add("react")
                        if "next" in content:
                            frameworks.add("nextjs")
                except:
                    pass
            elif file == "go.mod":
                frameworks.add("go-modules")
                try:
                    with open(file_path, "r", errors="ignore") as f:
                        content = f.read()
                        if "github.com/gin-gonic/gin" in content:
                            frameworks.add("gin")
                        if "github.com/labstack/echo" in content:
                            frameworks.add("echo")
                except:
                    pass
            elif file == "requirements.txt" or file == "Pipfile" or file == "poetry.lock":
                frameworks.add("python-env")
                try:
                    with open(file_path, "r", errors="ignore") as f:
                        content = f.read()
                        if "django" in content.lower():
                            frameworks.add("django")
                        if "flask" in content.lower():
                            frameworks.add("flask")
                        if "fastapi" in content.lower():
                            frameworks.add("fastapi")
                except:
                    pass
            elif file == "manage.py":
                frameworks.add("django")
            elif file == "pom.xml" or file == "build.gradle":
                frameworks.add("java-build")
                try:
                    with open(file_path, "r", errors="ignore") as f:
                        content = f.read()
                        if "spring" in content.lower():
                            frameworks.add("springboot")
                except:
                    pass
            
            # Entrypoint hints
            if file in {"main.py", "app.py", "run.py", "wsgi.py", "main.go", "index.js", "index.ts", "server.js", "app.js", "app.ts"}:
                entrypoints.append(rel_file_path)

    # Convert languages to RepoLanguage
    languages = [
        RepoLanguage(lang=lang, file_count=count)
        for lang, count in file_counts.items()
    ]
    # Sort languages by count descending
    languages.sort(key=lambda x: x.file_count, reverse=True)

    # Clean dirs
    # Add IGNORED_DIRS that are present in the repo to generated dirs
    for d in IGNORED_DIRS:
        if os.path.exists(os.path.join(repo_path, d)):
            generated_dirs.add(d)

    directories = RepoDirectories(
        source=sorted(list(source_dirs)),
        tests=sorted(list(test_dirs)),
        generated=sorted(list(generated_dirs))
    )

    return RepoProfile(
        repo_path=repo_path,
        languages=languages,
        frameworks=sorted(list(frameworks)),
        directories=directories,
        entrypoint_hints=sorted(entrypoints)
    )
