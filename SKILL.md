---
name: fuzzy-semantic-audit-v3
description: Universal codebase security auditor with capability-aware fallback, unified IR, multi-stage candidate pruning, evidence assembly, and adversarial LLM triage (V3)
---

# Fuzzy Semantic Audit V3 — Custom Skill

> [!NOTE]
> This folder constitutes a V3 custom skill for coverage-first, capability-aware, multi-language codebase security audits.

---

## 🚀 Primary Goal

V3 is designed to audit any repository with:

1. explicit capability levels (`L0/L1/L2/L3`)
2. transparent degradation (`full_semantic`, `semantic_fallback`, `lexical_fallback`, `rule_only`)
3. unified IR-based recall
4. static pruning before LLM triage
5. standardized evidence packaging

This branch currently contains the **V3 design baseline**, not a completed V3 implementation.

The main documents are:

1. `REQUIREMENTS.md`
2. `V3_SYSTEM_DESIGN.md`
3. `V3_SOFTWARE_DESIGN.md`
4. `V3_TASK_BREAKDOWN.md`

---

## 📚 What To Read

When working on V3, use the documents in this order:

1. `REQUIREMENTS.md`
2. `V3_SYSTEM_DESIGN.md`
3. `V3_SOFTWARE_DESIGN.md`
4. `V3_TASK_BREAKDOWN.md`

These four documents define:

- product goals
- architecture
- software/module boundaries
- executable implementation order

---

## 🛠️ Current Branch Intent

The `v3` branch is intended to be a clean V3 planning and implementation branch.

That means:

1. V2 implementation files should not remain as active branch content.
2. V3 work should be built under `src_v3/` and `workflows/v3_*`.
3. Reports, state contracts, fallback semantics, and provider abstractions should follow the V3 documents.

---

## ✅ Implementation Rule

If you are implementing V3 on this branch:

1. follow `V3_TASK_BREAKDOWN.md`
2. implement one task or one strongly related task group at a time
3. keep fallback states explicit
4. do not reintroduce V2-only assumptions such as:
   - single-language dominance
   - hidden fallback
   - direct severity-based candidate deletion

