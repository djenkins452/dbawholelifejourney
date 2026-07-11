# 99 · PREPARE NEXT CHAT  (drop this at the END of a working chat)

**What this is:** the runnable end-of-chat procedure. Danny drops this document into the current chat when it's time to wrap up. It implements the doctrine in `00_WLJ_CHIEF_OF_STAFF_STARTUP/98_SESSION_TRANSITION_PROTOCOL.md` and produces a **Transition Audit**.

**Not evergreen onboarding** — that's why it lives at the `@WLJ_SYSTEM_PROMPTS/` root, not inside the startup package. It is permanent and reused every chat, but it is an *action prompt*, not institutional memory.

---

## Claude: perform this workflow now

### 1. Review the session
Summarize everything accomplished in this conversation: what shipped, what was decided, what was investigated, what's still open.

### 2. Update the governing startup documents (only where a durable truth was established)
Fold knowledge **up** into the one document that owns it — do not duplicate:
- **`00_READ_FIRST…ARCHITECTURE.md`** — new fact about what WLJ is / architecture / maturity / a lesson.
- **`01_WLJ_CONSTITUTION.md`** — a protected principle changed. ⚠️ This is a **Constitutional Review** (default NO; requires Danny's explicit written approval). Never fold a constitutional change in silently.
- **`02_ENGINEERING_OPERATING_GUIDE.md`** — a durable engineering rule, gate, or discipline.
- **`03_DANNY_WORKING_PREFERENCES.md`** — a durable preference about working with Danny.

If nothing durable was established, change nothing — say so.

### 3. Update supporting documentation where appropriate
Only what actually changed (results, not intentions):
- Help topics / teaching destinations
- Admin guides
- Ops documentation / coverage docs
- Contracts / tests
- Runbooks
- **Changelog** (`docs/wlj_claude_changelog.md`) — every commit, no exceptions
- **What's New** (`apps/core/fixtures/release_notes.json`) — **only if user-visible**; benefit-first; "your Chief of Staff", never a user AI name or provider name.

### 4. Update the Reference Index
If any governing/supporting doc was added, moved, or reclassified, update `00_WLJ_CHIEF_OF_STAFF_STARTUP/99_REFERENCE_INDEX.md` in the same pass.

### 5. Rewrite the bootloader
Rewrite `@WLJ_SYSTEM_PROMPTS/99_NEXT_CHAT_STARTUP.md` from scratch. For **each** item, first ask: *"Has this now been incorporated into a permanent startup document?"* If yes → **remove it** from the bootloader. Keep only live sprint state (see that file's own contract). The bootloader should be **shorter** than last time whenever possible.

### 6. Commit & deploy
Commit the doc/code updates with a changelog entry and push `main` (Railway auto-deploys). No unrelated feature work.

### 7. Produce the Transition Audit
Output the checklist below, filled in honestly.

---

## Transition Audit (output this at the end)

```
TRANSITION AUDIT — <date>

Startup Package Updated
  [ ] Architecture              (changed? what / "no change")
  [ ] Constitution              (changed? what / "no change")
  [ ] Engineering Guide         (changed? what / "no change")
  [ ] Danny Preferences         (changed? what / "no change")

Supporting Documentation Updated
  [ ] Yes   [ ] No              (list docs touched)

Reference Index Updated
  [ ] Yes                       (or "not needed — no doc moved/added/reclassified")

Historical Documentation Reviewed
  [ ] Yes                       (anything to banner / reclassify?)

NEXT_CHAT_STARTUP regenerated
  [ ] Yes                       (shorter than before?  yes/no)

Outstanding work transferred
  [ ] Yes                       (all open items are in the bootloader)

Anything lost from this session?
  [ ] No                        (or list it)

Constitutional changes made?
  [ ] No                        (or list them — each with Danny's explicit approval)

Ready for next chat?
  [ ] Yes
```

---

## The permanent workflow (for reference)

```
Working chat
   │
   ▼  drop  99_PREPARE_NEXT_CHAT.md
Claude updates:  startup package · supporting docs · changelog
   │
   ▼
Claude rewrites:  99_NEXT_CHAT_STARTUP.md   (+ Transition Audit)
   │
   ▼
Open a brand-new chat
   │
   ▼  drag in:  00_WLJ_CHIEF_OF_STAFF_STARTUP/   +   99_NEXT_CHAT_STARTUP.md
   │
   ▼
Immediate continuity.
```
