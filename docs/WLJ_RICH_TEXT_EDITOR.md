# WLJ Rich Text Editor — the standard for all narrative writing

**Status:** Platform capability (Phase 1 shipped — Journal is the reference
integration). This is the ONE editor for every free-form/narrative field in WLJ.
Do **not** build a second editor, fork it per module, or add a different
storage strategy. New modules adopt this component with a few lines.

> One editor. One component. One styling system. One storage strategy.

---

## What it is

A reusable [TipTap](https://tiptap.dev)-based editor, self-hosted (no CDN),
dropped into any form by swapping a field's widget. It gives every writing
surface the same modern experience: bold/italic/underline/strike/inline-code,
H1–H3, bullet/numbered/task lists, block quote, divider, links (with pasted-URL
recognition), image upload (drag / paste / pick, resizable), simple tables,
left/center/right alignment, undo/redo, and the standard keyboard shortcuts
(Ctrl+B/I/U/Z/Y, Ctrl+K for links).

## Architecture (where everything lives)

| Concern | File |
|---|---|
| Vendored editor bundle (self-hosted IIFE, `window.WLJTipTap`) | `static/vendor/tiptap/tiptap.bundle.js` |
| Bundle build source (npm + esbuild) | `frontend/tiptap/` (`README.md` has build/upgrade steps) |
| Editor glue (mounts editor + toolbar on `[data-wlj-rte]`) | `static/js/wlj-rich-text.js` |
| Styling (editor chrome + rendered `.wlj-rich`) | `static/css/wlj-rich-text.css` |
| Form widget | `apps/core/widgets.py :: WLJRichTextWidget` |
| Page assets partial | `templates/components/_rich_text_editor_assets.html` |
| Sanitizer + plain-text shadow + storage mixin | `apps/core/rich_text.py` |
| Shared image upload endpoint | `apps/core/rich_text_views.py` → `core:rich_text_image_upload` |
| Uploaded-image record | `apps.core.models.RichTextImage` |

## Storage strategy — sanitized HTML + a plain-text shadow

The rich field stores **sanitized HTML** as the single source of truth. A
companion `*_plain` field holds an **auto-derived plain-text shadow** that keeps
everything that predates rich text working unchanged: full-text search, preview
snippets, word counts, reports/exports, and assistant narration all read the
shadow. The shadow is regenerated on every save and is never edited directly.

- **Sanitization is server-side and mandatory** (`nh3`, allow-list) — client HTML
  is never trusted, on any path (editor, API, migration). The allow-list matches
  exactly what the editor emits. Alignment is a `data-text-align` attribute, never
  inline `style` (nh3 cannot filter CSS properties).
- **Images** upload to the default storage (Cloudinary in prod / local FS in dev)
  via the one shared endpoint and embed as `<img>` in the HTML — part of the
  document, not an attachment.

## How to adopt a field (the standard)

For a model field `notes` that should become rich text:

1. **Model** — inherit the mixin, add the shadow field, declare the pair:
   ```python
   from apps.core.rich_text import RichTextMixin

   class Thing(RichTextMixin, UserOwnedModel):
       notes = models.TextField(blank=True)
       notes_plain = models.TextField(blank=True, default="", editable=False)
       RICH_TEXT_FIELDS = {"notes": "notes_plain"}
   ```
   `RichTextMixin.save()` sanitizes each HTML field and regenerates its shadow.
   If the model has its own `save()`, call `self.sync_rich_text_fields()` at the
   top before reading the field (e.g. for a word count).

2. **Form** — swap the widget:
   ```python
   from apps.core.widgets import WLJRichTextWidget
   widgets = {"notes": WLJRichTextWidget(placeholder="…")}
   ```

3. **Form template** — load the editor assets once:
   ```django
   {% include "components/_rich_text_editor_assets.html" %}
   ```
   Render the field with `{{ form.notes }}` (don't hand-roll a `<textarea>`).

4. **Read templates** — render the HTML inside `.wlj-rich`:
   ```django
   <div class="wlj-rich">{{ thing.notes|safe }}</div>
   ```
   The `.wlj-rich` render CSS is loaded globally in `base.html`.

5. **Consumers of the old plain text** — point word counts, previews,
   `*__icontains` search, `CONTEXT_FIELDS`, and exports at `notes_plain`.

6. **Migration** — add the shadow field, then a data migration that converts
   legacy plain text losslessly (`plaintext_to_html` escapes & wraps; derive the
   shadow with `rich_text_to_plaintext`). See
   `apps/journal/migrations/0012_backfill_journal_richtext.py` for the template.

## Which fields DO / DO NOT get the editor

**Do:** journal entries, reflections, notes, narrative descriptions, comments —
anything a person writes as prose.

**Do NOT:** titles, names, one-line descriptions/labels, status/type/reason
codes, search/keyword fields, tokens/OCR/error/system text, and AI-generated
display text. When in doubt: is the user *writing prose*? If not, leave it a
plain input.

## Rebuilding / upgrading the bundle

See `frontend/tiptap/README.md`. In short: edit `frontend/tiptap/src/index.js`
(only add an extension a toolbar control uses), `npm run build`, run
`collectstatic` (must be 0 errors), bump the `?v=` in
`_rich_text_editor_assets.html`, smoke-test, commit the new `tiptap.bundle.js`
and `package-lock.json`.

## Tests

`apps/core/tests/test_rich_text.py` locks the sanitizer (no XSS survives a save),
the plain-text shadow, the `RichTextMixin` storage contract, and the image
upload endpoint (auth + validation).
