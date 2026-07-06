import os
import re
from typing import List, Dict, Any
from src_v2.plugins.base import LanguagePlugin

# Regex patterns for function/symbol detection in various languages
SYMBOL_PATTERNS = [
    # Python
    re.compile(r"^\s*def\s+([a-zA-Z_][a-zA-Z0-9_]*)\s*\("),
    # Go
    re.compile(r"^\s*func\s+(?:\([^)]+\)\s*)?([a-zA-Z_][a-zA-Z0-9_]*)\s*\("),
    # JS/TS
    re.compile(r"^\s*(?:async\s+)?function\s+([a-zA-Z_][a-zA-Z0-9_]*)\s*\("),
    re.compile(r"^\s*(?:export\s+)?const\s+([a-zA-Z_][a-zA-Z0-9_]*)\s*=\s*(?:async\s*)?\([^)]*\)\s*=>"),
    # Java / C++ / C / C#
    re.compile(r"^\s*(?:public|private|protected|static|virtual|inline)\s+[\w<>]+\s+([a-zA-Z_][a-zA-Z0-9_]*)\s*\([^)]*\)\s*(?:const)?\s*\{?"),
]

# Track rules mappings for generic plugin (keyword/regex based recall)
TRACK_RULES = {
    "authz": [
        {"rule_id": "generic.authz.keyword", "pattern": r"(?i)(auth|permission|role|allow|authorize|privilege|owner|login|signin|session)", "priority": 30},
        {"rule_id": "generic.authz.bypass", "pattern": r"(?i)(bypass|skip|disable_auth|ignore_auth|no_auth)", "priority": 50}
    ],
    "state_machine": [
        {"rule_id": "generic.state.transition", "pattern": r"(?i)(state|status|transition|phase|step|step_to|set_status|set_state|update_status)", "priority": 25},
        {"rule_id": "generic.state.lifecycle", "pattern": r"(?i)(activate|deactivate|suspend|resume|terminate|complete|cancel|approve|reject)", "priority": 20}
    ],
    "resource_access": [
        {"rule_id": "generic.resource.db", "pattern": r"(?i)(db|database|query|sql|select|insert|update|delete|execute|fetch|find|save|create)", "priority": 20},
        {"rule_id": "generic.resource.file", "pattern": r"(?i)(open|read|write|file|path|fs|stream|load|save|download|upload)", "priority": 20}
    ],
    "injection": [
        {"rule_id": "generic.injection.command", "pattern": r"(?i)(exec|system|popen|subprocess|run_command|spawn|eval|sh|bash|cmd)", "priority": 40},
        {"rule_id": "generic.injection.sql", "pattern": r"(?i)(execute.*%|execute.*format|raw_query|raw_sql|danger)", "priority": 35}
    ],
    "input_validation": [
        {"rule_id": "generic.input.validation", "pattern": r"(?i)(validate|sanitize|clean|parse|check|verify|filter|escape|encode|decode)", "priority": 15},
        {"rule_id": "generic.input.request", "pattern": r"(?i)(req|request|params|param|query|body|headers|cookie|post_data|get_data)", "priority": 20}
    ],
    "deserialization": [
        {"rule_id": "generic.deserialization.load", "pattern": r"(?i)(unpickle|pickle|deserialize|unmarshal|loads|load|unsafe_load|json.*parse)", "priority": 35}
    ],
    "memory_safety": [
        {"rule_id": "generic.memory.alloc", "pattern": r"(?i)(malloc|calloc|realloc|free|memcpy|memmove|memset|strcpy|strncpy|strcat)", "priority": 30},
        {"rule_id": "generic.memory.unsafe", "pattern": r"(?i)(unsafe|pointer|addr|deref|alloc)", "priority": 25}
    ],
    "concurrency": [
        {"rule_id": "generic.concurrency.lock", "pattern": r"(?i)(lock|unlock|mutex|semaphore|thread|parallel|sync|atomic|race|concurrency|chan|go.*func)", "priority": 20}
    ],
    "crypto": [
        {"rule_id": "generic.crypto.hash", "pattern": r"(?i)(md5|sha1|sha256|sha512|hash|digest)", "priority": 20},
        {"rule_id": "generic.crypto.cipher", "pattern": r"(?i)(encrypt|decrypt|cipher|key|iv|salt|aes|des|rsa|blowfish|rc4|secret)", "priority": 30}
    ],
    "filesystem_boundary": [
        {"rule_id": "generic.filesystem.path", "pattern": r"(?i)(filepath|path|abspath|join|relative|symlink|realpath|canonical)", "priority": 20},
        {"rule_id": "generic.filesystem.traversal", "pattern": r"\.\./\.\.|directory_traversal|tarfile|zipfile", "priority": 40}
    ]
}

class GenericPlugin:
    plugin_name: str = "Generic Baseline Plugin"
    lang_key: str = "generic"
    capability_level: str = "L0"

    def match_files(self, repo_files: List[str]) -> List[str]:
        # Matches any file since it's the fallback plugin.
        # But we will exclude binary or known non-code files to save performance.
        filtered = []
        excluded_exts = {
            ".png", ".jpg", ".jpeg", ".gif", ".ico", ".svg", ".pdf", ".zip", ".tar",
            ".gz", ".mp3", ".mp4", ".wav", ".exe", ".dll", ".so", ".bin", ".db",
            ".woff", ".woff2", ".eot", ".ttf"
        }
        for f in repo_files:
            _, ext = os.path.splitext(f)
            ext = ext.lower()
            if ext not in excluded_exts:
                filtered.append(f)
        return filtered

    def enumerate_symbols(self, repo_path: str, files: List[str]) -> List[Dict[str, Any]]:
        symbols = []
        for file in files:
            abs_path = os.path.join(repo_path, file)
            if not os.path.exists(abs_path) or os.path.isdir(abs_path):
                continue
                
            try:
                with open(abs_path, "r", encoding="utf-8", errors="ignore") as f:
                    lines = f.readlines()
            except Exception:
                continue
                
            for idx, line in enumerate(lines):
                line_num = idx + 1
                for pat in SYMBOL_PATTERNS:
                    m = pat.match(line)
                    if m:
                        name = m.group(1)
                        # Estimate function end by reading forward up to 30 lines or until indentation shifts back to 0
                        # For generic, let's keep it simple: assume span is 30 lines
                        end_line = min(line_num + 30, len(lines))
                        symbols.append({
                            "symbol": name,
                            "start": line_num,
                            "end": end_line,
                            "file": file
                        })
                        break
        return symbols

    def detect_frameworks(self, repo_path: str, files: List[str]) -> List[str]:
        return []

    def build_track_rules(self, track_id: str) -> List[Dict[str, Any]]:
        return TRACK_RULES.get(track_id, [])

    def build_resource_signals(self) -> List[str]:
        return [
            r"(?i)(db|database|conn|sql|query|open|read|write|send|recv|socket|http|request|api|s3|storage|file|fs|path)"
        ]

    def supports_callgraph(self) -> bool:
        return False
