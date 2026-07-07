# Fuzzy Semantic Audit V3 —— 需求文档

> 目标: 定义 Fuzzy Semantic Audit V3 的产品需求、功能边界、验收标准和实施优先级。
> 本文档面向实现阶段,作为 `V3_SYSTEM_DESIGN.md`、`V3_SOFTWARE_DESIGN.md` 与 `V3_TASK_BREAKDOWN.md` 的上游输入。

---

## 1. 项目目标

V3 的目标不是继续在 V2 上局部修补,而是构建一套真正通用、能力透明、可降级、可扩展的代码审计 skill。

系统必须满足:

1. 任意语言仓库都可审计。
2. 主流语言具备更深的语义审计能力。
3. 降级路径必须透明。
4. 召回结果必须可收敛到可 triage 规模。
5. 输出必须区分 `verified`、`needs_review`、`false_positive`、`deferred`、`error`。

---

## 2. 核心需求

### 2.1 通用性

系统必须:

1. 支持多语言仓库与 monorepo。
2. 不允许通过“主语言唯一化”忽略其他语言。
3. 对弱支持语言至少提供 `L0/L1` 审计能力。

### 2.2 能力透明

系统必须:

1. 为运行、shard、candidate 显式标记 capability level。
2. 为降级运行显式记录 `run_mode` 与 `degradation_reasons`。
3. 在报告中展示 `indexed_fallback`、`recalled_fallback` 等状态。

### 2.3 统一数据平面

系统必须:

1. 用统一 IR 表达结构信息。
2. 用统一 CandidateRecord 表达召回结果。
3. 用统一 EvidenceBundle 表达验证输入。

### 2.4 多阶段收敛

系统必须:

1. 支持高召回多通道 recall。
2. 支持静态 pruning 与优先级排序。
3. 支持 evidence assembly。
4. 只让收敛后的候选进入 LLM triage。

### 2.5 验证机制

系统必须:

1. 至少保留三个裁判视角:
   - reachability
   - guard
   - exploitability
2. 用结构化写回保存 verdict。
3. 不允许因预算或调度问题直接把候选写成 `false_positive`。

---

## 3. 约束

系统不得:

1. 把单一工具链当成唯一真相源。
2. 把 fallback 伪装成 full semantic。
3. 仅凭函数名去重候选。
4. 把未审计候选伪装成已证伪结果。

---

## 4. 实施优先级

### P0

1. 核心数据模型
2. 状态机
3. plan/run manifest
4. storage/event log/metrics
5. workflow 骨架

### P1

1. inventory
2. parser providers
3. IR builder 与 cache
4. build_inventory/build_ir

### P2

1. semantic providers
2. embedding providers
3. provider registry
4. build_index

### P3

1. framework packs
2. recall pipeline
3. candidate store
4. recall_candidates

### P4

1. pruning
2. evidence
3. verify_batch
4. reports

---

## 5. 结论

V3 的需求核心可以概括为一句话:

> 构建一套对所有语言可审计、对主流语言可深审、对降级路径透明可见、并能把大规模召回稳定收敛到可 triage 规模的通用代码审计 skill。

