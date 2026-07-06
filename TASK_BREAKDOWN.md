# Fuzzy Semantic Audit V2 —— Task Breakdown

> 目的: 将 V2 的需求、系统设计、软件设计进一步拆解为可直接交给其他 AI 编码工具执行的原子任务。
> 本文档关注“先做什么、后做什么、每步交付什么、什么算完成”。

---

## 1. 使用方式

执行任务前必须同时阅读:

1. `REQUIREMENTS.md`
2. `V2_SYSTEM_DESIGN.md`
3. `V2_SOFTWARE_DESIGN.md`
4. `AI_IMPLEMENTATION_GUIDE.md`

任务执行规则:

1. 一次只做一个任务或一个强相关任务组。
2. 先完成 P0,再做 P1/P2。
3. 未完成前置依赖的任务不得提前实现。
4. 每个任务完成后必须满足该任务的 DoD。

---

## 2. 任务总览

### P0

1. T01 建立 V2 目录骨架
2. T02 实现核心数据模型
3. T03 实现状态机
4. T04 实现 plan 读写模块
5. T05 实现 candidate registry
6. T06 实现 queue store
7. T07 实现 `init_plan.py`
8. T08 实现 repo profiler
9. T09 实现 language sharder
10. T10 实现 `build_inventory.py`
11. T11 实现 coverage report
12. T12 实现 workflow 骨架

### P1

13. T13 实现 generic plugin
14. T14 实现 recall normalizer
15. T15 实现 recall orchestrator
16. T16 实现 `recall_candidates.py`
17. T17 实现 verdict policy
18. T18 实现 writeback
19. T19 实现 `verify_batch.py`
20. T20 实现 `compile_reports.py`

### P2

21. T21 接入 codegraph client
22. T22 接入 embedding index
23. T23 实现语言专属插件
24. T24 实现资源访问 recall
25. T25 完善验证包与裁判 prompt

### P3

26. T26 实现 audit report
27. T27 实现 review queue report
28. T28 实现 event log 与运行指标
29. T29 实现中断恢复与重试策略
30. T30 实现配置加载与默认配置
31. T31 完成端到端集成测试
32. T32 完成回归测试与黄金样例

### P4

33. T33 实现性能优化与增量索引验证
34. T34 实现 CLI/Workflow 错误语义统一
35. T35 实现旧版到 V2 的迁移工具
36. T36 完成用户文档与操作手册
37. T37 完成发布检查与交付封板

---

## 3. P0 任务

### T01 建立 V2 目录骨架

目标:

- 创建 `src_v2/`、`workflows/`、`resources_v2/` 的基础目录。

输入:

- 设计文档

输出:

- 空目录和 `__init__.py`

依赖:

- 无

DoD:

1. 目录结构与 `V2_SOFTWARE_DESIGN.md` 一致。
2. 关键 Python 包目录可导入。

---

### T02 实现核心数据模型

目标:

- 实现 `src_v2/core/models.py`

输入:

- `AI_IMPLEMENTATION_GUIDE.md` 中的数据契约

输出:

- `AuditPlan`
- `RepoProfile`
- `LanguageShard`
- `AuditTrack`
- `CandidateRecord`
- `VerificationResult`

依赖:

- T01

DoD:

1. 模型字段覆盖文档中的最小 schema。
2. 支持 `to_dict()` / `from_dict()` 或等价序列化方法。

---

### T03 实现状态机

目标:

- 实现 `src_v2/core/state_machine.py`

输入:

- `AI_IMPLEMENTATION_GUIDE.md` 的状态转移表

输出:

- `can_transition()`
- `transition()`

依赖:

- T02

DoD:

1. 文档允许的转移返回 true。
2. 文档禁止的转移返回 false 或抛异常。

---

### T04 实现 plan 读写模块

目标:

- 实现 `src_v2/core/plan_io.py`

输出:

- `load_plan()`
- `save_plan()`
- `update_plan_summary()`

依赖:

- T02

DoD:

1. 能创建和保存 `audit_plan.json`
2. 更新时间戳
3. 写盘幂等

---

### T05 实现 candidate registry

目标:

- 实现 `src_v2/core/candidate_registry.py`

输出:

- `upsert_candidates()`
- `load_candidates()`
- `get_candidate()`
- `update_candidate_status()`

依赖:

- T02
- T03

DoD:

1. 存储格式为 `jsonl`
2. 以 `identity_key` 去重
3. 不允许以函数名单独去重

---

### T06 实现 queue store

目标:

- 实现 `src_v2/core/queue_store.py`

输出:

- `enqueue()`
- `dequeue()`
- `requeue()`
- `peek()`

依赖:

- T02

DoD:

1. 支持 `verify_now`、`deferred`、`manual_review`
2. queue 文件结构符合文档约定
3. 出队不会删除 registry 中的候选

---

### T07 实现 `init_plan.py`

目标:

- 初始化 `.audit_workspace_v2`

输出:

- workspace 目录
- 空 `audit_plan.json`
- 空 `candidate_registry.jsonl`
- 空 queues

依赖:

- T04
- T05
- T06

DoD:

1. CLI 可执行
2. 最后一行输出 JSON contract

---

### T08 实现 repo profiler

目标:

- 实现 `src_v2/inventory/repo_profiler.py`

输出:

- 扫描仓库文件
- 识别语言分布
- 识别测试/生成目录
- 识别框架指纹

依赖:

- T02

DoD:

1. 生成 `RepoProfile`
2. 至少支持 Python/JS/TS/Go/Java/C/C++ 文件扩展名识别

---

### T09 实现 language sharder

目标:

- 实现 `src_v2/inventory/language_sharder.py`

输出:

- 基于 `RepoProfile` 生成 `LanguageShard[]`

依赖:

- T02
- T08

DoD:

1. 多语言仓库能拆成多个 shard
2. 未知语言走 `generic` shard

---

### T10 实现 `build_inventory.py`

目标:

- 调用 profiler 和 sharder,写回 `audit_plan.json`

依赖:

- T04
- T08
- T09

DoD:

1. 生成 `repo_profile.json`
2. 生成 `language_shards`
3. CLI 输出符合 contract

---

### T11 实现 coverage report

目标:

- 实现 `src_v2/report/coverage_report.py`

依赖:

- T04
- T05
- T06

DoD:

1. 报告标题和章节符合 `AI_IMPLEMENTATION_GUIDE.md`
2. 至少展示 shard 覆盖、track 覆盖、candidate status、zero recall、deferred、errors

---

### T12 实现 workflow 骨架

目标:

- 实现以下 workflow 占位版本:
  - `v2_orchestrate_audit.js`
  - `v2_build_inventory.js`
  - `v2_recall_candidates.js`
  - `v2_verify_queue.js`
  - `v2_compile_reports.js`

依赖:

- T07
- T10
- T11

DoD:

1. workflow 能按顺序调用 CLI
2. 输入输出 JSON contract 与文档一致
3. 即使 recall/verify 未完全实现,也不能静默跳过

---

## 4. P1 任务

### T13 实现 generic plugin

目标:

- 实现 `src_v2/plugins/base.py` 和 `src_v2/plugins/generic.py`

依赖:

- T02

DoD:

1. 接口字段与 `AI_IMPLEMENTATION_GUIDE.md` 一致
2. 可对未知语言文件提供最基本的规则和资源信号

---

### T14 实现 recall normalizer

目标:

- 实现 `src_v2/recall/normalizer.py`

依赖:

- T02
- T05

DoD:

1. 多 recall 源结果可合并
2. 候选 identity 稳定
3. 同名不同文件不会冲突

---

### T15 实现 recall orchestrator

目标:

- 实现 `src_v2/recall/orchestrator.py`

依赖:

- T13
- T14

DoD:

1. 能按 shard × track 跑 recall
2. 零召回也会记录结果

---

### T16 实现 `recall_candidates.py`

目标:

- 调 recall orchestrator
- upsert registry
- 更新 verify queue

依赖:

- T05
- T06
- T10
- T15

DoD:

1. CLI 输出包含 `candidates_total`
2. 输出 `zero_recall_pairs`
3. 入队结果可被后续 verify 使用

---

### T17 实现 verdict policy

目标:

- 实现 `src_v2/verify/verdict_policy.py`

依赖:

- T02

DoD:

1. `verified / needs_review / false_positive / deferred` 判定规则符合文档
2. 不把预算问题表达为安全结论

---

### T18 实现 writeback

目标:

- 实现 `src_v2/verify/writeback.py`

依赖:

- T04
- T05
- T17

DoD:

1. 支持批量写回
2. 支持 plan summary 更新
3. 支持失败重试

---

### T19 实现 `verify_batch.py`

目标:

- 消费 verify queue
- 写回 verdict

依赖:

- T06
- T17
- T18

DoD:

1. `verifyLimit` 仅限制本轮消费数量
2. 未消费候选仍在队列或进入 deferred
3. CLI 输出符合文档 contract

---

### T20 实现 `compile_reports.py`

目标:

- 汇总 audit report / coverage report / review queue

依赖:

- T11
- T18
- T19

DoD:

1. 输出 3 个报告文件
2. CLI 返回路径

---

## 5. P2 任务

### T21 接入 codegraph client

目标:

- 实现 `src_v2/integrations/codegraph_client.py`

依赖:

- T13

DoD:

1. 统一封装 files/symbols/source/callers/callees
2. 有超时和错误处理

---

### T22 接入 embedding index

目标:

- 实现 `src_v2/integrations/embedding_index.py`

依赖:

- T13

DoD:

1. 支持 build/search
2. 支持 shard 级索引

---

### T23 实现语言专属插件

目标:

- 实现:
  - `python.py`
  - `javascript.py`
  - `go.py`
  - `java.py`
  - `c.py`
  - `cpp.py`

依赖:

- T13
- T21

DoD:

1. 至少 3 个插件可工作
2. 可提供框架探测、资源信号和 track 规则

---

### T24 实现资源访问 recall

目标:

- 实现 `src_v2/recall/resource_recall.py`

依赖:

- T13
- T23

DoD:

1. 可对 `authz` / `resource_access` / `state_machine` 提供增强召回
2. 零召回会被记录

---

### T25 完善验证包与裁判 prompt

目标:

- 实现:
  - `package_builder.py`
  - `referee_prompts.py`

依赖:

- T17
- T21
- T23

DoD:

1. 候选包包含代码、调用链、track、rules、framework hints
2. 裁判 prompt 区分 reachability / guard / exploitability

---

## 6. P3 任务

### T26 实现 audit report

目标:

- 实现 `src_v2/report/audit_report.py`

依赖:

- T18
- T19

DoD:

1. 输出 verified / needs_review / false_positive 三桶明细
2. 每条结果包含 candidate identity、原因、证据摘要
3. 报告内容和 registry 状态一致

---

### T27 实现 review queue report

目标:

- 实现 `src_v2/report/review_queue.py`

依赖:

- T18
- T19

DoD:

1. 列出 `needs_review` 与 `deferred`
2. 按 shard、track、priority 分组
3. 给出人工复核建议入口

---

### T28 实现 event log 与运行指标

目标:

- 实现 `src_v2/core/event_log.py`
- 记录阶段事件、失败事件、计数指标

依赖:

- T04
- T05
- T06

DoD:

1. 每个阶段有开始/结束/失败事件
2. 记录耗时、候选数、队列数
3. 日志可供 report 和调试复用

---

### T29 实现中断恢复与重试策略

目标:

- 为 CLI 和 workflow 增加恢复能力

依赖:

- T06
- T18
- T28

DoD:

1. 中断后可从 queue 和 registry 恢复
2. `error -> queued_for_verify` 可重试
3. 幂等重复执行不会破坏状态

---

### T30 实现配置加载与默认配置

目标:

- 实现 `resources_v2/` 默认配置与加载逻辑

依赖:

- T13
- T23

DoD:

1. 支持语言配置
2. 支持 track 配置
3. 缺配置时有安全降级,不会静默失效

---

### T31 完成端到端集成测试

目标:

- 基于真实或半真实 fixture 跑通完整流程

依赖:

- T20
- T29

DoD:

1. 单语言仓库 E2E 通过
2. 多语言仓库 E2E 通过
3. 生成三类报告且内容完整

---

### T32 完成回归测试与黄金样例

目标:

- 建立 regression fixtures 与 golden outputs

依赖:

- T26
- T27
- T31

DoD:

1. 同名函数不丢失
2. budget 不会生成 `false_positive`
3. zero-recall pairs 会稳定进入 coverage report
4. 报告输出可对比 golden files

---

## 7. P4 任务

### T33 实现性能优化与增量索引验证

目标:

- 完成性能 profiling 与增量索引 correctness 校验

依赖:

- T22
- T31

DoD:

1. 增量索引可复用未变化 shard
2. 大仓库下 recall/verify 仍可分批推进
3. 输出性能基线数据

---

### T34 实现 CLI/Workflow 错误语义统一

目标:

- 统一错误码、错误 JSON、日志字段

依赖:

- T12
- T29

DoD:

1. 所有 CLI 失败时输出统一 JSON
2. workflow 可据此判断 `deferred` / `error`
3. 错误信息可定位到阶段和对象

---

### T35 实现旧版到 V2 的迁移工具

目标:

- 提供从旧 workspace 或旧 plan 迁移到 V2 的辅助工具

依赖:

- T04
- T05

DoD:

1. 可从旧结构导入项目路径和候选基础信息
2. 不复用旧版单语言假设
3. 迁移失败不覆盖原数据

---

### T36 完成用户文档与操作手册

目标:

- 补充运行说明、配置说明、常见故障说明

依赖:

- T31

DoD:

1. 提供 quickstart
2. 提供 monorepo 使用说明
3. 提供恢复和重试说明

---

### T37 完成发布检查与交付封板

目标:

- 完成全量实现前的最终核查

依赖:

- T32
- T33
- T34
- T36

DoD:

1. 所有 P0-P4 任务完成
2. 文档、测试、workflow、CLI 对齐
3. 可直接交付给其他 AI 或人工团队继续维护

---

## 8. 推荐任务分派

如果交给多个 AI 工具并行开发,推荐这样拆:

### Agent A

- T01-T07

### Agent B

- T08-T10

### Agent C

- T11-T12

### Agent D

- T13-T16

### Agent E

- T17-T20

### Agent F

- T21-T25

### Agent G

- T26-T32

### Agent H

- T33-T37

并行前提:

1. 公共 schema 以 T02 为准
2. 公共状态机以 T03 为准
3. CLI contract 以 `AI_IMPLEMENTATION_GUIDE.md` 为准

---

## 9. 交付检查清单

每个任务完成后必须检查:

1. 是否符合上游文档
2. 是否引入了旧版单语言假设
3. 是否可能静默丢候选
4. 是否把预算问题误写成 `false_positive`
5. 是否提供了结构化输出

---

## 10. 最小实施路径

如果只做 MVP,按以下顺序执行即可:

1. T01
2. T02
3. T03
4. T04
5. T05
6. T06
7. T07
8. T08
9. T09
10. T10
11. T11
12. T12
13. T13
14. T14
15. T15
16. T16
17. T17
18. T18
19. T19
20. T20

做到这里,其他 AI 工具已经能按文档完成一个可运行的 V2 MVP。

---

## 11. 全量实施路径

如果目标是全量实现,推荐顺序:

1. 完成全部 P0
2. 完成全部 P1
3. 完成全部 P2
4. 完成 T26-T32,先把功能闭环和测试闭环补齐
5. 完成 T33-T37,最后做性能、迁移、发布收口

全量实现的完成标准:

1. 多语言 shard、插件、召回、验证、报告全部可运行
2. 有 E2E 测试和回归基线
3. 有恢复策略和统一错误语义
4. 有文档和迁移工具
5. 可作为稳定 V2 主线继续迭代
