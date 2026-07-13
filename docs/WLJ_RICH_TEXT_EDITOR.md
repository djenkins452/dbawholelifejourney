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

## Rollout status & intentionally plain-text fields

**Guiding rule:** *if a user is expected to write paragraphs, they get the editor; if a field is
typically one or two sentences, an annotation, or operational metadata, it stays plain text.* We do
**not** mechanically convert every field named `notes`.

**Adopted (rich text):**
- Journal `body`; Notes `body`; Relationships `Person.notes`, `PersonGroup.description`;
  Faith `PrayerRequest.description`/`answer_notes`, `FaithMilestone.description`, `BibleStudyNote.content`;
  Legacy `Person.bio`, `Place.description`, `LifeMilestone.description`, `Relationship.notes`.

**Intentionally left plain (with reasoning):**
- **Legacy `Memory.body`** — *deferred, not declined.* It is the highest-value legacy narrative, but it also
  feeds the revision history (`MemoryRevision.body`), AI `Output` generation, `body__icontains` search, and the
  immersive preservation renderer, and lives under the Legacy preservation architecture (importer never
  discards; Smart Refresh). It deserves a dedicated pass (route Output/search to the shadow, decide revision
  rendering) rather than a mechanical conversion.
- **Health log `notes`** (weight/glucose/sleep/workout/… entries), **Medical** `LabPanel`/`LabResult`/
  `MedicalDocument.notes`, **Finance** account/transaction/budget/goal `notes`, **Life** task/inventory/
  maintenance/pet/document `notes`, **Meals** `MealPlan.notes` — these are short per-entry annotations /
  operational metadata rendered in table cells and previews, not paragraph writing. Plain text is the right fit.
- **Life** `Recipe.instructions`/`ingredients`, `Routine.description`, `SignificantEvent.custom_message` —
  structured or one-line content, not free prose.
- **Users `UserPreferences.ai_profile`** — consumed directly as AI prompt context (many builders read it);
  it is data-for-the-model more than a document, and rich markup would leak into prompts. Kept plain.
- **Billing `FeatureSuggestion.suggestion_text`** — feeds plain-text notification emails; rich HTML would
  degrade there. Kept plain.
- **Purpose** goal/intention descriptions & reflections (`LifeGoal`, `HabitGoal`, `ChangeIntention`,
  `ReflectionResponse`) and **Life** `Project` description/purpose/reflection are genuine paragraph surfaces and
  are good future adopters — they use **generic CBVs without ModelForms**, so adopting them needs a
  `form_class`/`get_form` override (a different wiring than the ModelForm apps). Queued as the next pass.

Any future field adopts the editor by following “How to adopt a field” above — the pattern and the
`backfill_rich_text` migration helper make it a small change.

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
