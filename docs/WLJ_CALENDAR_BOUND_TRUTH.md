# Calendar-Bound Truth — Governing Contract

**Date:** 2026-07-23
**Status:** IMPLEMENTED + CERTIFIED — AWAITING PRODUCTION VALIDATION
**Class:** Truth Retrieval Certification — calendar-bound truth (the class, not one module)
**Origin:** `WLJ_NUTRITION_STATE_INVESTIGATION.md` · `WLJ_WEIGHT_YESTERDAY_INVESTIGATION.md` · `5b4bd722` · `852e242c`

---

## The rule

> **Every deterministic truth whose meaning depends on a user's calendar day must carry
> the represented user-local day as part of its contract. Calendar-bound freshness is
> evaluated against that represented day — not merely against newer writes. Relative
> temporal expressions (today, yesterday, tonight, this week…) are always resolved
> through one canonical temporal authority using the user's local timezone.**

Two proven failure shapes it eliminates:

1. **Undated day-claims.** A cached value that says "today" without recording *which*
   day is correct when written and silently wrong after midnight. Write-based staleness
   cannot detect it — **calendar days advance without writes; midnight writes nothing.**
2. **Non-user-local dates.** "Today" resolved from UTC or server time is wrong for any
   user whose local day differs at that instant. At 11:00 PM Eastern it is still today
   for the user even though UTC has already rolled over.

---

## The authority — `apps/core/truth/calendar_day.py`

One façade; **it owns no date math of its own**, composing what already existed:

| Need | Delegates to |
|---|---|
| timezone / now / today | `apps.core.utils._get_user_tz` / `get_user_now` / `get_user_today` (zoneinfo → deterministic DST) |
| named windows, natural phrases | `apps.core.truth.periods.resolve_period` / `resolve_date_expression` |
| morning / evening / tonight | `apps.core.truth.daypart` |

```python
cal.today(user) / cal.yesterday(user) / cal.now(user)   # the user's calendar
cal.day_bounds(user, d)      # aware local midnight → next local midnight
cal.day_length(user, d)      # 23h spring-forward, 25h fall-back, else 24h
cal.week_bounds(user, d)     # via the shared period resolver
cal.resolve(user, "yesterday")   # phrase → Period, anchored to the USER's today
cal.stamp(user)              # the contract a cached day-claim must carry
cal.day_freshness(user, stamp)   # current | stale | unknown  (+ reason)
```

`periods.py` is a **pure** function of `today` — so its correctness depends entirely on
being handed a *user-local* today. That is precisely what this façade guarantees:
callers pass a `user`, never a date they computed themselves.

> ⚠️ **Trap, documented in code:** never compute a day's length as `end - start` from
> `day_bounds`. CPython skips offset arithmetic when both operands share a tzinfo object,
> so DST days silently return a flat 24 h. Use `day_length()`.

## The snapshot contract

A snapshot may **cache** canonical truth. It may never **calculate** it.

* Every calendar-bound builder stamps the day it built (`day_state_date`, or
  `daily_totals_date` for nutrition).
* `state_freshness._DATE_BOUND_MODULES` maps module → stamp field. **This registry is
  the contract.**
* `ensure_fresh()` checks **date rollover before** the raw-write check, because rollover
  is the staleness a write check structurally cannot see.
* Repair respects request-path safety: only builders in `_LIGHT_INLINE_REBUILD`
  (nutrition, journal, faith, tasks, calendar) rebuild synchronously. Everything
  else — notably the ~69-query `health` builder — goes through `safe_enqueue` and is
  **disclosed as stale** meanwhile. A heavy inline rebuild is never acceptable.
* `get_domain_state` returns `day_freshness` / `state_date` / `user_local_date` /
  `timezone`. **Stale values are still returned — disclosed, never hidden.**

## Coverage

| | Before | After |
|---|---|---|
| Calendar-day claims in cached state | 34 | 34 |
| **Day-stamped** | 7 (nutrition only) | **31** |
| Undated | 27 | **3** |

Registered: `nutrition`, `tasks`, `calendar`, `fitness`, `medicine`, `routine`,
`life_events`, `health`.

**Remaining 3 (deliberate):** `fasting.current_fast_active` is an *instantaneous state*
("is a fast running right now"), not a day-scoped total — stamping it would misrepresent
it as a day claim. The other two are its companions in the same builder.

## Certification — `apps/core/tests/test_calendar_bound_truth.py` (24 gates)

* **User-local calendar:** UTC midnight does not advance the user's today; after local
  midnight it advances **exactly once** (verified hour-by-hour across the boundary);
  nine zones resolve their own day from one UTC instant (UTC, Eastern, Central,
  Mountain, Pacific, Hawaii, Europe/London, Australia/Sydney, Asia/Kolkata incl. the
  +05:30 half-hour offset).
* **DST / edges:** spring forward = 23 h, fall back = 25 h, Hawaii always 24 h,
  southern-hemisphere (Sydney April) = 25 h, the skipped hour resolves without raising,
  **leap day** (2028-02-29) and **year rollover** both certified.
* **Contract:** stamp records day + timezone + authority; freshness returns
  current/stale/unknown; a stamp goes stale at the **user's** midnight and *not* at
  UTC's — the whole class in one assertion.
* **THE CLASS GATE:** every calendar-day claim must live in a registered module, and
  every registered module must actually stamp. Adding `foo_today` to an unregistered
  module **fails CI**. (It caught `fitness`, then `life_events`, then — after the regex
  was broadened to the infix form — `health.water_today_*`, during this very build.)

## Runtime validation (real gpt-4o, `CoSGateway.respond(surface="chat")`, ToolCallLog)

User in `America/New_York`, clock frozen at UTC instants straddling the user's midnight:

| Instant | Local | Question | Answer |
|---|---|---|---|
| 2026-07-23 03:55 UTC | 11:55 PM Jul 22 | protein **today** | ✅ 120 g (the user's Jul 22 — UTC was already the 23rd) |
| " | " | protein **yesterday** | ✅ 40 g (Jul 21) |
| 2026-07-23 04:05 UTC | 12:05 AM Jul 23 | protein **yesterday** | ✅ 120 g (now Jul 22 — advanced exactly once) |
| " | " | protein **today** | ✅ "has not been recorded" (Jul 23, nothing logged) |
| 2026-03-09 02:30 UTC | 10:30 PM Mar 8 (DST, 23 h day) | protein **today** | ✅ 95 g |
| 2027-01-01 04:40 UTC | 11:40 PM Dec 31 | protein **today** | ✅ 150 g (year rollover) |

**6/6.** In every case UTC had advanced past the user's day and the CoS still reasoned
from the user's calendar.

## Remaining risks

1. **~35 truth-layer files still call a server/UTC date** (`timezone.now().date()`,
   `date.today()`) — mostly `apps/health/services/*` analytics (cycle statistics,
   correlation, trend, protein service) and `meals/services`. None are the day-claim
   projections certified here, but each is a latent instance of shape #2. Ranked next.
   One was fixed in passing: `build_task_state` computed **overdue** from the server
   date, which could flag a task overdue a day early for a non-UTC user.
2. **`fasting`** deliberately unstamped (instantaneous state, see above).
3. **Legacy/ops call sites** (billing, observability, governance) legitimately use
   server time and are out of scope — they make no user-calendar claim.
4. Pre-existing and untouched: `test_empty_health_state`, `test_nutrition_entity_truth`,
   `test_chatgpt_cos_clean`, `test_p29_morning_and_precedence`.
