# Beth Change Control

> **Mandatory process for any significant change to the CoS / Beth subsystem.**
> Governs the code paths that produce the Golden Behaviors in
> `BETH_GOLDEN_BEHAVIORS.md`.
> **Last updated:** 2026-06-25

---

## Governing principle

> **Preserving stable functionality takes priority over shipping new features.**

If a proposed change puts an existing Golden Behavior at risk and that risk cannot
be eliminated, **do not ship it** — redesign the change so the guarantee is
preserved, or defer the feature. A regression in GB-1…GB-4 is never an acceptable
cost of a new feature.

---

## What counts as a "significant Beth change"

Any change that touches one or more of:

- `apps/ai/chatgpt_cos/**` (tasks, service, reasoning lane: `plan.py`, `stages.py`, `engine.py`, telemetry)
- `apps/ai/cos_gateway/**` (runtime resolution, dispatch)
- `apps/ai/views.py` chat views — `AssistantChatView`, `AssistantChatStreamView`, `AssistantChatResumeView`, `_chat_relay_stream`, `BethTelemetryView`
- `apps/ai/chat_stream_bus.py` (SSE relay snapshot bus)
- `templates/components/chat_widget.html`, `templates/components/assistant_panel.html`
- `apps/ai/intents/**`, `apps/ai/action_handlers.py`, `apps/ai/intent_service.py` (intent surface)
- `apps/core/services/notification_service.py` / `core.Notification` (completion notifications)
- `CELERY_BEAT_SCHEDULE`, queue routing, or worker/Procfile config affecting chat tasks

Trivial doc/comment/log-string edits are exempt.

---

## Required: BLAST RADIUS ASSESSMENT

Every significant Beth change MUST include this block in its PR description / task
write-up **before** implementation:

```
BLAST RADIUS ASSESSMENT
=======================
Files affected:
  - <paths>

Subsystems affected:
  - [ ] Reasoning lane (plan/stages/engine)
  - [ ] Streaming / relay / resume
  - [ ] Background task / persistence
  - [ ] Recovery / pending marker / thinking indicator (frontend)
  - [ ] Completion notifications
  - [ ] Intent registration (5-point)
  - [ ] Gateway / runtime resolution

Golden Behaviors at risk:
  - <list GB-x.y ids, or "none">

Regression tests required (must pass before merge):
  - <named test modules — see BETH_REGRESSION_TEST_MATRIX.md>

Production validation required:
  - <named sections of BETH_PRODUCTION_VALIDATION_CHECKLIST.md, or "none">

Rollback strategy:
  - <tag to roll back to + procedure ref, see BETH_ROLLBACK_AND_RECOVERY.md>
```

If **Golden Behaviors at risk** is non-empty, the PR requires explicit sign-off and
the named production validation MUST be completed before the change is considered
done.

---

## Hard rules (carried from CLAUDE.md — enforced here for Beth)

- **New intent → run the 5-point registration gate before deploying:**
  `python manage.py test apps.ai.tests.test_intent_registration -v 2 --failfast`.
  A new intent touches 5+ files; missing one is a silent runtime failure.
- **Never compute heavy analytics on the request/task path** where it can block or
  OOM a worker. Read pre-computed cache/snapshot; return "pending" if absent. (This
  is the open risk behind the worker-kill durability gap — see Golden Behaviors
  "Known limitations" #1.)
- **Never swallow errors on critical paths.** Separate `ImportError` (optional) from
  `Exception` (must be logged with `exc_info=True`). Fail-closed on safety gates.
- **Streaming vs non-streaming parity:** a fix to one chat path must be verified on
  the other.
- **Visual Truth Contract:** only actual completion may look complete
  (`docs/WLJ_VISUAL_TRUTH_CONTRACT.md`, `apps/core/tests/test_visual_truth_contract.py`).
- **CoS naming boundary:** never hardcode "Beth" in user-facing copy/fixtures/UI —
  use `cos_display_name`.
- **Single source of truth:** do not add a second pending-tracking system; the
  sessionStorage pending marker is authoritative for "request in flight."

---

## Definition of Done for a significant Beth change

1. Blast Radius Assessment completed and reviewed.
2. Required regression tests green (scoped run, per CLAUDE.md testing policy).
3. `python manage.py check` and `makemigrations --check --dry-run` clean.
4. Changelog entry appended (`docs/wlj_claude_changelog.md`).
5. If Golden Behaviors were at risk: named production validation scenarios PASS.
6. If the change is a new stability milestone: a new `beth-stable-vN` tag is cut
   (`BETH_ROLLBACK_AND_RECOVERY.md`).
