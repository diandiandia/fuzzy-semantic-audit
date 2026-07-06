# Fuzzy Semantic Audit V2 —— 需求文档

> 目标: 定义 Fuzzy Semantic Audit V2 的产品需求、功能边界、验收标准和实施优先级。
> 本文档面向实现阶段,作为系统设计与软件设计的上游输入。

---

## 1. 项目背景

现有版本已经证明两件事:

1. 用 workflow 编排代码审计,比纯 AI mode 更稳定。
2. 现有实现仍然存在单语言假设、候选漏收、预算即丢审等问题。

V2 的目标不是对现有版本做局部修补,而是构建一套真正面向多语言仓库、覆盖优先、可恢复的通用审计 skill。

---

## 2. 产品目标

### 2.1 核心目标

1. 支持多语言仓库代码审计。
2. 支持 workflow 全流程编排,避免 AI mode 跳步骤、跳候选、提前结束。
3. 对所有进入系统的候选建立可追踪状态。
4. 预算只影响调度顺序,不影响候选是否最终被审计。
5. 输出可区分“已证实漏洞”“待人工复核”“已证伪”的审计结果。

### 2.2 成功标准

1. 系统可对 monorepo 进行按语言分片审计。
2. 候选不会因 `limit` 或低 severity 被静默丢弃。
3. 每次运行后都能给出 coverage report。
4. 系统可从中断状态恢复继续执行。

---

## 3. 用户与使用场景

### 3.1 目标用户

1. 使用 Codex/Claude Code/类似 agent 的安全研究人员
2. 需要批量做代码审计的开发者
3. 需要在 monorepo 中做逻辑漏洞和实现漏洞扫描的工程团队

### 3.2 典型场景

1. 审计一个 Python + TypeScript + Go 的 monorepo。
2. 审计一个未知语言或框架较多的代码库,要求至少提供 generic coverage。
3. 审计中途中断,下次继续从队列恢复。
4. 审计完成后查看 verified、needs_review 和 deferred 的分布。

---

## 4. 功能需求

### 4.1 仓库分析

系统必须:

1. 扫描目标仓库文件树。
2. 识别语言分布。
3. 识别主要目录边界、测试目录、生成物目录。
4. 识别已知框架和构建线索。
5. 生成仓库级画像。

### 4.2 多语言分片

系统必须:

1. 将仓库拆分为多个 `language_shard`。
2. 支持一个仓库同时包含多个语言分片。
3. 对未知语言使用 `generic` 分片能力。
4. 不允许通过“选择主语言”覆盖其他语言内容。

### 4.3 索引与召回

系统必须:

1. 支持符号/调用图召回。
2. 支持向量语义召回。
3. 支持规则召回。
4. 支持资源访问类召回。
5. 对多个召回源做统一去重和归一化。

系统应该:

1. 支持 shard 级增量索引。
2. 支持索引失败后的降级模式。

### 4.4 审计轨道

系统必须至少支持以下轨道:

1. `authz`
2. `state_machine`
3. `resource_access`
4. `injection`
5. `input_validation`
6. `deserialization`
7. `memory_safety`
8. `concurrency`
9. `crypto`

系统必须:

1. 以 `track` 作为覆盖单位。
2. 允许一个候选同时属于多个 track。
3. 不允许在预扫描阶段直接删除整个 track。

### 4.5 候选注册与状态管理

系统必须:

1. 为每个候选生成稳定 `candidate_id`。
2. 存储候选的文件、符号、跨度、语言、来源轨道、召回来源。
3. 为每个候选维护状态机。
4. 支持批量写回状态。
5. 支持候选查询与恢复。

系统不得:

1. 仅使用函数名作为候选唯一键。
2. 因预算原因把候选直接写成 `false_positive`。

### 4.6 Workflow 编排

系统必须:

1. 用 workflow 负责全流程状态推进。
2. 用 workflow 显式驱动 inventory、index、recall、verify、report。
3. 用队列而不是 agent 自由发挥来控制验证批次。
4. 支持中断后恢复。

### 4.7 验证机制

系统必须:

1. 对候选运行多裁判验证。
2. 至少包含:
   - reachability
   - guard/authz
   - exploitability/state
3. 输出结构化裁判结果。
4. 根据策略将结果归类为:
   - `verified`
   - `needs_review`
   - `false_positive`
   - `deferred`
   - `error`

系统应该:

1. 对支持的语言启用语言特化裁判。
2. 为每个 verdict 保存证据与理由。

### 4.8 报告输出

系统必须输出:

1. `audit_report.md`
2. `coverage_report.md`
3. `review_queue.md`

`coverage_report.md` 必须包含:

1. shard 覆盖情况
2. track 覆盖情况
3. verified / needs_review / false_positive / deferred / error 数量
4. zero-recall 轨道
5. 未完成候选数量

---

## 5. 非功能需求

### 5.1 可恢复性

1. 任一阶段中断后可恢复。
2. 单个 shard 失败不应阻塞全部流程。
3. 单个候选失败应记录为 `error` 并继续其他候选。

### 5.2 可扩展性

1. 新语言应以插件方式接入。
2. 新审计轨道应以配置和模块方式接入。
3. 新的 recall 通道不应破坏现有 workflow。

### 5.3 可观测性

系统必须记录:

1. 各阶段耗时
2. 候选数量变化
3. 各轨道召回情况
4. 各 verdict 分布
5. 队列积压情况

### 5.4 准确性与可信度

1. `verified` 必须有清晰理由和证据。
2. `needs_review` 必须与 `verified` 区分。
3. `false_positive` 必须来自验证结果,不是预算裁剪。

### 5.5 性能

系统应该:

1. 支持增量索引。
2. 支持并行 recall。
3. 支持批量 writeback。

系统可以:

1. 对超大仓库分 shard 分批执行。

---

## 6. 数据与状态需求

系统必须维护以下持久化数据:

1. `repo_profile.json`
2. `audit_plan.json`
3. `candidate_registry.jsonl`
4. `verify queue`
5. `deferred queue`
6. `manual review queue`
7. 审计报告

系统必须保证:

1. 数据可重建
2. 状态可追踪
3. 写回幂等

---

## 7. 验收标准

### 7.1 MVP 验收

满足以下条件视为 V2 MVP 可用:

1. 能对包含至少两种语言的仓库建立 `language_shard`。
2. 能建立候选注册表并生成稳定主键。
3. 能通过 workflow 跑通 inventory -> recall -> verify -> report。
4. `limit` 只影响本轮验证量,未消费候选进入 deferred 或保留在队列中。
5. 能输出 coverage report。

### 7.2 完整版验收

1. 支持 generic plugin。
2. 支持至少 Python、JavaScript/TypeScript、Go、Java、C/C++ 插件。
3. 支持多 recall 通道并统一归一化。
4. 支持中断恢复。
5. 支持多裁判结果批量写回。

---

## 8. 范围边界

### 8.1 本期范围

1. 多语言分片
2. 候选注册表
3. workflow 队列化验证
4. coverage report
5. generic plugin
6. 核心语言插件框架

### 8.2 暂不纳入本期

1. 所有语言的深度语义建模
2. 自动 exploit 生成
3. 动态执行与运行时 instrumentation
4. IDE 或 Web UI

---

## 9. 实施优先级

### P0

1. 新 plan schema
2. candidate registry
3. state machine
4. workflow 队列化验证
5. coverage report

### P1

1. generic plugin
2. 多语言 shard
3. recall 归一化
4. batch writeback

### P2

1. 语言特化插件
2. 更多 track 规则
3. 更细粒度优先级排序

---

## 10. 结论

V2 的需求核心只有一句话:

> 构建一套覆盖优先、可恢复、可扩展的多语言代码审计 skill,让 workflow 负责保证“不会跳过”,让插件负责处理语言差异,让状态机负责保证结果可信。

---

## 11. AI 实施约束

为了让其他 AI 编码工具可以直接按文档实现,本需求文档补充以下约束:

1. 架构说明不是唯一输入,实现必须同时遵守 `V2_SYSTEM_DESIGN.md`、`V2_SOFTWARE_DESIGN.md` 和 `AI_IMPLEMENTATION_GUIDE.md`。
2. 若实现中出现文档未覆盖的选择题,必须优先满足:
   - 不丢候选
   - 不静默降级
   - 不把预算问题写成安全结论
3. 若某项能力做不到,必须输出 `deferred` 或 `error`,而不是伪造 `verified` / `false_positive`。
4. 未经文档明确授权,不得引入“主语言唯一化”“severity 直接排除”“仅凭函数名去重”这三类旧架构行为。
