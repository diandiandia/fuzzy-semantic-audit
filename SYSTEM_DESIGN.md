# Fuzzy Semantic Audit —— 系统设计文档 (V4.0)

> 目标:一套**稳定、可批量、低假阳性、可溯源**的 CWE 驱动代码审计系统。
> 本文档基于对现有 skill (V3.0) 与其真实运行数据 (`audit_plan.json`) 的诊断而来。

---

## 0. 设计决策(已拍板)

| 决策项 | 选择 | 影响 |
|---|---|---|
| 验证层循环控制 | **Workflow 强制遍历** | 循环写在 JS,模型无法提前收工 |
| 使用场景 | **两者都要 → 三桶输出** | 非对称阈值,确认/待人工/已排除 |
| 运行环境 | **兼容 Claude Code CLI 与 Antigravity CLI (agy)** | 复用 Skill/Workflow/Agent, 共享一致的运行机制与 API |
| 语义检索 | **实测已完成 → 确认需补向量层**(见 §9) | CodeGraph 两条通道均为词法匹配,无语义定位能力 |

---

## 1. 现状诊断(为什么要 V4.0)

现有 V3.0 skill 的真实运行数据暴露了**一个致命洞**:

```
explored(已定位CWE任务):      377
verdict:pending(待验证候选):  1441   ← 躺着没验
verdict:verified(确认漏洞):      4
verdict:false_positive(误报):   11
                          验证覆盖率 ≈ 1%
```

**根因**:V3.0 的 Step 1–6 是确定性 Python 脚本(健壮),但 **Step 7 验证层退回了"模型 + 人肉分批(每批7个,手动复制'继续验证下7个')"**。1441 个候选需人肉点击 200+ 次,现实中卡死在 1%。

**结论**:V4.0 唯一的架构级改动 = **把 Step 7 换成 Workflow 强制编排**。其余脚本保留、微调。

---

## 2. 系统四层架构

```
┌─ L4 编排层 (Workflow)  ★V4.0 新增,核心 ─────────────────┐
│  强制遍历全部 pending 候选 → 对抗性多票验证 → 三桶归类     │
└──────────────────────────────────────────────────────┘
              ↑ 由 Skill 触发,读写 audit_plan.json
┌─ L3 方法论层 (Skill)  ─────────────────────────────────┐
│  fuzzy-semantic-audit:定义流程、触发条件、验证方法论      │
└──────────────────────────────────────────────────────┘
              ↑ 调用
┌─ L2 数据/脚本层 (Python,确定性)  ──────────────────────┐
│  CWE解析 / 技术栈裁剪 / 定位导出 / verdict回写 / 报告      │
└──────────────────────────────────────────────────────┘
              ↑ 调用
┌─ L1 能力层 (MCP + 索引)  ──────────────────────────────┐
│  CodeGraph(调用图/符号)  +  向量语义检索(★新增)          │
└──────────────────────────────────────────────────────┘
```

**分工铁律**:
- **确定性的事(遍历、去重、裁剪、回写)→ 代码 (L2/L4 脚本)**
- **需要理解判断的事(是不是漏洞、能否触发)→ agent (L4 内调用)**
- V3.0 的病根就是把"遍历"这件确定性的事交给了模型。

---

## 3. 各层详细设计

### L1 能力层

**3.1 CodeGraph(已验证可用)**
提供:`query`(符号搜索)、`explore`(符号源码+调用路径)、`node`(单符号+caller/callee)、`callers`/`callees`(可达性反查)、`impact`。
- 定位阶段:找候选函数
- **验证阶段(关键)**:裁判用 `callers` 反查"这个 sink 上游是否经过 auth/校验"、"入口是否外部可达" —— 这是砍假阳性的核心证据来源。

**3.2 向量语义检索(★新增)**
问题:`explorer.py` 现用 `codegraph query` 是**符号名匹配**,而 skill 让 AI 生成的是**自然语言语义 intent**(如 "validate permission before access")—— 二者错配,导致定位召回率存疑。
方案:新增一层 embedding 检索(如 tree-sitter 切函数 → 本地 embedding 模型 → 向量库),`explorer.py` 对每个 intent **双路召回**:
- 符号路:`codegraph query`(精确命中函数名)
- 语义路:向量检索(命中"语义像"的函数)
- 合并去重后作为候选。

> ⚠️ 落地前先做**实测**:抽样几个真实 intent,对比符号路 vs 语义路的命中差异,用数据决定向量层的投入规模。若符号路已够,可延后此项。

### L2 数据/脚本层(现有,保留+微调)

| 脚本 | 职责 | V4.0 改动 |
|---|---|---|
| `cwe_parser.py` | 解析 699.xml → catalog | 保留 |
| `audit_orchestrator.py init` | 技术栈预扫描 + CWE裁剪 + 建 plan | 保留(裁剪逻辑见 §5.1) |
| `generate_ai_intents.py` | 合并 AI 生成的 intent/prompt | 保留 |
| `explorer.py` | CodeGraph 定位候选 | **加双路召回**(见 3.2) |
| `trifecta_verifier.py export` | 剪枝导出候选包 | 保留 |
| `trifecta_verifier.py update` | **回写 verdict** | **改:见 §4.3 三桶** |
| `audit_orchestrator.py report` | 出 Markdown 报告 | **改:见 §4.3 三桶** |

### L3 方法论层 (Skill)

改动:
- **删除** V3.0 的"交互式分批验证协议(每批7个,人肉续批)" —— 这是病根。
- Step 7 改为:**触发 Workflow**(见 L4)。Skill 只负责"当用户说审计 X → 依次跑 L2 脚本 → 到验证阶段拉起 Workflow"。
- 保留 Trifecta / 污点 / 攻击面 三种方法论描述,作为**注入给验证 agent 的 prompt**。

### L4 编排层 (Workflow) ★核心

见 §4。

---

## 4. 验证编排设计(V4.0 核心)

### 4.1 输入 / 输出
- **输入**:`audit_plan.json` 中所有 `verdict == "pending"` 的候选(当前 1441 个)。
- **输出**:每个候选被归入三桶之一,verdict 回写 plan,报告重新生成。

### 4.2 流程(Workflow 脚本逻辑)

```
1. 读 audit_plan.json,抽取全部 pending 候选
2. 去重(barrier):按 (file:function:cwe_id) 合并重复候选   ← 省成本,必须在验证前
3. pipeline 强制遍历每个去重后的候选:
     stage A —— 上下文补全:
        用 CodeGraph callers/explore 补全 source→sink 调用链、
        上游校验/auth、入口可达性(喂给裁判的证据)
     stage B —— 对抗性多票验证:
        parallel 派 3 个独立 agent,各持不同视角、默认"证伪"立场:
          裁判1: 路径可达性 (Path Reachability)
          裁判2: 守卫有效性 (Guard Validity / 净化是否可绕过)
          裁判3: 能否真实触发 (Control-Flow Exploitability + 攻击路径)
        每个裁判输出结构化 VERDICT(见 4.4)
4. 汇总投票 → 三桶归类(见 4.3)
5. 逐条调 trifecta_verifier.py update 回写 verdict
6. 调 audit_orchestrator.py report 出报告
```

**关键设计点(对应前面讨论的 13 条 checklist)**:
- 循环在 JS(`pipeline`),模型无法提前收工 → 解决 1% 覆盖率
- 裁判 `parallel` 独立,互不见判断 → 不串供
- 三视角差异化 → 投票有信息增益
- 默认证伪立场 → 砍假阳性
- 每个 agent 失败返回 null,`.filter(Boolean)` → 单点失败不毁全批
- `budget` 硬上限 → token 不失控
- 去重在验证前(barrier)→ 不重复烧钱

### 4.3 三桶归类 + 非对称阈值(场景=两者都要)

3 个裁判投票,**非对称阈值(偏向不漏报)**:

| 桶 | 判定规则 | 去向 |
|---|---|---|
| ✅ **确认 (verified)** | ≥2 票认为真 **且** 至少一票给出可复现攻击路径 | 报告主体 |
| ⚠️ **待人工 (needs_review)** | 恰好 1 票认为真 / 投票分歧 / 有 `missingEvidence` | 报告人工复核区 |
| ❌ **已排除 (false_positive)** | 3 票均证伪 **且** 给出排除理由 | 报告附录(证明查过了) |

> ⚠️ 需扩展 `trifecta_verifier.py`:现在只支持 `verified | false_positive` 两值,V4.0 需加 **`needs_review`** 第三值。同理 `report` 需渲染三桶。

### 4.4 验证结构化输出 schema

```json
{
  "isReal": true,
  "confidence": "high | medium | low",
  "lens": "reachability | guard | exploitability",
  "reason": "为什么真/假的推理",
  "attackPath": "如果真:从外部入口到触发点的可复现步骤",
  "missingEvidence": "如果不确定:还差什么信息才能定论"
}
```
- `attackPath` 是强过滤器:给不出攻击路径的"漏洞"基本是假阳性。
- `missingEvidence` 非空 → 进"待人工"桶,而非误判为已排除。

---

## 5. 成本控制

### 5.1 横向:候选裁剪(定位阶段,已有+强化)
- `audit_orchestrator.py` 已按技术栈预扫描裁剪 CWE(保留)。
- **强化**:去重后再验证。1441 个原始候选去重后预计大幅缩减。

### 5.2 纵向:上下文最小化(验证阶段)
- 裁判**只拿 sink 周边调用链**(靠 CodeGraph 定点补全),不吞整个子系统源码 —— 这是省 token 的主杠杆。

### 5.3 闸门:budget + 试点
- **强制先试点**:全量前先跑 **20 个 pending 候选**验证质量与单位成本,外推总成本,再决定全量。
- Workflow `budget` 设硬上限,烧到阈值自动停并**如实记录未验证的部分**(不静默截断)。

**粗算**:去重后 N 个候选 × 3 裁判 = 3N agent 调用。1441 未去重时 ≈ 4300+ 次,成本高 → 故 §5.1 去重 + §5.3 试点是必须的闸门。

---

## 6. 已知风险与诚实边界

| 风险 | 处理 |
|---|---|
| 向量层可能收益不明 | 先实测符号路 vs 语义路命中差异,数据驱动决定 |
| 逻辑漏洞无法靠 CWE 表穷举 | 留一个"自由探索"探针项兜底,不假装表能覆盖全部 |
| 全量验证成本高 | 去重 + 试点 + budget 三重闸门 |
| 裁判在信息不全时瞎猜 | stage A 强制补全调用链上下文后再交裁判 |
| 报告被误读为"全查过了" | 三桶都进报告 + 显式记录 budget 截断/未跑项 |

---

## 7. 落地改动清单(相对 V3.0)

**P0 — 信噪比命门(§10 实测:候选池 32% 是噪声,必须先修)**
1. **[改·P0]** `trifecta_verifier.py export` 剪枝 —— **加目录过滤**,砍掉 monitor/tools/client/unit/emulator 等非攻击面(§10 实测占 32%)。
2. **[改·P0]** `explorer.py` —— 双路召回:**向量路做语义定位** + **CodeGraph 路做调用链补全**;定位质量是信噪比根源,优先级高于验证层。
3. **[新增·P0·必需]** 向量语义检索层 —— **§9 实测确认必需**(CodeGraph 无语义定位)。
4. **[新增·P0·修复]** Step 4 intent 生成 —— 现退化为关键词,须真正产出语义 intent(否则向量检索 garbage in garbage out)。

**P1 — 验证层(§10 实测:Workflow 强制遍历已验证通过)**
5. **[新增·P1]** `verify_workflow` —— L4 Workflow 脚本(§4 核心)。**8/8 强制遍历实测通过**。
6. **[改·P1]** `trifecta_verifier.py` —— 支持 `needs_review` 第三 verdict。
7. **[改·P1]** `audit_orchestrator.py report` —— 渲染三桶报告。
8. **[改·P1]** 验证裁判证据源 —— 用 `codegraph node`(源码+trail)+ **文件路径粗可达性分流**,不依赖 `callers`(§10 实测其常只到"文件:1"级)。
9. **[改·P1]** `SKILL.md` —— 删人肉分批协议,Step 7 改为拉起 Workflow。

**P2 — 成本闸门(§10 实测:全量盲跑 ≈ 8600万 token,必须设闸)**
10. **[闸门·P2]** 候选去重(按 file:function:cwe)+ 目录过滤后再验证。
11. **[闸门·P2]** 20 候选试点校准单位成本,外推后再决定全量。

**不动**:`cwe_parser.py`、CWE 裁剪主逻辑。

---

## 8. 端到端数据流

```
699.xml
  │ cwe_parser.py
  ▼
cwe_699_catalog.json
  │ audit_orchestrator.py init (技术栈裁剪)
  ▼
audit_plan.json (tasks, 空候选)
  │ generate_ai_intents.py (AI填intent/prompt)
  │ explorer.py (CodeGraph双路召回定位)
  ▼
audit_plan.json (含 pending 候选)
  │ trifecta_verifier.py export (剪枝)
  ▼
pending_cands/*.json
  │ ★ verify_workflow (强制遍历+对抗验证+三桶)   ← V4.0 核心
  │ trifecta_verifier.py update (回写三桶 verdict)
  ▼
audit_plan.json (含 verified/needs_review/false_positive)
  │ audit_orchestrator.py report (三桶报告)
  ▼
audit_report.md
```

---

## 9. 实测结论:语义检索通道(2026-07-01)

**实验**:重建 bluez-5.86 索引(16,975 函数 / 706 C 文件),取真实 CWE(416 UAF / 190 溢出 / 476 空指针 等),各造"退化关键词"与"真语义"两种 intent,分别走 `codegraph query` 与 `codegraph explore` 对比命中质量。

**发现**:

| 通道 | 性质 | 铁证 |
|---|---|---|
| `codegraph query` | **纯词法词袋匹配**,无语义 | `double free` → 命中 `ecc_point_double_jacobian`(椭圆曲线数学函数) |
| `codegraph explore` | **词法匹配 + 调用图增强**,内核仍是词法 | 同样把 `double free` 命中到 `ecc_point_double_jacobian` |

**三条硬结论**:
1. CodeGraph 两条通道都**做不了语义定位**,都被字面词(free/double/null/check)带偏 → **必须补向量语义检索层**。
2. **CodeGraph 的正确定位是"调用链/可达性分析"**(explore 的 blast radius、callers),而非语义定位。据此修正分工:
   - 定位阶段 = **向量检索**(语义找候选)
   - 上下文阶段 = **CodeGraph**(调用图补全,喂验证裁判)
3. 叠加问题:现有 `query_intents` 已退化为"CWE名删虚词"的关键词(Step 4 未生效),376 任务全走了 `explorer.py` 的关键词兜底。**即便上向量层,仍须修 Step 4**,否则 garbage in garbage out。

---

## 10. 可行性验证:5 个核心假设(2026-07-01)

对设计的 5 个立身假设逐个实测,判定如下:

| 假设 | 判定 | 证据 | 替代方案 |
|---|---|---|---|
| **A. 需向量层做语义定位** | ✅ 成立 | 见 §9 | 已定:补向量层 |
| **B. Workflow 强制遍历,模型无法提前收工** | ✅ **成立** | 最小 workflow:8 候选 **8/8 全覆盖,零遗漏**(对照 V3.0 的 15/1441) | 无需替代,核心可行 |
| **C. CodeGraph 给裁判可达性证据** | ⚠️ **部分成立** | `node` 能给源码+caller/callee trail;但 `callers` 对多数函数只到"文件:1"级,函数级链不完整 | `node`+文件路径粗可达性分流,不依赖 `callers` |
| **D. 成本可控** | ⚠️ **需闸门** | 实测 8 agent = 15.7万 token → 外推 1456候选×3裁判 ≈ 4368 agent ≈ **8600万 token** | 目录过滤+去重+试点三闸门,从"建议"升为"必须" |
| **E. 候选质量** | 🔴 **不达标** | 1456 候选中 monitor(239)/tools(136)/client(128)/unit(56)/emulator(34) ≈ **32% 是非攻击面工具/测试代码** | `export` 剪枝加目录过滤 |

**两处必须在落地前修(否则翻车)**:
1. **候选质量(定位+剪枝)** —— 加目录过滤,这是信噪比命门。验证层再好也架不住候选池 1/3 是噪声 → 定位/剪枝优先级提到验证层之前(见 §7 P0)。
2. **成本闸门(去重+试点)** —— 按真实 token 标尺,全量盲跑 ≈ 8600万 token,不可接受 → 三闸门必须先行(见 §7 P2)。

**总体结论**:设计骨架成立,核心机制(Workflow 强制遍历)实测通过;假设 C 有可靠降级方案不阻塞;E 与 D 逼出的修正已并入 §7 落地清单并重排为 P0/P1/P2。

---

## 11. V1 向量层验证(2026-07-01)

**环境约束(已确认)**:本地、代码不出本机、Python 3.14、无 GPU、13G 内存 → 走 fastembed/ONNX(不引 torch)。

**可行性**:`fastembed 0.8.0` 在 py3.14 原生 wheel 装成功(onnxruntime cp314),`bge-small`(384维)对 574 函数秒级编码。**本地方案可行**,全量 16,975 函数预计分钟级建索引。

**检索质量(bge-small 基线,对照 §9 词法反例)**:
| intent | 向量 top 命中 | 判定 |
|---|---|---|
| `double free` | bt_att_free / device_free / bt_att_chan_free(**全是释放函数**) | ✅ 优于词法(词法命中椭圆曲线函数) |
| `integer overflow` | vli_mmod_fast / vli_clear(**大整数运算,跑偏**) | ⚠️ 懂字面语义,不懂漏洞语境 |

**两条硬结论**:
1. ✅ 向量检索确实优于词法(解决"撞词"),但相似度挤在 0.66–0.72,**区分度低**。
2. ⚠️ 向量也不够:懂字面语义,不懂"漏洞语境"(integer overflow→密码学定长运算)。

**据此定位修正(重要)**:**向量层是"召回层"不是"定位层"** —— 任务是"574→缩到 top-N 语义相关候选,别漏",不是"精确指出漏洞"。精确判断交验证层 agent。这与"检索找候选、agent 做判断"的分工一致,V1 用数据确认了不能对向量层期望过高。

**embedding 选型(实测对比 3 模型,574 函数 · 4 intent)**:

| 指标 | bge-small(384) | jina-code(768) | bge-base(768) |
|---|---|---|---|
| double_free 漏洞相关 | 4/5 | 4/5 | 2/5 |
| int_overflow 数学噪声(越低越好) | 5/5 | 4/5 | 2/5 |
| 区分度均值(越高越好) | 0.020 | **0.038** | 0.016 |
| 体积/算力 | 最轻 | 大 | 大 |

**结论:三模型同一水平线,代码专用的 jina-code 并未明显更准**(double_free 打平、null_deref 反而更差),仅区分度略高。`int_overflow` 三者全跑偏(数学噪声 5/4/2)→ **再次印证是"检索手段的天花板",非模型精度问题,换 embedding 治不好**。

**定型**:
- **默认 `bge-small-en-v1.5`** —— 最轻、已验证可跑、命中不输、零新增风险。
- **`jina-code` 列为大项目可选升级** —— 区分度更高,但需重调阈值、体积更大。

**关键判断**:embedding 已够用,不再优化;精度瓶颈在**验证层 agent**,不在这里差 0.02 的区分度。精力应转向召回层设计(top-N 阈值、去重)与验证层。

---

## 12. V3 对抗验证判定质量(2026-07-01)

**实验**:构造标准答案样本,跑三视角对抗裁判(默认证伪立场)+ 非对称阈值三桶归类。
- 正样本 `sdp_extract_pdu`(解析不可信 SDP 字节流,attrlen 未校验即用于指针推进)→ 预期 确认/待人工
- 负样本 `numeric_comparison_failed`(空函数)、`vli_add`(定长数学运算)→ 预期 已排除

**结果:3/3 归桶全对**。

| 样本 | 三视角投票(可达/守卫/触发) | 归桶 | 判定 |
|---|---|---|---|
| `sdp_extract_pdu`(正) | 真 / 假 / 假 | needs_review | ✅ |
| `numeric_comparison_failed`(空) | 假 / 假 / 假(全 high) | false_positive | ✅ |
| `vli_add`(数学) | 假 / 假 / 假(全 high) | false_positive | ✅ |

**三条结论(比 3/3 数字更重要)**:
1. ✅ **对抗验证能可靠砍假阳性** —— 两负样本 3 视角全假、high 置信,空函数/定长数学未蒙混。
2. ✅ **非对称阈值是正样本的救命阀** —— 正样本仅 1真2假,靠"1票真即进 needs_review"才没漏报。**若用对称多数票就会误杀** → 阈值方向经实测钉死,不可改。
3. ⚠️ **单裁判会误杀真漏洞** —— 正样本 2/3 裁判证伪它(因给不出现成 PoC)。"无攻击路径即证伪"这个强过滤器砍假阳性有效,但对"真但难构造 PoC"的漏洞是双刃剑 → **必须靠多视角+宽阈值+needs_review 兜底**,缺一不可。

**成本标尺更新**:9 agent = 22.2万 token,**单样本3视角 ≈ 7.4万 token**(含真实审计推理,tool_uses 62)。高于 §10 的粗估(单候选3裁判)→ **§7 P2 成本闸门更须严格**:1456 候选去重/过滤后按 7.4万/候选 外推,试点校准不可省。