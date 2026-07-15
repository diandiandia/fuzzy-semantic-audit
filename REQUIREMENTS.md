# Fuzzy Semantic Audit V4 —— 系统核心需求说明

V4 版本的核心设计宗旨是：**面向多语言，结合“本地轻量静态粗筛”与“大模型智能体自主追踪验证”，实现高效、精准、完备的漏洞研判。**

以下是系统的 8 大最简核心需求：

---

### 1. 🌐 多语言支持 (Requirement 1)
- 系统解析与扫描必须面向所有主流代码语言（如 Java, C/C++, Python, Go, Rust），不针对单一语言做编译器级强耦合。

### 2. 📂 语言发现与文件登记 (Requirement 2)
- 系统在 Inventory 阶段必须自动扫描并判别项目中包含的语言，并将所有相关的物理文件路径分门别类记录到 `repo_profile.json` 中。

### 3. 🛡️ CWE 语言画像 (Requirement 3)
- 系统必须为每类语言关联标准的安全漏洞维度（如 Authz, Injection, StateMachine, InputValidation），列举该语言可能存在的安全漏洞隐患。

### 4. 🧠 AI 动态规则打包 (Requirement 4)
- 识别到语言后，系统必须调用大模型为该语言动态生成特征关键字、Tree-Sitter AST 匹配模式及正则表达式，并将这些规则打包输出为静态扫描规则。

### 5. 🔍 AST 词法粗筛 (Requirement 5)
- 系统必须利用上一步打包的静态扫描规则，在本地通过 AST（Tree-Sitter）和正则进行秒级的“粗筛（Pre-Filter）”，过滤掉 90% 以上的无害代码，找出潜在的问题候选点（Candidate Sinks）。

### 6. 📈 严重性优先级排序 (Requirement 6)
- 系统必须在本地计算候选点的严重特征分数，并按 `Critical (危)`、`High (高危)`、`Medium`、`Low` 的严重性降序排列，写入待验证队列。

### 7. 🤖 智能体自主污点分析 (Requirement 7)
- 对于高危/危候选点，系统必须将线索直接提交给拥有工具使用权（`read_file_segment`, `find_callers`, `find_implementations`）的自主安全智能体（AI Agent）。
- Agent 必须模拟人类安全专家的思路，自行决定跳转并读取哪些文件，沿着调用链进行跨文件的数据流污点分析，最终做出可达性（Reachability）研判。

### 8. 📋 工作流串行验证机制 (Requirement 8)
- 系统必须使用串行队列（Workflow Queue）控制。所有的验证任务必须按照优先级高低的严格次序被依次分发给 Agent 验证，禁止以任何杂乱或并行的非受控方式跳过验证，确保审计结论的百分之百完整性。
