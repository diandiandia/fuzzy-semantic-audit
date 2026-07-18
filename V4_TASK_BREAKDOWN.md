# Fuzzy Semantic Audit V4 —— 工程化任务分解 (DoD)

本文件作为 V4 版本开发的指南针，严格拆解 8 大核心诉求为可执行的工程任务。所有后续开发必须依照此任务次序递进，禁止跳过。

---

## 🛠️ P0 阶段：多语言支持与文件索引 (对应诉求 1 & 2)

- [x] **Task 0.1: 语言自动发现与 Classify 引擎**
  - 在 `src_v4/inventory/language_sharder.py` 中实现对多语言文件后缀的扫描，识别项目中存在的所有语言。
  - 将识别结果和文件物理路径精确记录并保存到 `repo_profile.json` 中。
  - **DoD**: 能够识别 Java, C/C++, Python, Rust 等语言，输出完整的文件物理路径清单。

---

## 🛠️ P1 阶段：CWE 安全画像与动态规则打包 (对应诉求 3 & 4)

- [x] **Task 1.1: 静态 CWE 画像库**
  - 在 `src_v4/packs/tracks.py` 中，定义标准的通用 CWE 安全维度（如 Authz, Injection, InputValidation, StateMachine）。
- [x] **Task 1.2: AI 动态规则打包器 (Dynamic Rules Packer)**
  - 实现一个向大模型发送请求的包装器，针对每种发现的语言，输入 CWE 画像，要求大模型返回：
    1. 敏感汇聚特征关键字 (Keywords)；
    2. Tree-Sitter AST 查询片段 (AST Query Schemes)；
    3. 特征正则表达式。
  - 将这些规则打包存为 `scan_pack.json`。
  - **DoD**: 运行后可根据识别的语言，由 AI 自动生成并存盘该语言的词法/AST 筛选包。

---

## 🛠️ P2 阶段：静态粗筛与严重性排序 (对应诉求 5 & 6)

- [x] **Task 2.1: AST/正则粗筛器 (Coarse-Scanner)**
  - 根据 `scan_pack.json` 中的 AST 规则与正则，在本地使用轻量级 AST（Tree-Sitter）遍历，粗筛出潜在问题候选点（Candidate Sinks）。
- [x] **Task 2.2: 严重性优先级排序器 (Severity Scorer)**
  - 静态计算候选点的特征评分，区分出 `Critical` / `High` / `Medium` / `Low` 严重性等级。
  - 按优先级降序，写入待验证串行队列 `verify_queue.json` 中。
  - **DoD**: 能够在不请求大模型的情况下，在本地 10 秒内输出一个排好序的待验证高危队列。

---

## 🛠️ P3 阶段：智能体自主污点分析与串行 Workflow (对应诉求 7 & 8)

- [x] **Task 3.1: 交互式 Agent Tools 箱开发**
  - 在 `src_v4/tools/` 下，为 AI 智能体封装三项核心的本地代码图探索工具：
    1. `read_file_segment(path, lines)` (查看特定代码段)；
    2. `find_callers(symbol, file)` (查找上游调用点)；
    3. `find_implementations(interface)` (查找多态实现)。
- [x] **Task 3.2: 自主审计智能体 (Verifier Agent)**
  - 开发 `src_v4/verify/agentic_triage.py`。输入 Candidate 线索，拉起子 Agent，让其利用 Tools 自动自主分析调用路径与污点流动，直至给出 `YES (Reachable)` 或 `NO (Guarded)` 的可达性判定。
- [x] **Task 3.3: 队列串行 Workflow (Orchestration)**
  - 在 `src_v4/cli/orchestrate_audit.py` 中，实现串行轮询控制。读取 `verify_queue.json`，确保所有 Candidate **按优先级严格次序被依次分发给 Agent 研判并回写结果**。
  - **DoD**: 所有的 Candidate 都经过 Agent 的自主 Tool-Calling 跳转分析，且路径记录在最终报告中。
