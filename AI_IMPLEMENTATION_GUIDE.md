# Fuzzy Semantic Audit V2 —— AI 实施指南

> 目的: 这是一份给其他 AI 编码代理直接执行的实现契约。
> 它不重复讲愿景,而是把“必须产出什么、按什么顺序产出、输入输出长什么样、什么算完成”说清楚。

---

## 1. 可执行性评估

### 1.1 结论

当前三份文档:

- `REQUIREMENTS.md`
- `V2_SYSTEM_DESIGN.md`
- `V2_SOFTWARE_DESIGN.md`

已经足够定义方向,但**还不足以保证其他 AI 工具稳定实现**。

原因不是目标不清,而是以下实现契约仍然偏抽象:

1. CLI 的输入输出字段未完全定死。
2. workflow 各阶段的 JSON contract 未完全定死。
3. 状态机缺少完整转移表。
4. registry / queue / reports 的文件格式没有统一样例。
5. Phase-by-phase 的交付边界不够硬,AI 容易跨模块乱写。

因此本文件提供一套补充约束。

---

## 2. AI 开发总规则

其他 AI 工具在实现时必须遵守:

1. 先完成 `P0` 骨架,再做插件和优化。
2. 只要存在不确定性,优先保留候选并标记 `deferred`。
3. 不允许用预算逻辑直接生成 `false_positive`。
4. 不允许用函数名单独做 candidate identity。
5. 不允许把 monorepo 收敛成单一 `target_language`。
6. 所有 CLI 最后一行必须输出单行 JSON。
7. 所有 workflow 只能依赖 CLI/文件契约,不能依赖进程内共享状态。
8. 如果某个模块未完成,要返回结构化 `error`,不能静默跳过。

---

## 3. 目录与文件交付清单

### 3.1 P0 必须交付

以下文件是第一阶段最低交付物:

```text
/root/fuzzy-semantic-audit-v2/
  src_v2/
    core/
      models.py
      state_machine.py
      candidate_registry.py
      queue_store.py
      plan_io.py
    inventory/
      repo_profiler.py
      language_sharder.py
    cli/
      init_plan.py
      build_inventory.py
      recall_candidates.py
      verify_batch.py
      compile_reports.py
    report/
      coverage_report.py
  workflows/
    v2_orchestrate_audit.js
    v2_build_inventory.js
    v2_recall_candidates.js
    v2_verify_queue.js
    v2_compile_reports.js
```

### 3.2 P1 交付

```text
src_v2/
  plugins/
    base.py
    generic.py
    python.py
    javascript.py
    go.py
    java.py
    c.py
    cpp.py
  recall/
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
  integrations/
    codegraph_client.py
    embedding_index.py
    ripgrep_client.py
```

---

## 4. 规范化数据契约

### 4.1 `audit_plan.json`

最小 schema:

```json
{
  "version": "2",
  "repo_path": "/abs/path/to/repo",
  "repo_profile_path": ".audit_workspace_v2/repo_profile.json",
  "language_shards": [],
  "audit_tracks": [],
  "summary": {
    "shards_total": 0,
    "tracks_total": 0,
    "candidates_total": 0,
    "verified": 0,
    "needs_review": 0,
    "false_positive": 0,
    "deferred": 0,
    "error": 0
  },
  "created_at": "2026-07-05T00:00:00Z",
  "updated_at": "2026-07-05T00:00:00Z"
}
```

### 4.2 `repo_profile.json`

```json
{
  "repo_path": "/abs/path/to/repo",
  "languages": [
    {"lang": "python", "file_count": 120},
    {"lang": "js", "file_count": 88}
  ],
  "frameworks": ["django", "express"],
  "directories": {
    "source": ["backend", "frontend"],
    "tests": ["tests", "__tests__"],
    "generated": ["dist", "build", "vendor", "node_modules"]
  },
  "entrypoint_hints": ["backend/app.py", "frontend/src/router.ts"]
}
```

### 4.3 `candidate_registry.jsonl`

每行一个 JSON object,最小字段:

```json
{
  "candidate_id": "cand_py-backend_backend/orders/service.py_update_order_120_168",
  "identity_key": "py-backend|backend/orders/service.py|update_order|120|168",
  "shard_id": "py-backend",
  "lang": "python",
  "file": "backend/orders/service.py",
  "symbol": "update_order",
  "span": {"start": 120, "end": 168},
  "source_tracks": ["authz", "state_machine"],
  "matched_rules": ["idor.resource-update"],
  "recall_sources": ["graph", "resource"],
  "priority": 87,
  "status": "queued_for_verify",
  "evidence_refs": [],
  "created_at": "2026-07-05T00:00:00Z",
  "updated_at": "2026-07-05T00:00:00Z"
}
```

### 4.4 `queues/*.json`

文件结构统一:

```json
{
  "queue_name": "verify_now",
  "candidate_ids": [
    "cand_py-backend_backend/orders/service.py_update_order_120_168"
  ],
  "updated_at": "2026-07-05T00:00:00Z"
}
```

### 4.5 `verification_result`

```json
{
  "candidate_id": "cand_py-backend_backend/orders/service.py_update_order_120_168",
  "verdict": "needs_review",
  "reason": "ownership check missing on this call path but external reachability evidence is incomplete",
  "referee_votes": [
    {
      "lens": "reachability",
      "decision": "uncertain",
      "reason": "route source not resolved"
    },
    {
      "lens": "guard",
      "decision": "fail",
      "reason": "no ownership check on path"
    }
  ],
  "evidence": [
    {"type": "file", "value": "backend/orders/service.py:120"},
    {"type": "call_chain", "value": "OrderController.update -> OrderService.update_order"}
  ]
}
```

---

## 5. 状态机转移表

其他 AI 工具必须严格按照下表实现:

| From | To | Allowed | Notes |
|---|---|---|---|
| `discovered` | `indexed` | yes | shard 索引建立完成 |
| `indexed` | `recalled` | yes | 至少跑过一次 recall |
| `recalled` | `normalized` | yes | 已去重并完成 identity 补齐 |
| `normalized` | `queued_for_verify` | yes | 已入验证队列 |
| `queued_for_verify` | `verifying` | yes | workflow 正在消费 |
| `verifying` | `verified` | yes | 有完整 verdict |
| `verifying` | `needs_review` | yes | 有完整 verdict |
| `verifying` | `false_positive` | yes | 必须有验证理由 |
| `verifying` | `deferred` | yes | 仅调度/预算/依赖不足 |
| `verifying` | `error` | yes | 工具失败/上下文错误 |
| `deferred` | `queued_for_verify` | yes | 下轮恢复 |
| `error` | `queued_for_verify` | yes | 人工或自动重试 |

禁止的跳转:

1. `queued_for_verify -> false_positive`
2. `normalized -> verified`
3. `deferred -> verified`
4. 任意状态直接丢失记录

---

## 6. CLI 契约

### 6.1 `init_plan.py`

职责:

- 初始化 `.audit_workspace_v2`
- 初始化 `audit_plan.json`
- 初始化空队列和空 registry

命令:

```bash
python -m src_v2.cli.init_plan --project /path/to/repo
```

最后一行输出:

```json
{"ok":true,"workspace":"/path/to/repo/.audit_workspace_v2","plan":"/path/to/repo/.audit_workspace_v2/audit_plan.json"}
```

### 6.2 `build_inventory.py`

职责:

- 生成 `repo_profile.json`
- 生成 `language_shards`
- 写回 `audit_plan.json`

最后一行输出:

```json
{"ok":true,"repo_profile":".../repo_profile.json","shards_total":3,"languages":["python","js","go"]}
```

### 6.3 `recall_candidates.py`

职责:

- 按 shard × track 跑 recall
- upsert registry
- 更新 verify queue

最后一行输出:

```json
{"ok":true,"candidates_total":182,"queued_for_verify":182,"zero_recall_pairs":[["go-gateway","crypto"]]}
```

### 6.4 `verify_batch.py`

职责:

- 消费 verify queue
- 读取候选包
- 批量回写 verdict
- 未消费完的留队或进入 deferred

最后一行输出:

```json
{"ok":true,"consumed":50,"verified":3,"needs_review":11,"false_positive":20,"deferred":16}
```

### 6.5 `compile_reports.py`

职责:

- 生成三类报告

最后一行输出:

```json
{"ok":true,"audit_report":".../reports/audit_report.md","coverage_report":".../reports/coverage_report.md","review_queue":".../reports/review_queue.md"}
```

---

## 7. Workflow 契约

### 7.1 `v2_orchestrate_audit.js`

输入:

```json
{
  "projectPath": "/abs/path/to/repo",
  "verifyLimit": 100
}
```

顺序固定:

1. `init_plan`
2. `build_inventory`
3. `recall_candidates`
4. `verify_batch`
5. `compile_reports`

输出:

```json
{
  "ok": true,
  "workspace": "/abs/path/to/repo/.audit_workspace_v2",
  "shards_total": 3,
  "candidates_total": 182,
  "consumed": 100,
  "reports": {
    "audit_report": "...",
    "coverage_report": "...",
    "review_queue": "..."
  }
}
```

### 7.2 `v2_verify_queue.js`

强制要求:

1. `verifyLimit` 仅控制本轮消费数量。
2. 未消费候选不得从 registry 消失。
3. 若某候选上下文不足,优先写 `needs_review` 或 `deferred`。

---

## 8. 插件最小接口

其他 AI 实现插件时,必须至少实现:

```python
class LanguagePlugin(Protocol):
    plugin_name: str
    lang_key: str
    capability_level: str

    def match_files(self, repo_files: list[str]) -> list[str]: ...
    def enumerate_symbols(self, repo_path: str, files: list[str]) -> list[dict]: ...
    def detect_frameworks(self, repo_path: str, files: list[str]) -> list[str]: ...
    def build_track_rules(self, track_id: str) -> list[dict]: ...
    def build_resource_signals(self) -> list[str]: ...
    def supports_callgraph(self) -> bool: ...
```

`generic.py` 是必须实现的基线插件。

---

## 9. 验证策略硬约束

### 9.1 `verified`

至少满足:

1. 可达性有正向证据
2. 守卫/授权/状态校验存在明确缺陷
3. 有可解释的触发或利用路径

### 9.2 `needs_review`

任一情况满足即可:

1. 裁判分歧
2. 关键上下文缺失
3. 代码有明显风险但可达性不完整

### 9.3 `false_positive`

必须满足:

1. 已完成验证
2. 有证伪理由

### 9.4 `deferred`

仅用于:

1. 本轮预算不足
2. 外部工具暂不可用
3. 依赖前置步骤未就绪

不得用于表达安全结论。

---

## 10. Coverage Report 格式要求

`coverage_report.md` 至少包含以下标题:

```text
# Coverage Report
## Run Summary
## Shard Coverage
## Track Coverage
## Candidate Status
## Zero Recall Pairs
## Deferred Queue
## Errors
```

必须展示:

1. 每个 shard 的候选数
2. 每个 track 的召回数
3. 当前剩余未终结候选数
4. `zero_recall_pairs`

---

## 11. 分阶段 Definition of Done

### P0 DoD

算完成必须同时满足:

1. 可以初始化 workspace
2. 可以生成 `repo_profile.json`
3. 可以生成 `language_shards`
4. 可以建立空 registry 和队列
5. workflow 能串起 CLI

### P1 DoD

1. generic plugin 可工作
2. recall 能写入 registry
3. verify queue 能消费并回写
4. coverage report 可生成

### P2 DoD

1. 至少 3 个语言插件可工作
2. graph/vector/rule/resource recall 可并存
3. verdict policy 可稳定输出

---

## 12. 测试清单

其他 AI 实现后至少要覆盖以下测试:

1. 多语言仓库会生成多个 shard
2. 未知语言会走 generic plugin
3. 同名函数不会被错误合并
4. `verifyLimit=10` 时剩余候选仍在 queue 或 deferred
5. `severity` 不会直接把候选变成 `false_positive`
6. `zero_recall_pairs` 会进入 coverage report
7. workflow 中断后可继续

---

## 13. 禁止事项

实现时明确禁止:

1. 复用旧版 `target_language` 作为 V2 唯一语言真相
2. 用 `function` 名称作为 registry 主键
3. 用 `limit` 直接截断后不入报告
4. 预扫描未命中就删除整个 track
5. 未验证就输出 `false_positive`

---

## 14. 推荐实施顺序

其他 AI 工具最稳妥的实施顺序是:

1. `core` 数据模型与状态机
2. `init_plan.py`
3. `repo_profiler.py` 与 `language_sharder.py`
4. registry 与 queue store
5. workflow 骨架
6. generic plugin
7. recall 与 verify
8. coverage report
9. 语言专属插件

不要从向量索引或复杂裁判开始。
