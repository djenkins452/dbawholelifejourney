# WLJ Current Context Contract — Page Awareness as a Platform Capability

**Status:** IMPLEMENTED (2026-07-06). Core contract + auto-declaration + object-centered conversation + planner-owned object selection. Contract tests in `apps/core/tests/test_current_context.py` and `apps/ai/tests/test_page_reference.py`.

---

## Model-Interface path (KEEPER — post-pivot, 2026-07-10)

On the pivot-aligned runtime (`use_model_interface`), Current Context is **Pillar 4** of the Executive Context Envelope, not a lane. `apps/ai/cos_services/current_context.py :: get_current_context_baseline()` now RESOLVES the declared `focus_ref` server-side via `apps.core.current_context.resolve_current_context()` and emits `current_screen = {location, focus}`:

- **`location`** (WHERE) — deterministic navigation facts (url/module/title) from the client. Location, not content.
- **`focus`** (WHAT) — the canonical object the page declared, resolved from the source-of-truth model, user-scoped: `{ref, kind, title, content, source: "canonical"}`. **The client-scraped `page_content` blob is NOT forwarded as truth** on this path. A declared reference that fails to resolve → `focus: null` + a sync/ownership `note` (never "does not exist").

The keeper does **no reasoning** over the object (no bespoke LLM call — that was the legacy `answer_page_reference`); it hands `focus` to the model, and the constitution (`apps/ai/model_interface/constitution.py`) tells the model `focus.content` is authoritative and answers deixis ("this/that/it"). Tests: `apps/ai/tests/test_current_context_baseline.py`.

### Transport must exist on EVERY chat surface (2026-07-10)

WLJ ships two Beth surfaces — `chat_widget.html` (bubble) and `assistant_panel.html` (docked drawer) — both included in `base.html`. **Both MUST read `<meta name="wlj-context">` and send `focus_ref`.** `assistant_panel.html` originally did not, so Goal Detail (and every declaring page) read as "no focused object" *on the drawer* even though the meta rendered correctly upstream — the reference never left the browser. The declaration (View→HTML→Meta) was healthy; the transport layer was implemented on only one surface. Guarded by `apps/purpose/tests/test_goal_detail_declaration.py :: ChatSurfaceTransportContractTests`. Residual/follow-up: the meta read is duplicated inline per surface — extract a shared `wlj-current-context.js` so a future third surface can't drift.

### Ownership model — current request wins; conversation is a safety net (2026-07-10)

Current Context answers *"what is the user looking at RIGHT NOW?"*, so the **current request is always authoritative**; conversation state is a fallback that only fills a gap and **never becomes the authoritative source** (it would risk stale truth — e.g. returning Goal A after the user moved to Goal B). `get_current_context_baseline(user, page_context, conversation, now)` applies:

1. **Priority 1 (authoritative):** the current request's declared `focus_ref` resolves → `focus.authority = "current_request"`, and the ref is remembered against the conversation (`apps/ai/cos_services/current_focus_store.py` — cache-backed, **reference only**, 1h TTL, not history).
2. **Declared-but-unresolved:** the client sent a ref that failed (sync/ownership) → report it, **never** fall back (don't mask it with a different object).
3. **Priority 2 (safety net):** the client sent **no** ref this turn (intermittent omission) → re-resolve the conversation's last-seen ref to **fresh** canonical content, marked `authority = "conversation_fallback"`, `source = "fallback"`, with `freshness` (`current`/`stale` via `classify_sync_freshness`, 15-min threshold), `age_seconds`, `as_of`. Content is always fresh; only the identity can be stale, and it's flagged. A fallback turn does **not** refresh the remembered timestamp — age grows from the last authoritative sighting. The constitution tells the model to confirm a fallback (esp. `stale`) rather than assert it as current.

**Sequenced full-retire (blast-radius bound):** the DOM scraper (`extractPageContent` in `chat_widget.html`) and the legacy reasoning (`chatgpt_cos/page_reference.py :: answer_page_reference`) still feed the `chatgpt_cos` + `legacy` runtimes and are retired **when those runtimes are**, not before. Mixin rollout to Health/Calendar/Journal/Finance/Reports is the follow-up (proven on Goals first).

**Resolution order (`resolve_page_focus`):** (1) declared `focus_ref` (`<meta name="wlj-context">` — auto for any DetailView of a `UserOwnedModel`, or explicit via `CurrentContextMixin` on overview pages) → (2) deterministic URL-based `resolve_focused_object` (any detail/landing URL, no per-page code; **server truth over the client scrape**) → (3) legacy client content. Both `focus_ref` and the URL resolver return content via the model's `get_context_summary()`.

**Coverage (2026-07-06):** Goals (`LifeGoal` detail + Purpose dashboard → active mission goal), Journal (`JournalEntry`), Faith (the **production Journey system** `apps.faith.journey.JourneyDay`, narrated from scripture refs + verse blocks + `context_before` + `key_insight` + `reflection_prompt`; legacy `UserReadingPlan` preserved). A new page becomes conversational by being a `UserOwnedModel` DetailView (auto) or adding `CurrentContextMixin` (overview) — never by editing the Chief of Staff.

**Ownership (proven, 2026-07-06):** for the reasoning lane, the **PLANNER** owns object selection. `reasoning/engine.py` reads `get_current_focus()`; `reasoning/stages.py :: run_planner(user, message, focus)` receives the focus **identity only** (kind + title, never content) **before** planning and selects the domain. Retrieval/working-memory/reasoner are deterministic executors; the reasoner sets `skip_current_context=True` — it grounds through curated working memory, never a prompt-prepend. The shared choke point `services.py :: _ground_current_context` remains only for the planner-less tool-loop fallback.

**Governing rule — Object-Centered Conversation, NOT phrase matching.** The contract answers exactly one question: *"What canonical object is the user currently talking about?"* It hands that object to the executive brain; Beth determines intent and handles ANY natural question about it ("am I making progress?", "what concerns you?", "how does this apply to my life?") — grounded, without the user restating what's on screen. The contract never interprets a phrase.

**Injected ONCE, before lane routing (Chief-of-Staff capability, not per-lane / not tool-loop-only).** The turn's focused object is resolved once at the top of `ChatGPTCoSService.generate` (before `route_message`) and stored in a turn-scoped context (`current_context.set_current_focus`). It is then injected at the **single shared LLM-call choke point** — `services.py :: _ground_current_context`, called inside `_call_api` and `_call_api_with_tools` — so **every reasoning lane's answer** begins with the same `CURRENT CONTEXT / OBJECT IN FOCUS` preamble, then applies its specialization. No lane builds Current Context itself; adding a new lane requires no Current-Context code. Exclusions (must NOT be grounded): the **sandboxed general lane** (`bypass_breaker=True` — stays personal-data-free), the **planner/classifier** and **fact-phrasing** calls (`skip_current_context=True`), and `cos_page_reference` (self-grounds). Root cause this fixed: Current Context was injected only in the tool-loop path, so a reasoning lane (the health lane) that intercepted before the tool-loop built a health-only prompt with no object. `is_page_reference` remains only a deterministic deixis fast-path/degradation; it is not the capability.

**Declaration is automatic for DetailViews.** `base.html` emits `<meta name="wlj-context">` from `object` whenever it is a Narratable (`UserOwnedModel`) — so ANY DetailView is Beth-aware with zero per-view code. `CurrentContextMixin` is only for overview pages with ONE deterministic focus (e.g. the goals overview → active mission goal via `get_current_context_object`). A page with no single object stays honestly unresolved (Beth asks which one).
**Governing principle:** Beth (the One Brain) must understand *where the user is, what page is open, what object is in focus, and what canonical content belongs to it* — for **any** WLJ page — **without page-specific conversational code.** A new page becomes conversational by implementing ONE contract, not by editing Beth.

---

## 1. The core inversion

**Today:** Beth and the chat widget *reverse-engineer* the page — URL parsing, DOM scraping, and field-guessing spread across two places, one branch per module.

**Contract:** the page *declares* the canonical object in focus (a reference, not its content); Beth *resolves* it through Django's own ContentType framework plus a small model protocol. Module knowledge lives with the module (its view + model), never inside Beth or the widget.

> Declare **identity** on the page. Resolve **content** on the server. Beth consumes a uniform result.

---

## 2. The contract (three generic layers)

### Layer 1 — DECLARATION (the only thing a page implements)
A page states its focused canonical object **once**, declaratively — generalizing the existing `[data-help-context]` precedent.

- Class-based views add `CurrentContextMixin` and set `current_context_object = self.object` (DetailViews get this for free from `self.object`).
- `base.html` emits a standard descriptor into every page:
  ```html
  <meta name="wlj-context"
        content="purpose.lifegoal:42"            {# app_label.model:pk — a canonical ContentType ref #}
        data-kind="goal"
        data-title="France 2027 Family 18K Mission">
  ```
- Object-less pages (dashboards, lists) declare only a `context_type` (e.g. `goals_overview`) or nothing — Beth then falls back to the module's current object or an honest "which one?".

The page declares a **reference**, never the content. It says *"the object in focus is LifeGoal #42"*, not the goal's text.

### Layer 2 — TRANSPORT (one generic client reader)
`getPageContext()` becomes module-agnostic: read `<meta name="wlj-context">` + URL + title + `help_context_id`. It ships the **reference**. The per-page `extractPageContent()` scrapers are deleted. (Escape hatch for genuinely client-only content — e.g. an unsaved draft — is a single standard attribute `data-wlj-context-content`, the rare exception, not the rule.)

### Layer 3 — RESOLUTION (one generic server resolver — the source of truth)
`apps/core/current_context.py :: resolve_current_context(user, ref=None, url=None)`:
1. Parse the ref → `(app_label, model, pk)` (fallback: parse the URL for a `/<pk>/`).
2. `ContentType` → model class → fetch the object.
3. **Ownership enforced generically** — `UserOwnedModel` has a `user` FK, so `obj.user_id == user.id`; non-owned models implement `is_owned_by(user)`. Never leaks another user's record.
4. Return `obj.get_context_summary()` → `{title, content, kind}`.

Content is **always** resolved server-side from the canonical model — never trusted from client-scraped DOM (stale/tamperable, and it violates WLJ's "the data layer owns the truth").

### The model protocol (Narratable)
`get_context_summary(self) -> {"title", "content", "kind"}`, with a **default** on `UserOwnedModel`:
- `title` ← `title`/`name`/`__str__`
- `content` ← a declared `CONTEXT_FIELDS = ["description", "why_it_matters", ...]`, else common text fields
- `kind` ← the model's verbose name

A model becomes narratable by (optionally) declaring `CONTEXT_FIELDS` or overriding `get_context_summary()`. Most models need nothing.

---

## 3. Beth stays One Brain — unchanged
`answer_page_reference`, the `page_reference` lane, deixis handling, response coherence, and page-aware degradation are **already** module-agnostic. They consume `resolve_page_focus`, which now delegates to `resolve_current_context` instead of the `if module ==` branches. Beth never gains page-specific intelligence; the contract hands it uniform `{title, content, kind}`.

---

## 4. Where the current architecture fragments (evidence)
- **Client:** `getPageContext()` hard-codes `if url.startsWith('/faith/')…`; `extractPageContent(url, module)` has large per-page DOM scrapers (`templates/components/chat_widget.html`).
- **Server:** `resolve_focused_object(user, url, module)` has `if "/goals/" in u`, `/journal/`, `/task` branches (`apps/ai/chatgpt_cos/page_reference.py`).
- **Heuristics:** `_TEXT_FIELDS` / `_LIST_FIELDS` guess where content lives.
- **Net:** every new page requires code in **two** places that both encode module knowledge Beth should not own. This is the "twenty page integrations" trap.

---

## 5. Migration plan
**Phase 0 — build the contract (core, once):**
`apps/core/current_context.py` (`resolve_current_context`); `get_context_summary()` + `CONTEXT_FIELDS` on `UserOwnedModel`; `CurrentContextMixin` (CBV) + `{% wlj_current_context %}` in `base.html`; generic `<meta name="wlj-context">` reader in the widget.

**Phase 1 — point Beth at it:** `resolve_page_focus` delegates to `resolve_current_context`; **delete** the per-module branches in `resolve_focused_object`. Beth's lane code untouched.

**Phase 2 — migrate the current pages:** add `CurrentContextMixin` to Goals / Journal / Task / Faith detail views; declare `CONTEXT_FIELDS`/override `get_context_summary()` where richer narration helps; delete the client per-page scrapers.

**Phase 3 — make it the standard:** a contract test (à la the Visual Truth Contract) asserts every user-data DetailView declares a context object; document "add `CurrentContextMixin` → the page is conversational."

---

## 6. Why this is permanent
Beth only ever knows **the contract**. A new module's DetailView adds one mixin (and, optionally, `CONTEXT_FIELDS`) and immediately supports *"Explain this / Summarize this / What do you think? / Should I still do this? / What does this mean?"* — because those route through the module-agnostic `page_reference` lane consuming the generic resolver. Adding a page **cannot** require Beth changes, because the module declares its own context and the server resolves it through Django's own object graph. Page Awareness stops being a collection of integrations and becomes a platform capability.
