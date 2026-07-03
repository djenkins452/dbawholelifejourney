# =======================================================================# File: docs/wlj_claude_changelog.md
# Project: Whole Life Journey - Django 5.x Personal Wellness/Journaling App
# Description: Historical record of fixes, migrations, and changes
# Owner: Danny Jenkins (admin@wholelifejourney.com)
# Created: 2025-12-28
# Last Updated: 2026-06-02 (fix(briefing): Executive Briefing coherence — one dominant narrative, no contradictory state)
# ================================================================# WLJ Change History

## 2026-07-03 — polish(legacy): Import experience + statistics + two-stage permanent delete

**Why:** Refinement while Danny begins importing his autobiography — make it feel like Legacy is *reading his life*, not processing data. No engine/architecture/Canonical-Truth changes.

**What:**
- **Warm import wording** — dropped user-facing "batch/chunk/chunk number". The import detail now reads "{document} · 446 stories found · N brought into Legacy so far", buttons "Read the next 2 / Read the next 10 / Read all N remaining", and a "Stories in {document}" list.
- **Import statistics** (`import_engine.batch_stats`) — a "✨ Your life is coming together" panel showing Stories read, People, Relationships, Places, Events, Quotes, Themes, Traditions, Keepsakes, and People-you'd-already-added; updates as more stories are read.
- **Review workflow** — after reading stories, a "Review the next story ›" / "See all drafts" continue bar so the next action is obvious.
- **Two-stage permanent delete** — outside the archive, "delete" still means Set aside; **only a set-aside (archived) memory** can be permanently removed, via a confirmation modal ("Permanently delete this memory? This can't be undone." → Cancel / Delete forever) that hard-deletes. New `MemoryDeleteForeverView` (refuses non-archived) + a shared CSP-safe confirm modal in the Legacy shell.
- **Dashboard statistics** — expanded to include Relationships, Imported stories, Waiting for review, Discoveries pending, plus a "Recently imported" list; updates automatically as the library grows.
- Fixed a CSS-vs-`hidden` bug (`.legacy-modal{display:grid}` overrode the `hidden` attribute → modal showed on load) with `.legacy-modal[hidden]{display:none}`.

**Verification:** 97 scoped Legacy tests green (3 new: batch stats, permanent-delete-only-when-archived + auth, dashboard stat keys; Discovery/OpenAI mocked); `check` + `makemigrations --check` clean (no model change). Verified in-browser on Danny's real import: the stats panel ("26 People, 19 Relationships, 2 Quotes, 3 Themes…"), warm read-next buttons, review-next workflow; archived a memory → Delete forever → confirmation modal → permanently removed (confirmed gone); Dashboard shows Imported stories / Waiting for review / 48 Discoveries pending + Recently imported. No console errors; widget suppressed.

**Files:** edited `apps/legacy/services/import_engine.py`, `apps/legacy/{views,urls}.py`, `apps/legacy/tests/{test_import,test_library_editor,test_studio_contributors_outputs}.py`, `templates/legacy/{import_detail,dashboard,_memory_actions,base_legacy}.html`, `static/css/legacy.css`, `static/js/legacy.js`, `docs/wlj_claude_changelog.md`.
