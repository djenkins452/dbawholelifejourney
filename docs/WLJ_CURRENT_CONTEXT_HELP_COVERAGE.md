# WLJ Current Context & Context-Aware Help — Coverage Audit

**Status:** CURRENT · Milestone audit (2026-07-11)
**Contracts audited:** `docs/WLJ_CURRENT_CONTEXT_CONTRACT.md` (Current Context), context-aware help (`help_context_id` + fixtures)
**Scope decision:** This is a coverage **report + prioritized backlog**. The pattern is proven and locked (Constitution Article II); adoption across remaining pages is tracked, phased work — not a milestone blocker.

---

## 1. Headline

- **Context-aware Help (Contract B): healthy and broadly adopted.** 135 distinct `help_context_id`s in code, **all 135 have matching topics** in `help_topics.json` (159 topics), plus 187 teaching destinations.
- **Current Context (Contract A): the mechanism is complete; adoption is early.** Every user-owned `DetailView` auto-declares its object via `base.html` (`object.context_ref` on `UserOwnedModel` / `NarratableMixin`) — ~45 detail pages covered for free. The **overview page-summary pattern is live on exactly one page** (`health.weight`). ~90 overview/list/dashboard pages and ~9 non-DetailView detail pages remain to adopt it.

The architecture is not the gap — adoption is. This is expected: the two-pattern standard was ratified recently and rolls out page-by-page.

---

## 2. Current Context — coverage

| Mechanism | Count | Status |
|---|---|---|
| DetailView auto-declaration (`object.context_ref` on `UserOwnedModel`) | ~45 | ✅ Automatic, zero per-view code |
| `CurrentContextMixin` (overview → single object) | 3 (`PurposeHomeView`, `purpose.GoalListView`, `health.WorkoutDetailView`) | ✅ |
| `PageSummaryMixin` + `@register_page_summary` (overview → summary) | **1** (`health.WeightListView` → `health.weight`) | ✅ reference implementation |

### 2a. Highest-value gap — overview/dashboard pages with NO summary provider

Priority order (member-facing dashboards first). Each should ship a `@register_page_summary("<key>")` provider fed by the **same one deterministic source** as its page render (Article II.3).

**Tier 1 (in the contract backlog):** Home/Dashboard (`core.dashboard`), Glucose dashboard (`health.glucose`), Health overview (`health.overview`), Calendar overview (`calendar.overview`), Finance dashboard (`finance.dashboard`), Goals dashboard (`purpose.goals`), Task dashboard (`life.tasks`), Reports/Analytics.

**Tier 2 (not yet in backlog — add):** Faith home, Journal home, Life home, Nutrition/Intake/Fitness homes, Meals dashboard, Sleep/Fasting/Water/HeartRate lists, the 11 health-metric dashboards (`views_dashboards.py`), Relationships people/groups, Notes list, Finance lists, Purpose lists, Life lists.

### 2b. Detail pages that cannot auto-declare (TemplateView / plain `View`)

Add `CurrentContextMixin` + `get_current_context_object()` (the `WorkoutDetailView` pattern):

- `TemplateDetailView`, `IntakeDetailView`, `FoodEntryDetailView`, `MedicalProviderDetailView` (health, TemplateView)
- `EventDetailView`, `AvailabilityDetailView` (calendar, plain `View`)
- `SleepEntryDetailView` (health, plain `View`)
- `ComplianceDetailView` (dashboard_v2 — likely internal)

---

## 3. Context-aware Help — coverage

Help resolves via `HelpContextMixin`, explicit `context["help_context_id"]`, and a URL-prefix fallback (`_HELP_CONTEXT_MAP`, default `GENERAL`). Every id used in code has a fixture topic.

### Gaps — areas resolving to a generic/`GENERAL` topic

**Apps with zero per-page help:**
- **finance** — every page falls to a single broad `FINANCE_HOME` prefix (functionally generic across ~15 pages)
- **security** — no `help_context_id`, no `SECURITY_DASHBOARD` topic
- **sports** — `SportsHubView` → `GENERAL`, no `SPORTS_HUB` topic
- **owner_finance** — owner-only, low priority
- **core/blueprint** — `DriftSummaryView`, `NonNegotiableDetailView` → `GENERAL`

**Specific pages falling through:** Calendar event detail & availability detail (no `CALENDAR_EVENT_DETAIL` topic).

---

## 4. Prioritized backlog

| ID | Item | Phase |
|---|---|---|
| CC-1 | Tier-1 overview summary providers (8 dashboards) | Next |
| CC-2 | Non-DetailView detail pages adopt `CurrentContextMixin` (8 pages) | Next |
| CC-3 | Tier-2 overview summary providers | Following |
| CC-4 | Verify the ~45 auto-declared DetailViews all inherit `UserOwnedModel` (faith/medical/legacy shared-content models may not) | Next (spot-check) |
| HELP-1 | Per-page help for finance (replace single `FINANCE_HOME` prefix) | Following |
| HELP-2 | Add `SECURITY_DASHBOARD`, `SPORTS_HUB`, `CALENDAR_EVENT_DETAIL` help topics | Following |

## 5. Human-judgment items

1. **Where is the line for "overview page needs a summary"?** A true dashboard clearly does; a plain CRUD list (`NoteListView`, `TagListView`) arguably does not. Scope the ~90 candidates down to genuine dashboards.
2. **Goals pattern:** `GoalListView` currently declares a single active-goal *object* via `CurrentContextMixin`; the backlog wants a `purpose.goals` *summary*. Decide which pattern Goals should use.
3. **Staff/admin surfaces** (admin_console, owner_finance, security, blueprint, observability) — confirm whether Contracts A/B apply to internal pages or only member-facing.
4. **Prefix-level help acceptable?** Finance's single-prefix help technically passes "has help" but is functionally a gap.
