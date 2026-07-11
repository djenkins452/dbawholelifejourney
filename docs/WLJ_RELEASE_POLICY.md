# WLJ Release Policy

**Status:** CURRENT · Milestone artifact (2026-07-11)
**Principle:** Not every Chief-of-Staff refinement is a user announcement. Publish at the right altitude for the audience.

---

## Three publication levels

| Level | Audience | Where | Cadence | What goes here |
|---|---|---|---|---|
| **1 — Internal Technical Changelog** | Engineering (Danny + Claude) | `docs/wlj_claude_changelog.md` | **Every commit** (non-negotiable) | Every change: root cause, files, why. Full technical detail. |
| **2 — Milestone Release Notes** | Engineering + stakeholders | `docs/` milestone reports (e.g. `WLJ_MILESTONE_COS_ARCHITECTURE.md`) | Per milestone | The consolidated story of a body of work: what changed architecturally, what it guarantees, rollback point. |
| **3 — User-facing What's New** | Paying customers | `apps/core/fixtures/release_notes.json` | Per meaningful user improvement | Summarized, benefit-first, **no internal architecture, no assistant name**. "Your Chief of Staff now…". |

## Rules

1. **Level 1 is mandatory and total.** Every commit — even a one-line fix — appends to the changelog. No exceptions.
2. **Do not leak Level 1 into Level 3.** Users do not see "occurrence-scoped completion producer" — they see "Your Chief of Staff is now more accurate about what you've finished today." Summarize the *improvement*, not the mechanism.
3. **Naming discipline (Constitution §1).** User-facing release notes and help say **"your Chief of Staff"**, never "Beth" or any user-selected name, never a provider name.
4. **Meaningful ≠ every refinement.** Many CoS tuning changes are invisible to users by design. Only surface changes a customer would actually notice and value.
5. **Milestone notes (Level 2) are the bridge.** When a cluster of Level-1 changes constitutes a milestone, write one Level-2 report and, if any of it is user-visible, one Level-3 entry.

## Decision test for "does this get a What's New entry?"

Ask: *would a paying customer notice and care?* If yes → one concise, benefit-first Level-3 entry. If it's correctness/plumbing they'd never perceive → Level 1 only.
