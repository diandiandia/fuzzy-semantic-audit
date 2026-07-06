import os
import re
from typing import List, Dict, Any
from src_v2.plugins.base import LanguagePlugin

JAVA_SYMBOL_PATTERNS = [
    re.compile(r"^\s*(?:public|private|protected|static|\s)+[\w<>\s,\[\]]+\s+([a-zA-Z_][a-zA-Z0-9_]*)\s*\([^)]*\)\s*(?:throws\s+[\w,\s]+)?\s*\{"),
]

JAVA_TRACK_RULES = {
    "authz": [
        {"rule_id": "java.authz.annotation", "pattern": r"@(PreAuthorize|PostAuthorize|Secured|RolesAllowed|RequiresPermissions)", "priority": 40},
        {"rule_id": "java.authz.check", "pattern": r"(SecurityContextHolder|hasRole|hasAuthority|isAuthorized|checkPermission)", "priority": 30}
    ],
    "state_machine": [
        {"rule_id": "java.state.transition", "pattern": r"(?i)(transitionTo|setState|updateStatus|stateMachine|setStatus|status\s*=\s*)", "priority": 25}
    ],
    "resource_access": [
        {"rule_id": "java.resource.db", "pattern": r"\.(createQuery|createNativeQuery|prepareStatement|execute|executeQuery|executeUpdate|save|delete)\(", "priority": 20},
        {"rule_id": "java.resource.file", "pattern": r"\b(FileInputStream|FileOutputStream|FileReader|FileWriter|File\b|Path\b|Files\.(read|write))\b", "priority": 20}
    ],
    "injection": [
        {"rule_id": "java.injection.cmd", "pattern": r"\b(Runtime\.getRuntime\(\)\.exec|ProcessBuilder|Process|Ognl\.getValue|eval)\b", "priority": 45},
        {"rule_id": "java.injection.sql", "pattern": r"(\.createQuery\(.*?\+.*?\)|\.prepareStatement\(.*?\+.*?\)|Statement\b.*\.execute)", "priority": 40}
    ],
    "input_validation": [
        {"rule_id": "java.input.validate", "pattern": r"\b(validate|sanitize|isValid|clean|check|parse|RequestParam|PathVariable)\b", "priority": 20},
        {"rule_id": "java.input.request", "pattern": r"\b(HttpServletRequest|req\.getParameter|req\.getHeader|getBody)\b", "priority": 20}
    ],
    "deserialization": [
        {"rule_id": "java.deserialization.unsafe", "pattern": r"(ObjectInputStream\b.*\.readObject|XMLDecoder|YAMLMapper|JSON\.parseObject|ObjectMapper\b.*\.enableDefaultTyping)", "priority": 45}
    ],
    "memory_safety": [],
    "concurrency": [
        {"rule_id": "java.concurrency.sync", "pattern": r"\b(synchronized|ReentrantLock|Semaphore|Thread\b|Runnable\b|ExecutorService)\b", "priority": 20}
    ],
    "crypto": [
        {"rule_id": "java.crypto.hash", "pattern": r"\b(MessageDigest\.getInstance|DigestUtils|md5|sha1|sha256)\b", "priority": 20},
        {"rule_id": "java.crypto.cipher", "pattern": r"\b(Cipher\.getInstance|SecretKeySpec|JwtBuilder|Jwts)\b", "priority": 30}
    ],
    "filesystem_boundary": [
        {"rule_id": "java.fs.path", "pattern": r"\b(Paths\.get|File\.getCanonicalPath|File\.getAbsoluteFile|normpath)\b", "priority": 15},
        {"rule_id": "java.fs.traversal", "pattern": r"\.\./\.\.|ZipInputStream|TarArchiveInputStream", "priority": 35}
    ]
}

class JavaPlugin:
    plugin_name: str = "Java Specialized Plugin"
    lang_key: str = "java"
    capability_level: str = "L1"

    def match_files(self, repo_files: List[str]) -> List[str]:
        return [f for f in repo_files if f.endswith(".java")]

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
                    for pat in JAVA_SYMBOL_PATTERNS:
                        m = pat.match(line)
                        if m:
                            name = m.group(1)
                            end_line = min(line_num + 50, len(lines))
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
            if f.endswith(("pom.xml", "build.gradle")):
                try:
                    with open(os.path.join(repo_path, f), "r") as mf:
                        content = mf.read().lower()
                        if "spring" in content:
                            frameworks.append("springboot")
                        if "struts" in content:
                            frameworks.append("struts")
                        if "hibernate" in content:
                            frameworks.append("hibernate")
                except:
                    pass
        return list(set(frameworks))

    def build_track_rules(self, track_id: str) -> List[Dict[str, Any]]:
        return JAVA_TRACK_RULES.get(track_id, [])

    def build_resource_signals(self) -> List[str]:
        return [
            r"\b(execute|prepareStatement|openStream|exec|read|write|Connection|http|request|channel)\b"
        ]

    def supports_callgraph(self) -> bool:
        return True
