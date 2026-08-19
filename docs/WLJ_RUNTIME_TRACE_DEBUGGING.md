# WLJ Runtime-Trace Debugging Protocol

**Status:** Governing standard for ALL production debugging in WLJ.
**Origin:** 2026-07-06 — the "milestone win" incident, where a healed database row
still rendered stale in the browser. Multiple rounds were spent proving *which*
layer actually produced the observed output. This protocol makes that proof the
FIRST move, not the last.

---

## Primary Rule

**Never modify code until you have proven that the code being modified actually
produced the observed behavior.**

- Finding *plausible* code is NOT sufficient.
- Finding *similar* code is NOT sufficient.
- Finding the *actual runtime execution path* is REQUIRED.

If you cannot prove a function executed on the request that produced the bug, you
may not "fix" it.

---

## The Seven Phases

### Phase 1 — Reproduce
Capture the exact reported context before searching for any fix: **URL, user,
page, workflow, exact observed behavior, screenshot**. Record what the user
literally sees (a string, a number, a state), not your paraphrase of it.

### Phase 2 — Trace the runtime (work backwards)
Starting from the UI being displayed, prove every layer down to the database:

```
Browser DOM → HTTP response body → Template → View → Composer → Builder → Data source → Database
```

Produce the **exact** runtime call chain. Do not assume a template is used, a
composer is used, or a generator is used — resolve it (`django.urls.resolve`,
read the URLconf, read the view). In WLJ the entry point is often a *dispatcher*
(`dashboard_home_dispatch` → `DashboardV3View.as_view()`), not the obvious view.

### Phase 3 — Prove execution
For every function believed to participate, prove it ran: logging,
request instrumentation, a debug endpoint, or a runtime trace. **If it never
executes, it is not the code path — stop modifying it.**

### Phase 4 — Identify duplicate producers
Search for **every** producer of the observed behavior (composer, pipeline,
recommendation engine, signal, event processor, dashboard builder, cached
serializer, persisted object). If several exist, list them and determine which
one actually generated the output. **Never stop after finding one producer.**

WLJ-specific duplicate-producer traps proven in real incidents:
- A **persisted object** vs a **live composer**: the dashboard renders a stored
  `GuidanceItem` (produced earlier by `significant_events._persist_major_win`),
  not a value computed at render time — so fixing the composer does nothing to an
  already-persisted row. Heal the row (data migration) too.
- A **by-design label that shares the buggy string**: "Milestone reached" is BOTH
  a (buggy) card title AND a legitimate mission-panel *state label*
  (`_STATE_MILESTONE_WIN` / `_build_mission_panel`). A whole-document substring
  match is misleading — extract the specific element.

### Phase 5 — Build a glass box
If runtime ownership is unclear, create a **temporary authenticated debug
endpoint** that exposes raw deterministic truth — never composed, summarized, or
regenerated. Expose: source model, record id, generator, composer output,
template, rendered HTML, timestamps, cache state, response headers.

Reference implementation: `apps/dashboard_v3/debug_views.py`
(`/debug/purpose-recommendation/`). It returns, in one request:
1. the **raw DB record** the surface selects (exact ORM query replicated),
2. **`server_render`** — the real composer output + the real rendered fragment,
3. **`origin_document`** — an internal, cache-bypassing GET of the FULL page via
   `django.test.Client` (real host + HTTPS), reporting `git_commit`,
   `view_class`, `template_rendered`, `response_headers`, and the precisely
   extracted element (not a document-wide substring).

Cache-bypassing origin capture is the key technique: it separates "the origin
renders stale HTML" (a render bug) from "an intermediary served a stale body" (a
cache bug). Gotcha: `response.templates` is empty outside the test runner —
derive template/view from `resolve()` + `view_class.template_name`.

### Phase 6 — Implement
Only after the runtime path is proven. Fix the **proven** execution path. Do NOT
redesign, do NOT improve adjacent code, do NOT "clean up" nearby producers.

### Phase 7 — Verify five-way agreement
```
Database → Deterministic object → Composer → Rendered HTML → Browser DOM
```
If any two differ, keep tracing to the **first point of divergence**. A unit test
passing is NOT verification — the browser displaying the corrected behavior is.

---

## Required Output for Every Production Debugging Report
1. Runtime call chain.
2. Actual producer.
3. Duplicate producers discovered.
4. Root cause.
5. Why earlier assumptions were incorrect.
6. Files changed.
7. Proof the corrected runtime path now produces the expected behavior.

---

## Proving a capability is ABSENT (2026-08-18)

**A name search is not proof of absence.** While diagnosing the "Mark Shower complete"
incident, a grep for `complete_routine_item` returned nothing, and that was reported as
*"no routine-completion capability exists anywhere."* It was wrong. `complete_execution_item`
already existed, was already model-facing, and its routine branch already delegated to
`toggle_routine_completion` — the exact authority the Dashboard button uses. The proposed
fix would have added a **second** model-facing completion verb for objects that already
had one.

Before declaring a capability missing, trace it **by behaviour, not by name**:

1. Enumerate the tools/intents actually **registered** for the runtime (e.g. `all_tools()`,
   `ALLOWED_WRITE_INTENTS`, the intent registry) — not the names you expect to find.
2. Follow each plausible candidate to its **delegation target** and see which domain
   authority it ends at.
3. Compare that target with the authority the **visible UI control** uses. If they match,
   the capability exists and the defect is discoverability, parameters, or routing.

The corrected fix was much smaller: extend the existing verb to accept canonical identity,
rather than build a parallel one.

## Mutable state: current truth outranks history (2026-08-18)

**An assistant's prior statement about mutable state is conversation, not truth.**

Proven in production: a completion reported `recorded` and wrote no canonical row. Five
hours later, with **zero tool calls**, the CoS asserted the item was "already marked as
complete" — reading its own earlier sentence as current state. Canonical rows showed the
item was never completed by the assistant at all; the only completion row that day was
created manually, hours later.

The precedence rule for anything that can change (completion, progress, counts,
schedules):

> **current canonical truth  >  historical action result  >  assistant prose/history**

- *current canonical truth* — what is true NOW, read from the owning domain authority.
- *historical action result* — what a prior action reported at that time. It explains
  history; it never establishes the present.
- *assistant prose* — never a truth authority, at any age.

Two structural consequences, both now enforced:

1. **An action result may report success only when the domain authority verifies the
   requested state** (postcondition verification). A handler returning without raising is
   not evidence.
2. **Current state must be projected explicitly**, per item, from the canonical value —
   not left to be inferred from which bucket an item appears in, and never from memory.

The second matters because the first alone is not enough: correct truth was available and
fresh in the envelope, but nothing *stated* it about that item, so recollection filled the
gap. When a claim about mutable state is cheap to make explicit, make it explicit.

## Anti-Patterns (do NOT)
- Modify code because it *looks* related.
- Improve nearby code before proving ownership.
- Assume a template / composer / generator is used.
- Stop after finding one producer.
- Declare success from unit tests alone.

---

## Success Criteria
A bug is solved ONLY when the runtime execution path is proven, AND the browser
displays the corrected behavior, AND every deterministic layer agrees —
Database → Object → Composer → Template → Browser — with no contradictions.

---

## Standing WLJ instruments & traps (accumulated)
- **Glass box:** `/debug/purpose-recommendation/` (`apps/dashboard_v3/debug_views.py`) — remove when its incident closes.
- **Persisted vs live:** dashboard cards render stored `GuidanceItem` rows; the sticky win key is `cos_event:win:milestone:<id>`. See `docs/SIGNIFICANT_EVENT_PIPELINE.md`.
- **Cache layer:** the authenticated dashboard is `@never_cache`; without it, browser/WKWebView `NSURLCache`/CDN/bfcache can serve a stale authenticated document. A correct DB + a stale browser = suspect the response headers, not the composer.
- **Label trap:** "Milestone reached" is a legitimate mission-panel state label — never whole-document-match a string that a by-design label also emits.
