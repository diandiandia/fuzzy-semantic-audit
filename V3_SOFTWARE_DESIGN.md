# Fuzzy Semantic Audit V3 —— 软件设计

> 承接 `V3_SYSTEM_DESIGN.md`。
> 本文档回答: V3 代码如何拆分、模块如何交互、核心数据结构与存储契约是什么、workflow 与 Python 组件如何协作落地。

---

## 1. 设计目标

1. 将 V3 的系统设计下沉为可编码、可测试、可迭代的软件边界。
2. 保证 Provider、Pack、IR、Candidate、Evidence 五类核心对象可持久化和可恢复。
3. 让 workflow 只做编排、重试、并发调度,把解析、索引、召回、写盘留给确定性代码。
4. 让降级路径和正常路径共享同一套接口与状态契约。

---

## 1.1 实施口径

本文档中的目录结构和模块边界表示 V3 full implementation 目标形态。

这意味着:

1. 文档中列出的模块默认都属于目标实现范围,不是“可有可无”的示意目录。
2. 若某模块当前只有占位、stub、fallback 或启发式近似实现,应视为 `partial` 而不是 `done`。
3. 如果实现阶段采用临时降级方案,必须同步补充状态契约、manifest 语义和报告语义。

---

## 2. 目录结构

建议 V3 独立目录实现,不要混入 V2 模块:

```text
fuzzy-semantic-audit/
  V3_SYSTEM_DESIGN.md
  V3_SOFTWARE_DESIGN.md
  src_v3/
    core/
      models.py
      enums.py
      state_machine.py
      provider_registry.py
      config.py
      plan_io.py
      event_log.py
      metrics.py
    inventory/
      repo_profiler.py
      language_sharder.py
      capability_resolver.py
      framework_detector.py
    parse/
      parser_runtime.py
      query_loader.py
      ir_builder.py
      ir_cache.py
      file_classifier.py
    enrich/
      semantic_orchestrator.py
      reference_resolver.py
      call_edge_builder.py
      entrypoint_extractor.py
      framework_semantics.py
    recall/
      orchestrator.py
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
      pack_filters.py
    evidence/
      assembler.py
      package_builder.py
      completeness.py
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
        base.py
        treesitter_native.py
        treesitter_wasm.py
      semantic/
        base.py
        lsp_provider.py
        lsif_provider.py
        codegraph_provider.py
        ctags_provider.py
        null_provider.py
      embedding/
        base.py
        fastembed_provider.py
        openai_provider.py
        gemini_provider.py
        cohere_provider.py
        keyword_provider.py
      framework/
        base.py
        generic.py
        django.py
        express.py
        spring.py
        gin.py
        android.py
    packs/
      languages/
      semantic/
      frameworks/
      tracks/
    storage/
      ir_store.py
      index_store.py
      candidate_store.py
      evidence_store.py
      queue_store.py
      sqlite.py
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
    v3_build_index.js
    v3_recall.js
    v3_prune.js
    v3_build_evidence.js
    v3_verify_queue.js
    v3_compile_reports.js
```

说明:

1. `src_v3/parse/file_classifier.py`、`providers/framework/*Pack`、`packs/*` 属于 full implementation 必备模块,不是可长期缺失的占位项。
2. `packs/languages/`、`packs/semantic/`、`packs/frameworks/`、`packs/tracks/` 必须承载可版本化规则/查询/策略,不能长期只保留空目录或版本文件。

---

## 3. 核心数据模型

### 3.1 AuditPlan

```json
{
  "version": "3",
  "repo_path": "/path/to/repo",
  "workspace_dir": "/path/to/repo/.audit_workspace_v3",
  "repo_profile_path": "repo_profile.json",
  "language_shards": [],
  "audit_tracks": [],
  "run_manifest": {},
  "summary": {},
  "created_at": "ISO-8601",
  "updated_at": "ISO-8601"
}
```

### 3.2 RunManifest

```json
{
  "run_id": "uuid-or-ts",
  "run_mode": "semantic_fallback",
  "run_capability": "L2",
  "providers": {
    "parser": "TreeSitterNativeProvider",
    "semantic": "CtagsProvider",
    "embedding": "KeywordFallbackProvider"
  },
  "degradation_reasons": [
    "lsp unavailable",
    "embedding backend unavailable"
  ]
}
```

### 3.3 LanguageShard

```json
{
  "shard_id": "python-backend",
  "lang": "python",
  "paths": ["backend/**/*.py"],
  "frameworks": ["django"],
  "provider_set": {
    "parser": "TreeSitterNativeProvider",
    "semantic": "LSPProvider",
    "framework": "DjangoPack"
  },
  "capability": "L3",
  "status": "indexed"
}
```

补充约束:

1. `paths` 必须保存为相对 `repo_path` 的真实源码路径。
2. `provider_set` 记录的是“实际使用的 provider”,不是“理论首选 provider”。
3. `capability` 必须是 effective capability,不能按 provider 类名推断。
4. `status` 必须反映真实阶段结果; 解析异常、索引异常、无效 fallback 不得仍写成成功态。

### 3.4 IR Node

```json
{
  "node_id": "sym_backend_orders_service.py_update_order_120_168",
  "kind": "symbol",
  "lang": "python",
  "file": "backend/orders/service.py",
  "symbol": "update_order",
  "span": {"start": 120, "end": 168},
  "attributes": {
    "symbol_kind": "function",
    "visibility": "module",
    "code_density": 0.91
  }
}
```

### 3.5 IR Edge

```json
{
  "edge_id": "edge_call_001",
  "kind": "call",
  "src_node_id": "sym_handler_update",
  "dst_node_id": "sym_service_update_order",
  "confidence": 0.92,
  "resolution_kind": "exact",
  "provider_trace": ["LSPProvider"]
}
```

### 3.6 CandidateRecord

```json
{
  "candidate_id": "cand_python-backend_backend_orders_service.py_update_order_120_168",
  "identity_key": "python-backend|backend/orders/service.py|update_order|120|168",
  "shard_id": "python-backend",
  "lang": "python",
  "file": "backend/orders/service.py",
  "symbol": "update_order",
  "span": {"start": 120, "end": 168},
  "source_tracks": ["authz", "state_machine"],
  "matched_rules": ["authz.ownership.missing", "state.transition.skip"],
  "recall_sources": ["rule", "graph", "framework"],
  "provider_trace": ["TreeSitterNativeProvider", "LSPProvider", "DjangoPack"],
  "priority_score": 87.4,
  "candidate_capability": "L3",
  "status": "pruned"
}
```

### 3.7 EvidenceBundle

```json
{
  "candidate_id": "cand_python-backend_backend_orders_service.py_update_order_120_168",
  "symbol_body": "...",
  "upstream_entrypoints": [],
  "caller_chain": [],
  "callee_chain": [],
  "guard_snippets": [],
  "resource_snippets": [],
  "state_transition_snippets": [],
  "type_or_model_context": [],
  "provider_trace": ["LSPProvider", "DjangoPack"],
  "evidence_completeness_score": 78
}
```

### 3.8 VerificationResult

```json
{
  "candidate_id": "cand_python-backend_backend_orders_service.py_update_order_120_168",
  "verdict": "needs_review",
  "reason": "reachable path exists but ownership check evidence is incomplete",
  "confidence": 0.66,
  "referee_votes": [],
  "evidence": [],
  "written_at": "ISO-8601"
}
```

---

## 4. 状态模型

### 4.1 Shard 状态

```text
discovered
  -> parsed
  -> indexed | indexed_fallback | failed
  -> recalled | recalled_fallback | failed
```

### 4.2 Candidate 状态

```text
discovered
  -> recalled
  -> normalized
  -> pruned
  -> evidence_ready
  -> queued_for_verify
  -> verifying
  -> verified | needs_review | false_positive | deferred | error
```

### 4.3 运行状态

```text
full_semantic
semantic_fallback
lexical_fallback
rule_only
```

### 4.4 `core.state_machine`

职责:

- 检查 shard 与 candidate 状态转移是否合法
- 记录 `updated_at`
- 在关键状态间触发事件日志

接口:

```python
can_transition(kind: str, from_status: str, to_status: str) -> bool
transition(obj: Any, to_status: str, metadata: dict | None = None) -> Any
```

补充约束:

1. `transition()` 不仅要校验状态合法性,还要承担关键降级/失败事件的结构化写回职责。
2. 阶段内部若发生部分失败,调用方必须显式写入 `metadata` 或 event log,不能只靠 `except: pass` 吞掉。

---

## 5. 存储设计

### 5.1 Workspace 布局

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
  cache/
    ir.sqlite
    provider.sqlite
  event_log.jsonl
```

### 5.2 存储职责

#### `storage.ir_store`

- 保存 `FileNode` / `SymbolNode` / `Edge`
- 按 file / symbol / shard 查询

#### `storage.index_store`

- 保存 lexical / vector / semantic index 元数据
- 跟踪 `indexed` 与 `indexed_fallback`

#### `storage.candidate_store`

- 候选去重
- 按 status / track / shard 查询

#### `storage.evidence_store`

- 保存 `EvidenceBundle`
- 候选与证据包关联

#### `storage.queue_store`

- 调度队列
- 非真相源

---

## 6. Provider 接口设计

### 6.1 `providers.parser.base`

```python
class ParserProvider(Protocol):
    provider_name: str

    def parse_file(self, file_path: str, lang: str) -> Any: ...
    def extract_symbols(self, tree: Any, query_pack: Any) -> list[dict]: ...
    def extract_imports(self, tree: Any, query_pack: Any) -> list[dict]: ...
    def provider_version(self) -> str: ...
```

### 6.2 `providers.semantic.base`

```python
class SemanticProvider(Protocol):
    provider_name: str

    def capability_level(self) -> str: ...
    def resolution_confidence(self) -> float: ...
    def find_definitions(self, symbol_ref: dict) -> list[dict]: ...
    def find_references(self, symbol_ref: dict) -> list[dict]: ...
    def find_callers(self, symbol_ref: dict) -> list[dict]: ...
    def find_callees(self, symbol_ref: dict) -> list[dict]: ...
```

### 6.3 `providers.embedding.base`

```python
class EmbeddingProvider(Protocol):
    provider_name: str

    def build_index(self, records: list[dict], out_dir: str) -> bool: ...
    def search(self, query: str, out_dir: str, top_k: int) -> list[dict]: ...
```

### 6.4 `providers.framework.base`

```python
class FrameworkProvider(Protocol):
    framework_name: str

    def detect(self, repo_profile: dict, files: list[str]) -> bool: ...
    def extract_entrypoints(self, ir_store: Any) -> list[dict]: ...
    def extract_guards(self, ir_store: Any) -> list[dict]: ...
    def extract_resources(self, ir_store: Any) -> list[dict]: ...
    def extract_state_transitions(self, ir_store: Any) -> list[dict]: ...
```

### 6.5 Provider Registry

`core.provider_registry` 负责:

- 注册可用 Provider
- 根据环境和语言选择最佳 Provider
- 输出 `provider_set` 和 `provider_trace`

接口:

```python
resolve_parser(lang: str, config: dict) -> ParserProvider
resolve_semantic(lang: str, config: dict) -> SemanticProvider
resolve_embedding(config: dict) -> EmbeddingProvider
resolve_frameworks(profile: RepoProfile, lang: str) -> list[FrameworkProvider]
```

### 5.2 Workspace 与 Repo 边界

软件实现必须把源码输入和平面产物严格分开:

1. `audit_plan.json` 中的 `repo_path` 是源码扫描、规则定位、依赖定位、文件读取的唯一根目录。
2. `workspace_dir` 下的 `ir/`、`indices/`、`candidates/`、`evidence/`、`reports/`、`queues/`、`cache/` 都属于产物目录,不得反向参与 inventory/sharding。
3. 任何“通过 `workspace_dir` 的父目录推导 repo root”的实现都视为错误实现。

### 5.3 Ignore 规则

inventory 与 sharding 至少必须显式排除以下路径:

1. `.git/`
2. `.audit_workspace_v3/`
3. 其他历史审计目录或自定义 workspace 目录
4. `cache/`、`reports/`、`evidence/packages/` 等运行产物目录
5. provider 临时索引、导出结果、第三方缓存目录

### 5.4 Effective Capability 写回

实现中必须区分“名义 provider”与“实际能力”:

1. parser fallback 到 regex/text 时,默认 shard status 应保留为结构不足的降级态,不能直接当作稳定 `parsed + L1`。
2. semantic provider 若仅返回 IR/文本启发式结果,应显式落盘为 semantic fallback。
3. run manifest 的 `run_capability` 应反映本次运行真实达到的最高有效能力,而不是配置里的理想 provider。

---

## 7. Pack 设计

### 7.1 `packs.languages`

每个语言包包含:

- suffixes
- parser query pack
- symbol normalization rules
- unsupported/generated file hints

### 7.2 `packs.semantic`

每个语义包包含:

- provider preference order
- fuzzy resolution policy
- type/reference edge normalization

### 7.3 `packs.frameworks`

每个框架包包含:

- route patterns
- guard patterns
- resource patterns
- state-machine patterns

### 7.4 `packs.tracks`

每个 track 包包含:

- recall rules
- pruning rules
- evidence requirements
- severity prompt fragments

---

## 8. 模块设计

### 8.1 `inventory.repo_profiler`

职责:

- 扫描文件树
- 识别语言分布
- 识别构建系统与框架指纹
- 标记 source/test/generated/vendor 目录

输出:

- `RepoProfile`

### 8.2 `inventory.language_sharder`

职责:

- 基于语言和目录切 shard
- 为 shard 分配 `provider_set`
- 标记 `capability`

策略:

- 根目录语言独立为 `lang-root`
- 大目录语言独立为 `lang-<dir>`
- 未支持语言进入低能力 shard,但不静默丢弃

### 8.3 `parse.parser_runtime`

职责:

- 统一调用 `ParserProvider`
- 屏蔽 Native/WASM 差异
- 返回 parser tree

### 8.4 `parse.query_loader`

职责:

- 加载 `.scm`
- 按语言匹配查询包
- 管理 query pack 版本

### 8.5 `parse.ir_builder`

职责:

- 从 parser tree 构造 `FileNode` / `SymbolNode` / `ImportEdge`
- 估算 `code_density`
- 标记生成代码特征

### 8.6 `parse.ir_cache`

职责:

- 增量缓存 IR
- 以 `(file_hash, parser_provider_version, grammar_version, query_pack_version)` 为键

接口:

```python
load_ir_if_fresh(file_path: str, cache_key: dict) -> dict | None
save_ir(file_path: str, cache_key: dict, ir_doc: dict) -> None
```

### 8.7 `enrich.semantic_orchestrator`

职责:

- 协调 `SemanticProvider`
- 写入 definition/reference/caller/callee 边
- 记录 `provider_trace`

### 8.8 `enrich.framework_semantics`

职责:

- 协调框架包
- 产出 `Entrypoint`, `GuardCheck`, `ResourceAccess`, `StateTransition`

### 8.9 `recall.orchestrator`

职责:

- 对每个 `track x shard` 调用 recall 通道
- 合并候选
- 记录零召回组合

### 8.10 `recall.rule_recall`

输入:

- track pack rules
- IR store

输出:

- 规则命中候选

### 8.11 `recall.vector_recall`

输入:

- embedding index
- track intent query

输出:

- 语义召回候选

### 8.12 `recall.graph_recall`

输入:

- semantic edges
- fuzzy edges

输出:

- 图邻域扩展候选

### 8.13 `recall.resource_recall`

输入:

- `ResourceAccess`
- `Entrypoint`

输出:

- 资源路径相关候选

### 8.14 `prune.feature_extractor`

职责:

- 为候选提取特征分
- 包括:
  - `signal_score`
  - `semantic_similarity_score`
  - `reachability_score`
  - `guard_conflict_score`
  - `framework_risk_score`
  - `code_quality_score`

### 8.15 `prune.scorer`

职责:

- 融合特征分
- 输出 `priority_score`

### 8.16 `prune.static_pruner`

职责:

- 删除低价值候选
- 产出 backlog compression metrics

注意:

- 这一层是 `Static Pruning`,不是严格污点分析
- 允许轻量参数传播,但不得伪装成完整 taint engine

### 8.17 `evidence.assembler`

职责:

- 从 IR 和 semantic edges 构造 `EvidenceBundle`
- 计算 `evidence_completeness_score`

### 8.18 `verify.severity_filter`

职责:

- 先进行 cheap triage
- 仅决定是否值得进入三镜头,不决定最终真假

### 8.19 `verify.verdict_policy`

职责:

- 聚合 referee votes
- 输出最终 verdict

### 8.20 `report.coverage_report`

职责:

- 统计 shard/track/candidate/queue 状态
- 显示 capability 与 run_mode
- 显示 provider 降级比例

---

## 9. CLI 设计

### 9.1 `init_plan.py`

输出:

- `audit_plan.json`
- `run_manifest.json`

### 9.2 `build_inventory.py`

输入:

- `--project` 或 `--plan`

输出:

- `repo_profile.json`
- 更新 shard 列表

### 9.3 `build_ir.py`

输入:

- `--plan`

输出:

- `ir/files.jsonl`
- `ir/symbols.jsonl`
- `ir/edges.jsonl`

### 9.4 `build_index.py`

输入:

- `--plan`

输出:

- vector / lexical / semantic index
- shard 状态推进为 `indexed` 或 `indexed_fallback`

### 9.5 `recall_candidates.py`

输出:

- `candidate_registry.jsonl`
- 零召回事件

### 9.6 `prune_candidates.py`

输出:

- `pruned_registry.jsonl`
- backlog compression metrics

### 9.7 `build_evidence.py`

输出:

- `evidence/packages/*.json`

### 9.8 `verify_batch.py`

模式:

- `--get-batch`
- `--writeback`

### 9.9 `compile_reports.py`

输出:

- 4 类 markdown 报告

---

## 10. Workflow 合同

### 10.1 `v3_orchestrate_audit.js`

职责:

- 顺序触发:
  - `init_plan`
  - `build_inventory`
  - `build_ir`
  - `build_index`
  - `recall_candidates`
  - `prune_candidates`
  - `build_evidence`
  - `compile_reports`

### 10.2 `v3_verify_queue.js`

职责:

- 按批次消费 `verify_now`
- 调用 LLM referee
- 回写 `verification_results.jsonl`

### 10.3 workflow 约束

1. workflow 不直接写 registry
2. workflow 不自己计算候选分数
3. workflow 只消费 CLI JSON contract

CLI JSON contract 统一格式:

```json
{
  "ok": true,
  "stage": "build_ir",
  "workspace_dir": "/path/to/.audit_workspace_v3",
  "summary": {}
}
```

---

## 11. 事件与指标

### 11.1 `core.event_log`

记录:

- stage start/end
- provider chosen
- degradation reason
- zero recall pair
- prune ratio
- evidence score histogram

### 11.2 `core.metrics`

记录:

- `recall_total`
- `pruned_total`
- `compression_ratio`
- `mean_evidence_score`
- `queue_backlog`
- `token_cost`
- `wall_clock_seconds`

---

## 12. 降级契约

### 12.1 parser 降级

- `TreeSitterNativeProvider -> TreeSitterWASMProvider`

### 12.2 semantic 降级

- `LSPProvider -> LSIFProvider -> CodeGraphProvider -> CtagsProvider -> NullProvider`

### 12.3 embedding 降级

- `OpenAI/Cohere/Gemini/FastEmbed -> KeywordFallbackProvider`

### 12.4 报告要求

所有降级必须在:

- `run_manifest`
- `coverage_report`
- `metrics_report`

中可见。

---

## 13. 测试设计

### 13.1 单元测试

- models / state_machine
- provider registry
- ir cache
- candidate dedup
- verdict policy

### 13.2 集成测试

- `build_inventory -> build_ir`
- `build_index -> recall`
- `prune -> evidence`
- `verify_batch writeback`

### 13.3 回归测试

基于固定仓库比较:

- candidate total
- generic/fallback 比例
- precision@N
- compression ratio

---

## 14. 实施顺序

### Step 1

- `core`
- `inventory`
- `parse`

### Step 2

- parser providers
- language packs
- IR cache

### Step 3

- semantic providers
- framework packs
- enrich layer

### Step 4

- recall layer
- candidate store
- normalization

### Step 5

- prune layer
- evidence layer

### Step 6

- triage layer
- reports
- metrics

---

## 15. 最终结论

V3 软件设计的核心不是“继续增加语言特判”,而是:

1. 用统一 `IR` 作为主数据平面
2. 用 `ProviderRegistry` 管理所有能力与降级
3. 用 `Pack` 管理语言、语义、框架、轨道扩展
4. 用 `Recall -> Prune -> Evidence -> Triage` 做成本收敛
5. 用 `run_manifest + event_log + metrics` 保证透明性

这样 V3 才能被实现成一套真正可落地、可扩展、可维护的通用代码审计 skill。
