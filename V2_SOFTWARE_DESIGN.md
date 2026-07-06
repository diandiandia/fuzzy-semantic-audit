# Fuzzy Semantic Audit V2 —— 软件设计

> 承接 `V2_SYSTEM_DESIGN.md`。
> 本文档回答: 代码如何拆分、模块如何交互、核心数据结构是什么、workflow 和 Python 组件怎样协作实现。

---

## 1. 设计目标

1. 建立可扩展的软件边界,便于增加语言插件与审计轨道。
2. 保证状态、候选、队列三类核心数据可持久化和可恢复。
3. 让 workflow 只做编排与调度,把规则、索引、写盘留给确定性代码。

---

## 2. 目录结构

建议新增 V2 目录而不是直接覆盖现有 V4 实现:

```text
fuzzy-semantic-audit/
  V2_SYSTEM_DESIGN.md
  V2_SOFTWARE_DESIGN.md
  src_v2/
    core/
      plan_schema.py
      models.py
      candidate_registry.py
      queue_store.py
      state_machine.py
      event_log.py
    inventory/
      repo_profiler.py
      language_sharder.py
      framework_detector.py
    recall/
      orchestrator.py
      graph_recall.py
      vector_recall.py
      rule_recall.py
      resource_recall.py
      normalizer.py
      priority_ranker.py
    verify/
      package_builder.py
      referee_prompts.py
      verdict_policy.py
      writeback.py
    report/
      audit_report.py
      coverage_report.py
      review_queue.py
    plugins/
      base.py
      generic.py
      python.py
      javascript.py
      go.py
      java.py
      c.py
      cpp.py
    integrations/
      codegraph_client.py
      embedding_index.py
      ripgrep_client.py
    cli/
      init_plan.py
      build_inventory.py
      recall_candidates.py
      verify_batch.py
      compile_reports.py
  workflows/
    v2_orchestrate_audit.js
    v2_build_inventory.js
    v2_recall_candidates.js
    v2_verify_queue.js
    v2_compile_reports.js
```

---

## 3. 核心数据模型

### 3.1 AuditPlan

```json
{
  "version": "2",
  "repo_path": "/path/to/repo",
  "repo_profile": {},
  "language_shards": [],
  "audit_tracks": [],
  "summary": {},
  "created_at": "ISO-8601",
  "updated_at": "ISO-8601"
}
```

### 3.2 LanguageShard

```json
{
  "shard_id": "py-backend",
  "lang": "python",
  "paths": ["backend/**/*.py"],
  "frameworks": ["django"],
  "parser_capabilities": ["symbol", "callgraph"],
  "status": "indexed"
}
```

### 3.3 AuditTrack

```json
{
  "track_id": "authz",
  "title": "Authorization and Ownership",
  "mapped_cwes": ["285", "639", "862", "863"],
  "priority": "high",
  "status": "active"
}
```

### 3.4 CandidateRecord

```json
{
  "candidate_id": "cand_py-backend_000123",
  "shard_id": "py-backend",
  "lang": "python",
  "file": "backend/orders/service.py",
  "symbol": "update_order",
  "span": {"start": 120, "end": 168},
  "source_tracks": ["authz", "state_machine"],
  "matched_rules": ["idor.resource-update", "state.skip-precondition"],
  "recall_sources": ["graph", "resource"],
  "priority": 87,
  "status": "queued_for_verify"
}
```

### 3.5 VerificationResult

```json
{
  "candidate_id": "cand_py-backend_000123",
  "verdict": "needs_review",
  "reason": "ownership check missing on this path",
  "evidence": [],
  "referee_votes": [],
  "written_at": "ISO-8601"
}
```

---

## 4. 模块设计

### 4.1 `core.models`

职责:

- 定义 dataclass 或 pydantic schema
- 统一字段命名
- 统一序列化/反序列化

关键对象:

- `AuditPlan`
- `RepoProfile`
- `LanguageShard`
- `AuditTrack`
- `CandidateRecord`
- `VerificationResult`

### 4.2 `core.state_machine`

职责:

- 约束候选状态转移
- 检查非法跳转

接口:

```python
can_transition(from_status: str, to_status: str) -> bool
transition(candidate: CandidateRecord, to_status: str) -> CandidateRecord
```

约束:

- `queued_for_verify -> false_positive` 必须带验证结果
- `deferred -> verified` 不允许直接跳转

### 4.3 `core.candidate_registry`

职责:

- 候选持久化
- 基于稳定主键去重
- 按 shard / track / status 查询

建议存储:

- `candidate_registry.jsonl`

接口:

```python
upsert_candidates(records: list[CandidateRecord]) -> int
load_candidates(status: str | None = None) -> list[CandidateRecord]
get_candidate(candidate_id: str) -> CandidateRecord | None
```

去重键:

```text
(shard_id, file, symbol, span.start, span.end)
```

### 4.4 `core.queue_store`

职责:

- 管理验证队列
- 管理 deferred 队列
- 管理 manual review 队列

接口:

```python
enqueue(queue_name: str, candidate_ids: list[str]) -> None
dequeue(queue_name: str, limit: int) -> list[str]
requeue(queue_name: str, candidate_ids: list[str]) -> None
```

注意:

- 队列是调度结构,不是数据真相源
- 真相源仍是 registry + plan

### 4.5 `inventory.repo_profiler`

职责:

- 扫描仓库文件树
- 识别语言分布
- 识别入口点、测试目录、生成物目录
- 输出 `RepoProfile`

实现建议:

- `rg --files`
- 文件扩展名统计
- 常见框架指纹

### 4.6 `inventory.language_sharder`

职责:

- 从 `RepoProfile` 生成 `LanguageShard[]`
- 处理 monorepo 目录分片

规则:

- 同语言可按子系统进一步拆 shard
- 前后端混合项目不要合并成一个 shard

### 4.7 `plugins.base`

定义语言插件统一接口:

```python
class LanguagePlugin(Protocol):
    name: str
    capability_level: str

    def match_files(self, files: list[str]) -> list[str]: ...
    def enumerate_symbols(self, repo_path: str, files: list[str]) -> list[dict]: ...
    def build_rule_signals(self) -> list[str]: ...
    def build_resource_signals(self) -> list[str]: ...
    def build_track_rules(self, track_id: str) -> list[dict]: ...
```

### 4.8 `plugins.generic`

这是 V2 的兜底插件。

职责:

- 未知语言仍可运行
- 基于文本、路径、命名、资源访问模式做 recall

能力:

- 无类型语义
- 无强调用图保证
- 但可以提供最基础的轨道覆盖

### 4.9 `integrations.codegraph_client`

职责:

- 封装 `codegraph` CLI
- 提供稳定 Python API

接口:

```python
status(project_path: str) -> bool
init(project_path: str) -> None
files(project_path: str) -> list[dict]
symbols(project_path: str, file_path: str) -> list[dict]
source(project_path: str, symbol: str, file_path: str | None = None) -> str
callers(project_path: str, symbol: str, file_path: str | None = None) -> list[dict]
callees(project_path: str, symbol: str, file_path: str | None = None) -> list[dict]
```

要求:

- 超时控制
- 错误可观测
- 统一输出 schema

### 4.10 `integrations.embedding_index`

职责:

- shard 级构建 embedding index
- 提供 semantic search

接口:

```python
build(shard_id: str, records: list[dict]) -> None
search(shard_id: str, query: str, top_k: int) -> list[dict]
```

### 4.11 `recall.*`

`recall.orchestrator` 负责统一调度各 recall 通道:

```python
run_recall(plan: AuditPlan, shard: LanguageShard, track: AuditTrack) -> list[CandidateRecord]
```

子模块职责:

- `graph_recall`: 基于 symbol / call graph
- `vector_recall`: 基于 embedding
- `rule_recall`: 基于规则匹配
- `resource_recall`: 基于资源访问模式
- `normalizer`: 合并候选、补齐身份、去重
- `priority_ranker`: 计算优先级

### 4.12 `verify.package_builder`

职责:

- 把候选上下文打包给 workflow 裁判

包内容建议:

- candidate metadata
- code snippet
- call chain slice
- matched tracks
- matched rules
- framework hints
- prior evidence

### 4.13 `verify.verdict_policy`

职责:

- 定义 verdict 归类策略

接口:

```python
decide(votes: list[dict]) -> tuple[str, str]
```

规则:

- `verified`: 满足 reachability + exploitability + guard failure
- `needs_review`: 有冲突或缺证
- `false_positive`: 有充分证伪
- `deferred`: 由调度层产生,不是判决层产生

### 4.14 `verify.writeback`

职责:

- 批量写回 candidate 状态
- 更新 plan summary
- 记录 event log

要求:

- 原子写
- 幂等
- 可重试

### 4.15 `report.*`

三个报告模块:

- `audit_report.py`
- `coverage_report.py`
- `review_queue.py`

`coverage_report` 必须覆盖:

- shard 覆盖率
- track 覆盖率
- deferred 数量
- zero-recall events

---

## 5. Workflow 设计

### 5.1 `v2_orchestrate_audit.js`

总入口,顺序:

1. build inventory
2. build indices
3. recall candidates
4. fill verify queue
5. verify batch
6. compile reports

输入参数:

```json
{
  "repoRoot": "...",
  "projectPath": "...",
  "verifyLimit": 200
}
```

### 5.2 `v2_build_inventory.js`

职责:

- 调 Python CLI 生成 `repo_profile.json` 和 `audit_plan.json`

### 5.3 `v2_recall_candidates.js`

职责:

- 按 shard × track 遍历 recall
- 回写 registry
- 形成 verify 队列

关键约束:

- 任何 shard-track 组合都必须记录结果,即使为 0

### 5.4 `v2_verify_queue.js`

职责:

- 从 verify queue 拉取一批候选
- 对每个候选跑平行裁判
- 批量 writeback
- 未消费完则写入 deferred 或保留队列状态

关键点:

- `verifyLimit` 只决定本轮消费量
- 剩余候选继续排队

### 5.5 `v2_compile_reports.js`

职责:

- 汇总 registry 和 queues
- 输出三类报告

---

## 6. CLI 设计

建议暴露以下命令:

```text
python -m src_v2.cli.init_plan
python -m src_v2.cli.build_inventory
python -m src_v2.cli.recall_candidates
python -m src_v2.cli.verify_batch
python -m src_v2.cli.compile_reports
```

每个 CLI 最后一行打印单行 JSON,供 workflow 解析。

示例:

```json
{"ok": true, "queued": 182, "deferred": 0}
```

---

## 7. 配置设计

建议新增:

```text
resources_v2/
  languages/
    generic.json
    python.json
    javascript.json
    go.json
    java.json
    c.json
    cpp.json
  tracks/
    authz.json
    state_machine.json
    injection.json
    resource_access.json
```

配置内容包括:

- 文件扩展名
- 路由/资源/权限信号
- track 规则
- 默认 prompt 片段

---

## 8. 测试设计

### 8.1 单元测试

- state machine 转移
- candidate 去重
- queue store 行为
- plugin 匹配逻辑

### 8.2 集成测试

- 单语言项目
- 多语言 monorepo
- 未知语言项目
- codegraph 缺失场景
- embedding 构建失败场景

### 8.3 回归测试

重点验证:

1. 同名函数不丢
2. `deferred` 不会被写成 `false_positive`
3. zero-recall tracks 会进 coverage report
4. verify limit 不影响总覆盖保证

---

## 9. 迁移实现建议

### Step 1

先实现:

- `src_v2/core`
- `src_v2/inventory`
- `src_v2/cli/init_plan.py`

### Step 2

再实现:

- `generic` 插件
- registry
- queue store
- coverage report

### Step 3

最后接入:

- 语言专属插件
- 裁判 prompts
- workflow 批量验证

---

## 10. 结论

V2 软件设计的关键不是“把旧脚本拼起来”,而是建立三类长期稳定的边界:

1. 数据边界: `plan + registry + queue`
2. 语言边界: `plugin interface`
3. 编排边界: `workflow` 只调度,不持有业务真相

只要这三个边界稳定,后续增加 Rust、PHP、Ruby、Swift 或新的审计轨道,都不需要重写主流程。
