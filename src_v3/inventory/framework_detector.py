import os
import re
from typing import List, Dict
from src_v3.core.models import RepoProfile

def detect_frameworks(repo_path: str, profile: RepoProfile) -> List[str]:
    """
    Detects frameworks used in the repository by reading dependencies and looking at project files.
    """
    repo_path = os.path.abspath(repo_path)
    detected = set()
    
    # 1. Read package.json for Node.js frameworks
    package_json_path = os.path.join(repo_path, "package.json")
    if os.path.exists(package_json_path):
        try:
            with open(package_json_path, 'r', encoding='utf-8') as f:
                content = f.read()
                if "express" in content:
                    detected.add("express")
                if "react" in content:
                    detected.add("react")
                if "vue" in content:
                    detected.add("vue")
                if "next" in content:
                    detected.add("next")
                if "nest" in content:
                    detected.add("nestjs")
        except Exception:
            pass # Fail gracefully
            
    # 2. Read requirements.txt, pyproject.toml, Pipfile for Python frameworks
    requirements_path = os.path.join(repo_path, "requirements.txt")
    if os.path.exists(requirements_path):
        try:
            with open(requirements_path, 'r', encoding='utf-8') as f:
                content = f.read().lower()
                if "django" in content:
                    detected.add("django")
                if "flask" in content:
                    detected.add("flask")
                if "fastapi" in content:
                    detected.add("fastapi")
        except Exception:
            pass
            
    manage_py_path = os.path.join(repo_path, "manage.py")
    if os.path.exists(manage_py_path):
        detected.add("django")

    # 3. Read go.mod for Go frameworks
    go_mod_path = os.path.join(repo_path, "go.mod")
    if os.path.exists(go_mod_path):
        try:
            with open(go_mod_path, 'r', encoding='utf-8') as f:
                content = f.read()
                if "github.com/gin-gonic/gin" in content:
                    detected.add("gin")
                if "github.com/astaxie/beego" in content or "github.com/beego/beego" in content:
                    detected.add("beego")
                if "github.com/labstack/echo" in content:
                    detected.add("echo")
                if "github.com/fiber/fiber" in content:
                    detected.add("fiber")
        except Exception:
            pass

    # 4. Read pom.xml or build.gradle for Java/Kotlin frameworks
    pom_path = os.path.join(repo_path, "pom.xml")
    if os.path.exists(pom_path):
        try:
            with open(pom_path, 'r', encoding='utf-8') as f:
                content = f.read()
                if "spring-boot" in content or "org.springframework" in content:
                    detected.add("spring")
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
                        detected.add("spring")
                    if "com.android.application" in content or "com.android.library" in content:
                        detected.add("android")
            except Exception:
                pass

    # Search for AndroidManifest.xml for Android
    for root, dirs, files in os.walk(repo_path):
        # limit depth to avoid deep scanning
        if ".git" in dirs:
            dirs.remove(".git")
        if "AndroidManifest.xml" in files:
            detected.add("android")
            break

    return sorted(list(detected))
