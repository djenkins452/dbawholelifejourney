# LAYER 1 CONSTITUTION — Canonical Truth Foundation

> **The single entry point for understanding Layer 1.** If you are about to touch
> anything that retrieves, interprets, renders, or speaks the user's data, read this
> document first. Layer 1 is **CERTIFIED & FROZEN** (2026-06-29). It is permanent
> infrastructure; you build *on* it, you do not redefine it.
>
> Certified commit `d6c187f7` · tag `layer1-canonical-truth-v1` · GitHub Release of the
> same name · Acceptance: Smoke GREEN · Full GREEN · Deep GREEN · production-validated.

---

## 1. What Layer 1 IS

The deterministic foundation that lets WLJ **retrieve the user's truth, trust it, and
speak it without contradiction.** A value is "truth" only if it carries
**value + freshness + confidence + stability**, is retrieved **deterministically**, and
is rendered in **human-ready language**. Layer 1 is the substrate every higher layer
consumes.

## 2. What Layer 1 is NOT

- **Not reasoning / intelligence.** It surfaces facts; it does not decide strategy,
  coach, or compose multi-step plans. (That is Layer 4+.)
- **Not the LLM's job.** The LLM may *narrate* truth; it may never *assert* it. Any
  fact with a timestamp, clinical interpretation, or gated numeric value is answered
  deterministically — the LLM rephrase is bypassed.
- **Not per-domain feature work.** Rolling Current Truth / History out to every domain
  is Layer 2/3 application work, not new Layer 1 capability.
- **Not a place for casual edits.** See §8 Change Control.

## 3. Responsibilities (what Layer 1 guarantees)

1. **Deterministic retrieval** — the same question + unchanged data ⇒ the same answer.
2. **A complete fact object** — value + timestamp + freshness + confidence + interpretation.
3. **Freshness, read not inferred** — current / stale / pending / partial / missing.
4. **Confidence** — high / medium / low / none, from freshness + coverage + source.
5. **Clinical & temporal safety** — dangerous values are flagged, never reassured;
   impossible/future timestamps are never reported as real.
6. **Truth consistency** — the value answer and every follow-up originate from the
   same struct, so they can never contradict.
7. **Human-ready language** — user-preference dates/times; no ISO/UTC/24-hour/field/SAE leakage.

## 4. Non-responsibilities (explicitly out of scope)

Cross-domain correlation, recommendations, prioritized planning, proactive coaching,
goal strategy, and conversational reasoning beyond active-topic follow-ups. These
belong to higher layers and must *consume* Layer 1, not extend it.

## 5. Public interfaces (use these; do not bypass them)

| Need | Use | Module |
|---|---|---|
| A domain's truth | `get_domain_truth(user, domain)` → `.current()/.history()/.state()` | `apps/core/truth/domain.py` |
| Current value object | `CurrentTruth` | `apps/core/truth/current.py` |
| History over a period | `HistorySeries` + `resolve_period` | `apps/core/truth/history.py`, `periods.py` |
| Freshness verdict | `classify_period_freshness` / `classify_sync_freshness` | `apps/core/truth/freshness.py` |
| Confidence verdict | `confidence_from_*` / `combine` | `apps/core/truth/confidence.py` |
| Stability signature | `truth_signature` / `verify_stable` | `apps/core/truth/stability.py` |
| Clinical interpretation | `classify_glucose_mg_dl` / `interpret` | `apps/health/services/glucose_interpretation.py` |
| Temporal sanity | `validate_timestamp` / `is_future` | `apps/core/truth/temporal.py` |
| User-ready date/time | `render_date/time/datetime/relative_time` | `apps/core/truth/render.py` |
| Register a Beth fact provider | `register_fact_provider` | `apps/ai/chatgpt_cos/fact_registry.py` |
| Answerable-truth catalog | `truth_catalog` / `can_answer` | `apps/core/truth/catalog.py` |
| The morning briefing | `build_executive_briefing` | `apps/core/truth/briefing.py` |

**Rule:** never query raw models or format timestamps yourself in higher-layer code —
go through these interfaces.

## 6. Consumers

Beth (foundational fast path + conversation memory), the Executive Briefing, dashboards,
reports, exports, notifications, domain engines, cross-domain engines, and every future
interface. All read the same objects.

## 7. Architecture Laws governing Layer 1

Per `docs/WLJ_ARCHITECTURE_LAWS.md` (the constitution above the code): Law 0 Intent
Before Retrieval · Law 1 Freshness · Law 2 Confidence · Law 4 Deterministic Retrieval ≠
AI failure · Law 5 Stable Truth. Layer 1 implements the Answer Precondition Pipeline
(Intent → Scope → Freshness → Completeness → Confidence → Strategy → Retrieve →
Stability → Reason → Narrate).

## 8. Change Control (Layer 1 is immutable except through this)

Treat any edit to a Layer 1 module like a **database-schema change**. Required:
1. **Repository evidence** of the defect/need.
2. **Architectural justification** — which capability, why it must change here.
3. **Regression test** + the deterministic gate GREEN (`python manage.py certify_layers`).
4. **Smoke + Full + Deep** GREEN (Acceptance Center).
5. **Production validation** if behavior changes.

No direct edits. CI runs the **Layer 1 Certification Gate** on every merge
(`.github/workflows/test.yml`); no higher layer may bypass it.

## 9. Certification history

- 2026-06-28 — 8 platform capabilities implemented; Confidence + Stability ratified;
  deterministic gate GREEN; governance reconciliation (inventory defines scope).
- 2026-06-29 — Production Smoke/Full/Deep GREEN + real-conversation validation →
  **CERTIFIED & FROZEN**; tag `layer1-canonical-truth-v1`; GitHub Release; CI gate
  made mandatory.

## 10. Guaranteed behaviors (regression-locked)

- A low glucose is never called "good/in range."
- A future timestamp is never reported as a real time, on any path.
- "What is my glucose?" → "At what time?" can never contradict.
- "Why do you say that? / At what time? / Should I be concerned?" answer
  deterministically from the same fact, on the active topic.
- Calorie questions return a numeric total (0 when none); meal questions return meals.
- The briefing leads by significance (danger → time-critical → magnitude), not domain.
- No internal field/SAE/storage names ever reach the user.

## 11. Known constraints (NOT Layer 1 — Future Backlog / higher layers)

- Current Truth / History rolled out to every domain beyond thin registrations (L2/L3).
- "What changed / what's unusual" history-delta tier in the briefing.
- Freshness state-simulation harness for the live Deep 5-state matrix.
- The Acceptance Center live Deep run requires the production OpenAI stack (cannot run
  in CI; the deterministic gate is the CI enforcer).

See `apps/core/truth/certification.py::future_backlog` and
`docs/BETH_LAYER1_TRUTH_INVENTORY.md` for the authoritative lists.

---

*Layer 1 is permanent bedrock. Build upon it; do not redefine it.*
