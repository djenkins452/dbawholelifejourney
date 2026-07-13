# WLJ TipTap bundle — build source

This directory builds the **self-hosted** TipTap bundle that powers the WLJ
Rich Text Editor. There is **no runtime CDN dependency**: the built file is
committed to the repo and served by WhiteNoise like any other static asset.

## What it produces

`npm run build` bundles the entry `src/index.js` into a single minified IIFE:

```
static/vendor/tiptap/tiptap.bundle.js   (exposes window.WLJTipTap)
```

`window.WLJTipTap` exposes `Editor` plus only the extensions WLJ actually uses
(StarterKit, Underline, Link, ResizableImage, TextAlign, TaskList/TaskItem,
Table*, Placeholder). The editor UI/glue lives in
`static/js/wlj-rich-text.js`; styling in `static/css/wlj-rich-text.css`.

## Build / upgrade

```bash
cd frontend/tiptap
npm install          # installs pinned deps (package-lock.json is committed)
npm run build        # writes static/vendor/tiptap/tiptap.bundle.js
```

Then run the production static pipeline from the repo root so WhiteNoise's
manifest storage is happy before you push:

```bash
python3 manage.py collectstatic --noinput   # must report 0 errors
```

Bump the `?v=` querystring on the `<script>` in
`templates/components/_rich_text_editor_assets.html` so browsers pick up the
new bundle.

To upgrade TipTap: change the versions in `package.json`, `npm install`, run
`npm run build`, re-run `collectstatic`, smoke-test the editor, and commit the
new `tiptap.bundle.js` + `package-lock.json`.

## Notes

- `node_modules/` is git-ignored; `package.json` + `package-lock.json` are
  committed for reproducible builds.
- Only add an extension in `src/index.js` when a toolbar control in
  `static/js/wlj-rich-text.js` uses it — keep the bundle lean.
- The committed `tiptap.bundle.js` is the source of truth at runtime; you do
  **not** need Node installed to run WLJ, only to rebuild the bundle.
