# Calendar Engine — Discovery Document

**Created:** 2026-02-19
**Purpose:** Document existing models and architecture before building calendar_engine app.

---

## Existing Models Inventory

### Task (apps/life/models.py:161-344)
- **Key fields:** title, notes, priority (now/soon/someday), effort (quick/small/medium/large)
- **Date fields:** `due_date` (DateField), `start_date`, `end_date`
- **Status:** `is_completed` (bool), `completed_at`
- **Recurrence:** `is_recurring`, `recurrence_pattern` (CharField)
- **Domain:** None — no FK to LifeDomain. Task has no category/domain field.
- **Parent:** Optional FK to Project
- **Notes:** Priority auto-calculated from due_date proximity. Inherits from UserOwnedModel.

### LifeGoal (apps/purpose/models.py:190-436)
- **Key fields:** title, description, why_it_matters, success_looks_like
- **Date fields:** `target_date` (DateField), `completed_date`
- **Status:** active / paused / completed / released
- **Domain:** FK to `LifeDomain` (nullable)
- **Timeframe:** year_1 / year_2 / year_3 / ongoing
- **Milestones:** Has GoalMilestone children (title, target_date, completed bool)
- **Notes:** Has deadline_urgency, is_overdue properties. Inherits from UserOwnedModel + SoftDeleteModel.

### GoalMilestone (apps/purpose/models.py:442-522)
- **Key fields:** title, description, target_date, completed, sort_order
- **Parent:** FK to LifeGoal

### HabitGoal (apps/purpose/models.py:783-1219)
- **Key fields:** name, purpose, measurement_type (binary/duration/count/target)
- **Date fields:** `start_date`, `end_date`
- **Frequency:** `frequency_type` (daily/weekly/monthly), `sessions_per_week`
- **Domain:** FK to `LifeDomain` (nullable), also has `category` CharField
- **Status:** active / paused / completed / abandoned
- **Notes:** Has HabitEntry children for daily tracking. No recurrence rule model — frequency is on the goal itself.

### LifeEvent (apps/life/models.py:351-446)
- **Key fields:** title, description, event_type, location
- **Date fields:** `start_date`, `start_time`, `end_date`, `end_time`, `is_all_day`
- **Recurrence:** `is_recurring`, `recurrence_pattern`, `recurrence_end_date`
- **Domain:** `event_type` choices: personal, family, household, faith, health, work, social, travel, other
- **External:** `external_id`, `external_source`
- **Notes:** Existing calendar-like model but lacks source-linking/projection semantics. Could be migrated or co-exist.

### LifeDomain (apps/purpose/models.py:35-67)
- **Fields:** name, slug, description, icon, color (#hex), sort_order, is_active
- **Defaults:** Faith, Health, Family, Work, Finances, Learning, Personal Growth
- **Notes:** Already has everything CalendarDomain needs. calendar_engine will FK to this directly.

### ScheduledBlock (apps/core/blueprint/models.py:642-725)
- **Fields:** plan (FK), start_time, end_time, title, description, tier (1-4), source, source_id, behavior_key, is_locked, rationale, is_completed
- **Source choices:** non_negotiable, calendar, task, health, sleep, buffer
- **Notes:** Part of ArchitecturePlan (nightly pass). Calendar engine complements but doesn't replace this.

---

## Architecture Context

### Dashboard (apps/dashboard/)
- **Main view:** DashboardView at `/dashboard/`
- **Template:** `templates/dashboard/home.html` — 6-column CSS grid, HTMX tile loading
- **Existing tiles:** quick_stats, weather, ai_insights, goal_progress, habit_goals, upcoming_events, etc.
- **No existing timeline view** — calendar_engine adds this as a new tile/view

### CoS (Circle of Stewardship)
- **Blueprint:** PersonalOperatingBlueprint (apps/core/blueprint/models.py) — per-user governance
- **Governance:** cos_governance.py — decision layer for AI interactions
- **Architecture:** ArchitecturePlan + ScheduledBlock — daily schedule blocks
- **Drift:** DriftEvent + DriftScore — deviation tracking

### Tech Stack
- **No DRF** — use standard Django JSON views
- **HTMX** for dynamic content
- **CSP nonce-based** — no inline handlers
- **Crispy + Tailwind** for forms

---

## Design Decisions for calendar_engine

1. **Reuse LifeDomain** — no need for CalendarDomain model. FK directly to purpose.LifeDomain.
2. **Map LifeEvent.event_type → LifeDomain** where possible (event_type "faith" → Faith domain, etc.)
3. **Task has no domain** — default to Work domain, or infer from project if available.
4. **HabitGoal frequency → RecurrenceRule** — translate frequency_type + sessions_per_week.
5. **LifeEvent coexistence** — calendar_engine CalendarEvent is the projection layer; LifeEvent remains source of truth for manual events created through life app.
6. **No DRF** — use Django views returning JsonResponse.
7. **ScheduledBlock integration** — calendar_engine can read ScheduledBlocks for display but doesn't own them.
