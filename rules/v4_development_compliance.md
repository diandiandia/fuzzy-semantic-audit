---
description: Enforce V4 system architecture compliance and prevent design drift during development
globs: "V4_*"
---

# Fuzzy Semantic Audit V4 —— 开发合规性约束规则 (System Rule)

> [!IMPORTANT]
> **本规则为系统级强约束守则。所有处理此工作区的 AI 智能体（Agent / Subagent）必须严格遵守本规则的所有条款，严禁发生架构设计偏离。**

---

## 🛑 核心禁止项 (Architectural Boundaries)
1.  **禁止开发“复杂的静态跨文件判定”**：静态解析（[V4_TASK_BREAKDOWN.md](file:///root/fuzzy-semantic-audit/V4_TASK_BREAKDOWN.md#P2)）在本地只负责进行语法/正则的“粗筛（Pre-Filter）”和“排序（Scoring）”。严禁在静态侧编写繁琐、脆弱的静态跨文件连通性判定逻辑。
2.  **禁止使用“无状态批处理大模型裁判”**：在验证阶段，禁止直接将大段静态拼装的代码文本扔给 LLM 仅做单步判定。所有的判定动作必须交由**被授予工具使用权的自主智能体（Verifier Agent）**交互式执行。
3.  **禁止跳过验证队列**：禁止以任何非顺序或并行的粗暴方式抛弃队列。必须通过 [verify_queue.json](file:///root/fuzzy-semantic-audit/V4_TASK_BREAKDOWN.md#P3) 保证所有高危及危的问题依次串行被证明。

---

## ✅ 开发必须遵守项 (DoD Checklist)
1.  **多语言适配性**：所有新增的文件解析器和提取器必须使用通用的 Tree-Sitter 结构，不可针对单一语言做强耦合的编译器依赖设计。
2.  **线索分发机制**：静态漏斗只能将“Candidate Sink 节点”、“所在文件”以及“AI 生成的关键字/正则”作为**线索（Clues）**传递给 Verifier Agent。Agent 必须拥有独立的 `read_file_segment`、`find_callers` 和 `find_implementations` 工具。
3.  **智能体自主性**：Agent 必须扮演安全研究员，自主决定读取哪些文件，自主执行跨文件的 callers 追溯和污点判定。
4.  **工作流串行保障**：任何验证任务必须由工作流（Workflow）调度器按 `Critical -> High` 的优先级次序，逐一拉起 Agent 进行验证，并如实将 Agent 的推理链路回写至 review queue 报告中。
