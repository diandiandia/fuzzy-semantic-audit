---
name: fuzzy-semantic-audit-v4
description: CLI-based multi-language codebase security audit skill using local static pre-filtering and prompt-driven verifier execution (V4)
---

# Fuzzy Semantic Audit V4 — Custom Skill Specification

> [!IMPORTANT]
> **This workspace implements the V4 codebase security audit skill. Any CLI skill runner, tool wrapper, or external parser executing this skill MUST strictly adhere to the V4 architecture, requirements, and compliance rules documented here.**

---

## 🎯 V4 Core Objectives (The 8 Commandments)

V4 is built to enforce a clean separation between **high-speed local static filtering** and **high-precision prompt-driven verifier execution**:

1.  **Universal Multi-Language Support**: Support any codebase language (Java, C/C++, Python, Go, Rust, etc.) using Tree-Sitter parsing and regex fallback without compiler-level coupling.
2.  **Language Discovery**: Scan the project, determine present programming languages, and record their source paths in `repo_profile.json`.
3.  **CWE Security Profiling**: Associate each identified language with corresponding CWE security domains (e.g., Authz, Injection, StateMachine).
4.  **AI-Generated Scan Packs**: Invoke an LLM to dynamically generate search keywords, regexes, and AST query schemas for each detected language, saving them as `scan_pack.json`.
5.  **Local AST Pre-Filtering**: Perform a lightning-fast local AST/regex scan on source code to filter out 90%+ harmless nodes and identify Candidate Sinks.
6.  **Severity Prioritization**: Calculate static scores for Candidates and sort them by severity (Critical -> High -> Medium -> Low) in `verify_queue.json`.
7.  **Prompt-Driven Verifier Skill**: Distribute candidates sequentially as "clues" to a Verifier Skill. The skill uses the provided prompt, repository context, and local tools (`find_callers`, `read_file_segment`, `find_implementations`) to produce a structured verdict and evidence path.
8.  **Strict Serial Workflow Control**: Maintain a task queue ensuring all candidates are evaluated and proven strictly in order of their severity.

---

## 📚 Essential Documentation Index

When developing, configuring, or running V4, read and enforce compliance in this order:

1.  **[REQUIREMENTS.md](file:///root/fuzzy-semantic-audit/REQUIREMENTS.md)**: Product goals and the 8 core commandments.
2.  **[V4_SYSTEM_DESIGN.md](file:///root/fuzzy-semantic-audit/V4_SYSTEM_DESIGN.md)**: The hybrid pipeline architecture, system method specifications (APIs), and safety mitigations (Token limit cap, AST fallback, dynamic dispatch tools).
3.  **[V4_TASK_BREAKDOWN.md](file:///root/fuzzy-semantic-audit/V4_TASK_BREAKDOWN.md)**: The executable step-by-step P0-P3 project milestones with Definition of Done (DoD).
4.  **[rules/v4_development_compliance.md](file:///root/fuzzy-semantic-audit/rules/v4_development_compliance.md)**: The platform-level system prompt rules enforcing compliance and preventing architectural design drift.

---

## 🛠️ V4 Project Structure & Boundaries

All V4 development must take place within these specific namespaces:
*   **Source Code**: `src_v4/`
*   **Workflow Orchestration**: `src_v4/cli/` (unified python orchestrator)
*   **Test Suite**: `tests/` (v4 verification scripts)
*   **Runtime Cache & State**: `repo_profile.json`, `scan_pack.json`, `verify_queue.json`
