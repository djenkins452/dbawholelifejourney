# Close out the current coding session

model: sonnet

## Purpose

Review the current coding session and ensure all documentation, help systems, and tracking are up to date before ending work.

## Session Review Checklist

Perform each of the following checks and updates as needed:

### 1. Changelog Review

Read `docs/wlj_claude_changelog.md` and verify:
- All changes made this session are documented
- Each entry has: date, summary, files changed, and reason
- Migration names are included if any migrations were created

If anything is missing, add it now.

### 2. What's New Document

Check if any user-facing features were added or changed this session.

If yes, update or create entries in the What's New system:
- Location: Check for existing What's New fixture or template
- Include: Feature name, description, date, and how to use it

### 3. Context-Aware Help (Teaching Tool)

If any new pages, features, or navigation destinations were added:
- Update `apps/help/fixtures/teaching_destinations.json`
- Add entries for new destinations with:
  - `destination_id`: Unique slug
  - `name`: Display name
  - `path_description`: Navigation breadcrumb
  - `explanation`: What users can do there
  - `url`: Direct URL path
  - `keywords`: Search terms
  - `module`: App module name

### 4. WLJ Assistant Chat Updates

If any new data types, query patterns, or personal data features were added:
- Check `assistant/intent_detector.py` - Update PERSONAL_DATA_KEYWORDS if needed
- Check `assistant/data_service.py` - Add query methods for new data types
- Check `assistant/gap_detector.py` - Update SUPPORTED_DATA_TYPES list

### 5. CLAUDE.md Updates

Review if any new instructions should be added to CLAUDE.md:
- New project patterns or conventions established
- New API endpoints or commands
- New troubleshooting tips discovered
- Changes to deployment or testing procedures

### 6. Git Status Check

Run `git status` and `git log --oneline -5` to verify:
- All changes are committed
- Commits are pushed to both worktree branch and main
- No uncommitted work is left behind

### 7. Outstanding Tasks

Check for any tasks that were started but not completed:
```bash
curl -s -H "X-Claude-API-Key: a3f8b2c9d4e5f6a7b8c9d0e1f2a3b4c5d6e7f8a9b0c1d2e3f4a5b6c7d8e9f0a1" "https://wholelifejourney.com/admin-console/api/claude/ready-tasks/?limit=10"
```

Report any in_progress tasks that should be completed or reset.

## Output

After completing all checks, provide a **Session Summary** with:

1. **Changes Made This Session:**
   - List of features, fixes, or updates completed

2. **Documentation Updated:**
   - Changelog: Yes/No (entries added)
   - What's New: Yes/No/N/A
   - Teaching Tool: Yes/No/N/A
   - Assistant: Yes/No/N/A
   - CLAUDE.md: Yes/No

3. **Git Status:**
   - Branch: <current branch>
   - Uncommitted changes: Yes/No
   - Pushed to main: Yes/No

4. **Outstanding Items:**
   - Any incomplete tasks or follow-ups needed

5. **Ready to Close:** Yes/No

## Authority

Full authority to read files and update documentation.
Ask user before making significant changes to CLAUDE.md.
