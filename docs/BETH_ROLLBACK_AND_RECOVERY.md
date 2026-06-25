# Beth Rollback & Recovery

> **How to tag stable baselines, roll back, hotfix, and recover from a failed
> deploy of the CoS / Beth subsystem.**
> **Last updated:** 2026-06-25

**Deployment model (important):** production deploys from `main` pushed to GitHub
(Railway + Nixpacks builds on push; `migrate --noinput` runs on every deploy). There
is **no CLI/SSH to production** — rollback is performed by changing what `main`
points at and pushing, then letting Railway redeploy.

Push command (SSH on port 443):
```bash
GIT_SSH_COMMAND="ssh -p 443" git push git@ssh.github.com:djenkins452/dbawholelifejourney.git main
```

---

## 1. Identify the last known stable release

```bash
# List stability tags, newest first
git tag --list 'beth-stable-*' --sort=-creatordate

# Show what a tag points at
git show --no-patch --format='%H %ci %s' beth-stable-v1

# What is currently live (assuming main == production)
git log --oneline -1 main
```

The newest `beth-stable-vN` tag is, by definition, the last known stable release.
Record each tag's meaning in the table at the bottom of this doc.

---

## 2. Create a production stability tag

Cut a tag **only** after the full production validation checklist passes
(`BETH_PRODUCTION_VALIDATION_CHECKLIST.md`).

```bash
# Annotated tag at the validated commit (use the merge commit on main)
git tag -a beth-stable-v1 35c27f58 \
  -m "Beth stable v1 — conversation durability + persistent thinking indicator + health reasoning validated"

# Push the tag
GIT_SSH_COMMAND="ssh -p 443" git push git@ssh.github.com:djenkins452/dbawholelifejourney.git beth-stable-v1
```

Tagging does not deploy anything; it marks a rollback point.

---

## 3. Roll back to a prior stable version

> Prefer **forward-only revert** (a new commit that undoes the bad change) over
> moving `main` backward — it keeps history honest and the migration state monotonic.

### 3a. Preferred: revert the bad merge (forward-only)
```bash
git checkout main && git pull
# Revert the offending merge commit (-m 1 keeps main's first parent)
git revert -m 1 <bad_merge_sha>
python manage.py check
GIT_SSH_COMMAND="ssh -p 443" git push git@ssh.github.com:djenkins452/dbawholelifejourney.git main
```

### 3b. Hard rollback to a known-good tag (when revert is messy)
```bash
git checkout main && git pull
# Bring the working tree to the stable tag's state, but as a NEW commit
git revert --no-commit <bad_sha>..HEAD        # or: git read-tree / checkout files
git checkout beth-stable-v1 -- .              # restore tree to the stable snapshot
git commit -m "rollback: restore Beth to beth-stable-v1 (<reason>)"
python manage.py check
GIT_SSH_COMMAND="ssh -p 443" git push git@ssh.github.com:djenkins452/dbawholelifejourney.git main
```

> **Migration safety:** never roll *backward* across a migration that already ran in
> production without a paired reverse migration. If the bad release added a migration,
> write a forward migration that reverses the schema change rather than deleting the
> migration file. (Recall: prod has no manual shell — schema changes only happen via
> `migrate` on deploy.)

---

## 4. Create a hotfix branch from a stable tag

Use when production is broken and `main` has unshippable work-in-progress on top of
the last stable tag.

```bash
git fetch --tags
git checkout -b hotfix/beth-<short-desc> beth-stable-v1
# ... make the minimal fix + changelog entry ...
python manage.py test apps.ai.tests.<scoped_module> -v 1 --failfast
python manage.py check
git commit -am "hotfix(cos): <desc>"

# Ship: merge the hotfix into main and push
git checkout main && git merge --no-ff hotfix/beth-<short-desc>
GIT_SSH_COMMAND="ssh -p 443" git push git@ssh.github.com:djenkins452/dbawholelifejourney.git main

# After validation, cut the next stable tag
git tag -a beth-stable-v2 -m "Beth stable v2 — <desc>" && \
GIT_SSH_COMMAND="ssh -p 443" git push git@ssh.github.com:djenkins452/dbawholelifejourney.git beth-stable-v2
```

---

## 5. Recover from a failed deployment

1. **Confirm the symptom** quickly using Beth telemetry (grep prod logs):
   - `BETH_LIFECYCLE` / `COS_REQUEST_START` present but `COS_REQUEST_FINISH` absent → worker dying.
   - `BETH_RENDER_SKIPPED` / missing `BETH_RENDER_DOM_INSERTED` → frontend render fault.
   - 500s on `/assistant/api/chat/stream/` → server-side dispatch fault.
2. **Decide:** is it a code fault (→ revert, §3) or an env/worker fault (→ no code rollback; restart/scale the worker service)?
3. **Roll back** the most recent merge with §3a if it is a code regression.
4. **Re-run** `BETH_PRODUCTION_VALIDATION_CHECKLIST.md` after the rollback deploys.
5. **Post-mortem:** record root cause, add a regression test (or a manual-validation
   item if it is frontend-only), and note it in `docs/wlj_claude_changelog.md`.

---

## 6. Stability tag registry

| Tag | Commit | Date | Meaning / validated behaviors |
|-----|--------|------|-------------------------------|
| `beth-stable-v1` *(suggested, not yet cut)* | `35c27f58` | 2026-06-25 | Conversation durability (nav + refresh), background completion + recovery, completion notifications, persistent thinking indicator, validated health reasoning (2 intents). Known limits: worker hard-kill durability gap; no frontend automated tests. |
| `beth-stable-v2` | _tbd_ | _tbd_ | _next milestone_ |
