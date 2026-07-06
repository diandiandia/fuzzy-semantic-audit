import os
import re
from typing import List, Dict, Any
from src_v2.plugins.base import LanguagePlugin

CPP_SYMBOL_PATTERNS = [
    re.compile(r"^\s*(?:[A-Za-z0-9_]+(?:\s*\*+)?\s+)+([A-Za-z0-9_]+)\s*\([^)]*\)\s*(?:const)?\s*\{?"),
]

CPP_TRACK_RULES = {
    "authz": [
        {"rule_id": "cpp.authz.check", "pattern": r"\b(authorize|checkAccess|verifyUser|authenticate|isAdmin|hasPermission)\b", "priority": 30}
    ],
    "state_machine": [
        {"rule_id": "cpp.state.transition", "pattern": r"(?i)(transitionTo|setState|updateStatus|stateMachine|setStatus|status\s*=\s*)", "priority": 25}
    ],
    "resource_access": [
        {"rule_id": "cpp.resource.db", "pattern": r"\b(Query|Execute|Connect|Sql|Database)\b", "priority": 20},
        {"rule_id": "cpp.resource.file", "pattern": r"\b(fopen|open|read|write|fstream|ifstream|ofstream|open)\b", "priority": 15}
    ],
    "injection": [
        {"rule_id": "cpp.injection.cmd", "pattern": r"\b(system|exec|execve|execl|execp|popen|spawn)\b", "priority": 45}
    ],
    "input_validation": [
        {"rule_id": "cpp.input.validate", "pattern": r"\b(validate|sanitize|check|verify|parse|validate_input)\b", "priority": 15},
        {"rule_id": "cpp.input.buffer", "pattern": r"\b(argv|argc|stdin|read|recv|scanf|gets)\b", "priority": 20}
    ],
    "deserialization": [],
    "memory_safety": [
        {"rule_id": "cpp.memory.overflow", "pattern": r"\b(strcpy|strcat|sprintf|vsprintf|gets|memcpy|memmove)\b", "priority": 40},
        {"rule_id": "cpp.memory.alloc", "pattern": r"\b(malloc|calloc|realloc|free|new\s|delete\s|delete\[\])\b", "priority": 30},
        {"rule_id": "cpp.memory.pointer", "pattern": r"\b(unsafe|reinterpret_cast|cast|std::move)\b", "priority": 25}
    ],
    "concurrency": [
        {"rule_id": "cpp.concurrency.lock", "pattern": r"\b(mutex|lock_guard|unique_lock|pthread_mutex_lock|pthread_mutex_unlock)\b", "priority": 25},
        {"rule_id": "cpp.concurrency.thread", "pattern": r"\b(std::thread|pthread_create|fork)\b", "priority": 20}
    ],
    "crypto": [
        {"rule_id": "cpp.crypto.hash", "pattern": r"\b(MD5|SHA1|SHA256|SHA512|EVP_DigestSign|HMAC)\b", "priority": 20},
        {"rule_id": "cpp.crypto.cipher", "pattern": r"\b(AES_encrypt|AES_decrypt|RSA_public_encrypt|RSA_private_decrypt|DES_|cipher)\b", "priority": 30}
    ],
    "filesystem_boundary": [
        {"rule_id": "cpp.fs.path", "pattern": r"\b(realpath|canonicalize|abspath|normalize_path)\b", "priority": 15},
        {"rule_id": "cpp.fs.traversal", "pattern": r"\.\./\.\.|dirent|stat", "priority": 35}
    ]
}

class CppPlugin:
    plugin_name: str = "C/C++ Specialized Plugin"
    lang_key: str = "cpp"
    capability_level: str = "L1"

    def match_files(self, repo_files: List[str]) -> List[str]:
        return [f for f in repo_files if f.endswith((".cpp", ".cc", ".cxx", ".hpp", ".h", ".c"))]

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
                    for pat in CPP_SYMBOL_PATTERNS:
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
            if "cmake" in f.lower() or "makefile" in f.lower():
                frameworks.append("cmake-build")
        return frameworks

    def build_track_rules(self, track_id: str) -> List[Dict[str, Any]]:
        return CPP_TRACK_RULES.get(track_id, [])

    def build_resource_signals(self) -> List[str]:
        return [
            r"\b(fopen|read|write|send|recv|system|exec|connect|socket|db)\b"
        ]

    def supports_callgraph(self) -> bool:
        return True
