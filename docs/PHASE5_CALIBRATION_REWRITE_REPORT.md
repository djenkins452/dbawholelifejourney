# Phase 5: Conversational Calibration Rewrite Report

**Date:** 2026-02-19
**Author:** Claude (automated)

---

## Summary

Replaced the 14-day trickle calibration model (1 question per dashboard load, gated by day-ranges) with a fully conversational, chat-driven calibration session inside the Chief of Staff. The CoS now conducts a getting-to-know-you conversation in real time, asking 11 questions across core people, non-negotiables, preferred activities, negotiables, accountability style, communication frequency, and focus areas.

---

## Files Modified

| File | Change |
|------|--------|
| `apps/core/blueprint/cos_governance.py` | Replaced `CALIBRATION_PHASES` dict with flat `CALIBRATION_QUESTIONS` list; added 9 new public functions for conversational calibration; updated `should_ask_question()` to bypass daily cap during calibration; updated `build_governance_instructions()` |
| `apps/ai/intents/calibration_intents.py` | **NEW** — `pause_calibration` intent definition |
| `apps/ai/intents/__init__.py` | Wired `CALIBRATION_INTENT_TOOLS` into `ALL_INTENT_TOOLS` and `INTENT_HANDLERS` |
| `apps/ai/action_handlers.py` | Added `handle_pause_calibration()` method |
| `apps/ai/intent_service.py` | Added `pause_calibration` route in `execute_intent()` |
| `apps/core/ai_orchestrator/intent_engine.py` | Added `CALIBRATION_INTENTS` set with module routing |
| `apps/ai/personal_assistant.py` | Added calibration system prompt injection in `_generate_response()`; added answer recording in `send_message()` |
| `apps/dashboard/views.py` | Rewrote `_get_command_mode()` calibration section to use new state-based API |
| `apps/core/blueprint/tests.py` | Added `ConversationalCalibrationTests` class (16 tests); updated 3 existing tests |
| `apps/core/management/commands/reset_calibration_conversational.py` | **NEW** — one-time reset for existing users |

---

## New Intent

- **`pause_calibration`** — Triggered by: "pause", "enough for now", "stop asking", "continue later", "ask me later", "no more questions"

---

## State Fields (in `governance_overrides` JSON)

| Field | Type | Purpose |
|-------|------|---------|
| `calibration_stage` | int | Index of next question (0-10) |
| `calibration_paused` | bool | Whether user paused |
| `calibration_welcome_shown` | bool | Whether intro message was shown |
| `calibration_answers` | dict | Answers keyed by question key |
| `calibration_completed_at` | ISO str | Completion timestamp |
| `calibration_version` | str | `"conversational_v1"` |
| `calibration_reset_from_old` | bool | Whether reset from old system |

---

## Flow Diagram

```
Dashboard Load
  |
  v
get_calibration_state(user)
  |
  +-- active + not paused
  |     |
  |     v
  |   Show proactive question in CoS panel
  |   User sends ANY message to CoS chat
  |     |
  |     v
  |   _generate_response() injects calibration context into system prompt
  |   AI sees: current question + next question preview + rules
  |   AI responds naturally, weaving in next question
  |     |
  |     v
  |   send_message() records answer via record_calibration_answer()
  |   Stage advances automatically
  |   Next _generate_response() gets next question
  |     |
  |     +-- User says "pause" / "enough"
  |     |     Intent detected: pause_calibration
  |     |     "No problem. We'll pick this up where we left off."
  |     |     calibration_paused = True
  |     |
  |     +-- All 11 questions answered
  |           calibration_complete = True
  |           Completion message displayed
  |
  +-- active + paused
  |     Auto-resume on next dashboard load
  |     Show "Ready to pick up where we left off?"
  |
  +-- complete
        Post-calibration: ongoing relationship questions (unchanged)
```

---

## Example Conversation

```
CoS: I'd like to get to know you better so I can actually be useful.
     I'll ask you a few questions — nothing complicated, just the kind
     of things that help me understand what matters to you. You can
     pause anytime by saying 'that's enough for now' and we'll pick
     up where we left off.

User: Sounds good, let's do it.

CoS: Great. Who are the most important people in your daily life?

User: My wife Sarah, my mom, and my buddy John from work.

CoS: Sarah, your mom, and John — those are your core people.
     I'll keep them in mind. Is there anyone you've been meaning
     to reconnect with?

User: Actually yeah, my college friend Mike. Haven't talked in months.

CoS: Mike from college — I can help you find time for that.
     Now shifting gears a bit — what activities are sacred to you?
     Things you'd never want to skip?

User: Morning workout and my quiet time with God. Those are non-negotiable.

CoS: Morning workout and faith time — those are the first things I protect.
     What time of day do you feel most productive?

User: enough for now, let's pick this up later

CoS: No problem. We'll pick this up where we left off whenever you're ready.
```

---

## Tests Written

16 tests in `ConversationalCalibrationTests`:
- State management (active, paused, welcome shown, stage tracking)
- Question progression (first question, advance, completion)
- Answer storage and persistence
- Pause/resume behavior
- System injection content and conditional behavior
- Old-system reset logic
- Daily cap bypass during calibration

---

## Migration

No database migrations required. All state stored in existing `governance_overrides` JSONField.

**One-time command for existing users:**
```bash
python manage.py reset_calibration_conversational --dry-run
python manage.py reset_calibration_conversational
```

---

## Compatibility

- Existing drift engine, intervention engine, and Phase 4 authority modes are unchanged
- Old calibration functions (`get_calibration_question`, `mark_calibration_question_asked`, `advance_calibration_day`) remain for backward compatibility
- Alignment session takes priority if actively in progress
- Post-calibration ongoing questions continue to work unchanged
