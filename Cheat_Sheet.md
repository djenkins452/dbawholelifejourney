# Claude Code Cheat Sheet

A quick reference for getting the most out of Claude Code on this project.

---

## Slash Commands

| Command | Purpose |
|---------|---------|
| `/next` | Fetch next ready task, mark it in-progress |
| `/run-task` | Execute current task with full workflow (changelog → commit → deploy) |
| `/troubleshoot` | Match an error against known issues |
| `/log-change <desc>` | Manually add changelog entry |

**Tip:** Saying "What's next?" does the same thing as `/next`.

---

## Workflow Efficiency

### Parallel vs. Sequential

| Pattern | When to Use | Example |
|---------|-------------|---------|
| Parallel ("and") | Independent tasks | "Check tests AND search for UserPreferences" |
| Sequential ("then") | Dependent tasks | "Create migration, then run tests" |

### Specificity Guide

| Situation | Approach |
|-----------|----------|
| You know the exact file/function | Give the path: "Fix `apps/health/views.py` line 47" |
| You're not sure where code lives | Let me explore: "Where does weight logging happen?" |
| Complex multi-file feature | Start open: "How would you approach X?" |

---

## Communication Patterns

### Magic Phrases

| Say This | I'll Do This |
|----------|--------------|
| "Don't change anything yet" | Explore without editing |
| "Keep it simple" | Avoid over-engineering |
| "Check troubleshoot first" | Look for known issues |
| "Plan this first" | Enter plan mode before coding |
| "Make sure it's responsive" | Verify mobile/tablet/desktop |
| "Run X in the background" | Start task, continue working |

### Correcting Course

- **Be direct:** "Stop" or "Wait" works fine
- **Clarify:** "No, I meant X not Y"
- **Scope control:** "Let's finish this first, then handle that"

### Avoid These

| Don't | Do Instead |
|-------|------------|
| "Fix the page" (vague) | "The weight page shows wrong units" |
| 10 tasks in one message | 2-3 related tasks, then follow up |
| "You know what I mean" | Take 10 seconds to be clear |

---

## Project-Specific (WLJ)

### Task Pipeline

```
/next → /run-task → changelog → commit → merge to main → push → auto-deploy
```

**A task isn't done until it's deployed.**

### Task JSON Contract

Every task must have:
```json
{
  "objective": "What to accomplish",
  "inputs": ["Required context"],
  "actions": ["Step 1", "Step 2"],
  "output": "Expected deliverable"
}
```

### Known Gotchas (from troubleshoot doc)

| Issue | Solution |
|-------|----------|
| Records seem missing | SoftDeleteManager hides deleted - use `all_objects` |
| Property shadows field | Rename property or field |
| Prod differs from local | Nixpacks cache - may need clear |
| Tests fail on user data | Ensure test user has completed onboarding |

### Responsive Design Requirements

- Mobile-first defaults
- Breakpoints: 480px (mobile), 768px (tablet), 769px+ (desktop)
- Touch targets: 44x44px minimum
- Input font: 16px minimum (prevents iOS zoom)
- Test at 375px width (iPhone SE)

---

## Advanced Features

### Background Tasks

```
"Run all tests in the background and while that's happening, look at the views"
```

- Check status: `/tasks`
- I'll notify you when complete

### Plan Mode

Triggers:
- "Plan this out first"
- "Show me your approach before coding"
- Complex features (I may suggest it)

What happens:
1. I explore the codebase
2. Write a plan for your review
3. You approve → I execute
4. You request changes → I revise

### Exploration

For unfamiliar code, be open-ended:
- "How does AI coaching work?"
- "What's the flow when someone logs weight?"

I'll search, trace, and summarize.

### Parallel Agents

Independent research runs simultaneously:
```
"Search for soft_delete uses AND find weight validation"
→ Two agents, results combined
```

---

## Git Flow (This Project)

```bash
# Work happens in worktree
~/.claude-worktrees/dbawholelifejourney/strange-leavitt

# Push happens from main repo
~/Projects/dbawholelifejourney

# SSH uses port 443 (not 22)
GIT_SSH_COMMAND="ssh -p 443" git push git@ssh.github.com:...
```

---

## Quick Debugging

| Problem | First Step |
|---------|------------|
| Tests failing | `/troubleshoot <error>` |
| Something broken after deploy | Check Railway logs, Nixpacks cache |
| Records not appearing | Check SoftDeleteManager (`all_objects`) |
| Migration issues | `python manage.py showmigrations` |

---

## One-Liner Reference

```bash
# Fetch next task
curl -s -H "X-Claude-API-Key: <key>" "https://wholelifejourney.com/admin-console/api/claude/ready-tasks/?limit=1&auto_start=true"

# Run tests (specific)
python manage.py test apps.health.tests.test_fitness -v 1 --failfast

# Run all tests
python manage.py test -v 1

# Check for issues
python manage.py check
```

---

*Created: 2025-01-15*
