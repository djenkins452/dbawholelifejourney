# RETIRED — WLJ MASTER PROMPT — CLAUDE ARCHITECTURE MODE

**Status:** RETIRED 2026-08-24. This prompt is no longer an active boot authority and must not be
loaded, pasted, or followed.

**Use instead:** [`WLJ_MASTER_PROMPT.md`](../../WLJ_MASTER_PROMPT.md) — the single canonical session-boot prompt for
Whole Life Journey.

## Selecting a mode

The canonical prompt subsumes every mode this file used to provide. Paste
`WLJ_MASTER_PROMPT.md` as the first message of the session and declare the mode you want in §5:

| You want | Mode to declare | Governing doc the canonical prompt routes you to |
|---|---|---|
| System design / a new domain or capability | **ARCHITECT** | `@WLJ_SYSTEM_PROMPTS/00_WLJ_CHIEF_OF_STAFF_STARTUP/02_WLJ_CONSTITUTION.md` |
| "The app shows X, should show Y" | **DEBUG** | `docs/WLJ_RUNTIME_TRACE_DEBUGGING.md` |
| Multi-module / pipeline mystery, "why does…", "should we…" | **INVESTIGATE** | `docs/WLJ_CONDUCTOR_DEVELOPMENT_MODEL.md` |
| Implementing approved work | **BUILD** | `@WLJ_SYSTEM_PROMPTS/00_WLJ_CHIEF_OF_STAFF_STARTUP/03_ENGINEERING_OPERATING_GUIDE.md` |
| Reviewing a diff, a transcript, or a surface | **REVIEW** | `docs/WLJ_PRODUCT_VISION.md` |

## Why this was retired

Its contents taught an architecture WLJ no longer runs, and one framing the Constitution now
forbids outright. The retired teachings — **all void**:

- **"LLM-last"** as the governing architecture, and the *deterministic truth → engine
  interpretation → LLM narration* hierarchy.
- **Deterministic engines as the reasoning authority.** WLJ contains no reasoning engine; a
  reasoning miss is fixed with better truth, context, tools, or relationship (Constitution I.2, IV.4).
- **Narration as the Chief of Staff's primary role.** The conversational model *drives the turn* and
  owns reasoning, interpretation, judgment, and perception; WLJ exposes facts, never verdicts
  (Constitution I.2, I.4, I.5).
- **"Beth" as a system identity.** The assistant name is a per-user display preference only; no
  provider name and no assistant name is ever a WLJ system identity (Constitution §1, I.8).

Current model: **WLJ owns deterministic truth; the conversational model owns reasoning.**
*"The model reasons. WLJ knows."*

**History:** the original contents are preserved in git history and in the changelog entry for
2026-08-24. This file is intentionally not deleted so that existing links resolve to this notice.
