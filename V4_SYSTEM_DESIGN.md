# Fuzzy Semantic Audit V4 —— 自主智能体漏洞链研判系统设计

## 1. 架构设计愿景与背景

在 Fuzzy Semantic Audit V3 版本中，系统主要依赖“静态批处理管线 + 静态证据包组装 + 大模型无状态判定（Stateless Triage）”。该设计虽然在大规模并发筛选上具有极高效率，但其局限在于：
1.  **上下文信息孤岛**：无状态大模型无法在阅读证据时主动要求读取更多关联代码，导致复杂调用链极易因信息不全被误判为 `MAYBE` 或被搁置。
2.  **调用路径断层**：在遇到多态、接口实现类跳转、回调函数（Callbacks）或动态 Binder 路由时，静态 BFS 算法（[assembler.py](file:///root/fuzzy-semantic-audit/src_v3/evidence/assembler.py)）容易断链，无法将完整的 Source-to-Sink 传导链拼装出来。

**V4 架构的核心思想是：**
> **“以静态算法做极致收缩，以自主智能体（AI Agent）做深度研判”**

V4 不去用昂贵的 AI 扫全库，而是用 V3 静态管道将数十万节点快速预过滤为 10~20 个最高危的控制流 Sink 候选点（Candidate）；随后对每个高危点，启动一个拥有“代码检索与调用图探索工具箱”的 **Verifier Agent**。Agent 能够像安全研究员一样，主动、交互式地分析代码，一步步向上追溯调用链，直至完全确证或证伪其可达性（Reachability），生成完备的调用链传导证据图。

---

## 2. 系统核心控制流与漏斗模型

V4 采用混合式双引擎（Hybrid Dual-Engine）设计，分为两个主阶段：

```
                    [ 源码仓库 ]
                         │
                         ▼
┌──────────────────────────────────────────────────┐
│   阶段一：V3 静态预处理管线 (静态引擎)               │
│   - 自动发现多语言并登记路径 (repo_profile.json)   │
│   - AI 动态生成并打包规则 (scan_pack.json)        │
│   - 本地 AST 词法粗筛 (Candidate Sinks)           │
│   - 严重性打分排序 (verify_queue.json)             │
└──────────────────────────────────────────────────┘
                         │
                         ▼ (收缩至少量高疑点, e.g., <20 Candidates)
┌──────────────────────────────────────────────────┐
│   阶段二：V4 智能体链条研判循环 (智能体引擎)          │
│   - 串行工作流调度器轮询 (orchestrate_audit)       │
│   - 自主 ReAct 探索 (spawn_verifier_agent)       │
│   - 交互式代码图回溯 (tools calling)              │
│   - 最终可达性研判 (reachability verification)     │
└──────────────────────────────────────────────────┘
                         │
                         ▼
                 [ 漏洞报告输出 ]
```

---

## 3. 核心设计盲点规避与优化策略

为了确保 V4 系统在实际生产环境中的健壮性与经济性，设计中强制引入以下三项防御性规避策略：

### 3.1 AI 规则生成 AST 兼容性容错（Fallback 机制）
*   **盲点**：大模型生成的 Tree-Sitter AST 查询结构（S-expressions）可能因语法版本或大模型偏见产生解析异常。
*   **优化**：本地 `ASTCoarseScanner` 必须具备 **Fallback 降级逻辑**。如果大模型输出的 AST 规则发生编译/解析报错，系统必须自动退化为使用大模型同时输出的高精度**关键字/正则表达式**对源码进行文本行级检索过滤，确保粗筛不中断。

### 3.2 智能体 Token 熔断保护（Budget Cap 机制）
*   **盲点**：Agent 在追溯多层嵌套、循环调用（Circular Calls）的调用链时，可能会陷入无休止的代码读取和 callers 跳转循环，导致 Token 消耗爆炸或卡死。
*   **优化**：在 Agent 的 Tools 调度和推理循环中，强制定义 **“单漏洞分析预算上限”**（例如：最大 API 交互次数 = 12 次，最大累积 Token 数 = 50,000）。一旦达到该阈值，系统自动熔断，强制中断 Agent 的当前任务，将该候选点标注为 `needs_review` 并输出已探索的局部链路日志。

### 3.3 多态与虚函数跳转（Dynamic Dispatch 机制）
*   **盲点**：普通的 `find_callers` 工具遇到接口类调用（例如 Java Interface 的 `IEngine.run()`）时，会因静态方法签名不匹配而导致调用链在 interface 处中断。
*   **优化**：必须为 Agent 额外提供 `find_implementations`（寻找接口实现）的工具。当 Agent 发现上游节点是接口定义时，能通过此工具跳转到实现类（Impl Class）的方法体中，保证调用链能够穿透多态限制。

---

## 4. V4 API 与类方法规范设计

V4 代码库将分为 5 个核心模块，其类（Class）和公共 API 的标准设计如下：

### 📦 模块 1：语言发现器 (Inventory) —— 对应 `src_v4/inventory/`
```python
class LanguageDiscoverer:
    """自动扫描项目，识别所有存在的语言并归档文件物理路径"""
    
    def discover(self, repo_path: str) -> dict[str, list[str]]:
        """
        扫描目标仓库，依据后缀精确归类文件物理路径，并持久化写入 repo_profile.json
        输入示例: "/root/Bluetooth"
        返回示例: {
            "java": ["/root/Bluetooth/service/.../BluetoothManagerService.java", ...],
            "cpp": ["/root/Bluetooth/hal/..."]
        }
        """
        pass
```

### 📦 模块 2：AI 动态画像生成器 (Packs/Rules) —— 对应 `src_v4/packs/`
```python
class AIDynamicPacker:
    """面向发现的语言，调用大模型动态生成静态初筛匹配包"""
    
    def generate_pack(self, detected_languages: list[str]) -> dict:
        """
        输入检测到的语言列表，向大模型请求生成特征过滤规则，并持久化为 scan_pack.json
        返回示例: 
        {
            "java": {
                "keywords": ["enforcePrivileged", "AttributionSource"],
                "ast_queries": ["(method_declaration) @decl ..."],
                "regex_patterns": ["checkCallingOrSelf\\w*Permission"]
            }
        }
        """
        pass
```

### 📦 模块 3：静态初筛与严重性排序器 (Filter) —— 对应 `src_v4/filter/`
```python
class ASTCoarseScanner:
    """利用 scan_pack.json 规则对代码进行秒级 AST 词法初筛"""
    
    def scan(self, file_paths: list[str], pack: dict) -> list[dict]:
        """
        利用 Tree-Sitter AST 查询和正则过滤出 Candidate Sinks。
        具备 Fallback 降级机制（若 AST 解析失败，自动退化为正则过滤）。
        """
        pass

class SeverityScorer:
    """对初筛节点进行严重性特征打分并排序"""
    
    def score_and_queue(self, candidates: list[dict]) -> list[dict]:
        """
        计算每个 Candidate 严重分，标注等级 (Critical/High/Medium/Low)，
        按分值降序排列，持久化写入 verify_queue.json 待验证队列。
        """
        pass
```

### 📦 模块 4：自主验证智能体 (Verify) —— 对应 `src_v4/verify/`
```python
class AgentTools:
    """提供给大模型智能体执行交互式污点分析的本地工具箱"""
    
    def read_file_segment(self, file_path: str, start_line: int, end_line: int) -> str:
        """读取指定代码片段，辅助 AI 阅读"""
        pass
        
    def find_callers(self, symbol: str, file_path: str) -> list[dict]:
        """逆向查找所有调用此符号的上游入口和行区间"""
        pass
        
    def find_implementations(self, interface: str) -> list[dict]:
        """多态跳转：查找实现此接口或抽象方法的具体子类"""
        pass

class VerifierAgent:
    """自主研判智能体"""
    
    def verify_candidate(self, candidate: dict, tools: AgentTools) -> dict:
        """
        拉起子 Agent，载入 Tools，进行 ReAct 推理循环，追踪数据流，直至返回可达性报告。
        内置 Token 和调用深度熔断限制。
        返回示例: {
            "verdict": "YES" | "NO" | "NEEDS_REVIEW",
            "reasoning_path": ["SinkNode", "Caller_1", "Caller_2", "SourceEntrypoint"]
        }
        """
        pass
```

### 📦 模块 5：工作流控制器 (Workflow) —— 对应 `src_v4/cli/`
```python
class AuditOrchestrator:
    """系统工作流引擎控制器，作为串行队列的执行保障"""
    
    def execute(self, workspace_path: str):
        """
        控制流次序：
        1. 启动 LanguageDiscoverer -> 产出 repo_profile.json
        2. 启动 AIDynamicPacker -> 产出 scan_pack.json
        3. 运行 ASTCoarseScanner & Scorer -> 产出 verify_queue.json
        4. 循环从队列中 pop 高危 Candidate -> 拉起 VerifierAgent 验证 -> 串行回写报告
        """
        pass
```

---

## 5. Triage 决策判定与状态转换机制

Agent 完成审计后，必须提交一份结构化的漏洞分析报告，并输出最终的 Verdict 判决。[verdict_policy.py](file:///root/fuzzy-semantic-audit/src_v3/verify/verdict_policy.py) 依据 Agent 的报告进行最终状态路由：

| Agent 研判结论 (Verdict) | 可达性证据链 (Evidence Path) | 系统最终路由状态 |
| --- | --- | --- |
| **YES (Reachable)** | 存在清晰、无阻断的 Source-to-Sink 调用路径 | `verified` (确认漏洞，计入漏洞报告) |
| **NO (Unreachable)** | 控制流在中途被物理切断，或被安全 Sanitizer 彻底阻断 | `false_positive` (误报，排除) |
| **NEEDS_REVIEW / BLOCKED** | 发生 Token 熔断，或遇到混淆代码导致无法判定 | `needs_review` (待人工审核，归档) |

---

## 6. V4 开发路线实施计划

为保证系统的平稳升级，开发将分阶段执行（已对齐 [V4_TASK_BREAKDOWN.md](file:///root/fuzzy-semantic-audit/V4_TASK_BREAKDOWN.md)）：

1.  **Stage 1: P0 阶段 —— 自动发现多语言与文件登记**
    实现 `LanguageDiscoverer`，能够扫描多语言项目并保存 `repo_profile.json`。
2.  **Stage 2: P1 阶段 —— 动态规则生成**
    实现 `AIDynamicPacker`，能根据语言动态向大模型调配并打包出 `scan_pack.json` 规则。
3.  **Stage 3: P2 阶段 —— AST 粗筛与排序**
    开发本地 AST 词法扫描引擎与打分器，创建 `verify_queue.json` 严重性排序队列。
4.  **Stage 4: P3 阶段 —— 智能体验证环与 Workflow 串行集成**
    完成 Agent Tools 工具箱、Verifier Agent 自主 ReAct 环开发，并由 `AuditOrchestrator` 串联起整个流程，输出漏洞链报告。
