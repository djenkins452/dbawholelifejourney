# 99 · PREPARE NEXT CHAT  (drop this at the END of a working chat)

**What this is:** the runnable end-of-chat procedure. Danny drops this document into the current chat when it's time to wrap up. It implements the doctrine in `00_WLJ_CHIEF_OF_STAFF_STARTUP/98_SESSION_TRANSITION_PROTOCOL.md` and produces a **Transition Audit**.

**Not evergreen onboarding** — that's why it lives at the `@WLJ_SYSTEM_PROMPTS/` root, not inside the startup package. It is permanent and reused every chat, but it is an *action prompt*, not institutional memory.

---

## Claude: perform this workflow now

This is a **self-improving** close-out: it improves the permanent package *and* improves itself. Do every step.

### 1. Review the session
Summarize everything accomplished: what shipped, what was decided, what was investigated, what's still open, what was intentionally postponed.

### 2. Permanent Knowledge Review — fold durable knowledge UP into the package
Ask: **"What permanent knowledge belongs in the startup package instead of the temporary bootloader?"** For each durable fact/principle/rule/preference established this session, put it in the ONE document that owns it (do not duplicate):
- **`01_READ_FIRST…ARCHITECTURE.md`** — what WLJ is / architecture / maturity / a lesson.
- **`02_WLJ_CONSTITUTION.md`** — a protected principle changed. ⚠️ **Constitutional Review** (default NO; Danny's explicit written approval). Never fold a constitutional change in silently.
- **`03_ENGINEERING_OPERATING_GUIDE.md`** — a durable engineering rule, gate, or discipline.
- **`04_DANNY_WORKING_PREFERENCES.md`** — a durable preference about working with Danny.

If nothing durable was established, change nothing — say so.

### 3. Deferred Work Review — capture what was intentionally postponed
Ask: **"What important work was intentionally deferred this session?"** (e.g. Ops Wall implementation, deferred production work, deferred product refinements, deferred investigations, anything Danny postponed.) Ensure every deferred item is carried into `00_NEXT_CHAT_STARTUP.md` so it is never silently lost.

### 4. Update supporting documentation (only what actually changed — results, not intentions)
Help topics / teaching destinations · admin guides · ops/coverage docs · contracts/tests · runbooks · **Changelog** (`docs/wlj_claude_changelog.md`, every commit, no exceptions) · **What's New** (`apps/core/fixtures/release_notes.json`, **only if user-visible**; benefit-first; "your Chief of Staff", never a user AI name or provider name).

### 5. Update the Reference Index
If any governing/supporting doc was added, moved, or reclassified, update `00_WLJ_CHIEF_OF_STAFF_STARTUP/99_REFERENCE_INDEX.md` in the same pass.

### 6. Workflow Improvement Review — improve this process itself
Ask: **"What did we learn about the startup/transition workflow itself?"** If anything, update `98_SESSION_TRANSITION_PROTOCOL.md` (doctrine) or this file (`99_PREPARE_NEXT_CHAT.md`, procedure) so Danny never has to remember the improvement again. This is what keeps the close-out self-improving.

### 7. Rewrite the bootloader
Rewrite `@WLJ_SYSTEM_PROMPTS/00_WLJ_CHIEF_OF_STAFF_STARTUP/00_NEXT_CHAT_STARTUP.md` from scratch (it lives inside the package as `00`, read first). For **each** item ask: *"Has this now been incorporated into a permanent startup document?"* If yes → **remove it**. Keep only live sprint state. The bootloader should be **shorter** than last time whenever possible.

### 8. Startup Package Integrity Review — verify before finishing
Ask and fix before continuing:
- **"If I started a brand-new session tomorrow using only this startup package, would anything important be missing?"**
- Did I accidentally leave permanent knowledge in the bootloader?
- Did I fail to update any governing document that should have changed?
- Does every document still have exactly one responsibility (none summarizes another)?
- **Is the startup package better than when this session started?**

### 9. Commit & deploy
Commit the doc/code updates with a changelog entry and push `main` (Railway auto-deploys). No unrelated feature work.

### 10. Produce the Transition Audit
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

Deferred work transferred
  [ ] Yes                       (everything intentionally postponed is in the bootloader)

Anything lost from this session?
  [ ] No                        (or list it)

Constitutional changes made?
  [ ] No                        (or list them — each with Danny's explicit approval)

Startup package integrity verified?
  [ ] Yes                       (self-contained; one responsibility per doc; better than at session start)

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
Claude rewrites:  00_NEXT_CHAT_STARTUP.md   (+ Transition Audit)
   │
   ▼
Open a brand-new chat
   │
   ▼  drag in ONE folder:  00_WLJ_CHIEF_OF_STAFF_STARTUP/
   │  (ChatGPT reads 00_NEXT_CHAT_STARTUP.md first, then the rest in order)
   │
   ▼
Immediate continuity.
```
