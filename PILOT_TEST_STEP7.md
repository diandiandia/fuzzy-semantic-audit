# 试点测试：验证层（Step 7）—— 三视角对抗裁判 + Fast Severity Filter + 三桶归类

> 目的：前面的定位/召回/去重都已在本地实测通过（1258→186 去重、真语义 intent 把桩函数误召从 60→4、rbac 授权模块与 by-id 取资源函数被精准召回）。**唯一没验证的是验证层**——三视角裁判判越权准不准、severity filter 能否刷掉桩函数、三桶归类是否合理。本测试专门跑这一环。
>
> 之所以要换 CLI 跑：原环境 API key 预算超限（Max 7.0 / 当前 7.067），验证阶段每候选要 4 次 agent 调用，跑不动。

---

## 0. 环境与前置状态（已就绪，无需重跑前面步骤）

- **Skill 根目录**：`/home/zjamg/test_project_code_audit/fuzzy-semantic-audit`
- **目标项目**：`/home/zjamg/walle-web`（Flask / Python 后端，217 个索引函数，含 `walle/service/rbac/` 授权模块）
- **隔离解释器**：`/home/zjamg/test_project_code_audit/fuzzy-semantic-audit/.venv-embed/bin/python`（fastembed 装在这里；本测试的验证阶段不做向量检索，Python 步骤用它或系统 python3 皆可）
- **候选包目录**：`/home/zjamg/walle-web/.audit_temp/pending_cands/`（**21 个** `cand-uniq-*.json`，全部 `verdict=pending`）
- **audit_plan.json**：`.../resources/audit_plan.json`（`status=explored`，单个 deduped task，21 个候选，已裁剪到越权/认证类 6 个 CWE：306/419/425/601/639/749）
- **验证 workflow**：`.../workflows/verify_workflow.js`
- **回写 CLI**：`python -m src.m4_verify.trifecta_verifier update`
- **报告 CLI**：`python -m src.m5_report.reporter`

⚠️ 请勿重新 init / explore / 重建索引——那会覆盖已就绪的 21 个候选。直接从下面的验证步骤开始。

---

## 1. 要跑什么

在 skill 根目录下，让你的 coding-agent CLI 运行验证 workflow。它会：
1. 读 plan，收集全部 pending 候选（21 个）
2. 对每个候选：先跑 **Fast Severity Filter**（单 agent 打 1-10 分，<5 直接判 false_positive 跳过），≥5 才派 **3 个对抗裁判**（reachability / guard / exploit，默认证伪立场）
3. 三桶归类（verified / needs_review / false_positive，非对称阈值）
4. 逐条回写 verdict 到 plan
5. 编译三桶 Markdown 报告

**运行方式**（在 `/home/zjamg/test_project_code_audit/fuzzy-semantic-audit` 目录下，让 CLI 执行这个 workflow 脚本）：

- 脚本：`workflows/verify_workflow.js`
- 传入参数（args）：
  ```json
  {
    "planPath": "/home/zjamg/test_project_code_audit/fuzzy-semantic-audit/resources/audit_plan.json",
    "candDir": "/home/zjamg/walle-web/.audit_temp/pending_cands",
    "projectPath": "/home/zjamg/walle-web",
    "repoRoot": "/home/zjamg/test_project_code_audit/fuzzy-semantic-audit",
    "venvPython": "/home/zjamg/test_project_code_audit/fuzzy-semantic-audit/.venv-embed/bin/python",
    "limit": 21
  }
  ```

> 如果你的 CLI 不是 Claude Code / 不支持这个 Workflow API，见 **附录 A：无 workflow 的手动跑法**（用 shell 逐候选跑，等价）。

---

## 2. 需要回传给我的结果（按重要性排序）

### （必需）2.1 最终三桶报告
生成的报告文件：`/home/zjamg/walle-web/audit_report.md` —— **把整个文件内容贴回来**。

### （必需）2.2 每个候选的判定汇总表
跑完后执行这条命令，把输出贴回来：
```bash
cd /home/zjamg/test_project_code_audit/fuzzy-semantic-audit
/home/zjamg/test_project_code_audit/fuzzy-semantic-audit/.venv-embed/bin/python - <<'PY'
import json
p = json.load(open("resources/audit_plan.json"))
for c in p["tasks"][0]["result_candidates"]:
    votes = c.get("votes", [])
    vsum = "/".join(f"{v.get('lens','?')[:4]}:{'T' if v.get('isReal') else 'F'}" for v in votes) if votes else "(skipped)"
    print(f"{c['function']:22s} @ {c['file'].split('/')[-1]:16s} cwe={','.join(c.get('matched_cwes',[]))[:20]:20s} => {c['verdict']:15s} [{vsum}]")
PY
```

### （重要）2.3 逐候选的裁判理由
把 plan 里每个候选的 `triage_explanation` 和 `votes[].reason` 贴回来（或直接把整个 `resources/audit_plan.json` 回传，我自己提取）。这是判断裁判**推理质量**的关键，不只是看结论对错。

### （有用）2.4 运行元数据
- 总 token 消耗 / agent 调用次数 / 耗时（你的 CLI 若有统计）
- 有多少候选在 severity filter 阶段就被 skip（severity <5）
- 任何 agent 失败 / 报错

---

## 3. 我会用这些"标准答案"来判断裁判准不准

下面是我人工预判的**期望判定**（基于候选函数的性质）。裁判结果和这个对照，就能看出判定质量。**注意：这是启发式预期，不是铁律——裁判给出合理理由的偏离也算好结果。**

| 候选函数 | 文件 | 性质 | 期望桶 | 理由 |
|---|---|---|---|---|
| `unauthorized` | walle/app.py | 3-12 行的桩函数，仅 `return json(code=unlogin)` | **false_positive** | 无逻辑、无资源访问。**severity filter 应打低分 skip 掉**——这是验证 filter 灵不灵的关键样本 |
| `get_by_id` | walle/model/database.py | ORM 基类按主键取记录 | verified 或 needs_review | 典型 IDOR 面：若调用链上无归属校验即用 client 传入 id 取对象。看裁判能否从 call_chain 判断 |
| `fetch_by_id` | walle/model/server.py | 按 id 取 server 记录 | verified 或 needs_review | 同上，越权高发 |
| `load_user` | walle/service/rbac/passport.py | 认证/加载用户 | needs_review 或 false_positive | 是认证机制本身，需看它是否被正确调用 |
| `is_allow` | walle/service/rbac/access.py | RBAC 权限判定 | false_positive（若逻辑完整）或 needs_review | 这是**防御代码**本身；除非其逻辑可绕过，否则不该判成漏洞 |
| `decorator` | walle/service/rbac/role.py | 权限装饰器 | false_positive 或 needs_review | 同上，是守卫机制 |
| `validate_username` / `validate_user_ids` | walle/form/*.py | 表单校验 | false_positive | 输入校验函数，非漏洞点 |
| `lint` | walle/commands.py | CLI 命令 | false_positive | 不可外部触达（severity 应偏低） |

**我最关心的 3 个判断质量信号：**
1. **`unauthorized` 桩函数是否被 severity filter skip 掉**（<5 分）？—— 若它进了裁判甚至被判 verified，说明 filter 失灵。
2. **`get_by_id` / `fetch_by_id` 这类 by-id 取资源函数，裁判是否在用 call_chain 推理"这条路径上有没有归属校验"**（而不是只看单函数）？—— 这是 P1 调用链切片设计的核心验证点。理由里应体现跨函数推理。
3. **RBAC 防御函数（`is_allow`/`decorator`）会不会被误判成漏洞**（假阳性）？—— 好的裁判应识别出"这是守卫本身"。

---

## 4. 判定质量的评分维度（你不用评，回传数据我来评）

- 桶分布是否合理（不该 21 个全 verified，也不该全 false_positive）
- severity filter 拦截率（预期能刷掉 unauthorized / lint 等几个）
- 裁判理由是否引用了 call_chain_context（跨函数推理证据）
- attackPath 字段：判 verified 的是否给出了具体攻击路径
- 是否有明显误杀（真越权判成 false_positive）或明显误报（桩函数判成 verified）

---

## 附录 A：无 workflow 的手动跑法（如果你的 CLI 不支持 Workflow API）

验证的本质是对每个候选包跑 4 个 prompt。可以让 CLI 逐个候选手动做，然后用 CLI 回写。对每个 `cand-uniq-N.json`：

**Step A — severity（1 个 agent）**：读候选包，按下述评分，返回 `{severity:1-10, reason}`：
> 评估这个候选函数做安全漏洞验证的潜在严重度 1-10。高危(5-10)：直接处理不可信输入/网络包/认证/授权/内存/命令；**或**按调用方传入的 id/key/path 读写资源(CRUD/handler)、做状态转换、把门(gate access)——这些是 IDOR/越权/状态绕过高发面，即使无内存操作也算高危。低危(1-4)：日志/调试/纯配置加载/测试夹具/样板，无安全决策无不可信数据。

若 severity <5 → verdict=`false_positive`，跳过裁判。

**Step B — 3 个裁判（severity≥5 时，各 1 个 agent，独立、默认证伪立场）**，每个读候选包（尤其 `call_chain_context`）返回 `{isReal, confidence, lens, reason, attackPath, missingEvidence}`：
- **裁判1 reachability**：`unauthorized`/桩/测试/入口未知 → 判不可达 isReal=false。看 upstream callers 是否追溯到外部入口。
- **裁判2 guard**：BOLA/IDOR 视角——若函数按 client 传入 id/key/path 操作资源，**这条调用路径上**必须有归属/权限校验；别处有不算。路径上无 → isReal=true。
- **裁判3 exploit**：能否追出具体控制流触发（含状态机绕过/TOCTOU）。给不出具体攻击步骤 → isReal=false。

**Step C — 三桶归类**（确定性）：
- ≥2 票 isReal=true **且** 至少一票 attackPath 非 "None" → `verified`
- 恰好 1 票 true / 有分歧 / 任一票 missingEvidence 非 "None" → `needs_review`
- 3 票全 false → `false_positive`

**Step D — 回写**（对每个候选，在 skill 根目录跑）：
```bash
/home/zjamg/test_project_code_audit/fuzzy-semantic-audit/.venv-embed/bin/python -m src.m4_verify.trifecta_verifier update \
  --plan /home/zjamg/test_project_code_audit/fuzzy-semantic-audit/resources/audit_plan.json \
  --candidate-id <cand-uniq-N> \
  --verdict <verified|needs_review|false_positive> \
  --explanation "<归类理由>" \
  --votes '<votes 数组的 JSON 字符串>'
```

**Step E — 出报告**：
```bash
/home/zjamg/test_project_code_audit/fuzzy-semantic-audit/.venv-embed/bin/python -m src.m5_report.reporter \
  --plan /home/zjamg/test_project_code_audit/fuzzy-semantic-audit/resources/audit_plan.json \
  --output /home/zjamg/walle-web/audit_report.md
```

然后回传第 2 节要求的结果。

---

## 附录 B：候选清单（21 个，供核对）

| id | function | file | matched_cwes |
|---|---|---|---|
| cand-uniq-1 | unauthorized | walle/app.py | 419,425,601,749 |
| cand-uniq-4 | is_allow | walle/service/rbac/access.py | 419,306 |
| cand-uniq-7 | get_by_id | walle/model/database.py | 425,601,639 |
| cand-uniq-9 | load_user | walle/service/rbac/passport.py | 425,601 |
| cand-uniq-21 | fetch_by_id | walle/model/server.py | 639 |
| ... | （其余见 pending_cands/ 目录） | | |

> 完整 21 个：unauthorized, is_enable, is_authenticated, decorator, is_anonymous, fetch, logout, detection, lint, validate_user_ids, uid2name, on_open, validate_username, fetch_by_id, role, is_allow, list_enable, before_request, get_by_id, get_id, load_user
