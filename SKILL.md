---
name: fuzzy-semantic-audit
description: Discover 0-day logic vulnerabilities using the CWE-699 Software Development catalog, CodeGraph fuzzy semantic matching, concurrent subagents, and Trifecta verification.
---

# Fuzzy Semantic Audit Protocol (V4.0)

This skill automates parallel 0-day vulnerability analysis by leveraging CodeGraph, AI-generated semantic vulnerability prompts, test-suite heuristic pruning, advanced auditing methods (Trifecta Proof, Taint Analysis, Attack Surface Analysis), and concurrent subagents orchestrated via a Workflow (Claude Code / Antigravity `agent`/`pipeline`/`parallel` APIs).

## 🚀 Execution Procedures

### Primary Entrypoint: Full-Pipeline Orchestrated Workflow (推荐)

You can run the entire 7-step code audit process from zero to the final `audit_report.md` report via a **single workflow invocation**. This automatically detects the target language, builds indices, runs intent synthesis, recalls candidates, executes the three-referee verification, and compiles the report. It also automatically handles paths and encapsulates the python interpreter inside `.venv-embed`, eliminating environment traps.

To run:
1. Initialize the environment variables:
   ```bash
   export SKILL=/path/to/fuzzy-semantic-audit          # this skill's root directory (code + config only)
   export TARGET=/path/to/target/project                # project under audit
   ```
2. Prompt the coding assistant (Claude Code / Antigravity) with this single instruction:
   > *"Run the JavaScript workflow at `workflows/orchestrate_audit.js` with parameters: repoRoot = '$SKILL', projectPath = '$TARGET', limit = 200, severityThreshold = 5"*

This workflow will:
- Phase 1: **Prepare** (Parse catalog with `--lang all`, run `audit_orchestrator init` to detect language and build plan, build vector database).
- Phase 2: **Intents** (Run `fuzzy-semantic-intents` sub-workflow to synthesize search queries and templates).
- Phase 3: **Explore** (Recall candidates using dual-road search with ripgrep usage fallback and candidate deduplication).
- Phase 4: **Verify** (Run `fuzzy-semantic-verify` sub-workflow to filter by severity and evaluate candidates via three adversarial referees, updating verdicts in batch and compiling the report).

---

### Alternative Entrypoint: Step-by-Step Manual Execution (分步手动执行)

If you need to debug a specific step, adjust intermediate outputs, or run a subset of the pipeline, you can use the manual step-by-step procedures documented in the [Appendix: Step-by-Step Manual Execution](#appendix-step-by-step-manual-execution).

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

> **Universal check (新增)**: Regardless of which CWEs are tagged on the candidate, every referee independently assesses: can any parameter, size, or index cause an operation to read/write outside its intended bounds? Can any integer wrap? Can any pointer be used after free or dereferenced null? The matched CWE list may be incomplete — referees must not restrict their analysis to the listed CWEs alone.

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

---

## 📝 Appendix: Step-by-Step Manual Execution (分步手动执行)

### Step 1: Initialize CodeGraph Indexing
Ensure the CodeGraph index is initialized and active for the target project:
```bash
codegraph init /path/to/target/project
```

### Step 2: Ingest CWE-699 Weakness Catalog
Parse the CWE-699 XML file and extract weaknesses applicable to the target language. Catalog is written to `$TARGET/.audit_workspace/catalog.json`:
```bash
python3 -m src.m1_cwe.cwe_parser --cwe "$SKILL/resources/699.xml" --lang python --project "$TARGET"
```

### Step 3: Auto-detect Project Features & Initialize Audit Plan
Detect the dominant language and technology stack, prune irrelevant CWE tasks, and initialize the plan:
```bash
python3 -m src.m3_locate.audit_orchestrator init --project "$TARGET"
```

### Step 4: Build Vector Index (M2)
Build the vector database using fastembed for semantic search. **Must use `$VENV_PY`**:
```bash
"$VENV_PY" -m src.m2_index.vector_index build --project "$TARGET" --lang python
```

### Step 5: AI-Driven Prompt/Intent Synthesis (M6)
Orchestrate the LLM to translate CWE tasks into specific semantic queries using the JS workflow:
> *"Run the JavaScript workflow at `workflows/generate_intents_workflow.js` with parameters: planPath = '$TARGET/.audit_workspace/audit_plan.json', repoRoot = '$SKILL', venvPython = '$SKILL/.venv-embed/bin/python'"*

### Step 6: Run Semantic Exploration & Call-Chain Assembly (M3)
Recall candidates via vector search + CodeGraph + resource-access recall:
```bash
"$VENV_PY" -m src.m3_locate.explorer --plan "$TARGET/.audit_workspace/audit_plan.json" --project "$TARGET"
```

### Step 6.5: Recall Coverage Audit (Optional)
Deterministic scan to find functions with common sink patterns that have no corresponding candidate package:
```bash
python3 -m src.m3_locate.recall_auditor --cand-dir "$TARGET/.audit_workspace/pending_cands" \
  --project "$TARGET" --output "$TARGET/.audit_workspace/recall_gaps.md"
```

### Step 7: Execute Automated Verification Workflow (M4)
Run the JavaScript verification workflow to verify candidates:
> *"Run the JavaScript workflow at `workflows/verify_workflow.js` with parameters: planPath = '$TARGET/.audit_workspace/audit_plan.json', projectPath = '$TARGET', candDir = '$TARGET/.audit_workspace/pending_cands', repoRoot = '$SKILL', venvPython = '$SKILL/.venv-embed/bin/python', limit = 20, severityThreshold = 5"*
