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
| `WLJ_CONVERSATION_STATE_ARCHITECTURE.md` | Governing | Engineer | AWAITING VALIDATION | **Conversation State — the deterministic authority for "what are we talking about / doing / waiting on" (distinct from Current Context's "what page").** Conversation-scoped (`AssistantConversation.metadata["conversation_state"]`); tracks active subject/artifacts + reads-through pending confirmations; surfaced as a salient lead in `ModelInterfaceService`. WLJ owns the state; the model reasons over it (constitutionally compliant, no Review). Read before any follow-up/pronoun/pending-confirmation/active-artifact continuity work. |
| `WLJ_VISUAL_TRUTH_CONTRACT.md` | Governing | Engineer | CURRENT | Only real completion may look complete (Article V.1). |
| `WLJ_EXECUTIVE_REFLECTION_ARCHITECTURE.md` | Governing | Engineer | CURRENT | Reflection observes, never overrides. |
| `LAYER1_DOMAIN_FRAMEWORK.md` | Governing | Engineer | CURRENT | How a new canonical truth domain is built (Article III.1). |
| `WLJ_MEAL_INTELLIGENCE_ARCHITECTURE.md` | Governing | Engineer | CURRENT | **Meal Intelligence domain v1.0** — canonical food-lifecycle architecture. Meals owns operational recipe truth (Legacy projects meaning); supply is household-scoped, consumption/health person-scoped; two authoritative ledgers (inventory, consumption); *Capture Once, Reuse Everywhere*. Read before ANY meal/nutrition/pantry/recipe/shopping work. |
| `WLJ_MEAL_INTELLIGENCE_TRUTH_CERTIFICATION.md` | Governing | Engineer | CURRENT | Certification standard for each food truth — 7 gates, M0–M5 maturity ladder, per-truth register (owner/primary-truth/maturity/criteria/representative deterministic questions). The bar Meal Intelligence must clear to be a certified truth domain. |
| `WLJ_MEAL_INTELLIGENCE_ROADMAP.md` | Reference | Engineer | CURRENT | Implementation milestones (M1 consolidation → M2 recipe enrichment → M3 lifecycle spine → M4 supply intelligence → M5 automation → M6 external). Foundations first (recipe-structured-at-write; prep/consume spine). No time estimates; next milestone = implementation. |
| `WLJ_MODEL_INTERFACE_DESIGN.md` | Reference | Engineer | CURRENT | The Model Interface seam + executive context envelope. |
| `WLJ_TRUTH_SURFACES.md` | Governing | Engineer | CURRENT | **Validated as-built catalog of the 7 deterministic Truth Surfaces** the CoS reasons from (Current/Standing Context, Personal Truth, DomainTruth, Domain Entity, Executive Briefings, Decision Authority). Complementary not competing. Key principle: a missing provider changes WHICH surface answered, not whether it's possible. Read before assuming a "gap." |
| `WLJ_CERTIFICATION_BACKLOG.md` | Governing | Engineer | CURRENT | **The certification-driven operating model + evidence-ranked backlog** (measured vs NOT-YET-MEASURED). The roadmap driver: certification, not intuition. Companion: `WLJ_CUSTOMER_TRUTH_CERT_PROD1.md` (production scorecard), `WLJ_CUSTOMER_TRUTH_CERT_SLICE1.md` (local slice), `WLJ_TRUTH_RETRIEVAL_CERTIFICATION_AUDIT.md`, `WLJ_TRUTH_RETRIEVAL_COVERAGE.md`. |
| `WLJ_COS_DOMAIN_CERTIFICATION_STANDARD.md` | Governing | Engineer | CURRENT | **The RATIFIED 5-step per-domain completeness process (2026-07-19), extracted from Nutrition + Journal (both prod-complete).** (1) verify deterministic truth → (2) expose existing truth (exposure precedes new truth) → (3) validate conversational routing (routing is a separate layer; drift-proof metadata from ONE source) → (4) Danny production validation (the gate) → (5) close. Invariants: WLJ never renders a verdict; retrieve/search/analyze are distinct discoverable tools. Also folded into `03 §3d`. Run for every future CoS domain (Faith next). |
| `WLJ_TRUTH_VALIDATION_CENTER.md` | Governing | Engineer | CURRENT | **The deterministic CoS-vs-WLJ validator (Owner-2 instrument), built 2026-07-19.** One engine typed by `validation_type` (extends the Acceptance engine — no parallel framework); resolves each object by the app's own selection rule (visible resolution card); grades the CoS answer against WLJ truth deterministically (no model grades a model); classifies failures by first-failing-layer into an executive category breakdown; resolved/natural prompt modes. Read before ANY CoS certification/validation/truth-comparison work. **Altitude caveat:** certifies implementation layers (engineering diagnostic), not the operator's conversational certification. |
| `WLJ_CERTIFICATION_PLATFORM_FUTURE.md` | Reference | Engineer | **DEFERRED — first type OPENED** | The unified WLJ Certification Platform. Its **first type is now built** (the Truth Validation Center realizes the reserved design: one evidence-capturing runner typed by `validation_type`, two-owner model, discovery-suite work-list, first-failing-layer). Remaining types (CRUD/Reasoning/Executive/Check-in/Domain) plug into the same engine — still deferred; do not build ahead of need. |
| `WLJ_MULTIMODAL_INTAKE_ARCHITECTURE.md` | Governing | Engineer | CURRENT | **Canonical architecture for ALL multimodal intake** — how a person hands the CoS images/video/audio/documents/structured files and it becomes deterministic, provenance-bearing, permanently retrievable truth. ONE platform every domain leverages (never a per-domain upload path). The model perceives; WLJ never interprets bytes; perceived content becomes a normal named intent tagged `source_artifact_id`+`confidence`; one arrival path → one artifact seam → one truth spine (validate→dedup→confirm→execute→audit→link) → first-class retrieval. Read FIRST for ANY upload/attachment/perception/artifact/OCR/transcription/document-intake work. Execution companion: `WLJ_MULTIMODAL_INTAKE_ROADMAP.md`. |
| `WLJ_MULTIMODAL_INTAKE_ROADMAP.md` | Reference | Engineer | CURRENT | Execution companion to the multimodal architecture — production-readiness scorecard (ranked by customer impact), phased plan (Phase 0 harden → Phase 1 ChatGPT-parity intake), preserve-don't-rebuild list, and the living milestone status ledger. Implementation progress lives here + changelog, never in the governing doc. |
| `WLJ_REQUEST_PATH_SAFETY.md` | Governing | Engineer | CURRENT | Never compute/LLM on the request path. |
| `WLJ_RUNTIME_TRACE_DEBUGGING.md` | Governing | Engineer | CURRENT | Prove the runtime path before editing. |
| `WLJ_TIMESTAMP_PRECISION.md` | Governing | Engineer | CURRENT (Phase 1 shipped) | **A timestamp must never claim more precision than its source gave.** The reusable model `apps/core/truth/precision.py` (sibling of `temporal.py`): `Precision` vocabulary; `infer_precision`; `resolve_instant` (real time verbatim; date-only at noon **clamped ≤ now** — never future; precision reported); `format_instant` (honest per-precision render — DAY→"Today", never a clock time). Recommendation: first-class truth, adopted **per-domain, certification-gated**. Phase 1 (module + heart-rate/weight ingest dogfood) shipped 2026-07-20; Phase 2 (persist `observed_precision`) + Phase 3 (presentation) deferred with a full fabrication-site inventory. Read before ANY observed-timestamp ingest/display work. Principle folded into `03 §7`. |
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
