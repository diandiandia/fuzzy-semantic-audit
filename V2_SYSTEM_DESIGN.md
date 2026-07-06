# Fuzzy Semantic Audit V2 —— 系统设计

> 目标: 将现有 skill 重构为一套面向多语言仓库、覆盖优先、可恢复、可扩展的代码审计系统。
> 本文档回答: 系统要解决什么问题、核心约束是什么、整体如何分层、workflow 如何保证“不跳过”。

---

## 1. 设计目标

### 1.1 核心目标

1. 支持多语言仓库,而不是“自动猜一个主语言”。
2. 用 workflow 保证审计对象被遍历,避免 AI mode 提前收工、漏看、跳批次。
3. 召回、验证、报告全流程可追踪,任何候选都能解释“为什么被验证/延期/排除”。
4. 预算只能影响优先级,不能直接把候选判成 `false_positive`。
5. 语言差异下沉到插件层,主流程保持稳定。

### 1.2 非目标

1. 不追求一次性做到所有语言都深度语义理解。
2. 不依赖单一 parser 或单一向量模型作为真相源。
3. 不把“低分候选”直接删掉来换吞吐。

---

## 2. 现有 V1/V4 架构问题

### 2.1 架构层问题

1. `project -> target_language` 是单语言模型,不适合 monorepo。
2. 未知语言退化为 language-independent CWE,覆盖面直接塌缩。
3. 预扫描命中少量关键词后就裁掉整类 CWE,过于激进。
4. severity filter 和 verification limit 会让候选被静默跳过。
5. 候选主键不稳定,同名函数会互相覆盖。

### 2.2 直接后果

1. 多语言仓库会被错误抽样成某一种语言。
2. 逻辑漏洞、授权缺失、状态机绕过容易在预裁剪阶段就被删掉。
3. workflow 虽然存在,但没有形成“覆盖保证”。

---

## 3. 设计原则

1. 覆盖优先于吞吐。
2. 延期优先于丢弃。
3. 候选身份必须稳定。
4. 审计轨道优先于 CWE 预裁剪。
5. 语言能力插件化,工作流中心化。
6. 状态显式化,禁止隐式跳步。

---

## 4. 总体架构

系统分为五层:

```text
L5 Report Layer
  coverage report / audit report / review queue

L4 Verification Layer
  priority queue / referees / verdict writeback

L3 Recall Layer
  graph recall / vector recall / rule recall / resource recall

L2 Inventory Layer
  repo profiling / language sharding / framework detection

L1 Runtime Layer
  workflow engine / language plugins / storage / codegraph / embeddings
```

### 4.1 分层职责

- L1 负责底层能力接入。
- L2 负责“仓库是什么”。
- L3 负责“哪些代码值得看”。
- L4 负责“怎么判、怎么排队、怎么不漏”。
- L5 负责“输出给人看什么”。

---

## 5. 核心抽象

### 5.1 Repo Profile

仓库级画像,描述:

- 语言集合
- 目录布局
- 框架信号
- 构建系统
- 安全敏感区域

### 5.2 Language Shard

把仓库切成一组可独立审计的语言分片,每片包含:

- `shard_id`
- `lang`
- `paths`
- `parser_capabilities`
- `frameworks`
- `risk_hints`

### 5.3 Audit Track

V2 不再先围绕“删哪些 CWE”,而是围绕“哪些审计轨道必须覆盖”。

标准轨道:

1. `memory_safety`
2. `authz`
3. `state_machine`
4. `input_validation`
5. `injection`
6. `deserialization`
7. `resource_access`
8. `concurrency`
9. `crypto`
10. `filesystem_boundary`

每个 track 可以映射多个 CWE,但 workflow 关注的是 track 覆盖率。

### 5.4 Candidate

候选是系统的一等公民,必须有稳定身份:

- `candidate_id`
- `shard_id`
- `lang`
- `file`
- `symbol`
- `span`
- `source_tracks[]`
- `matched_rules[]`
- `recall_sources[]`
- `priority`
- `status`

禁止仅用函数名作为 key。

---

## 6. Workflow 总状态机

```text
discovered
  -> indexed
  -> recalled
  -> normalized
  -> queued_for_verify
  -> verifying
  -> verified | needs_review | false_positive | deferred | error
```

### 6.1 状态说明

- `discovered`: 已建立 repo profile 和 shard。
- `indexed`: shard 已完成索引。
- `recalled`: 已从至少一条 track 召回候选。
- `normalized`: 候选已去重、归一化、补足身份信息。
- `queued_for_verify`: 已进入验证队列。
- `verifying`: 正在被 workflow 消费。
- `verified`: 多视角验证通过。
- `needs_review`: 信息冲突或证据不足。
- `false_positive`: 经验证后被明确证伪。
- `deferred`: 因预算或调度原因延后,不是排除。
- `error`: 工具或数据异常。

### 6.2 状态机约束

1. `deferred` 只能回到 `queued_for_verify`,不能直接结束。
2. `false_positive` 必须由验证产生,不能由 budget gate 产生。
3. 任一 shard 若有未终结候选,coverage report 必须显式列出。

---

## 7. 端到端流程

### Phase 1: Inventory

1. 扫描仓库文件树。
2. 识别语言、框架、入口目录、测试目录、生成物目录。
3. 生成 `repo_profile` 和 `language_shards`。

### Phase 2: Index

1. 对每个 shard 独立建索引。
2. 索引类型至少包括:
   - symbol index
   - call graph index
   - embedding index
   - lightweight rule index

### Phase 3: Recall

每条 `audit_track` 在每个 `language_shard` 上并行执行:

1. graph recall
2. vector recall
3. rule recall
4. resource recall

然后统一去重和归一化。

### Phase 4: Prioritize

候选进入优先队列:

- 高风险入口
- 权限边界
- 状态变迁
- 外部输入直达关键资源
- 原生内存操作

优先级只影响先后顺序。

### Phase 5: Verify

每个候选进入多裁判验证:

1. reachability referee
2. guard/authz referee
3. exploitability/state referee

如语言插件支持,可加:

4. memory referee
5. concurrency referee

### Phase 6: Report

输出三类报告:

1. `audit_report.md`
2. `coverage_report.md`
3. `review_queue.md`

---

## 8. Coverage Guarantee 设计

这是 V2 最核心的设计点。

### 8.1 保证对象

系统保证以下对象不被静默跳过:

1. 每个 `language_shard`
2. 每个 `audit_track`
3. 每个进入注册表的 `candidate`

### 8.2 机制

1. workflow 基于显式队列遍历,不是让 agent 自己决定“下一批”。
2. 每个候选必须有终态或可恢复中间态。
3. 若 run 被中断,下次从 `queued_for_verify` 和 `deferred` 恢复。
4. 若某个 track 在某个 shard 上没有召回结果,要记录 `zero-recall event`,而不是静默通过。

### 8.3 反模式

以下行为在 V2 中禁止:

1. `limit = N` 后剩余候选不入报告。
2. `severity < threshold` 直接写 `false_positive`。
3. 预扫描没命中就删除整个审计类别。

---

## 9. 多语言设计

### 9.1 多语言原则

1. 仓库可以包含多个 shard。
2. shard 可以共享 track,但各自使用不同插件能力。
3. 语言未知时使用 `generic` 插件,而不是降级成“不审”。

### 9.2 插件能力等级

- `L0 generic`: 文件、文本、命名、路径、资源访问规则
- `L1 symbol-aware`: 符号提取、函数边界、调用关系
- `L2 semantic-aware`: 类型、对象、路由、框架语义

系统必须能在不同语言能力等级下继续运行。

### 9.3 Monorepo 支持

一个仓库可以同时存在:

- `backend/python`
- `gateway/go`
- `frontend/ts`
- `native/cpp`

V2 要把这些切成独立 shard 审计,最后汇总成统一报告。

---

## 10. 数据存储

工作目录建议统一放在:

```text
<project>/.audit_workspace_v2/
```

主要文件:

```text
repo_profile.json
audit_plan.json
candidate_registry.jsonl
queues/
  verify_now.json
  deferred.json
  manual_review.json
reports/
  audit_report.md
  coverage_report.md
  review_queue.md
indices/
  <shard_id>/
```

---

## 11. 容错与恢复

### 11.1 失败类型

1. 插件能力缺失
2. codegraph 不可用
3. embedding 索引构建失败
4. 某个候选验证中断
5. 单个 shard 构建失败

### 11.2 恢复策略

1. shard 级失败不阻塞其他 shard。
2. 单候选失败写 `error`,保留上下文。
3. 可恢复任务必须幂等。
4. 所有 writeback 必须批量、原子、可重试。

---

## 12. 安全与可信度

1. 所有裁判结论必须附带理由和证据引用。
2. `verified` 需要满足可达性和可利用性双条件。
3. `needs_review` 不能和 `verified` 混写。
4. 报告必须区分“已证实”和“待人工确认”。

---

## 13. 可观测性

必须输出以下指标:

1. 每个 shard 的候选数
2. 每个 track 的召回数
3. 每个阶段耗时
4. `verified / needs_review / false_positive / deferred / error` 数量
5. zero-recall tracks
6. 未完成候选数量

---

## 14. 版本迁移

### 14.1 从 V1/V4 到 V2 的迁移原则

1. 保留现有 workflow-first 思路。
2. 保留候选包导出与批量回写。
3. 重做 plan schema。
4. 重做 candidate identity。
5. 把单语言逻辑拆成 shard + plugin。

### 14.2 分阶段迁移

Phase A:

- 新 schema
- 新状态机
- 新 candidate registry

Phase B:

- 多语言 shard
- generic plugin
- deferred queue

Phase C:

- 各语言插件
- track-specific recall
- coverage report

---

## 15. 结论

V2 的本质不是“再加几个语言配置”,而是把系统从“单语言脚本流水线”升级为“覆盖优先的多语言审计平台”。

最重要的设计决策只有三条:

1. 用 `language_shard` 替代 `target_language`。
2. 用 `audit_track` 替代激进的 CWE 预裁剪。
3. 用 `deferred queue` 替代“低优先级就排除”。
