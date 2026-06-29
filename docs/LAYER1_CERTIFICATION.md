# WLJ Layer 1 — Canonical Truth Foundation — CERTIFIED & FROZEN

> **Status: CERTIFIED · FROZEN · FOUNDATION COMPLETE**
> **Certification date:** 2026-06-29
> **Certified commit:** `d6c187f734be0e020d56e42e2eacc91285b5db05`
> **Certification tag:** `layer1-canonical-truth-v1`
> **Acceptance:** Smoke GREEN · Full GREEN · Deep GREEN · Production-validated on real customer conversations
>
> This is the permanent engineering baseline. Layer 1 is the bedrock the rest of WLJ
> is built on. It changes only through formal change control (see §Change Control).

---

## 1. What Layer 1 is

Layer 1 — **Canonical Truth** — is the deterministic foundation that lets WLJ retrieve
the user's truth correctly, trust it, and speak it without contradiction. It is not a
feature; it is the substrate every higher layer consumes. A value is not "truth" in
WLJ unless it carries **value + freshness + confidence + stability**, is retrieved
deterministically, and renders in human-ready language.

## 2. Certified platform capabilities (8 — COMPLETE · CERTIFIED · FROZEN)

| Capability | Module | What it guarantees |
|---|---|---|
| **Per-Day Truth** | `apps/health/services/daily_health_queries.py` | A specific day's value (today/yesterday/date), never an average |
| **Freshness** (Law 1) | `apps/core/truth/freshness.py` | current/stale/pending/partial/missing — read, never inferred |
| **Confidence** (Law 2) | `apps/core/truth/confidence.py` | high/medium/low/none from freshness+coverage+source |
| **Stability** (Law 5) | `apps/core/truth/stability.py` | same question + unchanged data ⇒ same answer (signatures) |
| **Current Truth Objects** | `apps/core/truth/current.py` | one typed object composing value+freshness+confidence |
| **Point-in-Time History** | `apps/core/truth/history.py` + `periods.py` | "what was my X over a period" + aggregates |
| **Domain Truth Objects** | `apps/core/truth/domain.py` | one canonical interface per domain (`get_domain_truth`) |
| **Deterministic Provider Registry** | `apps/ai/chatgpt_cos/fact_registry.py` | a domain registers a provider instead of branching dispatch |

**Supporting truth layers also certified:** the Human-Ready Conversation Layer
(`apps/core/truth/render.py` user-preference date/time rendering; deterministic
conversation memory + active-topic follow-ups; clinical interpretation/temporal
sanity; Executive Briefing significance ranking). The **Truth Catalog**
(`apps/core/truth/catalog.py`) enumerates the answerable surface.

## 3. Acceptance results

- **Smoke: GREEN · Full: GREEN · Deep: GREEN** (production Acceptance Center).
- **Production validation:** real customer conversations completed without a
  trust-breaking response (clinical safety, temporal sanity, continuity, holistic
  synthesis, no internal leakage, calorie totals).
- **Deterministic gate:** `python manage.py certify_layers` re-runs the Layer 1 test
  modules; manifest `apps/core/truth/certification.py`.

## 4. Engineering risks permanently eliminated

- **Dangerous clinical misinterpretation** — a low glucose can never be narrated as
  "good/in range" (single canonical interpreter; LLM never makes clinical claims).
- **Impossible timestamps** — a future-dated reading is never reported as a real time.
- **Truth contradiction** — the value answer and every follow-up originate from the
  same deterministic struct (LLM rephrase bypassed for timestamped/clinical/numeric facts).
- **Conversation amnesia** — "why do you say that / at what time" answered from
  deterministic memory, not LLM reconstruction.
- **Domain-weighted prioritization** — the briefing leads by significance, not domain name.
- **Internal leakage** — storage/field/SAE names never reach the user.

## 5. Known future work (NOT Layer 1 — Future Backlog / higher layers)

- Per-domain rollout of Current Truth Objects + History to Tasks/Journal/Calendar/
  Faith/Relationships beyond their thin registrations (Layer 2/3 application).
- "What changed / what's unusual" history-delta tier in the Executive Briefing.
- Truth Catalog as a first-class consumer surface; Freshness state-simulation harness
  for the live Deep matrix. (See `certification.py::future_backlog`.)

## 6. Change control (Layer 1 is now immutable except via this process)

Any modification to a Layer 1 module is treated like a database-schema change and requires:
1. Repository evidence of the defect/need.
2. Architectural justification (which capability, why it must change here).
3. Regression test + the deterministic Layer 1 gate GREEN (`certify_layers`).
4. Smoke + Full + Deep GREEN.
5. Production validation if behavior changes.

No direct edits. Future improvements belong in Layer 2+.
