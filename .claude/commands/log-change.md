# Log a change to the changelog

model: haiku

## Arguments

$ARGUMENTS = description of the change

## Instructions

Append an entry to `docs/wlj_claude_changelog.md` with:

1. Today's date (if new date section needed)
2. The change description provided
3. Any files modified (if known from recent context)

## Entry Format

```markdown
### YYYY-MM-DD

- **<Change Type>:** <Description>
  - Files: <list of files if known>
```

## Change Types

- **Feature:** New functionality
- **Fix:** Bug fix
- **Refactor:** Code restructuring
- **Docs:** Documentation updates
- **Deploy:** Deployment changes
- **Test:** Test additions/fixes

## Example

Input: "Added auto_start parameter to ready-tasks API"

Output appended to changelog:
```markdown
### 2026-01-04

- **Feature:** Added auto_start parameter to ready-tasks API
  - Files: apps/admin_console/views.py, CLAUDE.md
```
