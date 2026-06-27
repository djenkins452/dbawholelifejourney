WLJ PROMPT LIBRARY INDEX

Version: 1.2
Last updated: 2026-06-26
Load class: REFERENCE_ONLY (superseded)

> **SUPERSEDED (2026-06-26):** Navigation and load-class guidance now live in the
> top-level `00_README_LOAD_MANIFEST.md`, which covers all folders (00–08) and tells
> you exactly what to load and when. This file predates folders 04–08 and is kept
> for history only. **Use the load manifest.**

This directory contains the operational prompt framework used to guide
AI-assisted development of the Whole Life Journey system.

The prompts define how ChatGPT and Claude collaborate with Danny
to design, debug, and maintain WLJ.

---

00_CONTEXT

WLJ MASTER CONTEXT — CONTINUATION SESSION

Used when starting a new chat session with ChatGPT.
Provides system overview, architecture rules, collaboration workflow,
and operational expectations.

---

01_CHATGPT

CHATGPT ARCHITECTURE MODE
Used when improving system design, domain structure, or long-term
architectural decisions.

CHATGPT DEBUGGING MODE
Used when diagnosing system behavior and identifying root causes
before implementing fixes.

SYSTEM INVESTIGATION MODE
Used for deep system analysis when issues span multiple modules,
pipelines, or architectural layers.

DANNY'S PREFERENCES
Operator-specific collaboration rules: tone, decisiveness, scope
discipline, deployment expectations. Loaded as a system prompt
alongside the work-mode prompt.

---

02_CLAUDE

CLAUDE ARCHITECTURE MODE
Used when Claude is implementing architectural improvements
in the WLJ codebase.

CLAUDE DEBUGGING MODE
Used when Claude is performing root-cause analysis
and proposing minimal fixes.

---

03_REFERENCE

WLJ ARCHITECTURE LAWS
Defines the non-negotiable architectural rules for WLJ
(LLM-last, raw-data-→-signals-→-CoS, phase boundaries,
state-first reads, no silent failures, schema parity,
streaming/non-streaming parity, deterministic rendering,
deterministic decisioning, recoverability).

WLJ DOMAIN REGISTRY
Defines the canonical life domains (Behavioral / Influence /
Context) and the Support Apps that are NOT domains. Tracks which
domains have canonical renderer coverage (Phase 1 vs legacy).

WLJ SIGNAL ONTOLOGY
Defines the canonical signal model — UnifiedSignal shape,
producers (PIE / PRIE / PGE / CDCE / Drift), priority tiers,
source precedence, foundational suppression, label taxonomy,
the renderer contract, and the decision-layer pipeline that
consumes signals.

These documents act as the governing standards for
all architecture and development work.

---

PROMPT USAGE WORKFLOW

Typical workflow:

Danny describes the problem or design goal
↓
ChatGPT analyzes conceptually
↓
ChatGPT produces a structured prompt
↓
Danny sends prompt to Claude
↓
Claude analyzes the codebase and proposes findings
↓
Danny returns findings to ChatGPT
↓
ChatGPT evaluates architectural impact
↓
Next action determined