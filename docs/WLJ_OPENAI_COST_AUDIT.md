# WLJ — OpenAI API Cost Audit (Forensic, Read-Only)

**Date:** 2026-08-16 · **Type:** forensic cost attribution · **Status:** READ-ONLY investigation, NO code/config changes made.
**Trigger:** Danny's OpenAI account began auto-charging ~$16–17 repeatedly, multiple charges in short periods, after historically being weeks/months apart.
**Scope:** determine *what generates OpenAI calls* and *which paths plausibly explain the recent surge*. Do not solve; prove.

> **Authoritative $ source not accessible to this audit:** the exact dollar history lives in Danny's
> **OpenAI usage dashboard** (platform.openai.com → Usage / Cost), which only Danny can open. This report
> attributes calls from **code + git evidence**; the dashboard's per-day cost + model breakdown is the one
> external fact that would confirm the ranking below in minutes and should be checked first.

---

## 1. Executive conclusion

**The surge is overwhelmingly explained by Claude's own certification / `cos-run` testing traffic during 2026-08-12 → 08-16, made more expensive per-turn by the Executive Synthesis Phase-2 feature that landed 08-13.** Three lines of evidence converge:

1. **Timing.** The acceleration coincides exactly with an intense CoS certification burst — 30+ `fix(cos)`/`feat(cos)` commits Aug 12–16 (`git log`), each validated by Claude with **real-model** `cos-run` turns (this is how the certification program was run). `cos-run` makes real, billable OpenAI calls identical to production (§4).
2. **Per-turn cost multiplier.** On **2026-08-13** bounded **Executive Synthesis Phase 2** was introduced (`4093c6e9`), and on 08-12 the `model_interface` tool loop was widened to **7 rounds / 3500 output / 64k input governor**. After that, every *broad* CoS turn costs **1 extra provider request (synthesis) + up to 8 tool-loop requests** instead of 1–2. Every certification broad turn Aug 13→16 paid this multiplier.
3. **Volume shape.** A single broad certification turn ≈ **3–9 billable requests**. A day of active certification (dozens of broad turns across natural-cert suites, multi-turn scripts, and repeated grounding runs) easily reaches **hundreds of requests** — matching *repeated* ~$16–17 replenishments *within short periods* (i.e. active working sessions), not a steady idle drip.

**Idle production is NOT the primary driver.** With Danny never opening the app, background OpenAI usage is only the proactive layer: **Daily Executive Brief + Midday Alignment + Evening Wrap** — **~4–11 model calls per eligible user per weekday** (§9). For a handful of users that is on the order of **$1–5/day**, not $16 repeatedly. Background is a real, growing, *untracked* cost — and it has a latent amplifier bug (generation happens before suppression, §3) — but it is not what spiked.

**The deepest structural finding:** the primary CoS runtime (`model_interface`) **records no token or cost telemetry to any queryable table** (§5/§10). `ToolCallLog` has no model/token fields; the token tables (`AIUsageLog`, `LLMUsageEvent`) are bypassed by the tool loop and by synthesis. So the surge *cannot be reconstructed from the database* — only from raw app logs. **We are flying without a cost instrument.** That is the single most important thing to fix (observability), before any optimization.

---

## 2. Every OpenAI call path (inventory)

Every model call in the CoS funnels through **one class, `AIService`** (`apps/ai/services.py`), via three methods, all ending at `self.client.chat.completions.create(...)`:

| Seam | File:line | Shape |
|---|---|---|
| `AIService._call_api` | `services.py:493` (SDK call `:599`) | single-shot completion; retry ×2 |
| `AIService._call_api_with_tools` | `services.py:701` (SDK call `:810`) | **agentic tool loop**, up to `max_rounds+1` billable calls (loop `:793`) |
| `AIService._call_api_stream` | `services.py:1019` (SDK call `:1070`) | request-path streaming only |

The certified CoS `ModelInterfaceService.generate()` (`apps/ai/model_interface/service.py:1100`) → `_call_api_with_tools` (`:1125`) → optional Phase-2 synthesis (`apps/ai/model_interface/synthesis.py:305`, its own `chat.completions.create`).

**Classified callers:**

| Class | Path | Reaches model? |
|---|---|---|
| **USER INTERACTIVE** | `ModelInterfaceService.generate()` via chat / stream; legacy `PersonalAssistant`/ChatGPTCoS (also through `AIService`); `post_response_intelligence` → `life_fact_extractor` (`ai_memory/life_fact_extractor.py:160`) after each user turn | YES — the dominant *real-user* cost |
| **DEV / CERTIFICATION** | `cos-run` operator endpoint (`admin_console/views.py:3713`) → `run_cos_acceptance_turn/conversation` (`core/tasks.py:49,94`) → `CoSGateway.respond(surface="chat")` → `generate()`; also any test that hits the live model | YES — **billed identically to real chat**, `surface="chat"` (§4) |
| **SCHEDULED BACKGROUND** | Celery Beat + ISE registry | **NO** model calls except PGS (below). All ISE runners + Beat tasks are deterministic engines (§3) |
| **EVENT-TRIGGERED BACKGROUND** | `fire_intelligence` → `deferred_fire_intelligence` → `run_intelligence_chain` (`update_user_state` + `run_insights`/PRIE) | **NO** — insights & predictions are **rule-computed**, not model-generated |
| **PROACTIVE** | PGS (`run_proactive_guidance`, ISE, 15 min) → **Daily Executive Brief** (`generate()`), **Midday Alignment** + **Evening Wrap** (`checkin_author.author_checkin` → `_call_api`) | YES — the only idle-background model callers |
| **OTHER (data-dependent)** | `process_pending_captures` (transcription/summarization), email intake, audio/video Whisper transcription — fire only when the user created content; **zero when idle** | Conditional |

There are ~30 other `chat.completions.create` sites (scan, meals, health, capture, journal, legacy) but all are **user/request-triggered**, none on an idle schedule.

---

## 3. Scheduled-call inventory (Celery Beat + ISE)

**Two scheduler layers:** Celery Beat (`config/settings.py:1253-1384`, ~26 jobs) and **ISE** (`run_ise_cycle_task` every 300s → registry in `apps/core/ai_scheduler/scheduler_registry.py`, ~30 runners).

**Finding: exactly ONE scheduled task can reach OpenAI — `run_proactive_guidance` (PGS).** Every other ISE runner and every Beat task is a **deterministic engine** (grepped for the seam across `scheduler_runner.py` and all target modules — zero hits):

- **Deterministic (wake, never call model):** DBE `run_daily_briefings` (rule-composed, *not* the model brief), guidance refresh (PGE), cross-domain insights / PIE / PRIE synthetics (rule/prediction engines), reflection queue, executive scorecards, drift scoring, weekly pressure, CDCE, relational drift, CoS-prompt schedule + deliver (`apps/cos`), DNE delivery cycle (delivers *pre-built* items), situation compute (registry notes "no LLM"), cos_event_engine, maturity snapshots.
- **Deterministic Beat:** SAME cycle (60s), ISE cycle dispatcher (300s), `cos_keepalive` (30s — only *constructs* the client via `warm_openai_client`, `services.py:230`, **no API call**), health-briefing recompute (1800s), nightly signals/patterns/activity/momentum/celebrations, all reminder + digest jobs.
- **Post-write chain:** `update_user_state` (SAE 69-query builder) + `run_insights` (PIE→PRIE) — **rule-computed, zero model calls.**
- **Data-dependent (zero when idle):** `process_pending_captures` (300s) reaches the model *only if a user capture is stuck*; email intake; Whisper transcription — all need pending user artifacts.

**PGS cadence:** ISE 900s → 96 passes/day, gated to the user's local time window (quiet hours <7 / ≥22 skipped). Windows (`proactive_checkins.py:2516-2519`): morning 7–9, midday 10–12, afternoon 13–16, evening 17–21.

**⚠ Amplifier bug (latent, real):** in `_create_proactive_message`, the **model call fires BEFORE suppression**. Each generator checks its dedup gate (`already_sent(type)` / `_has_brief_today`) against *persisted* messages, then calls the model, then may suppress via affirmation/conversation-mode (`:1307`/`:1322`) → returns `None` → **nothing persisted** → dedup gate stays unmet → **next 15-min pass re-calls and re-bills the model.** The Daily Brief has a 600s `cache.add` lock bounding this to ~1/10 min; **Midday Alignment and Evening Wrap have NO lock** → a persistently-suppressed midday/evening re-bills **every 15 min for its entire window** (midday 3h ≈ up to 12 calls; evening 5h ≈ up to 20 calls) for **one** intended message. This is a genuine defect worth fixing (near-term), independent of the surge.

---

## 4. Proactive-call inventory (the only idle model callers)

All gated by `_get_proactive_users()` (`:2522`: active + `personal_assistant_enabled` + consent + `ai_enabled` + `ai_data_consent` + `assistant_proactive_checkins`):

| Path | Window / cadence | Gate | Model calls / execution |
|---|---|---|---|
| **Daily Executive Brief** (`:3111`→`:3053`, `generate()`) | morning 7–9, PGS 15 min | `_has_brief_today` false; 600s lock | **agentic broad turn ≈ 2–9** (7 rounds + synthesis, endpoint `model_interface`, budget `(7,3500)`) |
| **Midday Alignment** (`:2570`, `author_checkin`) | midday 10–12, **weekdays only**, 15 min | `already_sent('midday_alignment')` false | **1** (`_call_api`, `max_tokens=400`) |
| **Evening Wrap** (`:2672`, `author_checkin`) | evening 17–21, **daily**, 15 min | `already_sent('evening_wrap')` false | **1** (`_call_api`, `max_tokens=400`) |

The other ~18 PGS generators (medicine, tasks, nudges, birthday, faith, finance, relationship, goal, journal-intelligence, health-trend, etc.) produce **templated deterministic content** — no model call.

---

## 5. Certification / testing traffic (the surge driver)

- **`cos-run` is billed exactly like production.** It routes `CoSGateway.respond(surface=SURFACE_CHAT)` → `generate()`. It creates real `ToolCallLog` rows and makes real OpenAI requests.
- **No test/real tag exists.** Acceptance traffic is `surface="chat"` — identical to genuine user chat. The *only* separator is on a different table: `AssistantConversation.title` starts with `"[acceptance-test]"` / `"[acceptance-conversation]"` (`core/tasks.py:68,124`). `ToolCallLog` stores only numeric `conversation_id`, so test vs real is separable **only** by a title join — and even then only for *turn counts*, never tokens/cost.
- **Volume shape (git-evidenced).** Aug 12–16: `39b5f024, 5da1a67a, afa36f8c, fa87eb08, e44f676c, 00b3e180, 401a47c5, 4093c6e9, 9583b51b, 61fad3bc, e078903c, 361b9f92, ebd9cb67, 5ff90b27, cb5b7fed, 9869d3c9` + Milestone-1 natural cert (Tests A–F, multi-turn scripts) on 08-16. Each `fix(cos)` was validated with **real-model broad turns** (whole-life assessment, executive synthesis, grounding, disagreement). Many domains × multiple broad turns × multi-turn scripts × repeated grounding runs.
- **One test conversation ≠ one API call.** A broad certification turn = **initial call + up to 7 tool continuations + 1 synthesis** = typically **3–9 billable requests**; multi-turn scripts multiply by turn count. This session alone (Milestone-1 natural cert) ran ~6 `cos-run` turns, several broad → ~15–30 provider requests in one sitting. The full Aug 12–16 program is plausibly **hundreds to low-thousands** of provider requests — the direct explanation for repeated $16–17 charges *within active working sessions*.

**We cannot give the exact number from the DB** (no per-request/token table). It is recoverable only from retained app logs (`COS_TOOL_LOOP_MEASURE`, `COS_OPENAI_START/FINISH`, `MI_SYNTHESIS_CALL`) or the OpenAI dashboard.

---

## 6. Model & pricing configuration (as deployed)

| Role | Value | Source |
|---|---|---|
| Primary / CoS model | **`gpt-4o`** (env `OPENAI_MODEL`) | `settings.py:80`; `AIService.model` `services.py:297` |
| Synthesis model | **`gpt-4o`** (same `self.model`) | `synthesis.py:306` |
| Vision model | `gpt-4o` (env `OPENAI_VISION_MODEL`) — *not used by CoS image path; images inline into primary* | `settings.py:81` |
| Mini / fallback | `gpt-4o-mini` (env `OPENAI_MINI_MODEL`) | `settings.py:82` |
| `COS_MODEL` | `gpt-4o` — **effectively dead config** (only a display label `personal_assistant.py:2338`); runtime uses `OPENAI_MODEL` | `settings.py:88` |
| reasoning_effort / service_tier | **not set** (no o1/o3/o4 reasoning model configured) | grep-negative |
| max output tokens | CoS answer **3500**; synthesis **650**; default tool-loop 1000 | `services.py:92`; `synthesis.py:309` |
| input governor | **64,000** tokens/request budget | `services.py:106` |
| temperature | tool loop 0.7; synthesis 0.5 | `services.py:708`; `synthesis.py:282` |
| timeout | `model_interface` 45s; synthesis 35s (hard bound) | `services.py:56`; `synthesis.py:278` |

**Approximate gpt-4o pricing** (public list, date/config-dependent — treat as rough): **~$2.50 / 1M input, ~$10 / 1M output** (cached input cheaper). No reasoning-model premium is in play. **Recent config change that raised cost:** not the *model* (stable `gpt-4o`), but the **per-turn request count and prompt size** — Phase-2 synthesis (+1 request/broad turn, 08-13) and the 7-round / 64k-input tool budget (08-12). Cost-per-broad-turn rose materially in the exact window of the surge.

---

## 7. Executive Synthesis cost multiplier

For a representative **broad executive turn** (≥2 substantive truth surfaces → `synthesis_eligible`):

- **Phase 1** (`_call_api_with_tools`, `services.py:793` loop): 1 initial request + 1 request per tool-continuation round. Typical **2–4 requests**, hard cap **8** (`range(7+1)`); each re-sends the growing context (system prompt + standing context + tool schemas + accumulated tool results), bounded by the 64k input governor.
- **Phase 2** (`synthesis.py:305`): **+1 separate request** (no tools, `max_tokens=650`, 35s bound).
- **Total broad turn: ≈ 3–5 requests typical, up to 9** (+1 if forced-final returns empty, +2 on loop-exception fallback).

A **narrow factual turn** (0–1 surfaces, no synthesis): **1–2 requests** (single answer, or 1 tool round + 1 final).

**Multiplier: a broad executive turn is ≈ 2–5× the request count of a narrow turn, and materially more input-tokens** (multi-round context re-send + synthesis). Rough cost: narrow ≈ **$0.02–0.08**, broad ≈ **$0.10–0.40** per turn (input-dominated; exact figure needs the untracked token counts). Certification and the Daily Brief are *all broad turns* — the expensive kind.

---

## 8. Retry / failure amplification

- `LLM_MAX_RETRIES = 2` (`services.py:36`); backoff 1/2/4s; rate-limit backoff 30s. **OpenAI SDK `max_retries=0`** (`:218`) — no hidden SDK retries.
- **Tool loop (`_call_api_with_tools`): no retry** — single try/except; on failure → `_call_api` fallback (up to 2 attempts).
- **Circuit breaker** (`openai_rate_limited`, 120s) is checked **only in the streaming path** (`:1053`); the tool loop and `_call_api` do **not** consult it — a 429 storm is bounded by retry count, not the breaker.
- **Synthesis is a deliberate single hard-bounded call** (`synthesis.py:274-278`) that bypasses the retry loop *specifically to prevent* the prior >260s retry-storm incident. **This is fixed and correct.**
- **Where 1 turn → many requests:** tool loop (up to 8) + empty-final retry (+1) + loop-exception fallback (+2) + synthesis (+1) → worst case ~9–12 requests for one "turn." No evidence of a *current* runaway (the historical storm was the synthesis path, now bounded). The tool-loop fan-out is by-design, not a bug — but it is the mechanism that makes each broad turn expensive.

---

## 9. Idle-24-hour call estimate (Danny never opens WLJ)

**Per eligible user, weekday (happy path):**
- Daily Executive Brief: 1 execution ≈ **2–9 calls**
- Midday Alignment: 1 call
- Evening Wrap: 1 call
- **≈ 4–11 OpenAI calls / eligible user / weekday** (weekend drops midday → 3–10).

**Everything else = 0 when idle** (all ISE/Beat/post-write deterministic; captures/transcription/email need user content).

**Two multipliers that make the true number higher and which code alone cannot resolve:**
1. **Eligible-user count `N`.** Background cost = `N × (4–11)` calls/day. `N` is runtime data (how many users have proactive enabled — including any test accounts), not knowable from code. For `N=1` ≈ $1–4/day; for `N=10–20` ≈ $10–40/day. **If test/demo users have proactive enabled, they each incur a daily broad Brief.**
2. **Suppression re-bill bug (§3).** A persistently-suppressed Midday/Evening re-bills every 15 min through its window (up to ~12 / ~20 extra calls/user/day) because it has no lock. Bounded but real.

**Provable bound:** with `N` eligible users and no suppression churn, idle production makes **`N × ~4–11` gpt-4o calls/day**, the Brief being a broad (expensive) turn. The missing fact is `N` and whether any Brief/Wrap is chronically suppressed — both require a runtime counter that **does not exist today**.

---

## 10. Telemetry / observability assessment

**What the DB CAN answer:** CoS **turn** counts and **tool-invocation** counts per day/user/surface (`ToolCallLog`, `kind='response'` = 1/turn); whether synthesis ran (`result_digest.synthesis_used`); token/cost for the **legacy `_call_api` + streaming paths and tool-loop *fallbacks* only** (`AIUsageLog` `models.py:461`, `LLMUsageEvent` `owner_finance/models.py:93`, `DailyCostRollup`).

**What the DB CANNOT answer (the gap):**
- **OpenAI request count per day** — no per-request table; `ToolCallLog` rows ≠ requests (1 turn = 2–9 requests).
- **Tokens / cost for the normal `model_interface` tool loop** — `response.usage` is read at `services.py:816-818` but **only logged, never persisted**. `_log_usage` is called from `_call_api`/stream, **never from `_call_api_with_tools`**.
- **Tokens / cost for Phase-2 synthesis** — untracked entirely.
- **Test (Claude) vs real-user vs proactive attribution** — all `surface="chat"`; separable only via a fragile `AssistantConversation.title` join, and only for turn counts.

**Net: the dominant CoS traffic (the certified `model_interface` runtime) is the *least* instrumented.** The cost tables that exist (`owner_finance`) were built for the legacy path and are bypassed by the keeper runtime. This is the root reason the surge can't be reconstructed and must be fixed first.

---

## 11. Ranked cost attribution

| Rank | Source | Evidence | Est. share / volume | Confidence |
|---|---|---|---|---|
| **1** | **Claude certification / `cos-run` testing (Aug 12–16 + Milestone-1)** | 30+ CoS commits each validated with real-model broad turns; `cos-run` billed as production; broad turn = 3–9 requests; charges cluster *within* active sessions | **Majority of the surge** — hundreds→low-thousands of requests in the window | **HIGH** (timing + mechanism); exact count needs logs/dashboard |
| **2** | **Executive Synthesis Phase-2 multiplier (08-13) + 7-round/64k tool budget (08-12)** | `4093c6e9`, `synthesis.py` (+1 request/broad turn); `services.py:92-106` | Amplifies #1 and every broad turn (cert + real + Brief) by ~1.5–2× cost | **HIGH** |
| **3** | **Proactive background (Brief + Midday + Evening)** | §4; 3 model callers; Brief is a broad turn | ~4–11 calls/user/weekday × N users; modest unless N large | **MEDIUM** (needs N) |
| **4** | **Suppression re-bill bug (midday/evening, no lock)** | §3 `_create_proactive_message` ordering | Up to ~12–20 extra calls/user/day *if* chronically suppressed | **MEDIUM-LOW** (conditional) |
| **5** | **Real interactive Danny use** | normal chat + `life_fact_extractor` per turn | Real but historically modest; not the recent spike | **MEDIUM** |
| **6** | **Retry amplification** | §8 | Bounded; historical storm already fixed | **LOW** (not a current driver) |
| — | Scheduled/ISE/Beat/post-write intelligence | §3 — all deterministic | **~$0** | **HIGH** |

---

## 12. Recommendations — IMMEDIATE (stop unnecessary spend; preserve function)

*(Recommendations only — nothing implemented per the read-only mandate.)*

1. **Gate real-model certification behind an explicit, rate-limited discipline** (§15). The single biggest lever: stop re-running broad `cos-run` suites for every code change. This alone would have avoided most of the surge.
2. **Confirm the driver in 5 minutes via the OpenAI dashboard** (Danny): check Usage → per-day cost + model. Expect spikes on Aug 12–16 aligned to certification sessions, `gpt-4o` only. This validates rank #1 externally.
3. **Check `N` (eligible proactive users)** and whether any **test/demo accounts have `assistant_proactive_checkins` enabled** — each incurs a *daily broad Brief*. Disabling proactive on non-Danny/test accounts removes that idle cost with zero product impact. *(Operational toggle, not code.)*
4. **Do not resume high-volume model testing** until observability (below) exists — we currently cannot see what we spend.

## 13. Recommendations — NEAR TERM (observability + guardrails)

1. **Persist token/cost on the keeper runtime.** Wire `response.usage` (already read at `services.py:816-818`) + model name from `_call_api_with_tools` **and** synthesis into `LLMUsageEvent`/`AIUsageLog` (the tables already exist). One row per provider request. This closes the core gap in §10.
2. **Tag surface/source.** Add a distinct `surface`/`source` for certification (`cos_run`/`acceptance`) so test traffic is separable from real use in telemetry — not via a title join.
3. **A read-only operator cost endpoint** (`api/claude/cost-audit/?from=&to=`) returning calls/day, tokens/day, est-cost/day, split by surface/model/proactive-vs-interactive-vs-cert — so this audit is a query, not a forensic exercise.
4. **Fix the suppression re-bill bug** (§3): suppress *before* generating, or give midday/evening the same `cache.add` lock the Brief has. Pure waste elimination.
5. **A soft daily budget alarm** (log/notify at $X/day) — visibility, not a hard cap, to preserve function.

## 14. Recommendations — LONG TERM (architecture-neutral efficiency)

1. **Right-size the tool loop.** 7 rounds + 64k input is generous; measure real round-distribution (most broad turns exit in 2–4) and consider a lower default with escalation — fewer context re-sends is the main input-token lever.
2. **Cheaper model for the small proactive authors.** Midday/Evening are 400-token templated authorings — candidates for `gpt-4o-mini` (they don't need flagship reasoning). Keep the Brief on `gpt-4o` (broad synthesis). *(Product/quality call — Danny decides.)*
3. **Prompt-cache the stable system prefix** (constitution + tool schemas are identical every call) to cut input cost on the multi-round loop. Architecture-neutral.
4. **Consolidate proactive model callers** so multiple systems can't independently pay to reason over the same state.

## 15. Recommended development-testing discipline

| Tier | What | When |
|---|---|---|
| **T1 — Deterministic/local** | Django unit tests, mocked `generate()`, catalog/registry certifiers, `manage.py check`, contract tests | **Default. Every change.** No model calls. |
| **T2 — One real-model smoke** | A *single* `cos-run` broad turn post-deploy to confirm the path is alive/grounded | Once per deploy of a CoS-affecting change. |
| **T3 — Repeated real-model runs** | Multiple broad/multi-turn `cos-run` runs | **Only** when actively investigating *stochastic* grounding/reasoning behavior — and stop once the behavior is characterized. |
| **T4 — Large natural-cert suite** | Full Tests A–F / domain sweeps | **Only at a major product milestone**, once — not per iteration. |

**Retrospective impact:** the Aug 12–16 program ran what were effectively T3/T4 volumes on nearly every commit. Under this discipline the same functional outcome would have used **one T2 smoke per deploy + a single T4 suite at the end** — plausibly a **~80–95% reduction** in certification request volume, i.e. most of the surge avoided, with no loss of certification confidence (the deterministic catalogs already prove exposure; the model runs only confirm grounding).

---

## Guardrail compliance

No models changed, no schedules altered, no proactive behavior modified, no synthesis/retry/caching/budget changes, **no code changes of any kind.** This document is the only artifact. Optimization is deferred to Danny's review.
