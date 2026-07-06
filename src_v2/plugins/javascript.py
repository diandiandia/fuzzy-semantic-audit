import os
import re
from typing import List, Dict, Any
from src_v2.plugins.base import LanguagePlugin

JS_SYMBOL_PATTERNS = [
    re.compile(r"^\s*(?:export\s+)?(?:async\s+)?function\s+([a-zA-Z_][a-zA-Z0-9_]*)\s*\("),
    re.compile(r"^\s*(?:export\s+)?const\s+([a-zA-Z_][a-zA-Z0-9_]*)\s*=\s*(?:async\s*)?\([^)]*\)\s*=>"),
    re.compile(r"^\s*(?:public|private|protected)?\s*(?:async\s+)?([a-zA-Z_][a-zA-Z0-9_]*)\s*\([^)]*\)\s*\{"),
]

JS_TRACK_RULES = {
    "authz": [
        {"rule_id": "javascript.authz.middleware", "pattern": r"(passport\.authenticate|authCheck|requireAuth|checkRole|checkPermission|hasRole|guard)", "priority": 40},
        {"rule_id": "javascript.authz.check", "pattern": r"(req\.isAuthenticated|req\.user|jwt\.verify|verifyToken|authorize|checkAccess)", "priority": 30}
    ],
    "state_machine": [
        {"rule_id": "javascript.state.transition", "pattern": r"(?i)(transitionTo|setState|updateStatus|stateMachine|setStatus|status\s*=\s*)", "priority": 25}
    ],
    "resource_access": [
        {"rule_id": "javascript.resource.db", "pattern": r"\.(query|execute|select|insert|update|delete|raw|find|save|create)\(", "priority": 20},
        {"rule_id": "javascript.resource.file", "pattern": r"\b(fs\.(readFile|writeFile|open|read|write|createReadStream|createWriteStream|promises))\b", "priority": 20}
    ],
    "injection": [
        {"rule_id": "javascript.injection.cmd", "pattern": r"\b(exec|execSync|spawn|spawnSync|fork|eval|Function|runCommand)\b", "priority": 45},
        {"rule_id": "javascript.injection.sql", "pattern": r"\b(db\.query\(.*req\.(body|query|params))\b", "priority": 40}
    ],
    "input_validation": [
        {"rule_id": "javascript.input.validate", "pattern": r"\b(validate|sanitize|escape|joi|yup|zod|validator|checkSchema)\b", "priority": 20},
        {"rule_id": "javascript.input.request", "pattern": r"\b(req\.(query|body|params|headers|cookies|input))\b", "priority": 20}
    ],
    "deserialization": [
        {"rule_id": "javascript.deserialization.proto", "pattern": r"(\.constructor\.prototype|__proto__|\.prototype)", "priority": 35},
        {"rule_id": "javascript.deserialization.unsafe", "pattern": r"(deserialize|unserialize|node-serialize|serialize-javascript)", "priority": 45}
    ],
    "memory_safety": [], # JS is memory-safe generally
    "concurrency": [], # JS is single-threaded generally, but has async race conditions
    "crypto": [
        {"rule_id": "javascript.crypto.hash", "pattern": r"(crypto\.createHash|md5|sha1|sha256|sha512|bcrypt|argon2)", "priority": 20},
        {"rule_id": "javascript.crypto.cipher", "pattern": r"(crypto\.createCipheriv|crypto\.createDecipheriv|jwt\.sign|jsonwebtoken|cryptojs)", "priority": 30}
    ],
    "filesystem_boundary": [
        {"rule_id": "javascript.fs.path", "pattern": r"\b(path\.(join|resolve|normalize|basename|extname))\b", "priority": 15},
        {"rule_id": "javascript.fs.traversal", "pattern": r"\.\./\.\.|unzipper|adm-zip|tar-stream", "priority": 35}
    ]
}

class JavaScriptPlugin:
    plugin_name: str = "JavaScript/TypeScript Specialized Plugin"
    lang_key: str = "javascript"
    capability_level: str = "L1"

    def match_files(self, repo_files: List[str]) -> List[str]:
        return [f for f in repo_files if f.endswith((".js", ".jsx", ".ts", ".tsx"))]

    def enumerate_symbols(self, repo_path: str, files: List[str]) -> List[Dict[str, Any]]:
        symbols = []
        for file in files:
            abs_path = os.path.join(repo_path, file)
            if not os.path.exists(abs_path):
                continue
            try:
                with open(abs_path, "r", encoding="utf-8", errors="ignore") as f:
                    lines = f.readlines()
                for idx, line in enumerate(lines):
                    line_num = idx + 1
                    for pat in JS_SYMBOL_PATTERNS:
                        m = pat.match(line)
                        if m:
                            name = m.group(1)
                            if name in {
                                "if", "for", "while", "switch", "catch", "with", "function", "class", 
                                "const", "let", "var", "return", "import", "export", "default", "from", 
                                "as", "async", "await", "try", "finally", "throw", "new", "delete", 
                                "typeof", "instanceof", "in", "of", "void"
                            }:
                                continue
                            end_line = min(line_num + 35, len(lines))
                            symbols.append({
                                "symbol": name,
                                "start": line_num,
                                "end": end_line,
                                "file": file
                            })
                            break
            except:
                pass
        return symbols

    def detect_frameworks(self, repo_path: str, files: List[str]) -> List[str]:
        frameworks = []
        for f in files:
            if f.endswith("package.json"):
                try:
                    with open(os.path.join(repo_path, f), "r") as pf:
                        content = pf.read().lower()
                        if "express" in content:
                            frameworks.append("express")
                        if "react" in content:
                            frameworks.append("react")
                        if "next" in content:
                            frameworks.append("nextjs")
                        if "nest" in content:
                            frameworks.append("nestjs")
                except:
                    pass
        return list(set(frameworks))

    def build_track_rules(self, track_id: str) -> List[Dict[str, Any]]:
        return JS_TRACK_RULES.get(track_id, [])

    def build_resource_signals(self) -> List[str]:
        return [
            r"\b(query|execute|readFile|writeFile|open|connect|request|fetch|axios|db|fs)\b"
        ]

    def supports_callgraph(self) -> bool:
        return True
