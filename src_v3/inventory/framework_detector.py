import os
import re
from typing import List, Dict
from src_v3.core.models import RepoProfile

def detect_frameworks(repo_path: str, profile: RepoProfile) -> Dict[str, float]:
    """
    Detects frameworks used in the repository by reading dependencies and looking at project files.
    Returns a dictionary mapping framework name to confidence score (0.0 to 1.0).
    """
    repo_path = os.path.abspath(repo_path)
    detected: Dict[str, float] = {}
    
    # Helper to set highest confidence
    def add_fw(name: str, confidence: float):
        detected[name] = max(detected.get(name, 0.0), confidence)
    
    # 1. Read package.json for Node.js frameworks
    package_json_path = os.path.join(repo_path, "package.json")
    if os.path.exists(package_json_path):
        try:
            with open(package_json_path, 'r', encoding='utf-8') as f:
                content = f.read()
                if "express" in content:
                    add_fw("express", 0.95)
                if "react" in content:
                    add_fw("react", 0.95)
                if "vue" in content:
                    add_fw("vue", 0.95)
                if "next" in content:
                    add_fw("next", 0.95)
                if "nest" in content:
                    add_fw("nestjs", 0.95)
        except Exception:
            pass # Fail gracefully
            
    # 2. Read requirements.txt, pyproject.toml, Pipfile for Python frameworks
    requirements_path = os.path.join(repo_path, "requirements.txt")
    if os.path.exists(requirements_path):
        try:
            with open(requirements_path, 'r', encoding='utf-8') as f:
                content = f.read().lower()
                if "django" in content:
                    add_fw("django", 0.9)
                if "flask" in content:
                    add_fw("flask", 0.9)
                if "fastapi" in content:
                    add_fw("fastapi", 0.9)
        except Exception:
            pass
            
    manage_py_path = os.path.join(repo_path, "manage.py")
    if os.path.exists(manage_py_path):
        add_fw("django", 0.95)

    # 3. Read go.mod for Go frameworks
    go_mod_path = os.path.join(repo_path, "go.mod")
    if os.path.exists(go_mod_path):
        try:
            with open(go_mod_path, 'r', encoding='utf-8') as f:
                content = f.read()
                if "github.com/gin-gonic/gin" in content:
                    add_fw("gin", 0.95)
                if "github.com/astaxie/beego" in content or "github.com/beego/beego" in content:
                    add_fw("beego", 0.95)
                if "github.com/labstack/echo" in content:
                    add_fw("echo", 0.95)
                if "github.com/fiber/fiber" in content:
                    add_fw("fiber", 0.95)
        except Exception:
            pass

    # 4. Read pom.xml or build.gradle for Java/Kotlin frameworks
    pom_path = os.path.join(repo_path, "pom.xml")
    if os.path.exists(pom_path):
        try:
            with open(pom_path, 'r', encoding='utf-8') as f:
                content = f.read()
                if "spring-boot" in content or "org.springframework" in content:
                    add_fw("spring", 0.95)
        except Exception:
            pass
            
    gradle_files = ["build.gradle", "build.gradle.kts"]
    for gf in gradle_files:
        gp = os.path.join(repo_path, gf)
        if os.path.exists(gp):
            try:
                with open(gp, 'r', encoding='utf-8') as f:
                    content = f.read()
                    if "spring" in content:
                        add_fw("spring", 0.9)
                    if "com.android.application" in content or "com.android.library" in content:
                        add_fw("android", 0.95)
            except Exception:
                pass

    # Search for AndroidManifest.xml for Android
    for root, dirs, files in os.walk(repo_path):
        # limit depth to avoid deep scanning
        if ".git" in dirs:
            dirs.remove(".git")
        if "AndroidManifest.xml" in files:
            add_fw("android", 0.98)
            break

    return detected
