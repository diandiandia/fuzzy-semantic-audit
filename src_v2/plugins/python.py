import os
import ast
import re
from typing import List, Dict, Any
from src_v2.plugins.base import LanguagePlugin

# Specialized Python rules
PYTHON_TRACK_RULES = {
    "authz": [
        {"rule_id": "python.authz.decorator", "pattern": r"@.*(login_required|permission_required|auth|require_auth|has_permission)", "priority": 40},
        {"rule_id": "python.authz.check", "pattern": r"(self\.)?(is_authenticated|has_perm|check_perm|authorize|is_admin|check_access)", "priority": 30},
        {"rule_id": "python.authz.django_rbac", "pattern": r"PermissionRequiredMixin|LoginRequiredMixin", "priority": 35}
    ],
    "state_machine": [
        {"rule_id": "python.state.transition", "pattern": r"(?i)(transition_to|set_state|update_status|state_machine|workflow|status\s*=\s*)", "priority": 25}
    ],
    "resource_access": [
        {"rule_id": "python.resource.db", "pattern": r"\.(objects\.raw|execute|select|insert|update|delete|raw)\(", "priority": 20},
        {"rule_id": "python.resource.file", "pattern": r"\b(open|read|write|save|load|os\.path|shutil)\b", "priority": 15}
    ],
    "injection": [
        {"rule_id": "python.injection.cmd", "pattern": r"\b(os\.system|os\.popen|subprocess\.run|subprocess\.Popen|subprocess\.call|eval|exec)\b", "priority": 45},
        {"rule_id": "python.injection.sql", "pattern": r"(?i)(cursor\.execute.*%|cursor\.execute.*format)", "priority": 40}
    ],
    "input_validation": [
        {"rule_id": "python.input.validate", "pattern": r"\b(clean_|validate_|is_valid|strptime|parser|schema\.validate)\b", "priority": 20},
        {"rule_id": "python.input.request", "pattern": r"\b(request\.(GET|POST|data|params|FILES|COOKIES|headers))\b", "priority": 25}
    ],
    "deserialization": [
        {"rule_id": "python.deserialization.pickle", "pattern": r"\b(pickle\.(loads|load)|pickle\.Unpickler|marshal\.loads|shelve\.open)\b", "priority": 45},
        {"rule_id": "python.deserialization.yaml", "pattern": r"\b(yaml\.unsafe_load|yaml\.load)\b", "priority": 40}
    ],
    "memory_safety": [], # Python is memory-safe generally
    "concurrency": [
        {"rule_id": "python.concurrency.thread", "pattern": r"\b(threading\.(Thread|Lock|RLock|Semaphore|Event)|multiprocessing\.Process|asyncio\.Lock)\b", "priority": 20}
    ],
    "crypto": [
        {"rule_id": "python.crypto.hash", "pattern": r"\b(hashlib\.(md5|sha1|sha224|sha256|sha384|sha512|new))\b", "priority": 20},
        {"rule_id": "python.crypto.cipher", "pattern": r"\b(cryptography|Crypto\.Cipher|pycrypto|fernet|jwt\.decode)\b", "priority": 30}
    ],
    "filesystem_boundary": [
        {"rule_id": "python.fs.path", "pattern": r"\b(os\.path\.(join|abspath|realpath|normpath|canonical))\b", "priority": 15},
        {"rule_id": "python.fs.traversal", "pattern": r"\.\./\.\.|zipfile|tarfile\.open", "priority": 35}
    ]
}

class PythonPlugin:
    plugin_name: str = "Python AST-Aware Plugin"
    lang_key: str = "python"
    capability_level: str = "L2"

    def match_files(self, repo_files: List[str]) -> List[str]:
        return [f for f in repo_files if f.endswith(".py")]

    def enumerate_symbols(self, repo_path: str, files: List[str]) -> List[Dict[str, Any]]:
        symbols = []
        for file in files:
            abs_path = os.path.join(repo_path, file)
            if not os.path.exists(abs_path):
                continue
            try:
                with open(abs_path, "r", encoding="utf-8", errors="ignore") as f:
                    content = f.read()
                
                # Parse AST
                tree = ast.parse(content, filename=file)
                
                # Class to walk function definitions
                class FuncVisitor(ast.NodeVisitor):
                    def visit_FunctionDef(self, node):
                        # Extract start and end lines
                        start = node.lineno
                        # end_lineno was added in Python 3.8
                        end = getattr(node, "end_lineno", start + 30)
                        symbols.append({
                            "symbol": node.name,
                            "start": start,
                            "end": end,
                            "file": file
                        })
                        self.generic_visit(node)
                        
                    def visit_AsyncFunctionDef(self, node):
                        start = node.lineno
                        end = getattr(node, "end_lineno", start + 30)
                        symbols.append({
                            "symbol": node.name,
                            "start": start,
                            "end": end,
                            "file": file
                        })
                        self.generic_visit(node)
                
                FuncVisitor().visit(tree)
            except Exception:
                # Fallback to regex line matching if AST fails
                try:
                    with open(abs_path, "r", encoding="utf-8", errors="ignore") as f:
                        lines = f.readlines()
                    for idx, line in enumerate(lines):
                        m = re.match(r"^\s*(?:async\s+)?def\s+([a-zA-Z_][a-zA-Z0-9_]*)\s*\(", line)
                        if m:
                            symbols.append({
                                "symbol": m.group(1),
                                "start": idx + 1,
                                "end": min(idx + 31, len(lines)),
                                "file": file
                            })
                except:
                    pass
        return symbols

    def detect_frameworks(self, repo_path: str, files: List[str]) -> List[str]:
        frameworks = []
        for f in files:
            if f.endswith("manage.py") or "settings.py" in f:
                frameworks.append("django")
            # Scan requirements.txt or code imports
            if f.endswith("requirements.txt"):
                try:
                    with open(os.path.join(repo_path, f), "r") as req:
                        content = req.read().lower()
                        if "django" in content:
                            frameworks.append("django")
                        if "flask" in content:
                            frameworks.append("flask")
                        if "fastapi" in content:
                            frameworks.append("fastapi")
                except:
                    pass
        return list(set(frameworks))

    def build_track_rules(self, track_id: str) -> List[Dict[str, Any]]:
        return PYTHON_TRACK_RULES.get(track_id, [])

    def build_resource_signals(self) -> List[str]:
        return [
            r"\b(open|read|write|execute|objects|db|cursor|send|recv|connect|session|request|urlopen)\b"
        ]

    def supports_callgraph(self) -> bool:
        return True
