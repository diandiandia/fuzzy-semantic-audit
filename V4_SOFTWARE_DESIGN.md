# Fuzzy Semantic Audit V4 —— 软件设计文档 (Software Design Document)

本文件定义 V4 版本各软件模块的内部实现细节、数据结构契约（JSON Schema）、大模型提示词工程规范以及异常处理逻辑。本设计是编写代码的直接蓝图。

---

## 1. 项目物理目录结构 (Folder Layout)

```text
/root/fuzzy-semantic-audit/
├── REQUIREMENTS.md                 # 核心需求
├── SKILL.md                        # 平台 Skill 描述
├── V4_SYSTEM_DESIGN.md             # 系统设计 (系统层控制流)
├── V4_SOFTWARE_DESIGN.md           # 软件设计 (数据与类实现)
├── V4_TASK_BREAKDOWN.md            # 开发计划拆解
├── rules/
│   └── v4_development_compliance.md # 开发防偏离规则
├── src_v4/                         # V4 源码根目录
│   ├── __init__.py
│   ├── inventory/                  # 阶段一：多语言发现
│   │   ├── __init__.py
│   │   └── language_sharder.py
│   ├── packs/                      # 阶段二：AI 画像生成
│   │   ├── __init__.py
│   │   └── dynamic_packer.py
│   ├── filter/                     # 阶段三：静态初筛与打分
│   │   ├── __init__.py
│   │   ├── coarse_scanner.py
│   │   └── severity_scorer.py
│   ├── verify/                     # 阶段四：智能体研判
│   │   ├── __init__.py
│   │   ├── agentic_triage.py
│   │   └── tools.py
│   ├── cli/                        # 控制流编排
│   │   ├── __init__.py
│   │   └── orchestrate_audit.py
│   └── utils/                      # 通用工具 (AST, IO)
│       ├── __init__.py
│       └── ast_helper.py
└── tests/                          # V4 单元与集成测试
    ├── __init__.py
    ├── test_language_discoverer.py
    ├── test_dynamic_packer.py
    ├── test_coarse_scanner.py
    └── test_agentic_triage.py
```

---

## 2. 数据结构与存储契约 (Data Schema Contracts)

为了保证模块间的弱耦合，阶段性产物全部通过 JSON 文件持久化交互。

### 2.1 `repo_profile.json` (多语言资产清单)
```json
{
  "repo_path": "/root/Bluetooth",
  "scanned_at": 1718458920,
  "languages": {
    "java": [
      "service/src/com/android/server/bluetooth/BluetoothManagerService.java",
      "service/src/com/android/server/bluetooth/BtPermissionUtils.java"
    ],
    "cpp": [
      "hal/bluetooth_interface.cpp"
    ]
  }
}
```

### 2.2 `scan_pack.json` (AI 动态生成的匹配包)
```json
{
  "scanned_languages": ["java", "cpp"],
  "rules": {
    "java": {
      "keywords": ["enforceCallingPermission", "checkCallingOrSelfPermission"],
      "regex_patterns": ["Binder\\.getCallingUid\\(\\)\\s*!=\\s*Process\\.ROOT_UID"],
      "ast_queries": [
        "(method_declaration (modifiers) (identifier) @name (#match? @name \"onShellCommand\"))"
      ]
    }
  }
}
```

### 2.3 `verify_queue.json` (待验证串行队列)
```json
[
  {
    "candidate_id": "cand_001",
    "language": "java",
    "file_path": "service/src/com/android/server/bluetooth/BluetoothShellCommand.java",
    "symbol": "onCommand",
    "line_number": 220,
    "severity": "Critical",
    "score": 95.0,
    "clues": {
      "matched_keyword": "onCommand",
      "trigger_regex": "Binder.getCallingUid()"
    },
    "status": "PENDING"
  }
]
```

---

## 3. 大模型提示词设计 (Prompt Engineering Specs)

### 3.1 动态画像生成 Prompt (Rule Generator Prompt)
*   **输入角色**：专家级静态代码分析工程师。
*   **任务**：针对特定语言（如 Java），分析 CWE 安全规则，生成用于本地粗筛的代码特征。
*   **输出格式约束**：强约束 JSON。
```text
System: You are an expert static analysis rules engineer.
User: Generate a scanner pack for the language: [Java], focusing on these security tracks: [authz, state_machine].
You must return a JSON object with:
1. "keywords": A list of highly suspicious API names or class names.
2. "regex_patterns": RegEx strings targeting insecure logic checks.
3. "ast_queries": Tree-sitter query patterns (S-expressions) targeting entrypoints or callbacks.
Strictly return JSON only.
```

### 3.2 Verifier Agent 系统提示词 (ReAct Triage System Prompt)
*   **输入角色**：经验丰富的高级安全审计专家。
*   **任务**：使用本地提供的工具（`find_callers`，`read_file_segment`），一步步追溯 Candidate 漏洞的可达性。
*   **推理格式**：遵循 Thought -> Action -> Observation -> Thought 结构。
```text
System: You are an elite security auditor. You are given a suspicious code candidate line (the Sink).
Your goal is to trace the execution path backwards to prove if any external inputs (the Source, e.g. Binder calls, HTTP endpoints) can reach this Sink without proper permission guards.

You have access to these tools:
- find_callers(symbol, file)
- read_file_segment(file, start, end)
- find_implementations(interface)

Format:
Thought: I need to check who calls this method.
Action: find_callers(symbol: "onCommand", file: "BluetoothShellCommand.java")
Observation: [...]
...
Thought: I have traced it to the public Binder entrypoint handleShellCommand() with NO UID check. This is reachable.
Verdict: YES (Reachable).
Path: [list the calling path in order]
```

---

## 4. 智能体验证工具箱 (Agent Tools Class Implementation)

在 `src_v4/verify/tools.py` 中，工具的 Python 封装设计如下：

```python
class AgentTools:
    def __init__(self, repo_path: str, repo_profile: dict):
        self.repo_path = repo_path
        self.profile = repo_profile

    def read_file_segment(self, file_path: str, start_line: int, end_line: int) -> str:
        """读取磁盘文件的特定行范围，以防上下文过大溢出 Token"""
        absolute_path = os.path.join(self.repo_path, file_path)
        # 实现逐行读取切片逻辑...
        return code_snippet

    def find_callers(self, symbol: str, file_path: str) -> list[dict]:
        """使用本地的 Ctags/AST 倒排索引，返回上游调用者的位置信息"""
        # 回溯调用关系...
        return [{"symbol": caller_name, "file": path, "start": start, "end": end}]

    def find_implementations(self, interface: str) -> list[dict]:
        """寻找接口或虚方法的具体覆写实现，解决动态分发断链问题"""
        # 基于 AST 检索所有 'class ... implements Interface' 或 'extends ...'
        return [{"class": impl_class_name, "file": path}]
```

---

## 5. 异常处理与预算保护 (Gaurds & Exception Handling)

在 `VerifierAgent.verify_candidate` 中必须设计严格的控制锁，以防 Agent 暴走或死循环：

```python
class TokenBudgetGuard:
    def __init__(self, max_turns=12, max_tokens=50000):
        self.max_turns = max_turns
        self.max_tokens = max_tokens
        self.current_turns = 0
        self.current_tokens = 0

    def check_and_record(self, prompt_tokens, completion_tokens):
        self.current_turns += 1
        self.current_tokens += (prompt_tokens + completion_tokens)
        
        if self.current_turns > self.max_turns or self.current_tokens > self.max_tokens:
            raise BudgetExceededException("Agent call budget exceeded safety limit.")
```
如果捕获到 `BudgetExceededException`：
1.  中断大模型循环。
2.  记录警告日志：“Candidate verify failed due to resource limits”。
3.  自动将 Candidate 的最终状态置为 `needs_review`，不判定为 `false_positive`，避免发生漏报。

---

## 6. 测试契约与质量保障 (DoD Tests)

对于核心开发，必须使用 **Test-Driven 思想**，确保每一个编写的模块都经过测试覆盖。
在 `tests/` 目录中，为每个模块配置对应的测试用例：
*   `test_language_discoverer.py`: 测试在混合项目（含 Java, Python, C）中，是否能正确输出 `repo_profile.json`，校验相对路径的准确性。
*   `test_dynamic_packer.py`: 测试向 LLM 请求规则时的解析逻辑，测试在 JSON 解析失败时是否能正确 Fallback 到正则和关键字模式。
*   `test_coarse_scanner.py`: 测试本地 Tree-Sitter 语法树解析速度与候选人过滤的准确率。
*   `test_agentic_triage.py`: Mock 大模型交互，校验 Agent 触发 Tools 的次数、顺序和熔断边界是否正确。
