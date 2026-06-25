# Beth Regression Test Matrix

> **Maps each Beth capability to existing automated coverage, gaps, and required
> manual validation.** Documentation only — no test code is added here.
> **Last updated:** 2026-06-25
> **Source:** `apps/ai/tests/`, `apps/core/tests/` (inventoried 2026-06-25).

**Scoped-run reminder (CLAUDE.md):** never run the full suite. Run the named
modules per change, e.g.:
```bash
python manage.py test apps.ai.tests.test_reasoning_lane apps.ai.tests.test_cos_gateway -v 1 --failfast
```

---

## Coverage by capability

### 1. Reasoning lane — health scoping & integrity  *(GB-3)*
- **Existing tests:** `test_reasoning_lane.py` (28) — `test_scope_drops_cross_domain_truth_and_never_fetches_it`, `test_health_working_memory_is_health_only`, `test_curator_reads_only_health_truth`, `test_raw_enum_never_leaks_to_model_facing_wm`, `test_severe_labels_softened`, `test_nutrition_context_morning_zero_not_a_risk`, `test_prompts_carry_calibration_and_no_alarmist_words`, `test_biggest_health_risk_no_contamination`, `test_overall_progress_end_to_end`. Plus `test_health_intelligence_cos.py` (18, enum-strictness/brevity), `test_cos_truth_enforcement.py` (18).
- **Coverage gaps:** only the 2 implemented intents are end-to-end tested; `health_focus_today` / `health_concerns` are unimplemented (no coverage, by design). No test asserts the *user-visible* rendered string is label-free end-to-end (curator-level only).
- **Recommended future tests:** golden-output snapshot per implemented intent asserting no `LOW|MED|HIGH|SAE\.|_label|source=` substrings in the final answer text.
- **Manual validation:** Checklist §G.

### 2. Reliability — always-answer & fallback  *(GB-4)*
- **Existing tests:** `test_reasoning_lane.py` (`test_health_fallback_uses_ranked_concerns`, `test_planner_unavailable_declines_for_non_health`, `test_garbage_returns_none`, `test_unknown_intent_becomes_other`); `test_foundation_validation.py` (10) — fast-path + deterministic-fallback-on-None/raises; `test_cos_empty_answer.py` (6).
- **Coverage gaps:** no explicit test that an implemented intent answers when BOTH planner and reasoning `_call_api` fail simultaneously (only individual failures covered).
- **Recommended future tests:** double-failure test (planner None + reasoning raises) asserting a non-empty deterministic answer.
- **Manual validation:** Checklist §H.

### 3. Gateway / runtime resolution  *(GB-4.5)*
- **Existing tests:** `test_cos_gateway.py` (14) — flag on/off routing, zero-legacy execution for chat & stream, surface suppression; `test_cos_account_flag.py`, `test_cos_router_bypass.py`, `test_cos_mode_router.py`.
- **Coverage gaps:** none significant.
- **Manual validation:** none required (well covered).

### 4. Background task — persistence & bus  *(GB-1.3, 1.4)*
- **Existing tests:** `test_chatgpt_cos_clean.py` (8) — `test_task_persists_and_writes_bus`, `test_warms_sae_and_standing_context`, `test_task_handles_generation_error_cleanly`, `test_clean_task_registered_via_autodiscovered_module`; `test_chat_background.py`.
- **Coverage gaps:** **R-1 (critical)** — no test for the worker hard-kill / orphaned-placeholder path (the empty `content="" status=processing` survivor). Hard to unit-test (SIGKILL), but the *recovery* contract (client sees a terminal/timeout state) is untested. No test that `BETH_TASK_FINALLY` always publishes a terminal bus status on the normal exception path vs. is skipped on kill.
- **Recommended future tests:** (a) assert the soft-time-limit handler persists a terminal message + bus `failed`; (b) a "stale processing placeholder" detector test (given an empty processing message older than the hard limit, recovery surfaces a timeout state).
- **Manual validation:** Checklist §D (return-after-completion) catches the happy path; the kill path needs ops observation.

### 5. Completion notifications  *(GB-1.5)*
- **Existing tests:** `test_cos_completion_notification.py` (4) — creation w/ deep-link, exactly-one (dedup), threshold gating, resilience-on-bad-user.
- **Coverage gaps:** the deep-link *scroll/highlight* and the toast are frontend JS — untested. Bell unread/read lifecycle for this category not asserted.
- **Recommended future tests:** integration test that `action_url` resolves and `Notification` is `is_read=False` + category `intelligence`.
- **Manual validation:** Checklist §F.

### 6. Streaming relay / resume  *(GB-1.x)*
- **Existing tests:** partial — `test_event_stream_routes.py`, `test_phase7_stream_tools.py`, `test_cos_gateway` stream routing.
- **Coverage gaps:** `AssistantChatResumeView` outcomes (410 expired / 403 owner-mismatch / attached) have **no direct test**. `_chat_relay_stream` `GeneratorExit`-does-not-cancel-task is asserted only by design/comment, not a test.
- **Recommended future tests:** view tests for resume 410/403/200; a test that closing the relay generator does not mark the task cancelled.
- **Manual validation:** Checklist §A, §C.

### 7. Frontend durability — pending marker, recovery poll, thinking indicator, deep-link  *(GB-1.1, 1.2, 1.6, GB-2 ALL)*
- **Existing tests:** **NONE.** This entire layer is template JavaScript (`chat_widget.html`, `assistant_panel.html`) with no JS test harness in the repo.
- **Coverage gaps:** **R-2 (highest-value gap)** — every behavior that regressed repeatedly during stabilization (navigation survival, refresh survival, single-indicator/dedup, no-orphan, no-duplicate, marker overwrite under concurrency) is 100% manual.
- **Recommended future tests:** introduce a lightweight JS/DOM test harness (e.g. Jest + jsdom, or Playwright component tests) covering: `ensureThinkingPlaceholder` dedup; marker-present⇒one-indicator; FOUND re-render removes indicator; `refreshHistory` `needsUpdate` logic; `?beth_msg` scroll. This is the single highest-leverage investment for Beth stability.
- **Manual validation:** Checklist §A–F (currently the ONLY guard).

### 8. Intent registration integrity  *(GB-4.2)*
- **Existing tests:** `test_intent_registration.py` (11) — the 5-point registration gate; `test_intent_service.py`, `test_intent_classifier.py`, plus routing tests (`test_glucose_intent_routing`, `test_sleep_intent_routing`, `test_update_intent_routing`, `test_voice_intent`).
- **Coverage gaps:** none significant for the registration contract.
- **Manual validation:** none required.

### 9. Truth / Visual Truth Contract  *(cross-cutting)*
- **Existing tests:** `test_cos_truth_enforcement.py` (18), `test_domain_truth_contracts.py`, `apps/core/tests/test_visual_truth_contract.py`.
- **Coverage gaps:** none significant.
- **Manual validation:** any homepage/Action Center CSS change → re-run visual truth tests.

---

## Summary table

| Capability | Automated coverage | Gap severity | Manual validation |
|------------|-------------------|--------------|-------------------|
| Reasoning health-scoping | Strong (28+18+18) | Low | §G |
| Reliability / fallback | Strong (10+) | Low–Med (double-failure) | §H |
| Gateway / runtime | Strong (14) | None | — |
| Background task / persistence | Medium (8) | **High (R-1: kill path)** | §D + ops |
| Completion notifications | Medium (4) | Med (FE deep-link) | §F |
| Streaming relay / resume | Weak (partial) | Med (resume outcomes) | §A, §C |
| **Frontend durability / indicator** | **None** | **Highest (R-2)** | §A–F (only guard) |
| Intent registration | Strong (11) | None | — |
| Truth / Visual Truth | Strong | None | per CSS change |

---

## Top recommendations (priority order)

1. **R-2 — Stand up a frontend test harness.** The durability/indicator layer that
   caused the most production churn has zero automated protection. Highest ROI.
2. **R-1 — Close the worker hard-kill durability gap** (move the heavy SAE rebuild
   off the synchronous task path / cache-first), then add the stale-placeholder
   recovery test. Until then, keep it listed as a known limitation.
3. **Add resume-view tests** (410/403/200) — small, high-confidence.
4. **Add a golden-output label-leak assertion** per implemented health intent.
