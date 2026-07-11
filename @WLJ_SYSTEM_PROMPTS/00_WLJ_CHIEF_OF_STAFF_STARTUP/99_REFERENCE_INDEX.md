# 99 · Reference Index — master table of contents

**Responsibility of this document:** the map. Every governing document — where it is, its authority, who it's for, whether it's current or historical, and what it's for. The startup package is the onboarding experience; the supporting library is the detail. Read the startup package; reach into the library on demand.

Legend — **Authority:** Constitutional / Governing / Reference / Operational. **Audience:** All (ChatGPT+Claude+Danny) / Engineer / Operator. **Status:** CURRENT / HISTORICAL.

---

## A. The startup package (read these; this folder)

| # | Title | Authority | Audience | Status | Purpose |
|---|---|---|---|---|---|
| 00 | READ FIRST — Architecture | Governing | All | CURRENT | What WLJ is, the vision, the OpenAI pivot, current architecture & maturity, lessons. |
| 01 | WLJ Constitution | **Constitutional** | All | CURRENT | Protected Articles + Constitutional Review (default NO). The apex. |
| 02 | Engineering Operating Guide | Governing | Engineer | CURRENT | How to evolve WLJ safely: tracing, root-cause proof, gates, deploy/doc discipline, Session Transition Protocol. |
| 03 | Danny Working Preferences | Governing | All | CURRENT | How to work with Danny: communication, workflow, product/investigation/decision philosophy. |
| 99 | NEXT CHAT STARTUP | Operational | All | CURRENT | Bootloader — current priorities & open work only. Gets shorter over time. |
| 99 | Reference Index | Reference | All | CURRENT | This file. |

## B. Supporting library — vision, contract, laws (authoritative detail, in `docs/`)

| Title | Authority | Audience | Status | Purpose |
|---|---|---|---|---|
| `WLJ_PRODUCT_VISION.md` | Governing | All | CURRENT | Highest-level "why": Personal Truth Platform; the model reasons, WLJ knows. |
| `WLJ_LLM_TRUTH_ACTION_CONTRACT.md` | Governing | Engineer | CURRENT | The truth/action/preference boundaries in detail (Article I). |
| `WLJ_ARCHITECTURE_LAWS.md` | Governing | Engineer | CURRENT | Answer Precondition Pipeline (Laws 0–5). |
| `WLJ_CONDUCTOR_DEVELOPMENT_MODEL.md` | Governing | Engineer | CURRENT | Layered development model (Truth→Reasoning→Action→Experience). |
| `WLJ_CURRENT_CONTEXT_CONTRACT.md` | Governing | Engineer | CURRENT | Current Context two-pattern standard (Article II). |
| `WLJ_VISUAL_TRUTH_CONTRACT.md` | Governing | Engineer | CURRENT | Only real completion may look complete (Article V.1). |
| `WLJ_EXECUTIVE_REFLECTION_ARCHITECTURE.md` | Governing | Engineer | CURRENT | Reflection observes, never overrides. |
| `LAYER1_DOMAIN_FRAMEWORK.md` | Governing | Engineer | CURRENT | How a new canonical truth domain is built (Article III.1). |
| `WLJ_MODEL_INTERFACE_DESIGN.md` | Reference | Engineer | CURRENT | The Model Interface seam + executive context envelope. |
| `WLJ_REQUEST_PATH_SAFETY.md` | Governing | Engineer | CURRENT | Never compute/LLM on the request path. |
| `WLJ_RUNTIME_TRACE_DEBUGGING.md` | Governing | Engineer | CURRENT | Prove the runtime path before editing. |
| `LAYER1_DOMAIN_FRAMEWORK.md` + Legacy/Medication canon docs | Reference | Engineer | CURRENT | Certified domain patterns. |

## C. Milestone record & coverage (in `docs/`, CURRENT)

| Title | Authority | Audience | Purpose |
|---|---|---|---|
| `WLJ_MILESTONE_COS_ARCHITECTURE.md` | Reference | All | The final milestone report + recovery point. |
| `WLJ_VERSION_MANIFEST.md` | Reference | Operator | SHA/tag/versions/migrations. |
| `WLJ_ACCEPTANCE_BASELINE.md` | Governing | Engineer | Permanent regression suite (14 areas → tests). |
| `WLJ_DOCUMENTATION_INVENTORY.md` | Reference | All | 186-doc classification + the 14 uncertain docs. |
| `WLJ_OPS_WALL_COVERAGE.md` | Operational | Operator | Observability coverage + OPS-1…10 backlog. |
| `WLJ_CURRENT_CONTEXT_HELP_COVERAGE.md` | Reference | Engineer | Page-coverage audit + CC/HELP backlog. |
| `WLJ_RELEASE_POLICY.md` | Governing | All | Three publication levels. |
| `WLJ_PRODUCTION_RUNBOOKS.md` | Operational | Operator | Failures, rollback, recovery, streaming, OpenAI, workers, Redis, Postgres. |
| `WLJ_SECURITY_PRIVACY_RETENTION.md` | Governing | Engineer | Ownership, 72h image retention (locked), audit, provenance. |
| `WLJ_KNOWN_LIMITATIONS.md` | Reference | All | Honest, phased limitations. |

## D. Project operating doc

| Title | Authority | Audience | Status | Purpose |
|---|---|---|---|---|
| `CLAUDE.md` (repo root) | Governing | Engineer | CURRENT | The in-repo operating instructions Claude Code loads each session. Should reference this package; keep in sync when governing docs move. |
| `docs/wlj_claude_changelog.md` | Operational | Engineer | CURRENT | Level-1 technical changelog (every commit). |
| `docs/wlj_claude_troubleshoot.md` | Reference | Engineer | CURRENT | Known-issue patterns (check first). |

## E. Historical & archived (preserved, not current)

Do **not** treat these as current design. The retired reasoning-engine ("Conductor / lanes / classifier / in-process Beth") docs are bannered HISTORICAL and must not be restored without a Constitutional Review.

- Full classification (95 CURRENT / 39 HISTORICAL / 3 SUPERSEDED / 49 ARCHIVE): `docs/WLJ_DOCUMENTATION_INVENTORY.md`.
- Retired startup material (superseded by this package): `@WLJ_SYSTEM_PROMPTS/00_CORE_STARTUP/*` and the earlier mode/reference folders `01_`–`08_` (supporting/legacy; consult only for history).
- **14 boundary docs pending Danny's judgment** before final classification — see inventory §6.

---

*Keep this index current: when a governing doc is added, moved, or reclassified, update the matching row here in the same change.*
