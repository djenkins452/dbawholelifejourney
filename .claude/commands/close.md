# Close out the current coding session

model: sonnet

## Purpose

Verify ALL documentation was updated for every change this session, fix any gaps, then provide a session summary. This is a safety net — the docs should already be done per "On Task Completion" in CLAUDE.md, but /close catches anything missed.

## Step 1: Identify Session Changes

Run `git log --oneline` from session start to HEAD. List every feature, enhancement, fix, and refactor completed.

## Step 2: Documentation Audit (DO, Don't Just Check)

For EACH user-facing change (feature or enhancement), verify ALL of the following exist. If any are missing, **create them now** — don't just report the gap.

### 2a. Changelog
**File:** `docs/wlj_claude_changelog.md`
- Every change has an entry with: date, summary, files changed, and why
- Migration names included if any were created

### 2b. Release Notes (What's New)
**File:** `apps/core/fixtures/release_notes.json`
- User-facing feature/enhancement has a release note entry
- Uses next available PK (check existing highest PK + 1)
- Entry has: title, description (user-friendly), entry_type, release_date, is_published=true

### 2c. Teaching Destinations
**File:** `apps/help/fixtures/teaching_destinations.json`
- Any new navigable page or significantly changed existing page has an entry
- Existing entries updated if feature scope changed (new keywords, updated explanation)
- Fields: destination_id, name, path_description, explanation, url, keywords, module

### 2d. Help Topics
**File:** `apps/help/fixtures/help_topics.json`
- Any page with a `help_context_id` has a corresponding help topic
- Existing help topics updated if the feature they describe changed significantly
- Content should cover what the feature does and how to use it

### 2e. Features Doc
**File:** `docs/wlj_claude_features.md`
- Major features have a section with: Overview, Features list, Key Files, Tests count
- Table of Contents updated if section added/renamed
- Existing sections updated if feature scope changed

### 2f. Fixture Loader Reset
**File:** `apps/core/management/commands/load_initial_data.py`
- If ANY fixture file was modified (release_notes, teaching_destinations, help_topics), a one-time reset method exists
- Reset method resets ALL modified fixture loaders (not just one)
- Reset method is called from handle()
- Uses unique tracker name like `reset_<feature>_<date>`

### 2g. CLAUDE.md
**File:** `CLAUDE.md`
- Only if new patterns, conventions, or troubleshooting tips were established
- Ask user before making changes

## Step 3: Commit & Deploy Any Fixes

If Step 2 found and fixed gaps:
- Commit the doc fixes
- Push: `GIT_SSH_COMMAND="ssh -p 443" git push git@ssh.github.com:djenkins452/dbawholelifejourney.git main`

## Step 4: Final Git Verification

Run `git status` and `git log --oneline -5`:
- All changes committed
- Pushed to main
- No uncommitted work left (ignore .claude/settings.local.json and Xcode state files)

## Step 5: Session Summary

Output a table:

| Document | Status | Detail |
|----------|--------|--------|
| Changelog | ✅/❌→✅ | What was added/fixed |
| Release Notes | ✅/❌→✅/N/A | PK number |
| Teaching Destinations | ✅/❌→✅/N/A | What was added/updated |
| Help Topics | ✅/❌→✅/N/A | What was added/updated |
| Features Doc | ✅/❌→✅/N/A | Section added/updated |
| Fixture Loader | ✅/❌→✅/N/A | Reset method name |
| CLAUDE.md | ✅/N/A | |
| Git | ✅ Pushed / ❌ Uncommitted | |

Then list: Changes Made, Tests Passing, Ready to Close: Yes/No

## Authority

Full authority to read files, update documentation, commit, and deploy.
Ask user before making significant changes to CLAUDE.md.
