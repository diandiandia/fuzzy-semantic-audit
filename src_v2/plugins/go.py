import os
import re
from typing import List, Dict, Any
from src_v2.plugins.base import LanguagePlugin

GO_SYMBOL_PATTERNS = [
    re.compile(r"^\s*func\s+(?:\([^)]+\)\s*)?([a-zA-Z_][a-zA-Z0-9_]*)\s*\("),
]

GO_TRACK_RULES = {
    "authz": [
        {"rule_id": "go.authz.middleware", "pattern": r"(AuthMiddleware|RequireAuth|CheckRole|JWTAuth|casbin|claims)", "priority": 40},
        {"rule_id": "go.authz.check", "pattern": r"(Context\.Get.*user|Session\.Get|IsAdmin|Authorize|HasPermission)", "priority": 30}
    ],
    "state_machine": [
        {"rule_id": "go.state.transition", "pattern": r"(?i)(TransitionTo|SetState|UpdateStatus|StateMachine|SetStatus|status\s*=\s*)", "priority": 25}
    ],
    "resource_access": [
        {"rule_id": "go.resource.db", "pattern": r"\.(Query|QueryRow|Exec|Raw|Find|Save|Create|Delete|Updates)\(", "priority": 20},
        {"rule_id": "go.resource.file", "pattern": r"\b(os\.(Open|OpenFile|Create|ReadFile|WriteFile)|io\.(Copy|ReadFull)|ioutil)\b", "priority": 20}
    ],
    "injection": [
        {"rule_id": "go.injection.cmd", "pattern": r"\b(exec\.Command|exec\.CommandContext|syscall\.ForkExec|syscall\.Exec)\b", "priority": 45},
        {"rule_id": "go.injection.sql", "pattern": r"fmt\.Sprintf\(\s*\"SELECT.*\",.*req", "priority": 40}
    ],
    "input_validation": [
        {"rule_id": "go.input.validate", "pattern": r"\b(Validate|BindJSON|BindQuery|ShouldBind|ParseForm|govalidator)\b", "priority": 20},
        {"rule_id": "go.input.request", "pattern": r"\b(c\.(JSON|String|Query|Param|PostForm|Request))\b", "priority": 20}
    ],
    "deserialization": [
        {"rule_id": "go.deserialization.unmarshal", "pattern": r"\b(json\.Unmarshal|xml\.Unmarshal|gob\.NewDecoder|yaml\.Unmarshal)\b", "priority": 25}
    ],
    "memory_safety": [
        {"rule_id": "go.memory.unsafe", "pattern": r"\b(unsafe\.Pointer|uintptr|C\.malloc|C\.free)\b", "priority": 30}
    ],
    "concurrency": [
        {"rule_id": "go.concurrency.race", "pattern": r"\b(go\s+func|sync\.(Mutex|RWMutex|WaitGroup|Cond|Map|Once)|atomic\.)\b", "priority": 20},
        {"rule_id": "go.concurrency.channel", "pattern": r"\b(make\(\s*chan|select\s*\{|<-chan)\b", "priority": 15}
    ],
    "crypto": [
        {"rule_id": "go.crypto.hash", "pattern": r"\b(crypto\.(md5|sha1|sha256|sha512)|bcrypt|scrypt)\b", "priority": 20},
        {"rule_id": "go.crypto.cipher", "pattern": r"\b(aes\.(NewCipher|NewCFBDecrypter)|rsa\.(Encrypt|Decrypt)|jwt-go)\b", "priority": 30}
    ],
    "filesystem_boundary": [
        {"rule_id": "go.fs.path", "pattern": r"\b(path\/filepath\.(Join|Abs|Clean|Rel|EvalSymlinks))\b", "priority": 15},
        {"rule_id": "go.fs.traversal", "pattern": r"\.\./\.\.|archive\/zip|archive\/tar", "priority": 35}
    ]
}

class GoPlugin:
    plugin_name: str = "Go Specialized Plugin"
    lang_key: str = "go"
    capability_level: str = "L1"

    def match_files(self, repo_files: List[str]) -> List[str]:
        return [f for f in repo_files if f.endswith(".go")]

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
                    for pat in GO_SYMBOL_PATTERNS:
                        m = pat.match(line)
                        if m:
                            name = m.group(1)
                            end_line = min(line_num + 40, len(lines))
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
            if f.endswith("go.mod"):
                try:
                    with open(os.path.join(repo_path, f), "r") as mf:
                        content = mf.read().lower()
                        if "gin" in content:
                            frameworks.append("gin")
                        if "echo" in content:
                            frameworks.append("echo")
                        if "fiber" in content:
                            frameworks.append("fiber")
                except:
                    pass
        return list(set(frameworks))

    def build_track_rules(self, track_id: str) -> List[Dict[str, Any]]:
        return GO_TRACK_RULES.get(track_id, [])

    def build_resource_signals(self) -> List[str]:
        return [
            r"\b(Query|Exec|Open|ReadFile|WriteFile|Command|dial|http|Get|Post|channel)\b"
        ]

    def supports_callgraph(self) -> bool:
        return True
