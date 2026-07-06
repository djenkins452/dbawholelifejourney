# WLJ Current Context Contract — Page Awareness as a Platform Capability

**Status:** IMPLEMENTED (2026-07-06). Phase 0–2 shipped: core contract + Beth delegation + Goals/Faith/Journal migrated. Task has no detail page (nothing to migrate). Contract tests in `apps/core/tests/test_current_context.py`.
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
