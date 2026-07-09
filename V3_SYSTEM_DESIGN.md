# Fuzzy Semantic Audit V3 —— 系统设计

> 目标: 将现有 V2 skill 演进为一套真正通用、能力透明、可降级、可扩展的代码审计系统。
> 本文档回答: V3 要解决什么问题、整体如何分层、如何支持“所有语言可审计”、如何把大规模召回稳定收敛到可验证规模。

---

## 1. 设计目标

### 1.1 核心目标

1. 支持任意语言仓库的统一审计入口,而不是只对少数语言“硬编码深度支持”。
2. 让所有语言至少具备可运行的基础审计能力,主流语言具备更深的语义审计能力。
3. 明确区分结构解析、语义增强、召回、静态收敛、证据构建、LLM 裁判几个阶段。
4. 所有降级必须显式可见,禁止把 fallback 扫描伪装成 full semantic audit。
5. 让候选数量从“高召回”稳定收敛到“可 triage”,避免全量验证成本失控。
6. 将语言差异下沉到 Provider / Pack 层,让主工作流长期稳定。

### 1.2 非目标

1. 不追求所有语言在 V3 一次性达到同等精度的调用图与数据流分析。
2. 不把单一工具链视为真相源,例如不把 Tree-sitter、LSIF、LSP 任意一个工具当成万能底座。
3. 不承诺严格意义上的完备污点分析; V3 先实现“轻量静态收敛 + 证据优先”。
4. 不为追求吞吐而静默删除候选。

---

## 2. 设计原则

1. 覆盖优先于吞吐。
2. 透明降级优先于伪精度。
3. 统一 IR 优先于语言分叉实现。
4. 审计轨道优先于具体 CWE 预裁剪。
5. 证据优先于 prompt 技巧。
6. 可扩展 Pack 优先于 if/else 堆叠。

---

## 2.1 实现约束补充

以下约束属于 V3 落地时必须显式遵守的系统级约束:

1. `repo_path` 是唯一源码真相根目录; 规则文件、源码文件、依赖文件、框架指纹都必须相对 `repo_path` 解析,不得从 `workspace_dir` 反推源码根。
2. `workspace_dir` 仅用于存放审计产物,不得被 inventory、sharding、IR build、recall 当作源码输入。
3. 任何历史审计目录、缓存目录、报告目录、临时工作目录都必须在 inventory 阶段显式排除,禁止把历史产物重新纳入本次审计。
4. capability level 必须按“实际可用能力”判定,而不是按 provider 类名判定。
5. parser/semantic/embedding/framework 任一阶段发生 fallback 时,必须在状态、manifest、event log、coverage report 中同步可见。
6. 宽泛异常捕获只能用于保持流水线可继续运行,不能替代状态写回、降级原因记录和质量统计。

---

## 3. V3 的核心判断

V3 不应被定义为“所有语言都一等深审”,而应定义为:

```text
所有语言可审计
  = 通用底座 + 能力等级 + 透明降级

主流语言可深审
  = 统一解析 + 语义增强 + 框架语义 + 证据构建
```

因此 V3 的真正目标是:

```text
Universal Auditability
  + Capability Transparency
  + Multi-stage Cost Convergence
```

---

## 4. 能力模型

### 4.1 Capability Level

V3 以能力等级而不是“是否支持某语言”来定义系统能力。

#### `L0 Text`

- 文件分类
- 路径权重
- 关键词/规则召回
- 通用报告

#### `L1 Structural`

- symbol / class / method / function 提取
- span 定位
- import / include / module dependency 提取
- 结构级片段证据

#### `L2 Semantic`

- definition / reference
- caller / callee
- 基础类型或模块语义
- 资源访问点与入口点关联

#### `L3 Deep Audit`

- CFG 或轻量控制流图
- 参数传播 / 简单污点近似
- 权限路径分析
- 状态机分析
- 跨函数证据聚合

### 4.2 Capability 标记范围

以下对象都必须带能力信息:

- `run_capability`
- `shard_capability`
- `candidate_capability`
- `provider_trace`
- `evidence_completeness_score`

### 4.3 Effective Capability 规则

V3 的 capability 判定遵循“结果优先”而不是“名义 provider 优先”:

1. 只有当 parser 实际产出稳定的 symbol/span/import 结构时,shard 才能被记为 `L1`。
2. 仅有 regex、关键词、文本扫描等弱 fallback 时,默认仍应视为 `L0`,除非额外证明其满足 `L1` 结构契约。
3. 只有当 semantic provider 实际提供 definition/reference/caller/callee 级别结果时,shard 才能被记为 `L2`。
4. `L3` 必须建立在可用语义关系、框架语义或跨函数证据聚合真实可用的前提上,不能因为 provider 被命名为 `LSPProvider`、`LSIFProvider` 或 `CodeGraphProvider` 就自动升级。
5. candidate capability 不得高于其所属 shard 的 effective capability。

---

## 5. 总体架构

```text
L7 Report Layer
  audit report / coverage report / review queue / metrics report

L6 Triage Layer
  severity filter / referee cluster / verdict policy / writeback

L5 Evidence Layer
  evidence assembly / path bundle / guard bundle / resource bundle

L4 Prune Layer
  static pruning / ranking / backlog compression

L3 Recall Layer
  rule recall / vector recall / graph recall / resource recall / framework recall

L2 Semantic Layer
  reference resolution / call edges / entrypoints / type hints / framework semantics

L1 Parse & Inventory Layer
  repo profiling / sharding / tree-sitter parsing / IR building

L0 Runtime Layer
  workflow orchestration / storage / queues / provider registry / event log
```

### 5.1 关键变化

与 V2 相比, V3 有四个本质变化:

1. 用统一 IR 代替语言插件各自维护的松散结构。
2. 用 Provider Layer 代替“某个工具就是通用 code graph”。
3. 明确引入 `Evidence Assembly` 作为独立阶段。
4. 用多级收敛机制解决召回过大问题,而不是把预算门槛混入真假判定。

---

## 6. 核心抽象

### 6.1 RepoProfile

描述仓库级画像:

- 语言集合
- 构建系统
- 框架集合
- 目录角色
- 入口提示
- 风险目录

补充约束:

- RepoProfile 必须能区分 `source`、`test`、`generated`、`vendor`、`workspace_artifact` 五类目录角色。
- 历史工作区与缓存目录应在 RepoProfile 阶段被识别并排除,而不是落到后续 pruning 再处理。

### 6.2 LanguageShard

将仓库切分为可独立处理的语言分片:

- `shard_id`
- `lang`
- `paths`
- `frameworks`
- `provider_set`
- `capability`
- `status`

补充约束:

- shard 的 `paths` 必须全部相对 `repo_path` 存储。
- shard 不得混入工作区产物、缓存文件、历史 evidence package、历史 reports。
- 不支持语言可以形成 `L0` shard,但不能因为 parser provider 存在就被自动提升到 `L1`。

### 6.3 AuditTrack

V3 保持“审计轨道优先”的原则,标准轨道至少包括:

1. `authz`
2. `state_machine`
3. `resource_access`
4. `injection`
5. `input_validation`
6. `deserialization`
7. `memory_safety`
8. `concurrency`
9. `crypto`
10. `filesystem_boundary`

### 6.4 Intermediate Representation (IR)

V3 的主流程不直接基于语言源码工作,而是基于统一 IR 工作。

最小 IR 对象:

- `FileNode`
- `SymbolNode`
- `ImportEdge`
- `CallEdge`
- `TypeHint`
- `ResourceAccess`
- `GuardCheck`
- `StateTransition`
- `Entrypoint`
- `GeneratedMarker`

### 6.5 Candidate

候选是一等公民,必须可稳定定位:

- `candidate_id`
- `identity_key`
- `file`
- `symbol`
- `span`
- `source_tracks[]`
- `matched_rules[]`
- `recall_sources[]`
- `priority_score`
- `candidate_capability`
- `evidence_refs[]`
- `status`

### 6.6 EvidenceBundle

每个候选在进入 LLM 前必须有标准化证据包:

- `symbol_body`
- `upstream_entrypoints`
- `caller_chain`
- `callee_chain`
- `guard_snippets`
- `resource_snippets`
- `state_transition_snippets`
- `type_or_model_context`
- `provider_trace`
- `evidence_completeness_score`

---

## 7. Provider Layer 设计

V3 不把任何单一工具定义成“通用图引擎”。V3 采用 Provider 抽象。

### 7.1 ParserProvider

职责:

- 语言语法树解析
- symbol/span/import 结构提取
- 注释率、代码密度、生成代码特征提取

实现:

- `TreeSitterNativeProvider`
- `TreeSitterWASMProvider`

说明:

- Tree-sitter 是默认结构解析底座。
- WASM 只是实现形态之一,不是架构前提。

### 7.2 SemanticProvider

职责:

- definition / reference
- caller / callee
- 基础类型关系
- 跨文件关系补强

实现:

- `LSPProvider`
- `LSIFProvider`
- `CodeGraphProvider`
- `CtagsProvider`
- `NullProvider`

说明:

- `LSIF` 只是一种可选语义后端,不能被定义为通用且唯一的 Code Graph。
- 若 provider 仅返回基于文本或 IR 的启发式近似结果,必须显式标注为 fallback semantic,不能在 capability/report 中冒充 full semantic。

### 7.3 EmbeddingProvider

职责:

- 文本向量化
- 语义检索
- 向量后端降级

实现:

- `LocalFastEmbedProvider`
- `OpenAIEmbeddingProvider`
- `GeminiEmbeddingProvider`
- `CohereEmbeddingProvider`
- `KeywordFallbackProvider`

### 7.4 FrameworkProvider

职责:

- 路由/Handler 识别
- Guard / Middleware 识别
- ORM / Resource 识别
- 状态转换语义识别

实现:

- `DjangoPack`
- `ExpressPack`
- `SpringPack`
- `GinPack`
- `AndroidPack`
- 其他框架包

---

## 8. Pack 体系

V3 的扩展能力依赖四种 Pack:

### 8.1 LanguagePack

包含:

- 文件后缀
- Tree-sitter grammar
- `.scm` query
- 基础结构映射

### 8.2 SemanticPack

包含:

- 可用 Provider 选择策略
- language-specific symbol normalization
- definition/reference/query adapter

### 8.3 FrameworkPack

包含:

- entrypoint 识别
- auth guard 识别
- resource surface 识别
- state transition 识别

### 8.4 TrackPack

包含:

- recall rules
- pruning rules
- evidence requirements
- triage prompt policy

---

## 9. 执行流程

V3 固化为八阶段流水线:

### Phase 1: Profile

1. 扫描仓库结构
2. 检测语言、构建系统、框架、目录角色
3. 输出 `RepoProfile`

### Phase 2: Inventory

1. 按语言、目录、模块切 shard
2. 为 shard 决定 Provider 组合
3. 计算 `shard_capability`

### Phase 3: Parse

1. 使用 `ParserProvider` 建立结构 IR
2. 提取 symbols/imports/classes/methods
3. 记录代码密度、注释率、生成代码特征

### Phase 4: Enrich

1. 使用 `SemanticProvider` 补 references / callers / callees
2. 使用 `FrameworkProvider` 提取入口、守卫、资源、状态点
3. 将结果写回 IR Store

### Phase 5: Recall

对每个 `track x shard` 并行执行:

1. `RuleRecall`
2. `VectorRecall`
3. `GraphRecall`
4. `ResourceRecall`
5. `FrameworkRecall`

然后统一去重与归一化。

### Phase 6: Static Pruning

目标: 将高召回候选压缩到可 triage 规模。

过滤包括:

- vendor / generated / test / mock 权重衰减
- code density 过滤
- entrypoint proximity
- resource / guard / state relevance
- call-path reachability
- 轻量参数传播近似

注意:

- 这一层是 `Static Pruning`,不是“严格 taint analysis”。
- 不能把简单 references BFS 直接当数据流分析。

### Phase 7: Evidence Assembly

为剩余候选强制生成 `EvidenceBundle`:

- 函数体
- 上游入口
- 下游资源
- 守卫上下文
- 状态转换上下文
- Provider trace

没有证据的候选不能直接送入三镜头验证。

### Phase 8: LLM Triage

1. `Severity Filter`
2. `Three-lens Referee`
3. `Verdict Policy`
4. `Writeback`

最后编译:

- `audit_report.md`
- `coverage_report.md`
- `review_queue.md`
- `metrics_report.md`

---

## 10. Recall 设计

### 10.1 Recall 通道

#### Rule Recall

- declarative YAML / JSON rules
- AST query
- keyword fallback

#### Vector Recall

- track 描述与 code snippet 语义匹配
- embedding provider 可替换

#### Graph Recall

- definition/reference/caller/callee 近邻扩展
- 受 `SemanticProvider` 能力影响

#### Resource Recall

- 文件、数据库、网络、对象存储、IPC、消息队列

#### Framework Recall

- route handler
- middleware
- ORM model update
- state transition API

### 10.2 候选融合

候选必须保留:

- `recall_sources`
- `matched_rules`
- `provider_trace`
- `source_tracks`

融合去重键:

```text
(shard_id, file, symbol, span.start, span.end)
```

---

## 11. 排序与静态收敛

V3 用打分模型代替单一规则命中数排序。

### 11.1 评分项

- `signal_score`
- `semantic_similarity_score`
- `reachability_score`
- `guard_conflict_score`
- `framework_risk_score`
- `code_quality_score`
- `evidence_seed_score`

### 11.2 典型收敛逻辑

1. 先降权:
   - vendor
   - docs
   - generated
   - test / mock
2. 再做路径相关性判断:
   - 是否靠近入口
   - 是否接触资源
   - 是否存在 guard / state / input 关系
3. 最后保留高优先候选进入证据构建

目标:

```text
30,000+ recalled
  -> < 1,000 pruned
  -> < 200 triage-ready
```

---

## 12. Evidence Assembly 设计

这层是 V3 与 V2 的关键差异之一。

### 12.1 证据构建原则

1. LLM 不直接面对“裸候选”。
2. 所有候选都必须被标准化打包。
3. 证据不足时进入 `needs_review` 或低优先延期,而不是伪造确定性。

### 12.2 必要证据片段

- `primary_code`
- `caller_context`
- `callee_context`
- `resource_context`
- `guard_context`
- `state_context`
- `entrypoint_context`
- `supporting_symbols`

### 12.3 证据完整度

评分建议:

- `0-30`: 仅文本或规则命中
- `31-60`: 有结构上下文
- `61-80`: 有调用链或资源链
- `81-100`: 有入口、资源、守卫、状态四类核心证据

---

## 13. Triage 设计

### 13.1 Stage 1: Severity Filter

快速过滤低价值候选,但不能把预算限制混入真假判断。

### 13.2 Stage 2: Three-lens Referees

三视角保持:

1. `reachability`
2. `guard`
3. `exploitability`

### 13.3 Stage 3: Verdict Policy

输出:

- `verified`
- `needs_review`
- `false_positive`
- `deferred`
- `error`

### 13.4 基本约束

1. `false_positive` 必须来源于验证,不能来源于调度。
2. `deferred` 只能表示延后,不能表示排除。
3. `needs_review` 必须附带证据缺口说明。

---

## 14. 状态模型

### 14.1 Shard 状态

```text
discovered
  -> indexed | indexed_fallback | failed
  -> recalled | recalled_fallback | failed
```

### 14.2 Candidate 状态

```text
discovered
  -> indexed
  -> recalled
  -> normalized
  -> pruned
  -> evidence_ready
  -> queued_for_verify
  -> verifying
  -> verified | needs_review | false_positive | deferred | error
```

### 14.3 Run 状态

- `run_mode = full_semantic`
- `run_mode = semantic_fallback`
- `run_mode = lexical_fallback`
- `run_mode = rule_only`

---

## 15. 存储设计

推荐 workspace:

```text
.audit_workspace_v3/
  run_manifest.json
  repo_profile.json
  audit_plan.json
  ir/
    files.jsonl
    symbols.jsonl
    edges.jsonl
  indices/
    lexical/
    vector/
    semantic/
  candidates/
    candidate_registry.jsonl
    pruned_registry.jsonl
  evidence/
    packages/
  queues/
    verify_now.json
    manual_review.json
    deferred.json
  reports/
    audit_report.md
    coverage_report.md
    review_queue.md
    metrics_report.md
  metrics/
    stage_metrics.json
  event_log.jsonl
```

---

## 16. 目录结构建议

```text
fuzzy-semantic-audit/
  V3_SYSTEM_DESIGN.md
  src_v3/
    core/
      models.py
      state_machine.py
      provider_registry.py
      plan_io.py
      event_log.py
    inventory/
      repo_profiler.py
      language_sharder.py
      capability_resolver.py
    parse/
      ir_builder.py
      parser_runtime.py
      query_loader.py
    enrich/
      semantic_orchestrator.py
      framework_detector.py
      entrypoint_extractor.py
    recall/
      rule_recall.py
      vector_recall.py
      graph_recall.py
      resource_recall.py
      framework_recall.py
      normalizer.py
    prune/
      feature_extractor.py
      scorer.py
      static_pruner.py
    evidence/
      assembler.py
      package_builder.py
    verify/
      severity_filter.py
      referee_prompts.py
      verdict_policy.py
      writeback.py
    report/
      audit_report.py
      coverage_report.py
      review_queue.py
      metrics_report.py
    providers/
      parser/
      semantic/
      embedding/
      framework/
    packs/
      languages/
      semantic/
      frameworks/
      tracks/
    cli/
      init_plan.py
      build_inventory.py
      build_ir.py
      build_index.py
      recall_candidates.py
      prune_candidates.py
      build_evidence.py
      verify_batch.py
      compile_reports.py
  workflows/
    v3_orchestrate_audit.js
    v3_build_inventory.js
    v3_build_ir.js
    v3_recall.js
    v3_prune.js
    v3_verify_queue.js
    v3_compile_reports.js
```

---

## 17. 评测体系

V3 必须从一开始就绑定评测。

### 17.1 核心指标

- `Recall@all`
- `Precision@50`
- `Precision@200`
- `BacklogCompressionRatio`
- `MeanEvidenceScore`
- `WallClockTime`
- `LLMTokenCost`

### 17.2 基准仓库

至少三类:

1. 业务应用仓库
2. 系统/基础设施仓库
3. 多语言混合大仓库

### 17.3 回归标准

任何架构变更都必须比较:

- 候选总数
- top-N 命中率
- generic/fallback 占比
- triage 成本
- provider 降级比例

---

## 18. 工程风险与优雅降级策略

V3 在工程实现上必须把若干“高频失败场景”视为正常路径,而不是异常补丁。

V3 用四个统一机制处理这些挑战:

- `Capability`: 当前阶段能做到多深
- `Confidence`: 当前结论有多可靠
- `Cache`: 如何避免重复计算
- `Trace`: 结果来自哪条工具链与哪种推断

### 18.1 挑战一: 语义后端缺失

#### 风险

在轻量容器、沙箱或无完整编译环境的仓库中:

- `LSIFProvider`
- `LSPProvider`
- 部分原生 indexer

可能无法正常工作。若系统把这些后端视为前提,则会在多语言仓库上频繁退化为“无图分析”,导致收敛阶段失效。

#### 优雅方案

将语义后端缺失设计为标准化 Provider 选择过程:

1. `SemanticProvider` 统一返回:
   - `capability_level`
   - `resolution_confidence`
   - `provider_trace`
2. 按优先级选择:
   - `LSPProvider`
   - `LSIFProvider`
   - `CodeGraphProvider`
   - `CtagsProvider`
   - `NullProvider`
3. 即使退化到 `CtagsProvider` 或 `NullProvider`,仍保留无编译依赖的轻量能力:
   - `git grep` caller 搜索
   - enclosing function 回溯
   - module/file proximity 过滤
4. 报告中必须显式写出:
   - `run_mode`
   - `provider_trace`
   - `shard_capability`

#### 设计收益

- fallback 成为正常路径
- 不会因为语义后端缺失导致整条链路中断
- 降级是透明的,而不是伪装成 full semantic

### 18.2 挑战二: 弱类型语言调用链不完备

#### 风险

在 Python / JavaScript 等语言中:

- 动态分派
- monkey patch
- 反射式调用
- 弱类型对象传递

会导致静态调用图天然不完备。如果系统只接受精确调用边,大量真实候选会因证据不够而堆入 `needs_review`。

#### 优雅方案

V3 允许带置信度的模糊边,而不是只承认“精确边或无边”。

调用边分为:

- `exact_edge`
- `fuzzy_edge`

`fuzzy_edge` 的构造可来自:

- 同模块同名符号
- receiver/object 名称近似
- 参数个数一致
- import 范围一致
- 框架约定入口模式

每条模糊边必须记录:

- `edge_confidence`
- `resolution_reason`
- `provider_trace`

证据与排序层不直接把“图不完整”映射成低质量,而是拆分为:

- `structure_score`
- `reachability_confidence`
- `guard_context_score`
- `resource_context_score`

#### 设计收益

- 弱类型语言不会系统性挤爆 `needs_review`
- 模糊解析可用,但不会伪装成确定事实
- 系统可以渐进增强,而不必等到完美调用图才可用

### 18.3 挑战三: 解析层性能开销

#### 风险

无论使用 Tree-sitter Native 还是 Tree-sitter WASM,在大仓库中对数千文件反复构建 AST 和查询结构都会成为明显热点。

#### 优雅方案

V3 优先优化“重复工作”,而不是只优化某个 parser 运行时。

引入 `IRCache`,缓存键至少包含:

- `file_hash`
- `parser_provider_version`
- `grammar_version`
- `query_pack_version`

策略如下:

1. 未变文件直接复用 IR
2. 仅重建变更文件及其受影响索引
3. 支持批量解析与并行 worker
4. 优先使用 `TreeSitterNativeProvider`,在不适用时再退化到 `TreeSitterWASMProvider`

缓存落地建议:

- SQLite 作为主缓存
- JSONL 作为导出或调试格式

#### 设计收益

- 性能从“每次全量解析”转变为“增量更新”
- 解析层不会被某个具体运行时形态绑死
- 大仓库可持续迭代而非每次冷启动

### 18.4 挑战四: 框架语义漂移

#### 风险

逻辑漏洞审计的关键往往不在语言本身,而在框架:

- 路由
- middleware
- ORM
- 权限守卫
- 状态转换 API

一旦框架识别偏移,系统会在以下方面整体失真:

- entrypoint 识别
- guard 判定
- resource surface 识别
- state-machine 证据

#### 优雅方案

V3 将框架语义独立为 `FrameworkPack`,而不是把框架知识散落在规则中。

每条框架语义证据都必须带:

- `framework_name`
- `framework_version`
- `framework_trace`
- `confidence`

当框架识别失败时:

1. 降级到 generic track 分析
2. 保留语言级与资源级证据
3. 不得伪装成 framework-aware 结果

同时必须建立 framework 级回归基线,验证:

- route 识别正确率
- guard 识别正确率
- resource 识别正确率
- state transition 识别正确率

#### 设计收益

- 框架漂移不会污染整个系统
- 逻辑漏洞能力真正可维护
- 回归测试可以直接绑定到 `FrameworkPack`

### 18.5 总结

V3 对工程挑战的最优雅处理不是继续增加特判,而是把它们全部纳入统一契约:

- 用 `Capability` 解决“当前能做多深”
- 用 `Confidence` 解决“当前推断有多准”
- 用 `Cache` 解决“如何跑得动”
- 用 `Trace` 解决“结果为何可信”

---

## 19. 迁移路线

### V3-A: 统一解析底座

- 引入 Tree-sitter
- 建立 IR
- 替换现有正则 symbol 提取

### V3-B: Provider 抽象

- ParserProvider
- SemanticProvider
- EmbeddingProvider
- FrameworkProvider

### V3-C: 收敛层

- scorer
- static pruner
- evidence assembler

### V3-D: 语义后端多样化

- 本地 embedding
- 云 embedding
- LSP / LSIF / codegraph / ctags

### V3-E: Framework 生态

- 先补高价值框架,后补语言长尾

---

## 20. 最终结论

V3 的正确系统定义不是:

```text
“所有语言都用同一套强语义工具深审”
```

而是:

```text
统一解析底座
  + 多后端语义增强
  + 审计轨道驱动召回
  + 多级静态收敛
  + 标准化证据构建
  + 透明降级与能力标注
```

这样 V3 才能真正满足:

1. 所有语言可审计
2. 主流语言可深审
3. 大仓库可收敛
4. 结果可信且可解释
