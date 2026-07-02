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
  get_source(symbol) -> str            # node 命令,函数源码+trail
  get_callers(symbol) -> List[str]     # 可达性(降级:见下)
  reachability_hint(file) -> str       # ★文件路径粗可达性分流(§10 降级方案)
  ```
- **降级(§10 实测)**:`callers` 不可靠 → 主用 `get_source` 的 trail + `reachability_hint`(src/=高可达,monitor|tools|unit=低)。

### M3 — 定位召回模块 [移植+改]
- **职责**:对每个 CWE 任务,用 intent 召回候选函数,补上下文,剪枝,写入 plan。
- **来源**:`explorer.py` + `audit_orchestrator.py init` + `trifecta_verifier.py export`
- **改动(系统设计 §7 P0)**:
  1. **双路召回**:M2a 向量(语义)+ M2b codegraph(精确符号),合并去重。
  2. **目录过滤剪枝**:在 `is_boilerplate_or_test` 基础上**加目录黑名单**(monitor/tools/client/unit/emulator)—— 砍 §10 实测的 32% 噪声。
  3. **技术栈预扫描裁剪** [移植 audit_orchestrator 的 PRE_SCAN_KEYWORDS,不变]。
- **输入**:catalog + intents(见 M6)+ project
- **输出**:plan 的 `result_candidates`(pending 候选)+ 剪枝后的候选包

### M4 — 验证编排模块 ★新增(P1 核心,Workflow)
系统设计 §4 + §12 实测确定。

- **技术栈**: Claude Code / Antigravity Workflow (JS) + `trifecta_verifier.py update` (Python 回写)
- **职责**:强制遍历全部 pending 候选 → 三视角对抗验证 → 三桶归类 → 回写。
- **流程**(§4):
  ```
  读 pending → 去重(barrier, file:function:cwe) → pipeline 每候选:
    stageA 上下文补全(调 M2b)
    stageB parallel 三视角裁判(可达/守卫/触发,默认证伪)
  → 非对称阈值三桶归类 → 调 M4-Python 回写 verdict
  ```
- **三桶阈值(§12 实测钉死,不可改为多数票)**:
  - `verified`:≥2票真 且 有可复现 attackPath
  - `needs_review`:1票真 / 分歧 / 有 missingEvidence
  - `false_positive`:全票证伪
- **成本闸门(§7 P2)**:去重+目录过滤后再跑;budget 硬上限;先 20 候选试点。

### M5 — 报告模块 [改:三桶]
- **职责**:读 plan → 渲染三桶 Markdown 报告。
- **来源**:`audit_orchestrator.py report`
- **改动**:现只渲染 verified → 改为**三桶都渲染**(确认主体 / 待人工区 / 已排除附录)+ 记录 budget 截断/未跑项(§7 诚实边界)。

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
  "entrypoint": "调用者或 reachability_hint",
  "verdict": "pending|verified|needs_review|false_positive",  // ★新增 needs_review
  "triage_explanation": "",
  "recall_source": "vector|symbol|both",   // ★新增:双路召回来源
  "votes": [ /* ★新增:三视角投票留痕,可溯源 */ ]
}
```

### 3.3 验证裁判输出 schema(M4 stageB,§12 实测过)
```jsonc
{ "isReal": bool, "confidence": "high|medium|low",
  "lens": "reachability|guard|exploit",
  "reason": str, "attackPath": str /* 无则填"无" */ }
```

---

## 4. 目录结构

```
fuzzy-semantic-audit/
├── SKILL.md                      # L3 方法论,删人肉分批,Step7→拉Workflow
├── SYSTEM_DESIGN.md              # 系统设计(已完成)
├── SOFTWARE_ARCHITECTURE.md      # 本文档
├── .venv-embed/                  # M2a 隔离环境(fastembed,不污染系统py)
├── resources/
│   ├── 699.xml
│   ├── cwe_catalog.json          # M1 产出
│   └── audit_plan.json           # 单一真相源
├── src/                          # ★重构后模块(旧scripts参考移植)
│   ├── m1_cwe/                   # CWE解析裁剪
│   ├── m2_index/                 # 向量检索 + codegraph封装
│   ├── m3_locate/                # 双路召回+剪枝
│   ├── m5_report/                # 三桶报告
│   └── common/                   # plan读写、schema、错误处理
├── workflows/
│   └── verify_workflow.js        # M4 编排(JS)
└── src/
    └── m3_locate/
        └── audit_orchestrator.py # 新增定位初始化脚本 (从 scripts.legacy 移入)
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
