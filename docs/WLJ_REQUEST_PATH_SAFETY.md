# WLJ Request-Path Safety Contract

> **Interactive user requests never depend on asynchronous infrastructure or heavy intelligence.**

Origin incident: 2026-07-05 — dashboard load and task completion both regressed from ~2s to 15–20s. Root cause: request-path writes fired `post_save` signals that synchronously `.delay()`'d a Celery task; a degraded Redis made the **result backend** retry its reconnect 20×1.0s (~20s) before raising, then a synchronous SAE rebuild ran on the request thread. See `docs/wlj_claude_changelog.md` (2026-07-05 fix(perf) entries).

---

## The six guarantees

1. No interactive request performs synchronous heavy intelligence.
2. No interactive request waits on asynchronous infrastructure (Celery / broker / result backend / Redis).
3. No interactive request rebuilds canonical state (SAE).
4. No dashboard request computes truth (reads snapshots only).
5. No request performs hidden LLM inference — only user-invoked, explicitly-awaited AI generation may call an LLM synchronously.
6. All background work is fire-and-forget, queue-based, or snapshot-based.

---

## Enforcement status (ENFORCED vs FOLLOWED)

| # | Guarantee | Status | Mechanism |
|---|-----------|--------|-----------|
| 2 | No wait on async infra (the 20s block) | **ENFORCED (config)** | `CELERY_TASK_IGNORE_RESULT=True` + `broker/result_backend_transport_options` 0.5s socket timeouts + bounded publish retry (`config/settings.py`). A `.delay()` cannot block on a degraded Redis regardless of who writes it. Nothing consumes a Celery `AsyncResult` (verified). |
| 6 | Background work is fire-and-forget/queue/snapshot | **ENFORCED (config) + helper** | Same config makes every enqueue fire-and-forget; `apps/core/celery_utils.py :: safe_enqueue` is the non-blocking primitive. |
| 1 | No synchronous heavy intelligence | **ENFORCED (test)** | `test_request_path_safety_contract.py` fails CI if a `views*.py`/`signals.py`/`api*.py` calls `update_user_state` / `rebuild_user_state` / `run_intelligence_chain` / `run_insights` / `build_health_state` / `compute_system_life_impact` / `compute_signal_health`. |
| 3 | No canonical-state rebuild | **ENFORCED (test)** | Same test bans the rebuild callees above; request-path reads use `get_module_state(..., allow_rebuild=False)`. |
| 5 | No hidden LLM inference | **ENFORCED (test) for inline** | Same test bans inline `OpenAI(...)` / `.chat.completions.create` / `.embeddings.create` / `.audio.speech.create` / `.responses.create` in request modules, except modules in `INLINE_LLM_ALLOWLIST`. |
| 4 | No dashboard computes truth | **ENFORCED (test + convention)** | Dashboard is a request module → covered by the heavy-intelligence ban; composer reads `allow_rebuild=False`; Ops Wall reads a snapshot, returns `pending` on miss (no live fallback). |

---

## The safeguard

`apps/core/tests/test_request_path_safety_contract.py` — an AST purity test (the WLJ idiom, cf. `test_visual_truth_contract.py`, `tests_metric_access.py`). It scans every request-path module and fails CI on a new heavy-intelligence call or inline LLM call. **To add a user-invoked AI endpoint, add its module path to `INLINE_LLM_ALLOWLIST` in the same change** — that entry is the reviewed audit trail.

Proven to bite: injecting `update_user_state(...)` + `OpenAI(...)` into a probe `views_*.py` fails the test with exact file:line; removing it goes green.

---

## Residual risk (documented, not statically enforceable)

- **LLM/heavy work reached through a service layer** (a view calls `service.analyze()` that internally calls OpenAI). Static call-graph analysis is out of scope. These endpoints are governed by the reviewed `INLINE_LLM_ALLOWLIST` of intentional AI endpoints + code review. The current intentional set (user invokes AI and waits, timeout-bounded): non-streaming chat fallback, scan/barcode lookups, receipt/pantry/recipe upload POSTs, Gmail scan, help chat, legacy import, TTS, provider lookup. Production mitigation for worker-pool contention is **queue isolation** (chat streaming already uses `CHAT_GENERATION_QUEUE`).
- **A synchronous fallback to a service that does heavy work** (`try: task.delay() except: service.do_it_sync()`) where the service function is not one of the banned names. The `.delay()` no longer blocks (config), and the removed fallbacks are covered, but a *new* such pattern to a *new* service is a review concern.

---

## Can WLJ honestly claim the guarantee?

**Yes** — for the class that caused the incident. Interactive requests cannot block on async infrastructure (config-enforced) and cannot inline heavy intelligence, canonical-state rebuilds, or hidden LLM calls in a request module (CI-enforced). The only synchronous LLM work remaining is on endpoints the user explicitly invokes and waits for, all timeout-bounded and enumerated in a reviewed allowlist. The remaining gap (service-layer LLM reachability) is a review concern, not a silent-regression risk for the failure mode that took the site down.
