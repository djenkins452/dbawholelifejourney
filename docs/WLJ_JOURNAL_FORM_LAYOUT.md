# WLJ Journal Form Layout — Scroll & Sizing Model

**Status:** RATIFIED 2026-07-21. Governs `templates/journal/entry_form.html` (Create **and** Edit — one template).
**Rule in one line:** the Journal form is **ordinary document-flow content inside the app shell**. It sets **no** viewport heights, **no** overflow, **no** flex-fill chain. The editor's height comes from the shared Rich Text Editor; the page scrolls exactly like every other page.

This document exists because the Journal editor's height/scroll behavior was "fixed" six times, each fix moving the failure instead of removing it. It records the layout stack, the scroll-ownership model, why the earlier fixes failed, and the durable design — so no future change reintroduces the class.

## 0. Presentation — the Compose Dock (Option C, shipped 2026-07-21)

On the reliable document-flow base below, the form presents as a **writing-first compose view**: a quiet title, a large editor, and a **compose dock** — a `position: sticky; bottom: 0` bar (inside the shell scroll, paint-only) that carries **always-visible mood / tags / categories chips** plus **Save / Cancel**. The chips mirror the current selection (e.g. `😊 Great · 🙏 Grateful`, `🏷 Family • Work`) so the user has continuous awareness without opening anything; tapping a chip opens a **lightweight picker** — an overlay anchored above the dock (`position: absolute`), so opening it causes **zero layout shift and no change to editor height or page scroll**. The metadata `<input>`s live inside the pickers, unchanged (names `emotions`/`categories`/`tags`), so POST is byte-for-byte identical. A small JS controller (CSP-safe: nonce, `addEventListener`, delegation) opens/closes one picker at a time and re-renders each chip live on `change`. This is Option C from the UI-architecture proposal, and it obeys every invariant in §8 — it is *the document-flow base wearing a writing-app surface*, not a new layout model.

**Visual hierarchy (fixed — the editor owns the screen; everything else supports writing):**

1. **Journal mode** (Just Write / Write Together / Talk It Through)
2. **Document** (the entry: title, date)
3. **Writing** (the editor — the largest, primary surface)
4. **Metadata** (mood / tags / categories — informational-first, editable-second; always visible, never competing)
5. **Save** (predictable, in the dock, always in reach)

**This is not a Journal control — it is the first implementation of a reusable WLJ *Workspace Dock*.** The pattern (a constant editor/workspace + a sticky dock of always-visible, domain-specific metadata chips + the primary action) generalizes across workspaces — Health (Measurements · Symptoms · Medications · Save), Travel (Destination · Travelers · Budget · Save), Faith (Scripture · Prayer · Reflection · Save) — the editor stays constant; only the metadata controls change. **Generalize the Compose Dock into a shared WLJ Workspace Dock only *after* the Journal implementation is complete** (a platform-consumer capability per architecture `01 §6`, not a Journal fork). Governing statement of the platform pattern: `@WLJ_SYSTEM_PROMPTS/00_WLJ_CHIEF_OF_STAFF_STARTUP/01_READ_FIRST…ARCHITECTURE.md §6`.

---

## 1. Layout hierarchy (as-built)

```
html
└─ body.has-desktop-nav              ← desktop: height:100vh; overflow:hidden  (NEVER scrolls — by design)
   └─ .desktop-layout-wrapper        ← flex row; flex:1; min-height:0; overflow:hidden
      ├─ .desktop-left-rail          ← fixed sidebar
      ├─ .desktop-main-area          ← flex:1; overflow-y:auto  ★ THE SCROLL OWNER (desktop) ★
      │  └─ .main-content            ← flex:1 0 auto (sized to content, grows on short pages)
      │     └─ .journal-compose      ← plain block (max-width, centered) — OUR page root
      │        ├─ .jc-topbar
      │        ├─ [methods chooser | draft card | review banner]   ← Create-only conditionals
      │        └─ .jc-body
      │           ├─ form.jc-main
      │           │  ├─ .notebook (title, date, .notebook-body → shared RTE)
      │           │  ├─ details.journal-details (mood / categories / tags)
      │           │  └─ .form-actions (Save / Cancel)   ← position:sticky; bottom:0
      │           └─ [.jc-combine]    ← Create-only (finish a draft that also has a conversation)
      └─ .assistant-panel            ← position:fixed (Chief of Staff; out of flow — no effect on content height)
```

Defined in `static/css/desktop-nav.css` (`@media (min-width:769px)`). The Journal-specific CSS lives in the `<style>` block of `entry_form.html`.

## 2. Scroll ownership

| Viewport | Body | Scroll owner |
|---|---|---|
| **Desktop (≥769px)** | `height:100vh; overflow:hidden` — clipped, never scrolls | **`.desktop-main-area`** (`overflow-y:auto`) — one internal scroll region |
| **Mobile (<769px)** | normal document flow — scrolls | **`body`** (the document) |

This is a deliberate **application-workspace shell** on desktop (fixed top bar + left rail + one scrolling content region + fixed CoS panel) and **normal document flow** on mobile. It is shared by every page and works in Chromium and WebKit. There is intentionally **no document/body scrollbar on desktop** — the scrollbar belongs to `.desktop-main-area`.

**The Journal form's only job is to be well-behaved content inside that region.** It must not introduce its own viewport sizing, its own scroll container, or its own overflow — doing so fights the shell.

## 3. Editor sizing (the durable rule)

The editable area's height comes **entirely from the shared RTE**:
- `apps/journal/forms.py` configures the body field with `WLJRichTextWidget(min_height=420)`.
- The RTE puts that as an inline `min-height:420px` on `.wlj-rte-content`; the editable surface inherits it (`.wlj-rte-prose { min-height: inherit }` in `wlj-rich-text.css`).
- Result: the writing area is a comfortable **420px** and **grows with the text**. No viewport units. Identical mechanism to every other RTE page (notes, etc.).

`entry_form.html` adds **styling only** to `.notebook-body .ProseMirror` (serif font, rhythm, caret) — **never** height, min-height, flex, or overflow. It must **not** override `.wlj-rte-content`'s min-height.

Because the editor height is `max(420px, content)` and depends on nothing external, **selecting/removing a mood, tag, or category cannot change it**, and nothing on the page can suppress scrolling.

## 4. Save / Cancel actions

`.form-actions` stays `position: sticky; bottom: 0` inside the scroll region — the "floating" controls the product wants. Sticky is a **paint-position** feature: it never creates or removes scroll, and it is the last element in the form so it hides nothing. Verified: with the sticky footer present, `.desktop-main-area` remains fully scrollable in every state.

## 5. Why the earlier fixes failed (the moving failure)

Each attempt tried to make the editor *fill the remaining viewport* — a goal that inherently pulls viewport math into a shell that already owns scrolling:

1. **Fixed/min-height editor (360px)** — didn't fill; large blank gap on tall viewports.
2. **Deep `flex:1 1 auto` fill-chain** inside `.journal-compose { min-height: calc(100dvh-64px) }` — filled at load, but WebKit **re-resolves `flex-basis:auto` against the indefinite (min-height) container on the first reflow** (selecting a mood toggles `:checked`), collapsing the editor to its floor → the "editor squishes on mood select" report.
3. **Sticky footer** — good UX, kept.
4. **`dvh`** — live-updates as the iOS URL bar shows/hides → interaction-time jump.
5. **`svh`** on the editor (`min-height: calc(100svh - 400px)`) — removed the flex-chain collapse, but injecting a **viewport-relative min-height into `.main-content` (flex:1 0 auto) inside a `100vh; overflow:hidden` workspace with a nested `overflow:auto` scroller** destabilized the scrollport in WebKit → **the page scrollbar vanished / content clipped and unreachable on Create.**
6. **Direct ProseMirror viewport sizing** — same class as #5.

**Root class:** *the Journal form tried to be a viewport-constrained workspace while living inside an app shell that is already the workspace.* Two workspace models nested → the inner one fought the outer one's scroll ownership. Every viewport-unit fix moved the symptom because the **condition** (viewport sizing inside the shell's scroll region) was never removed.

## 6. Chosen model & why

**Option A — normal document flow** (chosen). The Journal form is plain content; the shell scrolls it. Editor = shared-RTE 420px min-height, grows with content. No `vh/dvh/svh`, no flex-fill chain, no nested scroll container, no overflow rules. This makes Journal **identical to every other page**, which already scrolls correctly in Chromium and WebKit.

Rejected: **Option B** (build a true viewport workspace *inside* the page) — redundant with the shell and the source of the whole failure class. **Option C** (two-column desktop) — a larger redesign not required to fix correctness; can be layered later on top of the document-flow base without reintroducing viewport sizing.

## 7. Create vs Edit

Same template, same CSS, same editor sizing. They differ **only** in Create-only conditional blocks above/after the form (methods chooser, draft card, review banner, `.jc-combine`). None of these change the editor height or the scroll model — they are ordinary flow content. Verified DOM-identical for the sizing-relevant elements.

## 8. Invariants (do not break)

1. No viewport units (`vh/dvh/svh`) anywhere in the Journal form.
2. No `overflow`, `height`, `min-height`, `max-height`, or `flex` fill rules on `.journal-compose`, `.jc-body`, `.jc-main`, `.notebook`, or `.notebook-body`.
3. Never override `.wlj-rte-content`'s min-height (that is the editor's size, owned by the shared widget).
4. `.notebook-body .ProseMirror` rules are **styling only**.
5. The shared RTE (`wlj-rich-text.js/.css`) stays untouched and reusable — the page owns layout, the component owns the editor.
6. Same behavior on Create and Edit; scroll owner is `.desktop-main-area` (desktop) / `body` (mobile).

## 9. Verification (real rendered page, dev server)

Editor height **420px and invariant** across: Create empty · Create long (grows to content, page scrolls, all reachable) · Edit short · mood/tag/category select+remove · validation error (body preserved) · metadata collapse/expand · desktop (1440×900) · mobile (375×812). `.desktop-main-area` scrollable in every desktop state; `body` scrollable on mobile; no clipping; Save/Cancel reachable. Safari/WebKit cannot be driven locally — the design's guarantee is that Journal is now identical to every other RTE page, all of which scroll correctly in WebKit; final on-device confirmation is expected after deploy.
