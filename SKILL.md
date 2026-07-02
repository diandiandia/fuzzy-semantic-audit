---
name: fuzzy-semantic-audit
description: Discover 0-day logic vulnerabilities using the CWE-699 Software Development catalog, CodeGraph fuzzy semantic matching, concurrent subagents, and Trifecta verification.
---

# Fuzzy Semantic Audit Protocol (V4.0)

This skill automates parallel 0-day vulnerability analysis by leveraging CodeGraph, AI-generated semantic vulnerability prompts, test-suite heuristic pruning, advanced auditing methods (Trifecta Proof, Taint Analysis, Attack Surface Analysis), and concurrent subagents orchestrated via a Node.js workflow.

## 🚀 Execution Procedures

### Step 1: Initialize CodeGraph Indexing
Ensure the CodeGraph index is initialized and active for the target project:
```bash
# Run in project root:
codegraph init /path/to/target/project
```

### Step 2: Ingest CWE-699 Weakness Catalog
Parse the CWE-699 XML file and extract weaknesses applicable to the target language:
```bash
python3 -m src.m1_cwe.cwe_parser --cwe "$SKILL/resources/699.xml" --lang cpp --output "$SKILL/resources/cwe_699_catalog.json"
```

### Step 3: Auto-detect Project Features & Initialize Audit Plan
Detect the dominant language and technology stack, prune irrelevant CWE tasks, and initialize `audit_plan.json`:
```bash
python3 -m src.m3_locate.audit_orchestrator init --catalog "$SKILL/resources/cwe_699_catalog.json" --project "/path/to/target/project" --output "$SKILL/resources/audit_plan.json"
```

### Step 4: AI-Driven Prompt/Intent Synthesis (M6)
Orchestrate LLM to translate CWE tasks into specific semantic queries and vulnerability templates:
```bash
python3 -m src.m3_locate.intent_generator --plan "$SKILL/resources/audit_plan.json"
```

### Step 5: Run Semantic Exploration & Struct/Caller Tracing (M3)
Query CodeGraph and vector similarity search, trace callers (for reachability), filter boilerplates and directories (monitor/tools/client/unit/emulator), and export candidate packages:
```bash
python3 -m src.m3_locate.explorer --plan "$SKILL/resources/audit_plan.json" --project "/path/to/target/project"
```

### Step 6: Execute Automated Verification Workflow (M4)
Run the Node.js workflow script to verify candidates concurrently, apply non-symmetric voting thresholds, update candidates, and automatically generate the final three-bucket report:
```bash
node "$SKILL/workflows/verify_workflow.js" --plan "$SKILL/resources/audit_plan.json" --limit 20
```

---

## 🛡️ Auditing Methodology Reference (安全评估与对抗验证)

During candidate verification, the workflow employs a two-stage filtering process:

### Stage 1: Fast Severity Filter (安全等级评估过滤)
A single agent evaluates the potential security severity (1 to 10) of the candidate code based on its functionality (e.g., handles untrusted input vs. pure logging/debugging). If the rating is `< 5`, the candidate is immediately classified as `false_positive` (low severity, excluded) and skips the expensive verification stage.

### Stage 2: Parallel Adversarial Referees (三视角对抗验证)
If severity is `≥ 5`, the workflow spawns parallel subagents evaluating the target functions across three distinct perspectives with a default falsification stance (默认"证伪"立场):

1. **Path Reachability (路径可达性)**:
   - Verify if the function is accessible from untrusted external inputs/interfaces (IPC, socket recv, public API).
   - If the entrypoint is unknown, mock, or test code, the reachability must be falsified.

2. **Guard Validity (守卫有效性)**:
   - Identify boundary checks, size limits, authorization checks, mutex locks, or state assertions.
   - Prove if the checks are bypassable; if not, the candidate is marked as safe.

3. **Control-Flow Exploitability (可触发性)**:
   - Trace the flow of untrusted variables from source to sink (Taint Analysis).
   - Verify if input manipulation can trigger logic failures, out-of-bounds reads/writes, or memory corruption.
   - Require a concrete attack path to prove exploitability.

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
