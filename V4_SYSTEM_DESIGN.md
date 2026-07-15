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
│   - IR 构建 (build_ir)                           │
│   - 符号倒排索引 (build_index)                   │
│   - 多通道高召回 (recall_candidates)              │
│   - 特征修剪 (prune_candidates)                  │
└──────────────────────────────────────────────────┘
                         │
                         ▼ (收缩至少量高疑点, e.g., <20 Candidates)
┌──────────────────────────────────────────────────┐
│   阶段二：V4 智能体链条研判循环 (智能体引擎)          │
│   - 任务分发 (agentic_dispatcher)                │
│   - 自主 ReAct 探索 (spawn_verifier_agent)       │
│   - 交互式代码图回溯 (tools calling)              │
│   - 最终可达性研判 (reachability verification)     │
└──────────────────────────────────────────────────┘
                         │
                         ▼
                 [ 漏洞报告输出 ]
```

---

## 3. 研判智能体（Verifier Agent）与工具箱设计

### 3.1 Agent 角色与推理范式
每个被分发的 Candidate 都会启动一个独立的子 Agent（基于 ReAct 模式）。其 Prompt 指引其扮演一名精通 Java/C++/Rust 的高级安全研究员。

Agent 在分析过程中的思考-行动循环（Thought-Action-Observation Loop）如下：
*   **Thought**：当前节点是 `Enable.exec()`。我需要知道是谁调用了它。
*   **Action**：调用 `find_callers("exec", "com/android/server/bluetooth/BluetoothShellCommand$Enable.java")`。
*   **Observation**：发现上游唯一调用者是 `BluetoothShellCommand.onCommand()`。
*   **Thought**：我需要查看 `onCommand()` 的具体代码逻辑，检查其是否有 UID 校验。
*   **Action**：调用 `read_file_segment("com/android/server/bluetooth/BluetoothShellCommand.java", 220, 256)`。
*   **Observation**：发现只对 `isPrivileged() == true` 的命令做 ROOT_UID 检查，而 `enable` 命令的 `isPrivileged()` 是 `false`。
*   **Thought**：这表明控制流可以穿透！我需要继续向上寻找 `onCommand()` 的调用者，看是否能从外部 Binder 事务入口（Source）直接触发。

### 3.2 交互式工具箱接口规范 (Agent Tools)

Agent 在研判时可随时调用以下本地静态分析工具：

#### 1. `find_callers`
*   **输入**：`symbol_name: str`, `file_path: str`
*   **输出**：调用该符号的上游符号列表、文件路径及代码行区间。
*   **实现基础**：基于 V3 的 `CtagsProvider` 和 `ir_store` 中的 `IREdge` 调用边。

#### 2. `read_file_segment`
*   **输入**：`file_path: str`, `start_line: int`, `end_line: int`
*   **输出**：指定代码段 of 文本内容。

#### 3. `find_implementations`
*   **输入**：`interface_name: str`, `method_name: str`
*   **输出**：实现该接口或抽象方法的具体子类符号及所在文件。

#### 4. `search_keyword`
*   **输入**：`query_regex: str`
*   **输出**：仓库中所有匹配该正则的文件与行匹配点（用于定位隐蔽的动态反射或 intent-filter 路由）。

---

## 4. Triage 决策判定与状态转换机制

Agent 完成审计后，必须提交一份结构化的漏洞分析报告，并输出最终的 Verdict 判决。[verdict_policy.py](file:///root/fuzzy-semantic-audit/src_v3/verify/verdict_policy.py) 依据 Agent 的报告进行最终状态路由：

| Agent 研判结论 (Verdict) | 可达性证据链 (Evidence Path) | 系统最终路由状态 |
| --- | --- | --- |
| **YES (Reachable)** | 存在清晰、无阻断的 Source-to-Sink 调用路径 | `verified` (确认漏洞，计入漏洞报告) |
| **NO (Unreachable)** | 控制流在中途被物理切断，或被安全 Sanitizer 彻底阻断 | `false_positive` (误报，排除) |
| **MAYBE / BLOCKED** | 遇到混淆代码或缺乏底层环境无法判定 | `needs_review` (待人工审核，归档) |

---

## 5. V4 开发路线实施计划

为保证系统的平稳升级，开发将分阶段执行：

1.  **Stage 1: 基础工具箱定义**
    在 `src_v3/providers/semantic/` 的基础上，封装适合大模型 Tool Calling 的标准 API 接口，并导出为 Agent 可以使用的 Python 函数句柄。
2.  **Stage 2: 编写自主验证中心**
    创建 `src_v4/verify/agentic_triage.py` 作为新验证阶段 of 入口，取代原先批处理的 `verify_batch.py`。
3.  **Stage 3: 优化报告模块**
    重构 [compile_reports.py](file:///root/fuzzy-semantic-audit/src_v3/cli/compile_reports.py)，使编译出来的 [review_queue.md](file:///root/Bluetooth/.audit_workspace_v3_test/reports/review_queue.md) 可以渲染出 Agent 研判时输出的完整调用链路跳转图。
