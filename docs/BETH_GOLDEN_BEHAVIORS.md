# Beth Golden Behaviors — Production Stability Baseline

> **Status:** Authoritative line-in-the-sand for the Chief of Staff (CoS / "Beth").
> **Constitution:** governed by `BETH_ARCHITECTURAL_PRINCIPLES.md` (principles outrank this doc).
> **Behaviors stabilized at:** commit `35c27f58` — *"persistent thinking placeholder across navigation"* — and unchanged since (later commits are governance docs only).
> **Baseline tag:** ✅ `beth-stable-v1` — **CUT & PUSHED** at `b56b223e` (production-validated 2026-06-25). This is the protected production baseline; see `BETH_ROLLBACK_AND_RECOVERY.md`.
> **Last updated:** 2026-06-25

This document formally defines the behaviors that are **production-stable and
regression-sensitive**. Any change that alters one of these behaviors is a
regression unless it is an explicit, reviewed, intentional improvement that
preserves the guarantee. See `BETH_CHANGE_CONTROL.md` for the required process.

> **Naming boundary (applies to every behavior below):** the assistant name is
> user-configurable (`cos_display_name`). NEVER hardcode "Beth" in user-facing
> copy, fixtures, or UI strings. "Beth" in this doc and in code/changelog is the
> internal/dev name only.

---

## GB-1 — Conversation Durability

| ID | Behavior | Source of truth |
|----|----------|-----------------|
| GB-1.1 | A submitted question survives navigation to another module. | `templates/components/chat_widget.html`, `assistant_panel.html` (pending marker `wlj_chat_pending` / `wlj_ap_pending`) |
| GB-1.2 | A submitted question survives a hard refresh (F5). | sessionStorage pending marker re-derived on load |
| GB-1.3 | Background generation continues after the user navigates away. | `apps/ai/chatgpt_cos/tasks.py::run_chatgpt_cos_generation` (Celery task, independent of the SSE connection) |
| GB-1.4 | The completed answer persists and eventually appears **without reissuing** the question. | task persists `AssistantMessage`; recovery poll (`pollPendingReply` / `apPollPendingReply` / `watchBethCompletion`) surfaces it |
| GB-1.5 | A long-running answer (≥12s) produces a durable completion notification (bell + deep-link + toast). | `tasks.py::_notify_beth_completion` (reuses `core.Notification`, category `intelligence`) |
| GB-1.6 | The "thinking" indicator reappears after navigation and after refresh while a request is in flight. | `ensureThinkingPlaceholder()` / `apEnsureThinking()` |

**Invariant:** the SSE relay disconnecting (navigation) must NEVER cancel the
background task — disconnect ends an observer only (`apps/ai/chat_stream_bus.py`,
`apps/ai/views.py::_chat_relay_stream` GeneratorExit handling).

---

## GB-2 — User Experience Integrity

| ID | Behavior |
|----|----------|
| GB-2.1 | **Exactly one** thinking indicator per surface (widget: fixed id `cw-beth-thinking`; panel: container-scoped class `.ap-beth-thinking`; both removed-before-add). |
| GB-2.2 | No duplicate assistant messages. |
| GB-2.3 | No orphaned placeholders left on screen after an answer renders. |
| GB-2.4 | No crossed responses (an answer is never shown under the wrong question). |
| GB-2.5 | No permanently stuck thinking indicator — it is removed on the recovery re-render, or self-heals to a timeout message after the poll bound (~120s). |
| GB-2.6 | Each assistant response stays associated with the correct request (correlation id `cid` threads submit → job → task → render; see `BETH_LIFECYCLE` telemetry). |

**Single source of truth (do not duplicate):** *pending marker exists ⇔ a request
is in flight whose answer is not yet resolved.* The thinking indicator and all
recovery are derived from this one marker. **No second pending-tracking system.**

---

## GB-3 — Health Reasoning Integrity

| ID | Behavior | Enforced by |
|----|----------|-------------|
| GB-3.1 | Health responses are **health-only** — no cross-domain contamination. | `apps/ai/chatgpt_cos/reasoning/stages.py` (HEALTH-scoped retrieval + curator); tests `test_reasoning_lane::test_scope_drops_cross_domain_truth_and_never_fetches_it`, `test_biggest_health_risk_no_contamination` |
| GB-3.2 | No internal implementation details are exposed (no SAE paths, enums, field names, source identifiers). | curator strips `source`/`_label`/raw enums; `test_raw_enum_never_leaks_to_model_facing_wm` |
| GB-3.3 | No `LOW`/`MED`/`HIGH` (or equivalent) internal labels shown to users. | `_calibrate_label` / tone softening; `test_severe_labels_softened` |
| GB-3.4 | Morning nutrition counters are interpreted contextually (a 0 at 7am is not a "risk"). | `_nutrition_time_context`; `test_nutrition_context_morning_zero_not_a_risk`, `test_intra_day_hints` |
| GB-3.5 | Responses are evidence-based and non-alarmist. | `test_prompts_carry_calibration_and_no_alarmist_words` |
| GB-3.6 | The model never sees raw SAE; only a curated, executive-clean Working Memory. | `test_health_working_memory_is_health_only`, `test_curator_reads_only_health_truth` |

---

## GB-4 — Reliability Guarantees

| ID | Behavior | Enforced by |
|----|----------|-------------|
| GB-4.1 | Implemented reasoning intents **always return an answer** (never an empty/blank response). | `reasoning/engine.py` guarantee; `test_reasoning_lane::test_overall_progress_end_to_end` |
| GB-4.2 | Implemented intents never silently fall through to the legacy tool loop. | deterministic matcher `deterministic_health_intent` + `synthesize_health_plan`; `test_health_fallback_uses_ranked_concerns` |
| GB-4.3 | Deterministic fallbacks always exist for implemented intents. | `_health_risk_fallback`, `_health_progress_fallback`; `test_foundation_validation::test_deterministic_fallback_*` |
| GB-4.4 | Planner LLM failure cannot prevent a user response (planner never answers; its failure routes to the deterministic path). | `reasoning/plan.py::parse_plan` returns `None` safely → resilience matcher |
| GB-4.5 | The CoS path executes **zero** legacy conversation code when the flag is on. | `test_cos_gateway::test_flag_on_chat_executes_zero_legacy`, `test_flag_on_stream_executes_zero_legacy` |
| GB-4.6 | The fast path (foundational facts) uses a plain API call, never the tool loop. | `test_foundation_validation::test_fast_path_uses_plain_call_api_never_tool_loop` |

**Implemented reasoning intents at baseline (closed set):**
`biggest_health_risk`, `overall_progress`
(`apps/ai/chatgpt_cos/reasoning/plan.py::IMPLEMENTED_INTENTS`).
`health_focus_today` and `health_concerns` are **planned, not yet implemented**
— do not assume coverage for them.

---

## Known limitations AT baseline (documented, not regressions)

These are accepted, known states as of `beth-stable-v1` — fixing them is future
work, but they must not be *worsened*:

1. **Worker hard-kill durability gap.** If the Celery worker process is hard-killed
   (SIGKILL / OOM) mid-`generate()`, the empty assistant placeholder is left in the
   DB and the `finally` (terminal status + notification) never runs. UX is mitigated
   (the client recovery poll surfaces a timeout message after its bound), but the
   root cause — heavy synchronous SAE rebuild on the task path
   (`apps/ai/chatgpt_cos/service.py::generate` → `get_user_state(allow_rebuild=True)`)
   — is not yet addressed. See `BETH_REGRESSION_TEST_MATRIX.md` gap R-1.
2. **Zero automated coverage of the frontend durability layer.** GB-1.1/1.2/1.6 and
   all of GB-2 are template JavaScript with **no automated tests** — they are
   manual-validation only. This is the highest-value coverage gap.
3. **Single-marker concurrency.** Multiple simultaneous in-flight requests share one
   pending marker per surface, so there is one generic indicator, not one-per-request
   (by design — see GB-2 invariant).
