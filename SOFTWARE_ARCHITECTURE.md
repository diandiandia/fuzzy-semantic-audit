# Fuzzy Semantic Audit —— 软件架构设计 (V4.0)

> 承接 `SYSTEM_DESIGN.md`(做什么/为什么/可行性)。本文档回答**怎么组织代码实现**:
> 模块边界、接口契约、数据结构、目录结构、依赖关系、状态管理、错误处理。
> 所有 schema/接口基于对现有 5 个脚本与真实 `audit_plan.json` 的核实,非臆想。

---

## 0. 设计原则(承接系统设计的分工铁律)

1. **确定性交代码,判断交 agent** —— 遍历/去重/裁剪/IO/回写是 Python;是不是漏洞是 agent。
2. **检索是召回,agent 是判断**(V1 实测)—— 向量层只负责"缩范围别漏",精度靠验证层。
3. **单一数据真相源** —— `audit_plan.json` 是全流程唯一状态载体,所有模块读写它。
4. **模块间用文件/JSON 契约解耦** —— Python 脚本与 Workflow 通过 plan 文件交接,不共享内存。
5. **经验证的既有逻辑予以移植,不重造** —— 标注 [移植] 的是实测跑通的资产(技术栈预扫描、剪枝启发式、CWE解析)。

---

## 1. 模块总览与依赖关系

```
                         ┌─────────────────────────┐
                         │   audit_plan.json        │  ← 单一数据真相源
                         │   (全流程状态载体)        │
                         └─────────────────────────┘
        写↑        读↑写         读↑写        读↑写        读↑
   ┌────────┐ ┌──────────┐ ┌──────────┐ ┌──────────┐ ┌────────┐
   │ M1 CWE │ │ M2 索引/  │ │ M3 定位  │ │ M4 验证  │ │ M5 报告│
   │  数据  │ │  检索层  │ │  召回    │ │  编排    │ │        │
   └────────┘ └──────────┘ └──────────┘ └──────────┘ └────────┘
       │           │            │            │           │
    [移植]      ★新增        [移植+改]   ★新增Workflow  [改:三桶]
   Python      Python(venv)   Python      JS+Python     Python
```

**依赖方向(严格单向,无环)**:
- M1 → 产出 catalog,喂 M3 建 plan
- M2(索引/检索)→ 被 M3(定位)和 M4(验证)调用,自身不依赖别人
- M3 → 消费 M1 catalog + M2 检索,产出 pending 候选
- M4 → 消费 M3 候选 + M2 调用链,产出三桶 verdict
- M5 → 只读 plan,产出报告

**关键解耦**:M4(Workflow,JS)与其余(Python)**只通过 `audit_plan.json` 和候选包 JSON 交接**,不直接调用彼此代码。

---

## 2. 模块详细设计

### M1 — CWE 数据模块 [移植]
- **职责**:解析 CWE-699 XML → 按语言裁剪 → 结构化 catalog。
- **来源**:`cwe_parser.py`(已验证)。逻辑移植,接口不变。
- **输入**:`699.xml` + `--lang`
- **输出**:`cwe_catalog.json`(dict: cwe_id → {id,name,description,extended_description,consequences,languages})
- **不变式**:catalog 只含目标语言适用的 CWE。

### M2 — 索引 / 检索层 ★新增(P0 核心)
系统设计 §9/§11 实测确定的**双通道**,本模块是新增重点。

**M2a 向量语义检索(召回)**
- **技术栈**:fastembed(ONNX)+ bge-small-en-v1.5(默认)/ jina-code(可选),隔离在 `.venv-embed`。
- **职责**:
  1. `build_index(project)` —— tree-sitter/codegraph 切函数 → embed → 存本地向量索引
  2. `search(intent, top_k)` —— 语义召回 top-k 候选函数
- **索引存储**:`<project>/.audit_temp/vec_index/`(向量 + 函数元数据)
- **接口契约**:
  ```
  search(intent: str, top_k: int) -> List[{name, file, line, score}]
  ```
- **定位(V1 铁律)**:只做召回,top_k 宽松(如 30),宁多勿漏,精度交 M4。

**M2b CodeGraph 调用链(上下文)**
- **技术栈**:codegraph CLI 封装
- **职责**:给 M4 裁判提供可达性证据(系统设计 §10 假设C)
- **接口契约**:
  ```
  get_source(symbol) -> str                    # node 命令,函数源码+trail
  get_callers(symbol) -> List[str]             # 可达性(降级:见下)
  get_callees(symbol) -> List[str]             # ★P1:下游被调,看数据交给了谁
  explore(query) -> str                        # ★P1:相关符号源码+调用路径
  build_call_chain_context(symbol) -> str      # ★P1:上游callers+下游callees 拼成调用链切片
  reachability_hint(file) -> str               # ★文件路径粗可达性分流(§10 降级方案)
  ```
- **降级(§10 实测)**:`callers` 不可靠 → 主用 `get_source` 的 trail + `reachability_hint`(src/=高可达,monitor|tools|unit=低)。
- **★P1 调用链切片(系统设计 §13.2)**:逻辑漏洞(越权/状态机/信任边界)是跨函数的,`build_call_chain_context` 把上游 callers(谁能到达/是否校验)+ 下游 callees(是否敏感 sink)拼成切片,写入候选包 `call_chain_context` 字段,供 M4 裁判做跨函数推理。

### M3 — 定位召回模块 [移植+改]
- **职责**:对每个 CWE 任务,用 intent 召回候选函数,补上下文,剪枝,写入 plan。
- **来源**:`explorer.py` + `audit_orchestrator.py init` + `trifecta_verifier.py export`
- **改动(系统设计 §7 P0)**:
  1. **双路召回**:M2a 向量(语义)+ M2b codegraph(精确符号),合并去重。
  2. **目录过滤剪枝**:在 `is_boilerplate_or_test` 基础上**加目录黑名单**(monitor/tools/client/unit/emulator)—— 砍 §10 实测的 32% 噪声。
  3. **技术栈预扫描裁剪**:[移植] 逻辑不变,规则外置到 `resources/prescan_rules.json`(P0)。
  4. **★第三路资源访问召回(P2-a,系统设计 §13.3)**:仅对逻辑漏洞类 CWE(`LOGIC_FLAW_CWES`)开启,用资源访问信号词把"按传入标识访问资源"的函数灌进候选池(`recall_source="resource"`),补"缺失校验"型越权。带 `limit` 确定性闸门。⚠️ 词法级,待真实数据验证。
- **输入**:catalog + intents(见 M6)+ project
- **输出**:plan 的 `result_candidates`(pending 候选)+ 剪枝后的候选包
- **★P1 候选包扩展**:每个候选带 `call_chain_context`(调 M2b),裁判 instructions 增加逻辑漏洞视角(缺失授权/IDOR、状态机绕过、TOCTOU、信任边界)。

### M4 — 验证编排模块 ★新增(P1 核心,Workflow)
系统设计 §4 + §12 实测确定。

- **技术栈**: Claude Code / Antigravity Workflow (JS) + `trifecta_verifier.py update` (Python 回写)
- **职责**:强制遍历全部 pending 候选 → 三视角对抗验证 → 三桶归类 → 回写。
- **流程**(§4):
  ```
  读 pending → 去重(barrier, file:function:cwe) → pipeline 每候选:
    stageA  上下文补全(调 M2b)
    stageB1 安全等级过滤(单 Agent 评估 1-10，<5 直接判定为 false_positive 并跳过验证)
    stageB2 parallel 三视角裁判(仅对 severity >= 5，默认证伪)：
             ├ 裁判1 可达性 + 信任边界混淆
             ├ 裁判2 守卫有效性 + 缺失授权(BOLA/IDOR，须在 THIS PATH 上有校验)
             └ 裁判3 可触发性 + 状态机绕过 + TOCTOU/竞态
            三视角均读候选包的 call_chain_context 做跨函数推理(★P1)
  → 非对称阈值三桶归类 → 调 M4-Python 回写 verdict
  ```
- **三桶阈值(§12 实测钉死,不可改为多数票)**:
  - `verified`:≥2票真 且 有可复现 attackPath
  - `needs_review`:1票真 / 分歧 / 有 missingEvidence
  - `false_positive`:全票证伪
- **成本闸门(§7 P2)**:去重+目录过滤后再跑;budget 硬上限;先 20 候选试点。

### M5 — 报告模块 [改:三桶]
- **职责**:读 plan → 渲染三桶 Markdown 报告。
- **来源**:`m5_report/reporter.py`(三桶实现的唯一落点;`audit_orchestrator.py report` 仅作兼容入口,直接委托 `reporter.compile_report`,不再自带过时的两桶实现)。
- **改动**:三桶都渲染(确认主体 / 待人工区 / 已排除附录)+ 记录 budget 截断/未跑项(§7 诚实边界);代码块标签随 `target_language` 动态化(`lang_utils.markdown_tag`,不再硬编码 cpp)。

### M6 — intent 生成 [改:修复]
- **职责**:为每个 CWE 任务生成**真语义** query_intents + vulnerability_prompt。
- **来源**:`generate_ai_intents.py`(仅做合并,不生成)
- **改动(系统设计 §7 P0)**:现 intent 退化为关键词(§9 实测)→ 必须真正由 AI 产出语义 intent 供 M2a 向量检索。合并逻辑 [移植] 不变,**生成环节**是新增修复。

---

## 3. 核心数据结构(基于真实 audit_plan.json 核实)

### 3.1 audit_plan.json(单一真相源)
```jsonc
{
  "project_path": "/home/zjamg/bluez-5.86",
  "target_language": "cpp",
  "status": "initialized|exploring|explored|verifying|verified",
  "tasks": [
    {
      "id": "task-cwe-416",
      "cwe_id": "416",
      "cwe_name": "Use After Free",
      "description": "...",
      "query_intents": ["free memory then use pointer", ...],  // M6 填,真语义
      "vulnerability_prompt": "...",                            // M6 填
      "status": "pending|explored",
      "result_candidates": [ /* 见 3.2 */ ]
    }
  ]
}
```

### 3.2 候选对象(result_candidates 元素)
```jsonc
{
  "id": "cand-416-1",
  "function": "sdp_extract_pdu",
  "file": "lib/bluetooth/sdp.c",
  "code_snippet": "...",
  "struct_definitions": "...",
  "call_chain_context": "...",              // ★P1:上游callers+下游callees切片,供逻辑漏洞(越权/状态机/信任边界)跨函数推理
  "entrypoint": "调用者或 reachability_hint",
  "verdict": "pending|verified|needs_review|false_positive",  // ★新增 needs_review
  "triage_explanation": "",
  "recall_source": "vector|symbol|both|resource",   // ★双路召回来源;resource=P2-a 资源访问召回(逻辑漏洞补召回)
  "votes": [ /* ★新增:三视角投票留痕,可溯源 */ ]
}
```

### 3.3 验证裁判输出 schema(M4 stageB,§12 实测过)
```jsonc
{ "isReal": bool, "confidence": "high|medium|low",
  "lens": "reachability|guard|exploit",
  "reason": str, "attackPath": str /* 无则填"无" */ }
```

### 3.4 安全评级输出 schema (M4 stageB1, 新增)
```jsonc
{ "severity": number /* 1-10 整数 */,
  "reason": str /* 简短的评分依据说明 */ }
```

---

## 4. 目录结构

```
fuzzy-semantic-audit/
├── SKILL.md                      # L3 方法论,Step→拉 Workflow(含 venv/多语言指引)
├── SYSTEM_DESIGN.md              # 系统设计(§13 记录 P0/P1/P2-a 通用化改造)
├── SOFTWARE_ARCHITECTURE.md      # 本文档
├── .venv-embed/                  # M2a 隔离环境(fastembed,不污染系统py)
├── resources/
│   ├── 699.xml
│   ├── cwe_699_catalog.json      # M1 产出
│   ├── prescan_rules.json        # ★P0:外置技术栈预扫描规则
│   └── audit_plan.json           # 单一真相源
├── src/
│   ├── common/                   # plan_manager(读写)+ ★lang_utils(P0 语言映射)
│   ├── m1_cwe/                   # cwe_parser:CWE解析裁剪
│   ├── m2_index/                 # vector_index(向量) + codegraph_wrapper(★P1 调用链切片)
│   ├── m3_locate/                # explorer(★三路召回)+ intent_generator + audit_orchestrator
│   ├── m4_verify/                # trifecta_verifier:verdict 回写 CLI
│   └── m5_report/                # reporter:三桶报告(★动态语言标签)
└── workflows/
    ├── generate_intents_workflow.js  # M6 语义 intent 生成(JS)
    └── verify_workflow.js            # M4 编排:三视角对抗验证(JS,★逻辑漏洞视角)
```

---

## 5. 状态管理与健壮性

| 关注点 | 方案 |
|---|---|
| **断点续跑** | verdict=pending 即"未验证",Workflow 每次只捞 pending → 天然幂等续跑 |
| **并发写 plan** | M4 的 Python 回写(update)按 candidate_id 单条更新;Workflow 内串行回写,避免并发写冲突 |
| **单 agent 失败** | Workflow `.filter(Boolean)`,单裁判死不毁全批(§10) |
| **成本失控** | budget 硬上限 + 20候选试点 + 去重/过滤前置(§7 P2) |
| **索引失效** | M2 build 前检查 codegraph status,失效则重建(移植 explorer 的 check 逻辑) |
| **诚实边界** | 报告显式标注:budget 截断数、未跑 CWE、needs_review 数(§7) |

---

## 6. 实现顺序(承接系统设计 §7 的 P0/P1/P2)

**P0 — 信噪比地基**(先修,否则候选池 1/3 噪声)
1. M2a 向量检索层(build_index + search)—— 最核心新增
2. M3 目录过滤剪枝 —— 小改动见效快,可先行
3. M6 intent 真语义生成 —— 修复 §9 退化
4. M3 双路召回接入 M2

**P1 — 验证层**(机制已验证,填实现)
5. common/ plan读写+schema+needs_review 支持
6. M4 verify_workflow.js
7. M5 三桶报告

**P2 — 成本闸门**
8. 去重 + budget + 20候选试点校准

---

## 7. 已定架构决策

1. **函数切分粒度**:**整函数 embed**。理由:函数是最自然的语义单元,V1 实测(函数名+前8行)已能召回;实现时若召回不佳再引入"函数+周边"作为调优项。
2. **向量索引持久化**:**numpy `.npy`(向量)+ json(函数元数据)**,零新依赖。16,975 函数 × 384 维 float32 ≈ 26MB,内存可全量载入余量充足(13G);不引 sqlite/向量库,避免 py3.14 兼容风险。
3. **legacy 脚本**:**已被完全重构和迁移/清理**。有用的初始化逻辑已作为模块移植至 `src/m3_locate/audit_orchestrator.py`，无用脚本已删除。

> 三项均从"待确认"定案。软件架构设计完备,可进入 §6 的 P0 实现。
