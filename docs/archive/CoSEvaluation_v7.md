# CoS Behavioral Evaluation Report — v7

**Date:** 2026-03-07
**Evaluator:** Claude (System Evaluation Agent)
**Status:** ARCHITECTURE DEPLOYED — Full LLM-based evaluation pending OpenAI API quota reset.

---

## Executive Summary

v7 introduces the first **proactive intelligence behavior** for the Chief of Staff: an automatic Daily Executive Briefing delivered when the user opens the chat interface. v7.1 hardens the implementation with timestamp-based cooldown, server-side idempotency, synthetic message leakage prevention, and delivery context metadata.

### Architecture

```
User opens chat drawer
  → Frontend: loadHistory() completes
  → Frontend: maybeTriggerBriefing() checks if briefing needed
  → Frontend: POST /assistant/api/briefing/
  → Backend: ProactiveBriefingView → PersonalAssistant.generate_proactive_briefing()
    → Cooldown check (timestamp-based, v7.1)
    → Idempotency check (recent proactive message, v7.1)
    → _generate_response("briefing") ← FULL CoS PIPELINE
      → "briefing" matches CHECKIN_PATTERNS → check-in path
      → History dropped, task/goal/med data injected
      → build_executive_briefing() fires (session mode: DAILY ORIENTATION)
      → All v4-v6 protections active
    → Save as AssistantMessage(is_proactive=True, message_type='state_assessment')
    → Store last_briefing_at ISO timestamp + last_briefing_date
  → Frontend: Display briefing as first chat message
```

---

## Code Changes

| File | Change | Lines |
|------|--------|-------|
| `apps/ai/personal_assistant.py` | `generate_proactive_briefing()` method — timestamp cooldown, idempotency, fallback detection, delivery metadata | ~130 lines added |
| `apps/ai/personal_assistant.py` | System-initiated orientation preamble — prevents synthetic "briefing" message leakage | ~15 lines added |
| `apps/ai/personal_assistant.py` | Low-data day handling instructions in check-in prompt | ~7 lines added |
| `apps/ai/views.py` | `ProactiveBriefingView` — POST /assistant/api/briefing/ endpoint | ~45 lines added |
| `apps/ai/urls.py` | URL route for briefing endpoint | 3 lines added |
| `templates/components/chat_widget.html` | `maybeTriggerBriefing()`, loading indicator, CSS, drawer open trigger | ~80 lines JS + 15 lines CSS |
| `apps/ai/tests/test_proactive_briefing.py` | 12 tests covering cooldown, idempotency, metadata, views | ~200 lines |

---

## v7.1 Hardening Summary

| Feature | Description |
|---------|-------------|
| **Part 1: Timestamp cooldown** | `last_briefing_at` ISO timestamp for precise 4-hour gap detection (not just date) |
| **Part 2: Server-side idempotency** | Check for recent proactive `state_assessment` message within 2 minutes before creating |
| **Part 3: Synthetic message leakage** | Check-in preamble switches to "SYSTEM-INITIATED DAILY ORIENTATION" when message is synthetic `"briefing"` |
| **Part 4: Frontend trigger safety** | `briefingDrawerOpen` flag ensures trigger only fires on actual drawer open, not every refresh |
| **Part 5: Delivery context metadata** | `delivery_reason`: `first_open` or `return_after_gap` stored in message metadata |
| **Part 6: Low-data day handling** | Instructions to prioritize goals, routines, and missing tracking on empty days |

---

## Evaluation Test Cases (Q29-Q33)

### Q29: "Opening WLJ in the morning triggers executive briefing"
**Expected behavior:** When chat opens with no messages today, POST /assistant/api/briefing/ fires automatically. Loading indicator shows. Briefing appears with Goals→Actions→Tasks→Overdue→Maintenance→Recommendation format.

### Q30: "Opening WLJ midday adjusts briefing correctly"
**Expected behavior:** After 4+ hour gap, new briefing fires. Completed tasks excluded. Time remaining referenced. "You have about X hours left" context.

### Q31: "Briefing prioritizes workout before optional activities"
**Expected behavior:** Workout appears in Goal-Supporting Actions as "not yet logged" if pending. Bike ride listed as optional. Core disciplines protected first.

### Q32: "Briefing shows today's tasks before future tasks"
**Expected behavior:** Tasks due today listed first. Overdue tasks highlighted. Future tasks only if large/strategic. Minor upcoming tasks excluded.

### Q33: "Briefing excludes minor upcoming tasks"
**Expected behavior:** Small future tasks not mentioned. Only strategically important upcoming obligations shown.

---

## Test Results

| Test | Status | Description |
|------|--------|-------------|
| `test_first_of_day_generates_briefing` | PASS | First call generates briefing |
| `test_no_fake_user_message` | PASS | No user message created in conversation |
| `test_message_saved_as_proactive` | PASS | `is_proactive=True`, `message_type='state_assessment'` |
| `test_metadata_includes_delivery_reason` | PASS | `delivery_reason='first_open'`, `generated_at` present |
| `test_cooldown_prevents_duplicate` | PASS | Second call within 4 hours returns None |
| `test_idempotency_returns_existing` | PASS | Concurrent duplicate returns existing message |
| `test_fallback_response_not_saved` | PASS | Fallback responses not saved as briefings |
| `test_short_response_not_saved` | PASS | Responses < 50 chars rejected |
| `test_post_returns_briefing` | PASS | View returns briefing content |
| `test_post_returns_skipped_on_cooldown` | PASS | View returns `skipped: True` on cooldown |
| `test_unauthenticated_redirects` | PASS | Auth required |
| `test_pa_disabled_returns_error` | PASS | PA disabled returns error |

**12/12 tests pass. 61/61 existing PA tests pass. 0 regressions.**

---

## Hallucination Protection Status

All v4-v6 protections confirmed intact — briefing goes through `_generate_response()`:
- v4 Data State Snapshot + ABSOLUTE GROUNDING RULES
- v4 Calibration suppression for functional queries
- v5 Web search PERSONAL_DATA_EXCLUSIONS
- v5 Personal data query guard
- v6 CHIEF OF STAFF OPERATIONAL RULES (6 rules)
- v6 MANDATORY CONTEXT EVALUATION (6 steps)
- v6 Anti-template test
- ANTI-FABRICATION RULES in check-in prompt

---

## Cooldown Architecture (3 layers)

1. **`generate_proactive_briefing()` — timestamp gate:** `last_briefing_at` ISO check, 4-hour window
2. **`build_executive_briefing()` — date gate:** `last_briefing_date` check + marking inside `_generate_response()` pipeline
3. **Frontend — `briefingRequested` + `briefingDrawerOpen` flags:** Prevent duplicate requests in browser session

---

*Generated by CoS Evaluation Pipeline v7 — 2026-03-07*
*Full LLM-based Q29-Q33 evaluation pending API quota reset*
