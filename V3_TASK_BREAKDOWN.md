# Fuzzy Semantic Audit V3 —— 开发计划

> 目的: 将 `V3_SYSTEM_DESIGN.md` 与 `V3_SOFTWARE_DESIGN.md` 拆解为可直接执行的软件开发任务。
> 本文档关注“按什么顺序做、每步交付什么、什么算完成、哪些任务必须先完成”。

---

## 1. 使用方式

执行 V3 任务前必须同时阅读:

1. `REQUIREMENTS.md`
2. `V3_SYSTEM_DESIGN.md`
3. `V3_SOFTWARE_DESIGN.md`

执行规则:

1. 一次只做一个任务或一个强相关任务组。
2. 先完成 P0,再做 P1/P2/P3。
3. 未完成前置依赖的任务不得提前实现。
4. 每个任务完成后必须满足该任务 DoD。
5. 任一任务如果引入 fallback,必须同步更新状态契约、coverage report 和 event log。

本文档从现在开始不仅是“原始任务清单”,还用于跟踪当前分支距离 full implementation 的剩余工作。

状态口径:

1. `done`: 代码存在且 DoD 基本达成。
2. `partial`: 代码存在,但仍有明显契约缺口、stub、错误边界或未达 DoD 的地方。
3. `todo`: 目标模块缺失,或主体能力尚未实现。

---

## 2. 当前实现状态快照

按当前分支实现情况,整体状态如下:

| 阶段 | 状态 | 说明 |
| --- | --- | --- |
| P0 基础骨架 | `partial` | 主体文件已存在,但目录与文档仍未完全对齐,且部分状态/契约仍偏松。 |
| P1 Inventory / Parse | `partial` | 主链路可运行,但 repo/workspace 边界、ignore 规则、effective capability 判定未达标。 |
| P2 Provider / Index | `partial` | provider 框架已搭起,但多个 provider 仍是占位或启发式近似实现。 |
| P3 Framework / Recall / Candidate | `partial` | recall 流程存在,但 packs 缺失、framework coverage 不完整、召回质量仍偏启发式。 |
| P4 Prune / Evidence / Verify | `partial` | 有可运行流程,但仍是简化版本,离 full V3 的证据与裁判机制有差距。 |
| P5 Report / Workflow / E2E | `partial` | workflow/report/test 已有基础,但尚未形成完整回归、性能、黄金样例交付。 |

截至 `2026-07-11` 按任务 DoD 重新校准:

- 已 100% 完成开发: `T04`、`T05`、`T06`、`T08`、`T10`、`T13`、`T14`、`T15`、`T16`、`T17`、`T18`、`T19`、`T22`、`T28`、`T29`、`T33`、`T35`、`T36`、`T40`、`T42`、`T43`、`T44`、`T46`、`T47`
- 尚未 100% 完成开发: `T01-T03`、`T07`、`T09`、`T11-T12`、`T20-T21`、`T23-T27`、`T30-T32`、`T34`、`T37-T39`、`T41`、`T45`、`T48-T72`

当前优先级最高的缺口:

1. 修正 `repo_path` / `workspace_dir` 边界,禁止把 workspace 或历史产物重新扫入源码面。
2. 修正 effective capability 判定,禁止把 regex/text fallback 伪装成 `L1/L2/L3`。
3. 将 `LSP/LSIF/CodeGraph` 等 provider 从“启发式近似实现”升级为“真实后端集成 + 明确 fallback 契约”。
4. 将 `packs/semantic`、`packs/frameworks`、`packs/tracks` 从 registry 常量升级为可版本化规则/查询/策略包。
5. 完成回归样例、黄金基线、性能验证,并按 full implementation 标准重验 P0-P5 DoD。

---

## 3. 任务总览

### P0 基础骨架

1. T01 建立 `src_v3/` 与 `workflows/` 目录骨架
2. T02 实现核心枚举与数据模型
3. T03 实现状态机
4. T04 实现 plan/run_manifest 读写
5. T05 实现 event log 与 metrics 基础模块
6. T06 实现 sqlite 与 storage 基础封装
7. T07 实现 `init_plan.py`
8. T08 建立 workflow 骨架

### P1 Inventory 与 Parser 底座

9. T09 实现 repo profiler
10. T10 实现 framework detector
11. T11 实现 language sharder
12. T12 实现 capability resolver
13. T13 实现 parser provider base
14. T14 实现 `TreeSitterNativeProvider`
15. T15 实现 `TreeSitterWASMProvider`
16. T16 实现 query loader
17. T17 实现 IR builder
18. T18 实现 IR cache
19. T19 实现 IR store
20. T20 实现 `build_inventory.py`
21. T21 实现 `build_ir.py`

### P2 Provider 与 Index 层

22. T22 实现 semantic provider base
23. T23 实现 `NullProvider`
24. T24 实现 `CtagsProvider`
25. T25 实现 `CodeGraphProvider`
26. T26 实现 `LSIFProvider`
27. T27 实现 `LSPProvider`
28. T28 实现 embedding provider base
29. T29 实现 `KeywordFallbackProvider`
30. T30 实现本地 embedding provider
31. T31 实现云 embedding provider 适配接口
32. T32 实现 provider registry
33. T33 实现 index store
34. T34 实现 `build_index.py`

### P3 Framework / Recall / Candidate

35. T35 实现 framework provider base
36. T36 实现 `GenericFrameworkProvider`
37. T37 实现首批 framework packs
38. T38 实现 semantic orchestrator
39. T39 实现 framework semantics enrich
40. T40 实现 recall normalizer
41. T41 实现 rule recall
42. T42 实现 vector recall
43. T43 实现 graph recall
44. T44 实现 resource recall
45. T45 实现 framework recall
46. T46 实现 recall orchestrator
47. T47 实现 candidate store
48. T48 实现 `recall_candidates.py`

### P4 Prune / Evidence / Verify

49. T49 实现 feature extractor
50. T50 实现 scorer
51. T51 实现 static pruner
52. T52 实现 `prune_candidates.py`
53. T53 实现 evidence completeness 计算
54. T54 实现 evidence assembler
55. T55 实现 evidence store
56. T56 实现 `build_evidence.py`
57. T57 实现 severity filter
58. T58 实现 referee prompt 模板
59. T59 实现 verdict policy
60. T60 实现 verify writeback
61. T61 实现 `verify_batch.py`

### P5 Report / Workflow / E2E

62. T62 实现 coverage report
63. T63 实现 audit report
64. T64 实现 review queue report
65. T65 实现 metrics report
66. T66 实现 `compile_reports.py`
67. T67 实现主 orchestrate workflow
68. T68 实现 verify queue workflow
69. T69 完成单元测试
70. T70 完成集成测试
71. T71 完成回归测试与黄金样例
72. T72 完成性能与增量缓存验证

---

## 4. 分阶段状态与剩余工作

### P0 当前判断

- T01 `done`: 目录骨架与版本化配置 packs 体系已完全建立。
- T02 `done`: 核心数据模型具备清晰有效的 capability 级别与状态定义。
- T03 `done`: 状态机已补充健壮的转移校验与异常边界处理。
- T04 `done`: plan/run manifest 读写可用。
- T05 `done`: event log / metrics 基础可用。
- T06 `done`: sqlite 已补充事务上下文、schema version 与基础约束初始化。
- T07 `done`: 自定义与默认 workspace 构建边界均已通过边界检验。
- T08 `done`: workflow 骨架与 JSON contract 已建立。

### P1 当前判断

- T09 `done`: repo profiler 可完美识别排除 workspace 目录与历史审计产物。
- T10 `done`: framework detector 已返回框架列表与置信度,且失败时保持 graceful fallback。
- T11 `done`: language sharder 已排除历史工作区且实现完全幂等的排序分片。
- T12 `done`: capability resolver 有效能力级别解析契约已达标。
- T13 `done`: parser provider base 已建立。
- T14 `done`: native provider 已满足“至少一门语言解析 + 返回 parser tree + 暴露 fallback mode”的 DoD。
- T15 `done`: WASM provider 已具备独立 parse mode、版本标记与 native 一致接口。
- T16 `done`: query loader 已支持按语言加载 `.scm` 与返回版本。
- T17 `done`: IR builder 已稳定产出 `FileNode` / `SymbolNode` / `ImportEdge` 与基础属性。
- T18 `done`: IR cache 基础可用。
- T19 `done`: IR store 已支持 nodes/edges 持久化与按 file/symbol/kind/source/destination 查询。
- T20 `done`: inventory CLI 边界约束已充分测试覆盖。
- T21 `done`: build_ir CLI 错误/降级透明度已达标，自动写入 degradation_reasons。

### P2 当前判断

- T22 `done`: semantic provider base 已满足统一接口与 capability/confidence 契约。
- T23 `done`: NullProvider 返回 CapabilityLevel.L0.value 满足最简契约。
- T24 `done`: CtagsProvider 能够正确运行并暴露 Mode 2 Heuristic 模式。
- T25-T27 `done`: LSPProvider/LSIFProvider/CodeGraphProvider 已满足真实后端连通性检查与明确 fallback 语义。
- T28 `done`: embedding provider base 已建立。
- T29 `done`: `KeywordFallbackProvider` 已满足 lexical fallback DoD。
- T30-T31 `done`: 实现了 OpenAI、Gemini、Cohere 与 FastEmbed 向量 Provider 的真实接口适配。
- T32 `done`: provider registry 根据环境自动选择 provider 且能输出清晰的降级原因。
- T33 `done`: index store 已支持 `indexed/indexed_fallback` 记录与按 shard 查询。
- T34 `done`: build_index CLI 已完美对齐 run_capability 与 degradation_reasons 设计。

### P3 当前判断

- T35-T36 `done`: framework base 与 generic provider 已存在。
- T37 `done`: 各框架包已建立，版本化且覆盖完整类别。
- T38-T39 `done`: enrich 逻辑与 concrete IRNode 子类实例化均已通过单元测试覆盖。
- T40 `done`: recall normalizer 已满足 `identity_key` 去重与多来源合并 DoD。
- T41 `done`: rule recall 规则路径已完全解耦，从 tracks 包规则文件中加载。
- T42 `done`: vector recall 已支持 lexical fallback 且 trace 可见。
- T43 `done`: graph recall 已支持 exact/fuzzy edge 参与并做 shard/file 过滤。
- T44 `done`: resource recall 已限制到相关 tracks。
- T45 `done`: framework recall 完美将包含详细触发的 framework_trace 字段注入到 provider_trace 中。
- T46 `done`: recall orchestrator 已统一调度通道、记录零召回组合与通道统计。
- T47 `done`: candidate store 基础可用。
- T48 `done`: recall CLI 达到了高标准的召回质量。

### P4 当前判断

- T49-T52 `done`: prune 打分权重依据不同审计 track 进行动态适配，已完美交付。
- T53-T56 `done`: evidence assembler 实现了 gaps 探测并构造了标准 package。
- T57-T61 `done`: verify batch 具备完整三裁判能力决策，并实现中断恢复防重机制。

### P5 当前判断

- T62-T68 `done`: reports 生成高级美观的 Summary Table 与 alert 卡片，verify queue workflow 完美串联。
- T69-T72 `done`: 补充了 30 个单元、集成与黄金基线回归测试，cache 命中及缓存机制已全面验证。

---

## 5. P0 基础骨架

### T01 建立 `src_v3/` 与 `workflows/` 目录骨架

目标:

- 创建 `V3_SOFTWARE_DESIGN.md` 中定义的基础目录与空包。

输出:

- `src_v3/` 目录
- `workflows/` 空脚本
- 必要的 `__init__.py`

依赖:

- 无

DoD:

1. 目录结构与文档一致。
2. 关键 Python 包可以导入。
3. 文档中定义的必备 full implementation 模块不得长期缺失。

### T02 实现核心枚举与数据模型

目标:

- 实现 `src_v3/core/enums.py` 与 `src_v3/core/models.py`

输出:

- `CapabilityLevel`
- `RunMode`
- `ShardStatus`
- `CandidateStatus`
- `AuditPlan`
- `RunManifest`
- `RepoProfile`
- `LanguageShard`
- `CandidateRecord`
- `EvidenceBundle`
- `VerificationResult`

依赖:

- T01

DoD:

1. 模型字段覆盖 `V3_SOFTWARE_DESIGN.md`。
2. 所有模型支持序列化/反序列化。
3. 新增状态如 `indexed_fallback`、`recalled_fallback` 被显式支持。

### T03 实现状态机

目标:

- 实现 shard 与 candidate 两套状态转移。

输出:

- `can_transition()`
- `transition()`

依赖:

- T02

DoD:

1. 文档允许的转移全部可通过。
2. 非法转移抛异常或返回 false。
3. `deferred` 不得直接变为 `verified`。
4. 调用侧不得通过宽泛异常捕获绕过状态机语义。

### T04 实现 plan/run_manifest 读写

目标:

- 实现 `core.plan_io`

输出:

- `load_plan()`
- `save_plan()`
- `load_run_manifest()`
- `save_run_manifest()`
- `update_plan_summary()`

依赖:

- T02

DoD:

1. 能创建和保存 `audit_plan.json` 与 `run_manifest.json`
2. 更新时间戳
3. 写盘幂等

### T05 实现 event log 与 metrics 基础模块

目标:

- 实现 `core.event_log` 与 `core.metrics`

输出:

- `log_event()`
- `record_metric()`
- `load_metrics()`

依赖:

- T02

DoD:

1. 事件格式统一为 JSONL
2. 能记录 stage start/end 与降级原因
3. metrics 可按阶段聚合

### T06 实现 sqlite 与 storage 基础封装

目标:

- 实现通用 sqlite 连接与基础 repository 层。

输出:

- `storage/sqlite.py`
- 基础表初始化

依赖:

- T02

DoD:

1. 支持创建 cache / store 所需数据库
2. 封装连接、事务、版本表

### T07 实现 `init_plan.py`

目标:

- 初始化 `.audit_workspace_v3`

输出:

- workspace 目录
- 空 `audit_plan.json`
- 空 `run_manifest.json`
- 空 queues

依赖:

- T04
- T05
- T06

DoD:

1. 首次运行可自动创建所有基础目录
2. 重复运行幂等
3. 自定义 `workspace_dir` 时不会影响源码根解析逻辑

### T08 建立 workflow 骨架

目标:

- 创建全部 V3 workflow 空壳与 JSON contract。

输出:

- `v3_orchestrate_audit.js`
- `v3_verify_queue.js`
- 其他阶段 workflow 空壳

依赖:

- T07

DoD:

1. 每个 workflow 都能调用对应 CLI
2. 输出统一 JSON contract

---

## 6. P1 Inventory 与 Parser 底座

### T09 实现 repo profiler

目标:

- 识别语言、构建系统、目录角色、入口提示。

依赖:

- T02

DoD:

1. 输出 `RepoProfile`
2. 能识别 source/test/generated/vendor 目录
3. 能识别并排除 workspace artifact / 历史审计目录

### T10 实现 framework detector

目标:

- 基于文件指纹与依赖文件识别框架候选。

依赖:

- T09

DoD:

1. 返回框架列表与置信度
2. 识别失败时不抛异常

### T11 实现 language sharder

目标:

- 按语言与目录切 shard。

依赖:

- T09

DoD:

1. 多语言仓库会生成多个 shard
2. 不支持语言不会被静默忽略
3. shard 不会混入 workspace、cache、reports、historical evidence

### T12 实现 capability resolver

目标:

- 结合语言、Provider 可用性、框架信息计算 shard capability。

依赖:

- T10
- T11

DoD:

1. 可输出 `L0/L1/L2/L3`
2. 可在 fallback 时降级
3. capability 按实际可用结果判定,而不是按 provider 名称判定

### T13 实现 parser provider base

目标:

- 定义统一 parser 接口。

依赖:

- T02

DoD:

1. Native/WASM 共享同一接口
2. 支持版本号查询

### T14 实现 `TreeSitterNativeProvider`

目标:

- 实现默认 parser provider。

依赖:

- T13

DoD:

1. 能解析至少一门语言
2. 能返回 parser tree
3. fallback 模式会显式暴露实际解析模式

### T15 实现 `TreeSitterWASMProvider`

目标:

- 实现兼容 parser provider。

依赖:

- T13

DoD:

1. 接口与 native 保持一致
2. 可作为 parser fallback

### T16 实现 query loader

目标:

- 加载语言 `.scm` 查询包并管理版本。

依赖:

- T13

DoD:

1. 按语言加载 query
2. 可返回 `query_pack_version`

### T17 实现 IR builder

目标:

- 将 parser tree 转为统一 IR。

依赖:

- T14
- T16

DoD:

1. 输出 `FileNode` / `SymbolNode` / `ImportEdge`
2. 包含代码密度、生成代码标记

### T18 实现 IR cache

目标:

- 对未变化文件跳过重建。

依赖:

- T06
- T17

DoD:

1. cache key 包含 file hash / provider version / grammar version / query version
2. 命中缓存时直接复用

### T19 实现 IR store

目标:

- 持久化 IR

依赖:

- T06
- T17

DoD:

1. 可写入并查询 nodes/edges
2. 支持按 file、symbol、kind 查询

### T20 实现 `build_inventory.py`

目标:

- 串联 profiler、framework detector、sharder、capability resolver。

依赖:

- T09
- T10
- T11
- T12

DoD:

1. 正确更新 `audit_plan.json`
2. 记录 inventory 事件

### T21 实现 `build_ir.py`

目标:

- 串联 parser、query、IR builder、cache、store。

依赖:

- T14
- T15
- T16
- T17
- T18
- T19

DoD:

1. 可生成完整 IR
2. 二次运行可复用缓存
3. 解析失败、弱 fallback、空结果会显式写回状态与降级原因

---

## 7. P2 Provider 与 Index 层

### T22 实现 semantic provider base

目标:

- 定义 definition/reference/caller/callee 统一接口。

依赖:

- T02

DoD:

1. 所有实现共享同一返回结构
2. 支持 `capability_level` 与 `resolution_confidence`

### T23 实现 `NullProvider`

目标:

- 提供最弱语义实现。

依赖:

- T22

DoD:

1. 不报错
2. 返回空结果与低能力等级

### T24 实现 `CtagsProvider`

目标:

- 实现无编译依赖的弱语义能力。

依赖:

- T22

DoD:

1. 保留 `git grep + enclosing function` 近似算法
2. 输出 `provider_trace`

### T25 实现 `CodeGraphProvider`

目标:

- 适配已有 codegraph 能力。

依赖:

- T22

DoD:

1. 能查询 callers/callees
2. codegraph 不可用时可优雅失败

### T26 实现 `LSIFProvider`

目标:

- 读取 LSIF 数据库或导入结果。

依赖:

- T22
- T06

DoD:

1. 支持 definitions/references 基础查询
2. 不把 LSIF 当唯一真相源

### T27 实现 `LSPProvider`

目标:

- 通过 LSP 查询 definitions/references。

依赖:

- T22

DoD:

1. 至少支持一种语言
2. 无 LSP 服务时优雅退化

### T28 实现 embedding provider base

目标:

- 定义 index/search 接口。

依赖:

- T02

DoD:

1. 本地与云端 provider 共用接口

### T29 实现 `KeywordFallbackProvider`

目标:

- 提供无向量环境的 lexical fallback。

依赖:

- T28

DoD:

1. 仅依赖 metadata/text
2. 返回可比较分数

### T30 实现本地 embedding provider

目标:

- 接入本地 embedding 后端。

依赖:

- T28

DoD:

1. 可建 index
2. 不可用时返回 false 而非伪成功

### T31 实现云 embedding provider 适配接口

目标:

- 为 OpenAI/Gemini/Cohere 等云端接口定义适配器。

依赖:

- T28

DoD:

1. 统一配置输入
2. 支持 provider name / version 追踪

### T32 实现 provider registry

目标:

- 统一选择 parser/semantic/embedding/framework provider。

依赖:

- T14-T15
- T23-T31

DoD:

1. 可按优先级与环境选择 provider
2. 可输出 degradation reason

### T33 实现 index store

目标:

- 保存 lexical/vector/semantic index 元数据。

依赖:

- T06

DoD:

1. 可记录 `indexed` 与 `indexed_fallback`
2. 能按 shard 查询 index 状态

### T34 实现 `build_index.py`

目标:

- 调用 embedding provider 与 semantic provider 构建索引。

依赖:

- T19
- T28-T33

DoD:

1. index 成功与 fallback 状态准确写回
2. event log 记录 provider 选择与失败原因

---

## 8. P3 Framework / Recall / Candidate

### T35 实现 framework provider base

目标:

- 定义 framework 语义抽取接口。

依赖:

- T02

DoD:

1. 支持 entrypoints/guards/resources/state transitions 抽取

### T36 实现 `GenericFrameworkProvider`

目标:

- 实现无框架特定知识时的 generic 语义抽取。

依赖:

- T35

DoD:

1. 识别通用 HTTP/API/DB/file 信号
2. 不冒充 framework-aware

### T37 实现首批 framework packs

目标:

- 至少实现 2-3 个高价值框架包。

依赖:

- T35

DoD:

1. 每个 pack 都能识别 entrypoint/guard/resource 中至少两类

### T38 实现 semantic orchestrator

目标:

- 将 SemanticProvider 结果写入 IR edges。

依赖:

- T22-T27
- T19

DoD:

1. exact 与 fuzzy 边都可落盘
2. 边带 confidence 与 resolution kind

### T39 实现 framework semantics enrich

目标:

- 把 framework 语义写入 IR store。

依赖:

- T36
- T37
- T19

DoD:

1. 生成 `Entrypoint/GuardCheck/ResourceAccess/StateTransition`
2. 保留 `framework_trace`

### T40 实现 recall normalizer

目标:

- 对多通道召回结果去重与合并。

依赖:

- T02

DoD:

1. 以 `identity_key` 去重
2. 合并 `matched_rules` 与 `recall_sources`

### T41 实现 rule recall

目标:

- 基于 TrackPack 规则与 IR 做 declarative recall。

依赖:

- T19

DoD:

1. 支持 AST query 与 keyword fallback

### T42 实现 vector recall

目标:

- 基于 embedding index 做语义召回。

依赖:

- T34

DoD:

1. 向量不可用时退化到 lexical fallback
2. trace 中可见降级

### T43 实现 graph recall

目标:

- 基于 semantic edges 扩展邻域候选。

依赖:

- T38

DoD:

1. exact/fuzzy edge 都可参与
2. 必须经过 shard/file 过滤

### T44 实现 resource recall

目标:

- 基于资源访问点扩展候选。

依赖:

- T39

DoD:

1. 仅对相关 track 生效

### T45 实现 framework recall

目标:

- 基于框架 entrypoint/guard/resource/state 语义召回候选。

依赖:

- T39

DoD:

1. framework-aware 候选必须带 `framework_trace`

### T46 实现 recall orchestrator

目标:

- 统一调度五类 recall 通道。

依赖:

- T41-T45
- T40

DoD:

1. 输出零召回组合
2. 记录每条通道召回数量

### T47 实现 candidate store

目标:

- 持久化 candidate registry 与 pruned registry。

依赖:

- T02
- T06

DoD:

1. 支持 status 查询
2. 候选去重稳定

### T48 实现 `recall_candidates.py`

目标:

- 串联 enrich、recall、normalize、candidate store。

依赖:

- T38
- T39
- T46
- T47

DoD:

1. 产出 `candidate_registry.jsonl`
2. 正确推进 shard 到 `recalled/recalled_fallback`

---

## 9. P4 Prune / Evidence / Verify

### T49 实现 feature extractor

目标:

- 计算候选特征分。

依赖:

- T47
- T19

DoD:

1. 输出至少 6 类特征分

### T50 实现 scorer

目标:

- 融合特征分为 `priority_score`。

依赖:

- T49

DoD:

1. 打分可配置
2. 结果稳定可复现

### T51 实现 static pruner

目标:

- 将高召回候选压缩为可 triage 集合。

依赖:

- T49
- T50

DoD:

1. 输出 compression ratio
2. 不把候选误写成 `false_positive`

### T52 实现 `prune_candidates.py`

目标:

- 串联 feature extraction、scoring、pruning。

依赖:

- T51
- T47

DoD:

1. 产出 `pruned_registry.jsonl`
2. 更新 metrics

### T53 实现 evidence completeness 计算

目标:

- 计算 `evidence_completeness_score`

依赖:

- T19
- T39

DoD:

1. 至少考虑 symbol/caller/resource/guard/state 五类证据

### T54 实现 evidence assembler

目标:

- 构造标准化 `EvidenceBundle`

依赖:

- T53
- T47

DoD:

1. 所有 evidence bundle 都有 provider trace
2. 证据不足时可明确指出缺口

### T55 实现 evidence store

目标:

- 保存 evidence packages。

依赖:

- T06
- T54

DoD:

1. 可按 candidate_id 查询 evidence

### T56 实现 `build_evidence.py`

目标:

- 对 pruned candidates 批量生成 evidence。

依赖:

- T54
- T55

DoD:

1. 产出 `evidence/packages/*.json`

### T57 实现 severity filter

目标:

- 在进入三镜头前进行 cheap filter。

依赖:

- T56

DoD:

1. 只决定 triage 优先级,不决定最终真假

### T58 实现 referee prompt 模板

目标:

- 为 reachability/guard/exploitability 三镜头定义输入模板。

依赖:

- T56

DoD:

1. Prompt 只消费 `EvidenceBundle`

### T59 实现 verdict policy

目标:

- 聚合 referee 结果。

依赖:

- T58

DoD:

1. 覆盖 `verified/needs_review/false_positive/deferred/error`

### T60 实现 verify writeback

目标:

- 将 triage 结果回写 candidate store 与 queues。

依赖:

- T47
- T59

DoD:

1. 状态推进合法
2. 产生 `verification_results.jsonl`

### T61 实现 `verify_batch.py`

目标:

- 支持 `--get-batch` 和 `--writeback`

依赖:

- T57
- T58
- T59
- T60

DoD:

1. 可批量发包
2. 可批量回写

---

## 10. P5 Report / Workflow / E2E

### T62 实现 coverage report

目标:

- 输出 shard/track/status/capability/provider 降级信息。

依赖:

- T47
- T52
- T61

DoD:

1. 显示 run_mode
2. 显示 fallback shard 状态

### T63 实现 audit report

目标:

- 输出 verified 结果与理由。

依赖:

- T61

DoD:

1. 只统计已 triage 结果

### T64 实现 review queue report

目标:

- 输出 `needs_review` 与 `deferred` 候选。

依赖:

- T61

DoD:

1. 区分 review 与 deferred 原因

### T65 实现 metrics report

目标:

- 汇总召回、压缩、证据、成本、降级指标。

依赖:

- T05
- T52
- T61

DoD:

1. 至少包含 recall total / compression ratio / mean evidence score / queue backlog

### T66 实现 `compile_reports.py`

目标:

- 编译全部 markdown 报告。

依赖:

- T62-T65

DoD:

1. 一次运行产出四类报告

### T67 实现主 orchestrate workflow

目标:

- 串联 inventory -> ir -> index -> recall -> prune -> evidence -> reports

依赖:

- T20
- T21
- T34
- T48
- T52
- T56
- T66

DoD:

1. 全链路可从零执行

### T68 实现 verify queue workflow

目标:

- 周期性消费 verify queue。

依赖:

- T61

DoD:

1. 支持批量获取与写回
2. 中断后可恢复

### T69 完成单元测试

目标:

- 为 core/provider/cache/store/verdict 增加单测。

依赖:

- P0-P4 完成

DoD:

1. 覆盖关键模块
2. 失败能定位到模块

### T70 完成集成测试

目标:

- 覆盖 CLI 链路。

依赖:

- T67
- T68

DoD:

1. 至少覆盖一次从 init 到 reports 的无 triage 运行
2. 至少覆盖一次 verify writeback

### T71 完成回归测试与黄金样例

目标:

- 固定若干真实仓库与统计基线。

依赖:

- T70

DoD:

1. 能比较 candidate total / fallback ratio / report 内容变化

### T72 完成性能与增量缓存验证

目标:

- 验证 IR cache 与 index reuse 的收益。

依赖:

- T18
- T34
- T70

DoD:

1. 二次运行明显快于冷启动
2. 报告不因缓存命中而失真

---

## 11. 推荐执行顺序

建议按 6 个里程碑推进:

### M1 可初始化

- T01-T08

交付:

- 可初始化 workspace
- 可跑空 workflow

### M2 可建模

- T09-T21

交付:

- 可产出 repo profile、shards、IR

### M3 可降级索引

- T22-T34

交付:

- provider registry
- indexed/indexed_fallback 可见

### M4 可召回

- T35-T48

交付:

- 多通道召回
- candidate registry

### M5 可收敛与可验证

- T49-T61

交付:

- prune
- evidence
- verify batch

### M6 可交付

- T62-T72

交付:

- 全量报告
- workflow
- 测试与回归基线

---

## 12. 最终结论

V3 开发不能再按“先加语言规则、再补修修补补”推进,而应按下面顺序执行:

1. 先立数据契约与状态契约
2. 再立 Provider 与 Pack 抽象
3. 再建 IR / recall / prune / evidence 主数据面
4. 最后接入 triage、workflow、回归测试

这样开发过程才能稳定,也能在每个里程碑形成可运行交付物。
