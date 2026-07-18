# 99 · Reference Index — master table of contents

**Responsibility of this document:** the map. Every governing document — where it is, its authority, who it's for, whether it's current or historical, and what it's for. The startup package is the onboarding experience; the supporting library is the detail. Read the startup package; reach into the library on demand.

Legend — **Authority:** Constitutional / Governing / Reference / Operational. **Audience:** All (ChatGPT+Claude+Danny) / Engineer / Operator. **Status:** CURRENT / HISTORICAL.

---

## A. The startup package (drag in this ONE folder; read in order)

| # | Title | Authority | Audience | Status | Purpose |
|---|---|---|---|---|---|
| 00 | NEXT CHAT STARTUP | Operational | All | CURRENT (regenerated) | **START HERE** — the bootloader. Live sprint state only; the one temporary file; shrinks over time. Points you at the rest. |
| 01 | READ FIRST — Architecture | Governing | All | CURRENT | **WHAT WLJ is** — vision, the OpenAI pivot, current architecture & maturity, lessons. |
| 02 | WLJ Constitution | **Constitutional** | All | CURRENT | **WHAT MUST NOT CHANGE** — protected Articles + Constitutional Review (default NO). The apex. |
| 03 | Engineering Operating Guide | Governing | Engineer | CURRENT | **HOW TO BUILD SAFELY** — tracing, root-cause proof, gates, deploy/doc discipline. |
| 04 | Danny Working Preferences | Governing | All | CURRENT | **HOW TO WORK WITH DANNY** — communication, workflow, product/investigation/decision/life philosophy. |
| 98 | Session Transition Protocol | Governing | All | CURRENT | **HOW TO CLOSE A CHAT** — the doctrine (executed by root `99_PREPARE_NEXT_CHAT.md`). |
| 99 | Reference Index | Reference | All | CURRENT | **WHERE EVERYTHING IS** — this file. |

*The package is self-contained: dragging in `00_WLJ_CHIEF_OF_STAFF_STARTUP/` is all a new session needs. Only `00_NEXT_CHAT_STARTUP.md` is temporary; the other six are evergreen.*

## A2. End-of-chat executor (at the `@WLJ_SYSTEM_PROMPTS/` root — NEVER loaded into a new chat)

| File | Authority | Audience | Status | Purpose |
|---|---|---|---|---|
| `99_PREPARE_NEXT_CHAT.md` | Operational | All | CURRENT | Dropped at the **end** of a working chat. Runs the transition, produces the Transition Audit, rewrites `00_NEXT_CHAT_STARTUP.md`. Permanent but action-oriented — that's why it stays outside the package. |
| `00_README_LOAD_MANIFEST.md` | Reference | All | CURRENT | Library load-guidance + the permanent startup/transition workflow diagram. |

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
| `WLJ_MEAL_INTELLIGENCE_ARCHITECTURE.md` | Governing | Engineer | CURRENT | **Meal Intelligence domain v1.0** — canonical food-lifecycle architecture. Meals owns operational recipe truth (Legacy projects meaning); supply is household-scoped, consumption/health person-scoped; two authoritative ledgers (inventory, consumption); *Capture Once, Reuse Everywhere*. Read before ANY meal/nutrition/pantry/recipe/shopping work. |
| `WLJ_MEAL_INTELLIGENCE_TRUTH_CERTIFICATION.md` | Governing | Engineer | CURRENT | Certification standard for each food truth — 7 gates, M0–M5 maturity ladder, per-truth register (owner/primary-truth/maturity/criteria/representative deterministic questions). The bar Meal Intelligence must clear to be a certified truth domain. |
| `WLJ_MEAL_INTELLIGENCE_ROADMAP.md` | Reference | Engineer | CURRENT | Implementation milestones (M1 consolidation → M2 recipe enrichment → M3 lifecycle spine → M4 supply intelligence → M5 automation → M6 external). Foundations first (recipe-structured-at-write; prep/consume spine). No time estimates; next milestone = implementation. |
| `WLJ_MODEL_INTERFACE_DESIGN.md` | Reference | Engineer | CURRENT | The Model Interface seam + executive context envelope. |
| `WLJ_TRUTH_SURFACES.md` | Governing | Engineer | CURRENT | **Validated as-built catalog of the 7 deterministic Truth Surfaces** the CoS reasons from (Current/Standing Context, Personal Truth, DomainTruth, Domain Entity, Executive Briefings, Decision Authority). Complementary not competing. Key principle: a missing provider changes WHICH surface answered, not whether it's possible. Read before assuming a "gap." |
| `WLJ_CERTIFICATION_BACKLOG.md` | Governing | Engineer | CURRENT | **The certification-driven operating model + evidence-ranked backlog** (measured vs NOT-YET-MEASURED). The roadmap driver: certification, not intuition. Companion: `WLJ_CUSTOMER_TRUTH_CERT_PROD1.md` (production scorecard), `WLJ_CUSTOMER_TRUTH_CERT_SLICE1.md` (local slice), `WLJ_TRUTH_RETRIEVAL_CERTIFICATION_AUDIT.md`, `WLJ_TRUTH_RETRIEVAL_COVERAGE.md`. |
| `WLJ_CERTIFICATION_PLATFORM_FUTURE.md` | Reference | Engineer | **DEFERRED (future initiative)** | The unified WLJ Certification Platform discovered this milestone — DO NOT implement; open as its own initiative only AFTER CoS Truth is production-validated. Production Test Plans = orchestration; subsystems = providers. |
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
| `WLJ_OPERATIONS_VISION.md` | Governing | Engineer | **The WLJ Operations subsystem (architecture FROZEN 2026-07-11)** — Layer 1 truth domain; internal architecture + object model + package layout + import boundaries; recovery classification (R0–R4), lifecycle, maturity model (O0–O5); living roadmap + ledger. **Phase I visibility + Phase II framework + Phase II-B expanded R1 (three dark handlers / two shapes, incl. maturity-staleness coverage) SHIPPED (dark)**; Phase III deferred (evidence-gated); next = controlled production enablement. |
| `WLJ_OPERATIONS_PHASE2_PLAN.md` | Reference | Engineer | Deterministic Recovery engineering plan (IMPLEMENTED, ship-dark) + risk register; §11.1 production-enablement runbook; §14 handler comparison + evidence-backed Phase III deferral. |
| `WLJ_OPS_WALL_COVERAGE.md` | Operational | Operator | Observability coverage + OPS-1…10 backlog (Phase I as-built). |
| `WLJ_CURRENT_CONTEXT_HELP_COVERAGE.md` | Reference | Engineer | Page-coverage audit + CC/HELP backlog. |
| `WLJ_RELEASE_POLICY.md` | Governing | All | Three publication levels. |
| `WLJ_PRODUCTION_RUNBOOKS.md` | Operational | Operator | Failures, rollback, recovery, streaming, OpenAI, workers, Redis, Postgres. |
| `WLJ_SECURITY_AUTHORIZATION_FRAMEWORK.md` | Governing | Engineer | **RATIFIED 2026-07-18 (architecture only — not implemented).** The complete long-term *authorization* model: primitives **Identity · Space · Capability · Ownership · Delegation · Trust**; one deterministic PDP; roles = capability bundles; **Space is the canonical container** (every resource belongs to exactly one; ownership/capabilities/authorization evaluated within a Space; the Platform is NOT a Space); AI is a derived principal that never self-authorizes; platform authority is separate from data ownership. Fits within the Constitution (no Review; Article VI NOT created). Distinct from `WLJ_SECURITY_PRIVACY_RETENTION.md` (that = privacy/retention/audit-of-data; this = who-may-do-what). Read before ANY authorization/identity/admin/sharing/AI-authority work. |
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
- Retired startup material (superseded by this package): `@WLJ_SYSTEM_PROMPTS/_ARCHIVE_SUPERSEDED_STARTUP/*` (the former `00_CORE_STARTUP` docs) and the earlier mode/reference folders `01_`–`08_` (supporting/legacy; consult only for history).
- **14 boundary docs pending Danny's judgment** before final classification — see inventory §6.

---

*Keep this index current: when a governing doc is added, moved, or reclassified, update the matching row here in the same change.*
