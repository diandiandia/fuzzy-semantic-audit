# 📋 Fuzzy Semantic Audit Requirements & Design Specification

This document details the system requirements (Functional, Verification, and Operational) extracted from the `fuzzy-semantic-audit` codebase, workflows, and design files, mapping each requirement to its design implementation.

---

## 1. 📂 CWE Catalog & Tech Stack Requirements

### REQ-CAT-001: CWE XML Parser and Filtering
*   **Description**: The system must ingest the official CWE-699 Software Development catalog XML file, parse it, and filter out weaknesses that are not applicable to the target programming language.
*   **Design Brief**: Satisfied by `cwe_parser.py` ([M1](file:///home/zjamg/test_project_code_audit/fuzzy-semantic-audit/src/m1_cwe/cwe_parser.py)). It uses `xml.etree.ElementTree` to parse the catalog, matches `<Language>` nodes, and writes the language-specific catalog to `catalog.json` under `.audit_workspace/`.

### REQ-DET-001: Automatic Stack & Language Detection
*   **Description**: The system must automatically detect the target project's primary programming language and framework stack to prune irrelevant CWE tasks. Note: Pruning is conservative — only CWEs explicitly mapped to missing tech stacks in prescan_rules are pruned; unmapped CWEs are preserved by default to prevent false negatives.
*   **Design Brief**: Satisfied by `audit_orchestrator.py` ([M3](file:///home/zjamg/test_project_code_audit/fuzzy-semantic-audit/src/m3_locate/audit_orchestrator.py)) and `lang_utils.py` ([common](file:///home/zjamg/test_project_code_audit/fuzzy-semantic-audit/src/common/lang_utils.py)). It counts file extensions in the target directory (ignoring build, test, and vendor dirs) and identifies frameworks based on dependency files (e.g., `package.json` for JS, `requirements.txt`/`Pipfile` for Python).

---

## 2. 🔍 Double-Road Recall (Candidate Exploration)

### REQ-REC-001: Dual-Road Symbol and Semantic Recall
*   **Description**: The system must recall candidate functions matching CWE vulnerabilities through two parallel roads: precise symbol lookup and semantic vector search.
*   **Design Brief**: Satisfied by `explorer.py` ([M3](file:///home/zjamg/test_project_code_audit/fuzzy-semantic-audit/src/m3_locate/explorer.py)) which performs:
    1. Exact matching of generated keywords against the CodeGraph index.
    2. Embedding-based semantic search querying the vector database built by `vector_index.py` ([M2](file:///home/zjamg/test_project_code_audit/fuzzy-semantic-audit/src/m2_index/vector_index.py)) using `fastembed` and `bge-small-en-v1.5`.

### REQ-REC-002: Logical Vulnerability Resource Recall
*   **Description**: The system must open a third recall road specifically targeting logical weaknesses (e.g., IDOR, BOLA, missing authorization) by harvesting functions that access resources using user-controlled parameters.
*   **Design Brief**: Satisfied by `explorer.py` ([M3](file:///home/zjamg/test_project_code_audit/fuzzy-semantic-audit/src/m3_locate/explorer.py)) for CWE IDs belonging to `LOGIC_FLAW_CWES`. It matches per-language resource access patterns (e.g., `findById`, `get_by_id`) configured in the unified `languages.json` config.

### REQ-REC-004: Usages-based Ripgrep Fallback Recall
*   **Description**: The candidate explorer must support usage-based signal recall by searching for references of signals (including regexes and chain properties like objects.filter) and identifying their enclosing functions to bypass definition-only query limits.
*   **Design Brief**: Satisfied by `find_usages_enclosing_functions` in `codegraph_wrapper.py` ([M2](file:///home/zjamg/test_project_code_audit/fuzzy-semantic-audit/src/m2_index/codegraph_wrapper.py)) which runs `rg -n` on project files and searches upwards for function signatures.


### REQ-REC-003: Boilerplate and Noise Pruning
*   **Description**: The system must ignore candidates in auxiliary folders (e.g., unit tests, client mockups, monitoring scripts) to keep the candidate pool relevant.
*   **Design Brief**: Satisfied by `is_boilerplate_or_test` in `explorer.py` ([M3](file:///home/zjamg/test_project_code_audit/fuzzy-semantic-audit/src/m3_locate/explorer.py)) which checks filenames and paths against `BLACKLIST_FOLDERS` (e.g., `test`, `mock`, `emulator`, `monitor`).

---

## 3. 🚀 Workflow Execution & verification

### REQ-WF-001: Dynamic Workflow Orchestration
*   **Description**: Verification iteration must be orchestrated by a JavaScript-driven pipeline to guarantee that all candidate packages are systematically traversed without premature termination.
*   **Design Brief**: Satisfied by [verify_workflow.js](file:///home/zjamg/test_project_code_audit/fuzzy-semantic-audit/workflows/verify_workflow.js) (L4), which pulls `pending` candidates from `audit_plan.json` and runs them through `pipeline()` and `parallel()` agent APIs.

### REQ-WF-002: Batch Writeback Optimization
*   **Description**: The system must aggregate candidate verification verdicts in memory and perform a single writeback operation to minimize LLM command execution overhead.
*   **Design Brief**: Satisfied by [verify_workflow.js](file:///home/zjamg/test_project_code_audit/fuzzy-semantic-audit/workflows/verify_workflow.js) and `trifecta_verifier.py` ([M4](file:///home/zjamg/test_project_code_audit/fuzzy-semantic-audit/src/m4_verify/trifecta_verifier.py)). The JS workflow dumps the results array to a temporary file (`temp_batch_results.json`) and calls the `batch-update` subcommand once, executing a single file lock write in `plan_manager.py`.

### REQ-WF-003: End-to-End Workflow Orchestration
*   **Description**: The system must provide a single entry point workflow that orchestrates the entire 7-step code audit process end-to-end to eliminate manual shell chaining.
*   **Design Brief**: Satisfied by [orchestrate_audit.js](file:///home/zjamg/test_project_code_audit/fuzzy-semantic-audit/workflows/orchestrate_audit.js) (L4), which calls Python CLIs and sub-workflows. Python CLIs output a single-line JSON at the end (e.g. `cwe_parser` outputs `{"catalog": "<path>", "weaknesses": N}`) which is parsed by the JS workflow using a schema.


---

## 4. 🛡️ Verification & Adversarial Triage

### REQ-VER-001: Fast Severity Pre-Filter
*   **Description**: The system must pre-screen candidate functions and assign them a security severity rating (1–10). Verification must be bypassed for low-severity candidates (below threshold).
*   **Design Brief**: Satisfied by Stage B1 in [verify_workflow.js](file:///home/zjamg/test_project_code_audit/fuzzy-semantic-audit/workflows/verify_workflow.js) calling a severity agent. Candidates below `SEV_THRESHOLD` (default 5) are automatically triaged as `false_positive` without invoking the expensive referee stage.

### REQ-VER-002: Three-Perspective Adversarial Verification
*   **Description**: High-severity candidates must be analyzed by three independent LLM referees from three distinct perspectives with a default-falsification stance.
*   **Design Brief**: Satisfied by Stage B2 in [verify_workflow.js](file:///home/zjamg/test_project_code_audit/fuzzy-semantic-audit/workflows/verify_workflow.js), executing three parallel agents:
    1.  **Referee 1**: Path Reachability (external input tracing).
    2.  **Referee 2**: Guard Validity (checking if constraints/defense logic can be bypassed).
    3.  **Referee 3**: Exploitability (proving control-flow state changes or memory corruption).

### REQ-VER-003: Asymmetric Three-Bucket Triage
*   **Description**: Candidates must be triaged into three buckets (verified, needs_review, false_positive) using asymmetric voting rules to prevent false negatives.
*   **Design Brief**: Satisfied by the `triage` function in [verify_workflow.js](file:///home/zjamg/test_project_code_audit/fuzzy-semantic-audit/workflows/verify_workflow.js):
    *   `verified`: $\ge$ 2 votes of true vulnerability **and** a concrete `attackPath`.
    *   `needs_review`: $\ge$ 1 vote or any `missingEvidence`.
    *   `false_positive`: 3 votes for dismissal.

### REQ-VER-004: Caller Context Enrichment
*   **Description**: To audit logical weaknesses, candidate functions must carry context about their call chains, including code snippets of their closest callers.
*   **Design Brief**: Satisfied by `build_call_chain_context` in `codegraph_wrapper.py` ([M2](file:///home/zjamg/test_project_code_audit/fuzzy-semantic-audit/src/m2_index/codegraph_wrapper.py)). It queries CodeGraph for up to 3 upstream callers and extracts the first ~15 lines of their source code.

### REQ-VER-005: CodeGraph Callers Ripgrep Fallback
*   **Description**: If CodeGraph struggles to resolve caller associations due to dynamic routing or decorators, the system must search the codebase for text references to prevent reachability false negatives.
*   **Design Brief**: Satisfied by `get_callers_ripgrep_fallback` in `codegraph_wrapper.py` ([M2](file:///home/zjamg/test_project_code_audit/fuzzy-semantic-audit/src/m2_index/codegraph_wrapper.py)). If CodeGraph's caller command yields 0 items, it runs `rg -n -w <symbol>`, opens the file, and reads backwards to find the nearest enclosing function header.

---

## 5. 📊 Reporting & Completeness

### REQ-REP-001: Three-Bucket Report Compilation
*   **Description**: The system must generate a Markdown report summarizing the audit results grouped into verified vulnerabilities, needs review cases, and false positives.
*   **Design Brief**: Satisfied by `reporter.py` ([M5](file:///home/zjamg/test_project_code_audit/fuzzy-semantic-audit/src/m5_report/reporter.py)). It formats candidate data, inlines the call chains, code snippets, and individual referee votes, and writes to `audit_report.md`.

### REQ-REP-002: Honest Completeness Boundary Logging
*   **Description**: The report must display the count of remaining pending candidates to indicate that the verification run is potentially incomplete.
*   **Design Brief**: Satisfied by `reporter.py` ([M5](file:///home/zjamg/test_project_code_audit/fuzzy-semantic-audit/src/m5_report/reporter.py)) which counts the remaining candidates in the plan with `verdict == "pending"` and flags them in the report as "Unverified / Pending Candidates" to indicate incomplete audits.

---

## 6. ⚙️ Operational & Performance Controls

### REQ-CST-001: Pre-Deduplication cost controls
*   **Description**: The system must deduplicate exploration results across all CWEs before starting verification to avoid duplicate LLM evaluation of the same function.
*   **Design Brief**: Satisfied by `explorer.py` ([M3](file:///home/zjamg/test_project_code_audit/fuzzy-semantic-audit/src/m3_locate/explorer.py)) which groups candidates by `(file, function)` and merges their associated CWE IDs into `matched_cwes`.

### REQ-CST-002: Adaptive Vector Search Width
*   **Description**: The system must scale the vector search top-K retrieval limit based on the size of the codebase to prevent candidate explosion on small projects.
*   **Design Brief**: Satisfied by `adaptive_vector_topk` in `explorer.py` ([M3](file:///home/zjamg/test_project_code_audit/fuzzy-semantic-audit/src/m3_locate/explorer.py)), which maps index size to an optimized top_k search width (`clamp(index_size * 5%, 5, 30)`).

### REQ-ENV-001: Workspace Separation
*   **Description**: All audit work products (catalog, plans, indices, reports) must be isolated inside the target project workspace to support multi-project audits.
*   **Design Brief**: Satisfied by `paths.py` ([common](file:///home/zjamg/test_project_code_audit/fuzzy-semantic-audit/src/common/paths.py)) which points all outputs to a `.audit_workspace/` directory under the target project's root.

### REQ-ENV-002: Parallel Write Lock Protection
*   **Description**: The system must prevent file corruption during parallel write operations to the plan JSON file.
*   **Design Brief**: Satisfied by `plan_manager.py` ([common](file:///home/zjamg/test_project_code_audit/fuzzy-semantic-audit/src/common/plan_manager.py)), which acquires an exclusive file lock (`fcntl.flock(f, fcntl.LOCK_EX)`) before modifying the audit plan.
