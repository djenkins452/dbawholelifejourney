# HealthKit ↔ Manual Weight Precedence — decision required

**Status:** Investigated. **Not implemented — awaiting Danny's product decision** (per the "document options,
don't guess when there's blast radius" rule). Date: 2026-07-15.

## The issue (proven, not guessed)

`process_weight_metric` (`apps/mobile/views.py`) resolves an incoming Apple-Health weigh-in in two steps:

1. **By `sync_id`** — matches an existing row with the same Apple-Health `sync_id`. A **manual** entry has no
   `sync_id`, so this step never touches manual data. ✅ safe.
2. **Date fallback** — if no `sync_id` match:
   ```python
   existing = WeightEntry.objects.filter(user=user, recorded_at__date=metric_date).first()
   ```
   This is **not scoped by source.** If you manually logged your weight today and Apple Health then syncs a
   weight for the same day, this matches your **manual** row and:
   - overwrites `value` / `unit` with the Apple-Health value,
   - flips `source` to `apple_health`,
   - stamps the Apple `sync_id`.

**Result:** a user-entered weigh-in can be silently converted to an Apple-Health row and its value overwritten —
violating "HealthKit never silently overwrites user-confirmed truth." (Other handlers that key only on `sync_id`
or on `source`-scoped queries do not have this issue; weight's date fallback is the outlier.)

## Blast-radius finding

The **canonical** weight accessor `apps/health/services/weight_queries.py` (`on_date` / `series`) is
**latest-reading-per-local-day** (`.order_by("-recorded_at").first()`), and `weight_summary` reads the latest.
So for the dominant read path, having two rows on one day is deterministic and safe — the **latest by
`recorded_at` wins.** `WeightEntry` has **no** unique constraint on `(user, date)`, so two same-day rows are
already permitted by the schema.

The residual risk is any *non-canonical* consumer that **counts or averages** raw `WeightEntry` rows per day
(a naive average would double-count a manual+Apple pair). A full audit of every weight consumer was **not
completed** (tooling limits during this session), so this is flagged rather than assumed away — which is why the
fix is not applied unilaterally.

## Options

| # | Rule | Preserves manual truth? | Duplicates? | Loses Apple data? | Notes |
|---|------|---|---|---|---|
| **A** | **Manual suppresses Apple for that day** — if the date fallback matches a `manual` row, **skip** the Apple update. | ✅ | ❌ none | ⚠️ Apple's same-day value is not stored | Most conservative; no schema/aggregation risk; simplest. **Recommended.** |
| **B** | **Coexist** — Apple never modifies a manual row; it creates its **own** `apple_health` row for the day (two rows). | ✅ | ⚠️ manual + Apple on the same day | ❌ | Correct-ish (two real measurements); relies on latest-per-day consumers; small risk to naive count/avg. |
| **C** | **Apple wins** (current behavior) | ❌ | ❌ | ❌ | Rejected — clobbers user truth. |

**Recommendation: Option A.** It fully preserves user-entered truth, creates no duplicate rows (zero
aggregation blast radius), and is deterministic. The only cost is that Apple Health's value for a day you
*manually* logged is ignored — which is the desired precedence ("your explicit entry wins that day").

## Ready-to-apply patch (Option A)

In `process_weight_metric`, in the date-fallback branch, before overwriting `existing`:

```python
# Fall back to date-based matching
existing = WeightEntry.objects.filter(
    user=user,
    recorded_at__date=metric_date,
).first()

if existing:
    # PRECEDENCE: never let Apple Health overwrite a user's manual weigh-in.
    # A manual entry for the day is user-confirmed truth and wins (Apple's
    # same-day value is skipped, not stored). Apple still updates its own rows.
    if existing.source == "manual":
        return "skipped"
    ...  # (existing update logic unchanged)
```

Add a test asserting: a manual WeightEntry for today + an Apple-Health weight sync for today → the manual row is
unchanged (`source="manual"`, original value) and the result is `"skipped"`.

**Scope note:** apply the same guard to any other handler whose date fallback is not source-scoped
(`body_fat`, `lean_body_mass` update the same `WeightEntry`; verify they don't convert a manual row either).

## Why it's not implemented tonight

Choosing A vs. B is a **product decision** (drop Apple's same-day value vs. keep both), and B carries a real
(if small) aggregation blast radius that a full consumer audit — not completed this session — should clear
first. Per the standing instruction, the safe move is to surface the decision with a ready patch rather than
guess. Pick A or B and it's a ~10-line change plus a test.
