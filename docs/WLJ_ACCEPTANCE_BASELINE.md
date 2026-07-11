# WLJ Chief of Staff — Permanent Acceptance Baseline

**Status:** CURRENT · Constitutional companion to `docs/WLJ_CONSTITUTION.md`
**Established:** 2026-07-11 (Architecture Milestone)
**Purpose:** The permanent regression suite that protects the locked architecture. These tests are the executable form of the Constitution — weakening any of them is a **constitutional change** (see Constitution §3).

---

## 1. What this baseline guarantees

Every architectural guarantee that took months to establish has at least one automated test that fails CI if the guarantee regresses. This document is the map from **guarantee → test**. It is kept in sync with the tests; if you add a constitutional contract, list it here.

## 2. Coverage map (milestone areas → tests)

| # | Acceptance area | Status | Test file(s) / class |
|---|---|---|---|
| 1 | Current Context (page awareness, `<meta name="wlj-context">`, baseline resolution) | ✅ Strong | `apps/core/tests/test_current_context.py`; `apps/ai/tests/test_current_context_baseline.py`; `apps/ai/tests/test_page_context_diag.py` |
| 2 | Navigation (context lifecycle across navigation) | ✅ Strong | `apps/ai/tests/test_current_context_navigation.py`; `apps/ai/tests/test_historical_navigation.py` |
| 3 | Current Action (single Execution Decision Authority) | ✅ Strong | `apps/core/tests/test_execution_decision_authority_contract.py`; `apps/core/execution/tests/test_selectors.py` |
| 4 | Execution Truth (occurrence-scoped completion) | ✅ Strong | `apps/core/tests/test_completion_single_source_contract.py`; `apps/core/execution/tests/test_completion_reconciliation.py`; `apps/life/tests/test_routine_execution_truth.py`; `apps/ai/tests/test_routine_occurrence_single_writer.py` |
| 5 | Mission Link (action→mission deterministic truth) | ✅ Strong | `apps/purpose/tests/test_mission_link.py`; `apps/dashboard_v3/tests/test_mission_truth_reconciliation.py` |
| 6 | Timing calculations | ✅ Strong | `apps/core/execution/tests/test_timing.py`; `apps/core/tests/test_phase2_time_authority.py`; `test_phase7_dst_time_authority.py` |
| 7 | Scheduled check-ins | ◐ Partial | `apps/ai/tests/test_proactive_scheduler.py`; `test_checkin_happy_path.py`; `test_checkin_authoring.py` |
| 8 | Multimodal ingestion | ✅ Strong | `apps/ai/tests/test_multimodal.py`; `apps/ai/tests/test_multimodal_wiring.py` |
| 9 | Action execution | ✅ Strong | `apps/ai/tests/test_action_execution.py` |
| 10 | Confirmation (confirmation queue) | ✅ Strong | `apps/ai/tests/test_crud_confirmation_bridge.py`; `apps/core/ai_orchestrator/tests/test_confirmation_escape.py` |
| 11 | Conversation integrity (transcript / attachment persistence) | ◐ Partial | `apps/ai/tests/test_multimodal_wiring.py::ConversationIntegrityTests` |
| 12 | Duplicate prevention / detection | ◐ Partial (per-domain) | `apps/calendar_engine/tests/test_recurrence_duplicate.py`; `apps/ai/tests/test_multimodal.py` (artifact hash dedup) |
| 13 | Results-not-intentions / no-fabrication | ✅ (added at milestone) | `apps/core/tests/test_constitution_contract.py::ConstitutionResultsNotIntentionsContractTests`; adjacency in `test_verified_completion.py` |
| 14 | Constitutional / architectural contracts | ✅ Strong | See §3 |

## 3. The constitutional contract tests (the enforcement layer)

These are AST/static/structural tests that make architecture impossible to violate silently:

| Contract test | Guards |
|---|---|
| `apps/core/tests/test_constitution_contract.py` | **NEW at milestone** — the Constitution doc, its Articles, enforcement references, naming rule, no-fabrication clause |
| `apps/core/tests/test_request_path_safety_contract.py` | No inline heavy-intelligence / un-allowlisted inline LLM on request path (I.2, IV.2) |
| `apps/core/tests/test_execution_decision_authority_contract.py` | Exactly one `current_action` producer (III.2) |
| `apps/core/tests/test_completion_single_source_contract.py` | Execution Truth is the sole "completed today" producer (III.1, Execution Truth) |
| `apps/core/tests/test_visual_truth_contract.py` | Only real completion may look complete (V.1) |
| `apps/core/tests/test_domain_truth_contracts.py` | Execution Truth / SAE / UI agree per domain |
| `apps/ai/tests/test_conductor_contract.py` | Orchestration stays orchestration-only (no reasoning engine) (I.2) |
| `apps/ai/tests/test_intent_registration.py` | New intents registered across all 5 surfaces |
| `apps/cos/tests/test_contracts.py` | CoS action contract / registry integrity |

## 4. Running the baseline

Run the full constitutional contract suite before any deploy that touches architecture:

```bash
python manage.py test \
  apps.core.tests.test_constitution_contract \
  apps.core.tests.test_request_path_safety_contract \
  apps.core.tests.test_execution_decision_authority_contract \
  apps.core.tests.test_completion_single_source_contract \
  apps.core.tests.test_visual_truth_contract \
  apps.core.tests.test_domain_truth_contracts \
  apps.ai.tests.test_conductor_contract \
  apps.ai.tests.test_intent_registration \
  apps.cos.tests.test_contracts \
  --keepdb -v 1
```

Broader behavioral baseline (the areas in §2) — run the owning app's tests when you touch that area; never run the full ~4,400-test suite unless explicitly required.

## 5. Known gaps in the baseline (tracked, not hidden)

Per Article IV.1 (results, not intentions) we record what the baseline does **not** yet fully cover:

1. **Scheduled check-ins end-to-end (area 7)** — scheduler windows and check-in authoring are each covered, but no single test drives a scheduled window → authored check-in from execution truth. *Phase: next.*
2. **Conversation integrity as a standalone contract (area 11)** — attachment persistence is covered only inside the multimodal wiring test; there is no dedicated durable-transcript contract (turn ordering + attachment retention). *Phase: next.*
3. **Cross-cutting duplicate-prevention contract (area 12)** — dedup is strong per-domain (calendar, multimodal) but there is no unified contract asserting every action write path runs duplicate detection. *Phase: after CoS action registry adoption.*

These gaps are real and are listed in `docs/WLJ_KNOWN_LIMITATIONS.md`. They do not block the milestone; they are the next increments of the permanent baseline.

## 6. Milestone fix applied to the baseline

- Restored `apps/core/ai_state/test_health_contract_glucose_extensions.py` (was `tests_…`, silently uncollected since 2026-05-31 — 26 regression tests were dormant in CI; rename makes them discoverable again).
