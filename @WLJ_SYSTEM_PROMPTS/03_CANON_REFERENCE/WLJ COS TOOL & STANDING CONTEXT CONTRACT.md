# WLJ COS TOOL & STANDING CONTEXT CONTRACT

```text
Version:      1.0
Last updated: 2026-06-26
Authority:    Danny Jenkins
Applies to:   ChatGPT CoS tool surface (production truth)
Load class:   CANON (load for CoS tool / integration work)
```

> **AS BUILT.** This document describes the ChatGPT Chief-of-Staff tool surface
> **as implemented in production**, not as proposed. The design rationale lives in
> `../06_COS_DESIGN_REFERENCE/` and `../07_COS_TOOLS_REFERENCE/`; **this document is
> the canonical contract.** When design docs and code disagree, code wins and this
> contract is updated to match. Implementation: `apps/ai/cos_services/`.

---

## 1. Governing principle

WLJ owns truth; ChatGPT owns understanding. Every tool here is a **thin binding to
an existing deterministic provider** — no new intelligence, no new engines, no new
write paths. The reasoning layer *requests*; WLJ *computes/executes*
deterministically; the LLM *narrates* (Architecture Law 1).

Compliant with Architecture Laws **1** (LLM Last), **8** (UAIO sole write
authority), **9** (State-First Reads — no re-aggregation), **14** (Deterministic
Decisioning), **16** (Narration Contract / trust framing).

---

## 2. Activation & rollback (feature flag)

Resolved in `tool_registry.evidence_tools_enabled(user)`:

1. Global override `settings.WLJ_COS_EVIDENCE_TOOLS_ENABLED` — default **`False`**.
   When `True`, the tool loop is active for everyone (dev / testing / emergency).
2. Otherwise per-account opt-in `UserPreferences.use_chatgpt_cos` — the production
   switch (Danny = Alpha User #1).

**Rollback** is zero-deploy, zero-code: turn the flag off. The legacy in-process
conversational layer ("Beth") remains the global default until Phase 8 cutover.

The tool loop is invoked from `apps/ai/personal_assistant.py` on **both** chat
paths (non-streaming and streaming/persistent), advertising only enabled tools via
`get_tool_schemas(enabled_only=True)` and routing every call through
`dispatch_tool_call` (Law 12 — streaming/non-streaming parity).

---

## 3. Standing context schema (v1.0)

`get_standing_context(user, *, page_context=None, allow_build=False)` →
`apps/ai/cos_services/standing_context.py`. The always-loaded package the reasoning
layer carries every turn. **Cache-first, never live-computed on the request path**:
it projects the pre-warmed `cos_context` (`readiness_cache`); on a miss it returns
a `pending` shell (it does **not** rebuild). `allow_build=True` is reserved for
background warmers.

`STANDING_CONTEXT_SCHEMA_VERSION = "1.0"`. Fields:

| Field | Source (in assembled `cos_context` / executive projection) |
|-------|------------------------------------------------------------|
| `status` | `"ready"` or `"pending"` |
| `schema_version` | `"1.0"` |
| `generated_at` | ISO timestamp |
| `personalization` | `cos_name` (`prefs.get_cos_name()`, default "Chief of Staff"), `user_first_name`, `enabled_modules` (from `module_permissions`) |
| `current_screen` | client-supplied `page_context` — the ONLY non-deterministic field; in-app only |
| `time` | `now`, `day_significance`, `right_now_focus` |
| `execution_summary` | `execution_summaries` |
| `active_block` | from `right_now_focus.active_block` |
| `capacity` | `capacity_snapshot` |
| `strategic_summary` | executive `strategic_state_summary` |
| `top_risks` | executive `risk_flags` |
| `momentum` | executive `momentum_indicators` |
| `pressure` | executive `pressure_indicators` |
| `health_summary` | executive `health_status` |
| `relational_status` | executive `relational_status` |
| `recommended_focus` | executive `recommended_focus_for_today` |
| `current_mode` | executive `tone_mode` |
| `top_signals` / `critical_signals` | unified feed (capped at 8) |
| `priorities` | `user_priorities` (capped at 6) |
| `medication_adherence` | `medication_adherence_state` |
| `active_fast` | `active_fast_status` |
| `calendar_today` | `calendar_events_today` (capped at 6) |
| `cos_intelligence` | composed standing CoS read (`build_cos_intelligence`) |
| `travel_state` | **always `None`** — Travel is an unbuilt domain; never inferred |
| `trust_framing` | Law-16 guard string: standing context is canonical SUMMARY state; confirm item-level claims via domain/decision tools |
| `_meta` | `source`, `build_ms` |

Caps (`_MAX_SIGNALS=8`, `_MAX_EVENTS=6`, `_MAX_PRIORITIES=6`) keep the package
token-cheap. Every field is `.get()`-guarded: present truth surfaced, absent truth
omitted, nothing fabricated.

---

## 4. Tool surface (registry)

`apps/ai/cos_services/tool_registry.py :: TOOL_REGISTRY`. Each entry:
`{schema (OpenAI function), handler, kind, enabled, phase}`. Disabled tools are
registered but not advertised and are rejected by the dispatcher. **All six tools
below are currently `enabled=True`.**

| Tool | kind | phase | Handler → provider | Purpose |
|------|------|-------|--------------------|---------|
| `get_standing_context` | read | 1 | `standing_context.get_standing_context` | Always-loaded holistic context ("how am I / focus / biggest risk") |
| `get_foundational_health_facts` | read | 2 | `health_facts.get_foundational_health_facts` | Focused scalar health facts (weight/glucose/sleep/calories/meds). Preferred over `get_domain_state` for specific health numbers |
| `get_domain_state` | read | 2 | `domain_state.get_domain_state` | FULL canonical SAE state for one domain (broad/overview only) |
| `get_decision` | read | 4 | `_h_decision` → `normalize_mode` → `build_execution_state` → `selectors.select` | Deterministic Execution/Risk/Fix decision (reuses the CosDecisionView pipeline; no new logic) |
| `search_history` | read | 5 | `history_search.search_history` | Keyword search over deterministic history (journal/health/goals/faith/tasks/finance/captures/notes) |
| `execute_action` | action | 6 | `action_execution.execute_action` | The single write surface (see §6) |

`get_decision` modes: `execution` | `risk` | `fix`. `get_domain_state` /
`search_history` domains are validated against `supported_domains()` /
`SUPPORTED_HISTORY_DOMAINS`. `get_foundational_health_facts` keys are validated
against `SUPPORTED_FACTS`.

### Domain registry (read surface)
`domain_state.DOMAIN_REGISTRY` maps ChatGPT-facing domain → canonical SAE module
key (an **exposure** layer on top of SAE; it never edits SAE's own alias map). 23
domains, e.g. `purpose→goals`, `life→tasks`; `notes→None` (no SAE state — retrieved
via `search_history`, returns `no_state_source`). Unknown domains return
`unsupported_domain` with the supported list.

---

## 5. Dispatch model

`apps/ai/cos_services/tool_dispatcher.py :: dispatch_tool_call(user, name, arguments)`.
Deterministic routing only — validate → execute bound handler → JSON-safe envelope.
**Never raises into the OpenAI tool loop.**

Envelope: `{ "tool", "ok": bool, "result" | "error", "code" }`.

Error codes: `unknown_tool`, `tool_not_enabled`, `bad_arguments` (TypeError from the
model's args), `execution_error`. No silent failures — every path is logged +
telemetered. Results over `_MAX_RESULT_CHARS` (8000 bytes serialized) are replaced
with a `{_truncated: true, _note}` stub so the model asks for a narrower scope.

---

## 6. Write surface & safety constraints

`apps/ai/cos_services/action_execution.py :: execute_action(user, action, params)`.
ChatGPT **never writes directly.** It requests; WLJ executes through the **single
existing write path**:

```
execute_action()  →  IntentService.execute_intent(IntentResult, user)  →  UAIO  →  handler
```

No new write path, no new action framework, no direct model writes, no UAIO bypass
(Law 8). The fail-closed Learning-Mode gate and existing validators are preserved
automatically because dispatch goes through `execute_intent`.

**Day-1 allowlist** (`DAY1_ACTION_ALLOWLIST`, 13 actions): `create_task`,
`mutate_task`, `complete_task`, `create_goal`, `update_goal_progress`,
`create_journal_entry`, `add_gratitude`, `log_prayer`, `save_verse`, `create_event`,
`add_reminder`, `log_habit`, `log_workout`. Anything else → `denied`. Widening a
phase = widening this allowlist; **no dispatch changes**.

**Confirmation gate** (`_confirmation_required`, reuses
`apps.core.ai_orchestrator.action_policy.ACTION_POLICY`): an action requires explicit
`confirmed=true` when its policy category is `DESTRUCTIVE`, its risk is
`HIGH`/`CRITICAL`, or it `requires_explicit_verb`. Unknown action → require
confirmation (safe default). Routine creates/logs/completes execute directly.

Action statuses: `success`, `failed` (handler returned `success=False` — e.g. not
found, learning-mode active), `denied` (not allowlisted), `confirmation_required`,
`error` (raised — logged). The model must report the returned message honestly and
never claim an action it didn't perform.

---

## 7. Authoritative implementation locations

| Concern | File |
|---------|------|
| Service package / public API | `apps/ai/cos_services/__init__.py` |
| Standing context | `apps/ai/cos_services/standing_context.py` |
| Generic domain reads | `apps/ai/cos_services/domain_state.py` |
| Foundational health facts | `apps/ai/cos_services/health_facts.py` |
| History search | `apps/ai/cos_services/history_search.py` |
| Action execution (write) | `apps/ai/cos_services/action_execution.py` |
| Tool registry + schemas + flag | `apps/ai/cos_services/tool_registry.py` |
| Tool dispatcher | `apps/ai/cos_services/tool_dispatcher.py` |
| JSON-safety helpers | `apps/ai/cos_services/serialization.py` |
| Tool-loop wiring (both paths) | `apps/ai/personal_assistant.py` |
| Decision pipeline reused | `apps/ai/cos_mode_router.py`, `apps/core/execution/execution_state.py`, `apps/core/execution/selectors.py` |
| Write path reused | `apps/ai/intent_service.py` (`execute_intent`) → UAIO |
| Live validation command | `apps/ai/management/commands/validate_cos_tools.py` |

---

## 8. Change discipline

This contract is **canon** — keep it in sync with `apps/ai/cos_services/` whenever
the tool surface, standing-context schema, allowlist, or flag model changes (the
same auto-maintain discipline as `docs/ENGINE_COS_REFERENCE.md`). Bump the version
and `Last updated` on any change.

---

*Related: [[WLJ ARCHITECTURE LAWS]], [[WLJ SIGNAL ONTOLOGY]], [[WLJ DOMAIN REGISTRY]].
Design rationale: `../06_COS_DESIGN_REFERENCE/`, `../07_COS_TOOLS_REFERENCE/`.
Live status: `../08_IMPLEMENTATION_TRACKER/`.*
