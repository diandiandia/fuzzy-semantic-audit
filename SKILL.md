---
name: fuzzy-semantic-audit
description: Discover 0-day logic vulnerabilities using the CWE-699 Software Development catalog, CodeGraph fuzzy semantic matching, concurrent subagents, and Trifecta verification.
---

# Fuzzy Semantic Audit Protocol (V4.0)

This skill automates parallel 0-day vulnerability analysis by leveraging CodeGraph, AI-generated semantic vulnerability prompts, test-suite heuristic pruning, advanced auditing methods (Trifecta Proof, Taint Analysis, Attack Surface Analysis), and concurrent subagents orchestrated via a Workflow (Claude Code / Antigravity `agent`/`pipeline`/`parallel` APIs).

## 🚀 Execution Procedures

> **Environment variables (set these first):**
> ```bash
> export SKILL=/path/to/fuzzy-semantic-audit          # this skill's root directory (code + config only)
> export VENV_PY="$SKILL/.venv-embed/bin/python"       # isolated interpreter with fastembed installed
> export TARGET=/path/to/target/project                # project under audit
> ```
> **产物位置**: 所有审计产物(catalog / audit_plan.json / 候选包 / 向量索引 / 报告)统一落在
> `$TARGET/.audit_workspace/` —— **不写入 skill 目录**。skill 只保留代码(`src/`,`workflows/`)
> 与配置(`resources/699.xml`,`resources/prescan_rules.json`)。多项目审计互不覆盖。
> 下面的命令用 `--project "$TARGET"` 驱动,产物路径自动推导;也可用 `--output`/`--plan` 显式覆盖。
> ⚠️ **Interpreter note**: `fastembed` (required by the M2 vector layer) is installed **only** in `.venv-embed`.
> Any step that touches the vector index — Step 4 (build) and Step 6 (explorer) — MUST run with `$VENV_PY`,
> not the system `python3`, or it will crash with `ImportError: fastembed`. Steps 2/3 may use plain `python3`.

### Step 1: Initialize CodeGraph Indexing
Ensure the CodeGraph index is initialized and active for the target project:
```bash
# Run in project root:
codegraph init /path/to/target/project
```

### Step 2: Ingest CWE-699 Weakness Catalog
Parse the CWE-699 XML file and extract weaknesses applicable to the target language. Catalog is written to `$TARGET/.audit_workspace/catalog.json`:
```bash
python3 -m src.m1_cwe.cwe_parser --cwe "$SKILL/resources/699.xml" --lang python --project "$TARGET"
```

### Step 3: Auto-detect Project Features & Initialize Audit Plan
Detect the dominant language and technology stack, prune irrelevant CWE tasks, and initialize the plan (into `$TARGET/.audit_workspace/audit_plan.json`). Omit `--lang` to auto-detect:
```bash
python3 -m src.m3_locate.audit_orchestrator init --project "$TARGET"
```

### Step 4: Build Vector Index (M2)
Build the vector database using fastembed for semantic search. (Although the explorer will lazily build it if missing, explicit pre-building is recommended). Index is written to `$TARGET/.audit_workspace/vec_index/`. **Must use `$VENV_PY`** (fastembed lives in `.venv-embed`):
```bash
"$VENV_PY" -m src.m2_index.vector_index build --project "$TARGET" --lang python
```

### Step 5: AI-Driven Prompt/Intent Synthesis (M6)
Orchestrate the LLM to translate CWE tasks into specific semantic queries and vulnerability templates using the JavaScript workflow. **This step MUST complete before Step 6** — otherwise the explorer falls back to degenerate keyword search (garbage-in, see System Design §9):
> **How to Run**: Prompt the coding assistant (Claude Code or Antigravity) to run this workflow:
> *"Run the JavaScript workflow at `workflows/generate_intents_workflow.js` with parameters: planPath = '$TARGET/.audit_workspace/audit_plan.json', repoRoot = '$SKILL', venvPython = '$SKILL/.venv-embed/bin/python'"*

### Step 6: Run Semantic Exploration & Call-Chain Assembly (M3)
Recall candidates via **three roads** — vector semantic search + CodeGraph symbol query + (for logic-flaw CWEs) resource-access recall — then assemble each candidate's `call_chain_context` (upstream callers + downstream callees), filter boilerplate/blacklisted directories (monitor/tools/client/unit/emulator), and export candidate packages into `$TARGET/.audit_workspace/pending_cands/`. **Must use `$VENV_PY`** (this step performs vector search and requires fastembed). Ensure Step 5 has already populated semantic intents:
```bash
"$VENV_PY" -m src.m3_locate.explorer --plan "$TARGET/.audit_workspace/audit_plan.json" --project "$TARGET"
```

### Step 7: Execute Automated Verification Workflow (M4)
Run the JavaScript verification workflow to perform two-stage severity filtering (Stage 1) and parallel referee verification (Stage 2), update verdicts, and compile the final report (into `$TARGET/.audit_workspace/audit_report.md`).
> **`severityThreshold` (default 5)**: the Fast Severity Filter drops candidates scoring below this before the expensive three-referee stage. **Lower it (e.g. 3) to hunt 0-days** (fewer skips, wider coverage, higher cost); raise it (e.g. 7) for a cheap quick scan.
> **How to Run**: Prompt the coding assistant (Claude Code or Antigravity) to run this workflow:
> *"Run the JavaScript workflow at `workflows/verify_workflow.js` with parameters: planPath = '$TARGET/.audit_workspace/audit_plan.json', projectPath = '$TARGET', candDir = '$TARGET/.audit_workspace/pending_cands', repoRoot = '$SKILL', venvPython = '$SKILL/.venv-embed/bin/python', limit = 20, severityThreshold = 5"*

---

## 🛡️ Auditing Methodology Reference (安全评估与对抗验证)

During candidate verification, the workflow employs a two-stage filtering process:

> **Cross-function reasoning (关键)**: every candidate package carries a `call_chain_context` field
> (upstream callers + downstream callees). Logic vulnerabilities (越权/状态机/信任边界) have NO syntactic
> signature and cannot be judged from a single function — the referees reason over this call-chain slice.

### Stage 1: Fast Severity Filter (安全等级评估过滤)
A single agent evaluates the potential security severity (1 to 10) of the candidate code. High severity includes not only untrusted-input/crypto/memory handling, but ALSO functions that access a resource by a caller-supplied id/key/path or perform a state transition (order/payment/session) — prime logic-flaw surfaces with no syntactic signature. If the rating is `< 5`, the candidate is classified as `false_positive` and skips the expensive verification stage.

### Stage 2: Parallel Adversarial Referees (三视角对抗验证)
If severity is `≥ 5`, the workflow spawns parallel subagents evaluating the target functions across three distinct perspectives with a default falsification stance (默认"证伪"立场). Each lens now covers both memory-class and logic-class flaws:

1. **Path Reachability & Trust Boundary (路径可达性 + 信任边界)**:
   - Verify if the function is reachable from untrusted external inputs/interfaces (IPC, socket recv, public/HTTP API, route handler) via the upstream callers.
   - Trust-boundary confusion: is data assumed internal-only actually reachable from an external caller?
   - If the entrypoint is unknown, mock, or test code, reachability must be falsified.

2. **Guard Validity & Missing Authorization (守卫有效性 + 缺失授权)**:
   - Identify bounds/size/auth checks, locks, state assertions in the function AND its callers.
   - **BOLA/IDOR lens**: if the function acts on a caller-supplied id/key/path, an ownership/permission check must exist **on this call path** — a check existing elsewhere does not count. Missing → real.
   - Prove if guards are bypassable; if valid, mark safe.

3. **Exploitability: Control-Flow / State-Machine / Race (可触发性 + 状态机 + 竞态)**:
   - Trace untrusted variables source→sink across the chain (Taint Analysis).
   - State-machine bypass: can a required prior step (payment/validation/auth) be skipped by calling directly or reordering calls?
   - TOCTOU/race: is there a check-then-use gap on shared/filesystem state?
   - Require a concrete attack path (memory corruption OR logic bypass) to prove exploitability.

---

## 🔧 Installation & Compatibility (环境适配与安装)

This skill is fully compatible with both **Claude Code CLI** and **Google Antigravity CLI (`agy`)**. Both platforms share the same customizations, YAML frontmatter triggers, and JavaScript dynamic workflow APIs (`agent`, `pipeline`, `parallel`).

To load this skill, create a symbolic link from your active environment's customizations root to this folder:

### A. For Antigravity CLI (`agy`)
- **Global registration**:
  ```bash
  ln -s "/path/to/fuzzy-semantic-audit" "$HOME/.gemini/config/skills/fuzzy-semantic-audit"
  ```
- **Workspace-specific registration** (under target project root):
  ```bash
  mkdir -p .agents/skills
  ln -s "/path/to/fuzzy-semantic-audit" ".agents/skills/fuzzy-semantic-audit"
  ```

### B. For Claude Code CLI
- **Global registration**:
  ```bash
  ln -s "/path/to/fuzzy-semantic-audit" "$HOME/.claude/skills/fuzzy-semantic-audit"
  ```
- **Workspace-specific registration** (under target project root):
  ```bash
  mkdir -p .claude/skills
  ln -s "/path/to/fuzzy-semantic-audit" ".claude/skills/fuzzy-semantic-audit"
  ```
