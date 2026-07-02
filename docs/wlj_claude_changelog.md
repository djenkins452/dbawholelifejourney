# =======================================================================# File: docs/wlj_claude_changelog.md
# Project: Whole Life Journey - Django 5.x Personal Wellness/Journaling App
# Description: Historical record of fixes, migrations, and changes
# Owner: Danny Jenkins (admin@wholelifejourney.com)
# Created: 2025-12-28
# Last Updated: 2026-06-02 (fix(briefing): Executive Briefing coherence — one dominant narrative, no contradictory state)
# ================================================================# WLJ Change History

## 2026-07-02 — feat(legacy): Legacy Domain — Phase 1 Slice 1 (foundation + Home/Hearth)

**Why:** First implementation slice of the Legacy Experience (Personal Legacy Operating System), built on the frozen architecture/UX/UI docs. Delivers the permanent foundation + the pixel-faithful Home (the Hearth) matching the approved mockup. Standalone and non-Beth (the global Chief-of-Staff chat widget is suppressed inside Legacy). Legacy is a new first-class WLJ domain reached from the existing WLJ nav — the existing dashboard/home is untouched.

**What:**
- **New `DomainClass.PRESERVATION`** (`apps/core/domain_registry/descriptors.py`) — append-only/testimonial/outlives-the-owner. Intentionally kept OUT of `USER_LIFE_DOMAINS` and `COS_PARTICIPATING` so Legacy stays fully standalone (no cross-domain/assistant iteration) in Phase 1.
- **New app `apps/legacy`** registered in `INSTALLED_APPS` + `config/urls.py` (`/legacy/`). Capability registered via `capabilities.py` (autodiscovered).
- **Canonical models (faithful shape, minimal machinery):** Memory (attestation container w/ provenance: source_kind/attributed_to/contributor/created_via), Person, Place, Media (evidence carrier), Relationship (typed edge), Contributor (permanent attribution), Output (projection); through-models MemoryPerson/MemoryPlace. All soft-deletable via a Legacy-namespaced `LegacyOwnedModel` base (avoids reverse-accessor clash with `ai_relationships.Relationship`). Migration `0001`.
- **Layer-1 conformance:** `LegacyDomainTruth` (`services/legacy_domain_truth.py`) implements `describe()` → `CompleteEntity` (preservation-shaped dims in `extensions`) + `current()` counters; registered via `register_domain_truth`.
- **Module catalog + nav:** data migration `0002` seeds the `legacy` ModuleDefinition (default OFF for everyone) and enables it for the owner account; the data-driven WLJ left rail picks it up automatically. Added `legacy_enabled` context flag.
- **Immersive shell + Home:** `templates/legacy/base_legacy.html` overrides the base `body` block to take over the viewport with Legacy's own sidebar + top bar (inherits auth/themes/CSP/scripts); `base.html` gained a `global_chat_widget` block so Legacy can suppress the assistant. Home (`home.html`) = hero + Tell-your-story tiles + Recently-resurfaced + Today/Continue/Family-highlights + month strip, with a curated sample fallback until real memories exist. All 12 other destinations render as graceful in-shell placeholders (real screens land in later slices).
- **Design system** `static/css/legacy.css` (warm palette, serif content / sans chrome, gradients, WLJ-theme-driven dark mode — not OS-driven) + CSP-safe `static/js/legacy.js` (progress fills, notifications toggle, ⌘K→search).

**Verification:** `apps.legacy` suite (12 tests) + `DomainClassMetadataTest` (6) all green; `manage.py check` and `makemigrations --check` clean. Home + a placeholder page verified in-browser (light warm mockup fidelity, sidebar/nav/tiles/cards, no console errors, chat widget absent). Pre-existing registry `test_full_alignment_is_healthy` failure (faith.journey/sports signal-type drift) is unrelated — no faith/sports files touched and zero `legacy` issues in the health summary.

**Deferred (intentionally):** user-facing release notes / help / teaching entries are held until Legacy is enabled beyond early access (flag currently OFF for all). Slices 2–4 (Editor+Library, People/Places/Media + profiles, Dashboard/Contributors/Outputs) follow.

**Files:** new `apps/legacy/**`, `static/css/legacy.css`, `static/js/legacy.js`, `templates/legacy/**`; edited `apps/core/domain_registry/descriptors.py`, `apps/core/context_processors.py`, `config/settings.py`, `config/urls.py`, `templates/base.html`, `docs/wlj_claude_changelog.md`.
