---
name: fuzzy-semantic-audit
description: Multilingual coverage-first codebase vulnerability scanner with adversarial LLM referee triage and state tracking (V2)
---

# Fuzzy Semantic Audit V2 — Custom Skill

> [!NOTE]
> This folder constitutes a Google Antigravity (AGY) Custom Skill designed to run coverage-first, state-tracked, concurrent-safe codebase security audits.

---

## 🚀 Orchestration Entrypoint (一键工作流调用)

The primary and recommended entrypoint to run the complete V2 audit pipeline is via the **`v2_orchestrate_audit.js`** Javascript workflow. 

To run the audit workflow, prompt the Google Antigravity agent with the following instruction:

> *"Run the JavaScript workflow at `workflows/v2_orchestrate_audit.js` with parameters: repoRoot = '$SKILL', projectPath = '$TARGET', limit = 100"*

Where:
* `$SKILL` is the absolute path to this skill's root folder (`/root/fuzzy-semantic-audit`).
* `$TARGET` is the absolute path to the repository under audit.

This orchestrator workflow executes the complete end-to-end audit:
1. **Phase 1: Ingestion & Inventory** — Initializes the plan (`init_plan`) and slices the repository files into `language_shards` (`build_inventory`).
2. **Phase 2: Indexing** — Extracts symbols and pre-builds Fastembed vector indices for discovered shards (`build_index`).
3. **Phase 3: Recall & Normalize** — Coordinately triggers Multi-Channel Recall (Rule, Graph, Vector, Resource) to identify candidate vulnerability records (`recall_candidates`).
4. **Phase 4: Adversarial Verification** — Leases candidate batches, spawns referee agents in parallel to decide verdicts (`reachability`, `guard`, `exploit`), maintains active leases in the background via a 60-second renew heartbeat loop, and commits verdicts back (`verify_batch`).
5. **Phase 5: Reports Compilation** — Compiles Markdown reports summarizing audit findings, backlogs, zero-recall facts, and phase durations (`compile_reports`).

---

## 🛠️ Step-by-Step Manual Execution (分步手动执行)

If you need to debug specific pipeline phases, you can execute individual Python CLI commands manually in sequence:

### Step 1: Initialize Workspace & Load Tracks
Initialize the workspace structure, loading standard default tracks and overlaying custom tracks from `resources_v2/tracks/*.json`:
```bash
python3 -m src_v2.cli.init_plan --project "$TARGET"
```
*Outputs: `$TARGET/.audit_workspace_v2/audit_plan.json`*

### Step 2: Build Language Sharding Inventory
Profile the repository and slice target files into language shards:
```bash
python3 -m src_v2.cli.build_inventory --plan "$TARGET/.audit_workspace_v2/audit_plan.json"
```
*Sets Shard Status to: `"discovered"`*

### Step 3: Build Shard Code Symbol Indices
Extract code symbols and pre-calculate embeddings:
```bash
python3 -m src_v2.cli.build_index --plan "$TARGET/.audit_workspace_v2/audit_plan.json"
```
*Sets Shard Status to: `"indexed"`*

### Step 4: Multi-Channel Candidate Recall
Coordinately execute recall channels (Rule, Graph, Vector, Resource) across all active shard × track pairs, normalizing and prioritizing findings:
```bash
python3 -m src_v2.cli.recall_candidates --plan "$TARGET/.audit_workspace_v2/audit_plan.json"
```
*Sets Shard Status to: `"recalled"`*
*Creates: `$TARGET/.audit_workspace_v2/candidate_registry.jsonl` and enqueues to `verify_now` queue.*

### Step 5: Fetch Triage Batch
Acquire a batch of leased candidates for referee verification:
```bash
python3 -m src_v2.cli.verify_batch --plan "$TARGET/.audit_workspace_v2/audit_plan.json" --get-batch --limit 10 --lease-timeout 1800
```
*Creates packaging envelopes in `$TARGET/.audit_workspace_v2/packages/`*
*Transitions candidate status: `"queued_for_verify" -> "verifying"`*

### Step 5.5: Lease Heartbeat Renewal
For active long-running verification jobs, periodically renew candidate lease limits:
```bash
python3 -m src_v2.cli.verify_batch --plan "$TARGET/.audit_workspace_v2/audit_plan.json" --renew-lease <candidate_id>
```

### Step 6: Writeback Verdicts
Apply asymmetric decision policies on parallel referee evaluation votes and commit final verdicts:
```bash
python3 -m src_v2.cli.verify_batch --plan "$TARGET/.audit_workspace_v2/audit_plan.json" --writeback <verdicts_file_path>
```
*Updates registry, syncs `manual_review` queue, and transitions fully triaged shards to status `"verified"`.*

### Step 7: Compile Reports
Generate user-facing Markdown reports summarizing findings, backlogs, zero-recall pairs, and phase durations:
```bash
python3 -m src_v2.cli.compile_reports --plan "$TARGET/.audit_workspace_v2/audit_plan.json"
```
*Creates: `$TARGET/.audit_workspace_v2/reports/{audit_report,coverage_report,review_queue}.md`*

---

## 📦 Custom Skill Registration (Skill 注册与集成)

To integrate this custom skill into your Google Antigravity CLI (`agy`) environment, create a symbolic link from your configurations directory to this directory:

- **Workspace-specific registration**:
  Create an `.agents/skills` folder under your project root and link this folder:
  ```bash
  mkdir -p .agents/skills
  ln -s "/path/to/fuzzy-semantic-audit" ".agents/skills/fuzzy-semantic-audit"
  ```
- **Global registration**:
  Alternatively, link globally to your CLI configurations directory:
  ```bash
  ln -s "/path/to/fuzzy-semantic-audit" "$HOME/.gemini/config/skills/fuzzy-semantic-audit"
  ```
