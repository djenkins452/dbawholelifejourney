# Local User Preferences

These preferences override default Claude Code behaviors for this user.

## Session Start

- **Always read CLAUDE.md first** - Don't wait to be asked
- Context is already there, use it immediately
- Start working, not asking questions

## Permission Handling

**Do NOT ask permission for:**
- Reading files
- Searching/grepping the codebase
- Running tests
- Making commits (when task is complete)
- Running migrations
- Proceeding to next steps
- Moving between sections/topics

**Still ask permission for:**
- Destructive operations (deleting files, dropping tables)
- Actions outside the normal task workflow
- Anything genuinely ambiguous or risky

**Deploy workflow (from CLAUDE.md):**
- After code changes: changelog → commit → merge to main → push
- This is the standard flow - just do it, don't ask

## Communication Style

- Be direct, skip "Would you like me to..."
- Execute rather than propose
- If something fails, fix it and move on (don't ask "should I retry?")
- Only stop for genuine decision points

## Task Execution

- When given a task, start immediately
- Don't recap what you're about to do - just do it
- Summarize results, not intentions

---

*User feedback: "I have not told you no on any permission you have requested."*
