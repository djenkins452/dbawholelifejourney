# WLJ UI & Dashboard Catalog

Objective inventory of every major user-facing screen/page/dashboard in the Whole Life Journey (WLJ) Django app. All claims proven with `file:line`. Read-only knowledge extraction — no code modified.

Root URL map: `config/urls.py`.

---

## Dashboard App Status (which is active)

There are three dashboard apps. Routing is in `config/urls.py:74-79`:

| App | Mount | Status | Proof |
|-----|-------|--------|-------|
| **`apps/dashboard_v3`** | served at `/dashboard/` (default) **and** `/dashboard-v3/` | **ACTIVE / PRODUCTION DEFAULT** (promoted 2026-05-28) | `config/urls.py:79`; dispatcher `apps/dashboard_v2/views.py:31-52`; flag `DASHBOARD_V3_DEFAULT=True` in `config/settings.py:130` |
| `apps/dashboard_v2` | `/dashboard/classic/` (direct), is the rollback target | **PRESERVED / ROLLBACK** — `/dashboard/` falls back to v2 when `DASHBOARD_V3_DEFAULT=False` | `apps/dashboard_v2/urls.py` (`classic`); `apps/dashboard_v2/views.py:58` |
| `apps/dashboard` (v1 legacy) | `/dashboard/legacy/` → redirects to v2; v1 preserved at `/dashboard/legacy/classic/` | **LEGACY** — root redirects to `dashboard_v2:home` | `config/urls.py:77`; `apps/dashboard/urls.py` (RedirectView → `dashboard_v2:home`) |

Key fact: `/dashboard/` → `dashboard_v2:home` → `dashboard_home_dispatch()` which serves **DashboardV3View** by default (`apps/dashboard_v2/views.py:45-52`). All v2 action/HTMX endpoints (task toggle, intake log, routine toggle, cockpit panel) remain mounted and are **reused by v3** — the dispatcher only swaps the HOME view.

---

## Master Surface Table

| Surface | Route | View (file:line) | Data sources | Reads cache / snapshot or live? |
|---------|-------|------------------|--------------|---------------------------------|
| **Main Dashboard (Home / Action Center)** | `/dashboard/` | `dashboard_v3/views.py:25` (DashboardV3View) via dispatch `dashboard_v2/views.py:31` | composer `dashboard_v3/services/composer.py:59`; SAE snapshots, `build_today_execution`, GoalMomentumSnapshot, Insight rows | **READS canonical snapshots + execution contract** (composer reads SAE/snapshots, freshness-guarded; never live-computes heavy builders) |
| Dashboard v2 (classic / rollback) | `/dashboard/classic/` | `dashboard_v2/views.py:58` (DashboardV2View) | `DashboardV2Service`, `GoalCockpitService`, WaterEntry, weather | **Section cache** (`DashboardV2CacheService`) + SAE state; execution 30s TTL |
| Dashboard v1 (legacy) | `/dashboard/legacy/classic/` | `dashboard/views.py` (DashboardView) | legacy tiles, Command Brief builders | live tiles (HTMX) |
| Health Home (Physical) | `/health/physical/` | `health/views.py:105` (HealthHomeView) | `_fresh_module_state('health'/'medicine')` SAE, fallback WeightEntry/HeartRate/Fasting | **SAE snapshot**, live fallback only if SAE empty |
| Health Intelligence | `/health/intelligence/` | `health/views.py:7373` | **DailyHealthSummary** (precomputed daily aggregates), BodyCompositionEntry | **READS DailyHealthSummary cache**, staleness flag at 36h |
| Fitness Home | `/health/physical/fitness/` | `health/views.py:1551` | WorkoutSession, WorkoutTemplate, PersonalRecord | **LIVE** |
| Nutrition Home | `/health/physical/nutrition/` | `health/views.py:4591` | `NutritionQueries`, `build_meal_signals`, NutritionGoals | **LIVE** (deterministic signals) |
| Intake / Medicine Home | `/health/physical/intake/` | `health/views.py:3264` | Intake, IntakeSchedule, IntakeLog (Prefetch) | **LIVE** (batch-optimized) |
| Vitals dashboards (BP, HR, HRV, VO2, etc.) | `/health/physical/<metric>/dashboard/` | `health/views_base.py` (HealthMetricDashboardMixin) | per-metric entry models | **LIVE** |
| Faith Home | `/faith/` | `faith/views.py:104` (FaithHomeView) | DailyVerse, PrayerRequest, JournalEntry(faith), FaithMilestone, UserReadingPlan, `get_module_insight('faith')` | **Verse 24h cache**; rest live; insight from cache |
| Today's Verse | `/faith/verse/` | `faith/views.py:200` | DailyVerse / cached ScriptureVerse | **24h per-user cache** |
| Reading Plans / Progress | `/faith/reading-plans/...` | `faith/views.py:1138` / `:1320` | ReadingPlanTemplate, UserReadingPlan, UserReadingProgress | **LIVE** |
| Faith Journey (Walking With God) | `/faith/journey/today/` | `faith/journey/views.py:93` | UserJourney, JourneyDay, JourneyPath; emits resumed signal | **LIVE** + engagement signals |
| Journal Home | `/journal/` | `journal/views.py:769` (JournalHomeView) | JournalEntry, Emotion, JournalPrompt, Tag, `get_module_insight` | **LIVE** (insight from cache) |
| Journal Entry List | `/journal/entries/` | `journal/views.py:67` | JournalEntry, Category, Tag | **LIVE** |
| Journal Prompts | `/journal/prompts/` | `journal/views.py:592` | JournalPrompt, Category; HTMX random prompt | **LIVE** |
| Purpose Home (goals/vision) | `/purpose/` | `purpose/views.py:61` (PurposeHomeView) | AnnualDirection, LifeGoal, ChangeIntention, HabitGoal, Reflection, Insight | **LIVE** (insight from cache) |
| Goal List | `/purpose/goals/` | `purpose/views.py:262` | LifeGoal, LifeDomain | **LIVE** |
| Life Home (organize / tasks) | `/life/` | `life/views.py:81` (LifeHomeView) | Project, Task, LifeEvent, `get_module_insight('life')` (48h) | **LIVE + insight cache read** |
| Task List (Today/priorities) | `/life/tasks/` | `life/views.py:317` | Task, Project; `classify_time_status()` | **LIVE** |
| Routine List | `/life/routines/` | `life/views.py:3405` | `build_routine_state()` (SAE), `evaluate_all_routine_health()` | **STATE-BUILDER READ** (SAE) + live health signals |
| Routine Adherence | `/life/routines/adherence/` | `life/views.py:3711` | behavior_score_engine (`compute_adherence_summary`) | **LIVE** |
| Project / Inventory lists | `/life/projects/`, `/life/inventory/` | `life/views.py:193` / `:834` | Project, InventoryItem | **LIVE** |
| Calendar (Time Command Center) | `/calendar/` | `calendar_engine/views.py:145` (CalendarDashboardView) | CalendarEvent, Domain, RecurrenceRule, `metrics.get_today/week_balance()` | **Balance precomputed**, events live (recurrence expansion) |
| Capture (audio transcription) | `/capture/` | `capture/views.py:280` (CaptureListView) | CaptureEntry, PendingCapture; S3/Cloudinary | **LIVE** (summaries pre-stored); status-poll endpoint |
| Relationships | `/relationships/` | `relationships/views.py:36` (PersonListView) | Person, RelationshipInteraction, `RelationshipAnalyticsService` | **LIVE** (per-person analytics) |
| AI Chat (CoS) — non-stream | `POST /assistant/api/chat/` | `ai/views.py:732` (AssistantChatView) | PersonalAssistant orchestrator, AssistantConversation/Message | **LIVE context rebuild** |
| AI Chat (CoS) — streaming SSE | `POST /assistant/api/chat/stream/` | `ai/views.py:1058` (AssistantChatStreamView) | Celery `run_chat_generation`, `chat_stream_bus` relay | **LIVE** generation, snapshot relay via cache |
| AI Chat — resume | `GET /assistant/api/chat/stream/resume/<job_id>/` | `ai/views.py:1160` | chat_stream_bus snapshot | **READS cache snapshot** |
| CoS Settings | `/assistant/cos/settings/` | `ai/views.py` (CosSettingsView), `ai/urls.py:62` | PersonalOperatingBlueprint | live on save |
| Settings / Preferences | `/user/preferences/` | `users/views.py` (PreferencesView), `users/urls.py:42` | UserPreferences | live |
| Intelligence Command Center (ICC) | `/intelligence/` | `core/views_intelligence_center.py:27` | UserState, GuidanceItem, DailyBriefing, WeeklyIntelligenceReport, Prediction, `compute_all_maturity_scores` | **MIXED — reads model rows, but LIVE-computes maturity** (`:112`) |
| AI Insights Inbox (PIE) | `/insights/` | `core/ai_insights/views.py:13` | Insight | **LIVE model read** |
| AI Guidance Inbox (PGE) | `/guidance/` | `core/ai_guidance/views.py:26` | GuidanceItem (lifecycle) | **LIVE model read** |
| Weekly Intelligence Reports (WIRE) | `/intelligence/weekly/`, `/<id>/` | `core/ai_weekly_report/views.py:14` | WeeklyIntelligenceReport | **READS persisted report rows** (generated in background) |
| Daily Briefing (DBE) | embedded in ICC `/intelligence/` (+ legacy dashboard) | `core/views_intelligence_center.py:189` | DailyBriefing (`core/ai_briefing/models.py`) | **READS persisted briefing row** (generated each morning) |
| Evidence & Explainability (E3) | `/intelligence/explain/<engine>/<type>/<id>/` | `core/ai_explain/views.py:16` | ExplainRecord (lookup or create) | reads / on-demand create |
| Delivery & Notification (DNE) | `/intelligence/delivery/settings/`, `/history/` | `core/ai_delivery/views.py` | UserPreferences, DeliveredNotification | **LIVE model read** |
| Admin Console Dashboard | `/admin-console/` | `admin_console/views.py:242` (AdminDashboardView) | User, JournalEntry, maturity_engine, domain_registry | **LIVE-computes maturity** (`:278`) |
| **Operations Wall v2 (Ops Wall)** | `/admin-console/ops/` | `core/ai_observability/ops_views.py:42` (OperationsWallView) | cache `wlj:ops:maturity_scores`, SystemMaturitySnapshot | **READS PRE-COMPUTED CACHE ONLY** (SAME cycle 60s) — `:100,121-126` |
| Ops Wall Stream (poll) | `/admin-console/ops/stream/` | `core/ai_observability/ops_views.py:255` (OpsStreamView) | cache `OPS_STREAM_CACHE_KEY` | **READS CACHE ONLY**, `{status: pending}` on miss (`:277`) |
| Diagnostics Console | `/admin-console/diagnostics/` | `core/ai_observability/diagnostics_views.py` | diagnostic logs / trace records | reads diagnostic stream |
| Security Dashboard (CISO) | `/security/dashboard/` | `security/views.py:71` (SecurityDashboardView) | SecurityRun, SecurityScore, SecurityTest, SecurityFinding | **LIVE model read** (`@staff_member_required`) |

---

## Per-Surface Detail

### Main Dashboard / Home (Action Center) — ACTIVE (v3)

- **Route:** `/dashboard/` (also `/dashboard-v3/`). Dispatcher `apps/dashboard_v2/views.py:31-52` serves `DashboardV3View` (`apps/dashboard_v3/views.py:25`) when `DASHBOARD_V3_DEFAULT=True` (`config/settings.py:130`).
- **Purpose:** CoS-first "Life Command Center" single-page render — mission card, gauges, action center / execution rhythm, accountability cards.
- **Template:** `dashboard_v3/home.html`. Cockpit dials reuse the canonical v2 partial `dashboard_v2/.../cockpit_dial.html` (`composer.py:138-153`).
- **Major sections (composer `apps/dashboard_v3/services/composer.py`):** cockpit domains (`_build_cockpit_domains_raw` :138), mission card + panel (`_build_mission_card` :465, `_build_mission_panel` :603), mission drivers/signals/status/progress/weight-status (:695–:1353), executive summary + rhythm (`_build_executive_summary` :1676, `_build_rhythm` :1681), status gauges (`_build_gauges` :1389 / SAE fallback `_fallback_gauges_from_sae` :1453), accountability cards (`_build_accountability_cards` :1717).
- **Data sources / canonical state:** SAE module snapshots (`_read_mission_states` :642 reads nightly/SAME-cycle SAE snapshot with freshness guard, never live-computes heavy builders — explicit comment :646-667), `GoalMomentumSnapshot` (`_latest_momentum` :416), `build_today_execution()` execution contract (fetched once and threaded to avoid redundant calls — `views.py:67-78`, `_load_execution_contract` :1655), `Insight` rows for accountability (`:1742`).
- **Cache vs live:** **Compliant.** Composer reads canonical pre-composed state and indexed insight rows; mission states come from snapshots with a freshness guard that reads stale snapshot rather than live-computing (`composer.py:651-667`). Wake-up auto-completion runs idempotently on render (`views.py` `complete_wake_up`).
- **On-render writes:** `complete_wake_up()` (verified auto-completion, Rule 1 — authenticated presence) and day-start initializer (idempotent / cache-gated).
- **Visual Truth Contract:** This is the surface the contract governs (`docs/WLJ_VISUAL_TRUTH_CONTRACT.md`). Only `completed`-equivalent data booleans may render completion visuals (strike-through, filled checks); overdue/behind/missed use badges/dimming. Origin incident 2026-05-20.

### Dashboard v2 (classic / rollback)

- **Route:** `/dashboard/classic/` (`apps/dashboard_v2/urls.py`). View `DashboardV2View` (`apps/dashboard_v2/views.py:58`).
- **Data:** `DashboardV2Service.get_critical_context()` (`services/dashboard_service.py:74`), `GoalCockpitService` (`:86`), WaterEntry tile (`:106-146`), weather.
- **Cache:** `DashboardV2CacheService` section cache (`apps/dashboard_v2/cache.py`) — TTLs: execution 30s, state 300s, celebration 600s, momentum 300s, daily_prog 120s. State panel reads SAE builders (`apps/core/ai_state/state_builder.py` via `dashboard_service.py:854`). `?refresh=1` invalidates execution cache (`views.py:69-71`).
- **HTMX section endpoints (lazy-load):** execution, state, celebration, insights, action-center, suggestions, signal-insights, physical-intelligence, reconciliation (`apps/dashboard_v2/urls.py`).
- **Action endpoints (reused by v3):** task toggle, intake log (single/group/kind/action), routine complete/toggle, block-complete-toggle, celebration reveal/dismiss, compliance drill-down (`apps/dashboard_v2/urls.py`).

### Health Dashboard

- **Health Home** `/health/physical/` (`health/views.py:105`): Today status block (workout/medication/glucose/sleep/water), priority cards, vitals cards. Reads SAE via `_fresh_module_state('health')` and `_fresh_module_state('medicine')` (`:129-188`); live fallback queries only when SAE unavailable.
- **Health Intelligence** `/health/intelligence/` (`health/views.py:7373`): body-composition trends, plateau risk, fat-loss phase, 56-day chart. **Reads DailyHealthSummary precomputed aggregates** (`:7390`), 36h staleness flag (`:7399`).
- **Fitness / Nutrition / Intake / Vitals:** all live-compute (batch-optimized for Intake, deterministic signals for Nutrition). Vitals use generic `HealthMetricDashboardMixin` (`health/views_base.py`) for ~10 metric dashboards.

### Faith Dashboard

- **Faith Home** `/faith/` (`faith/views.py:104`): AI insight card, today's scripture, Walking-With-God journey card, prayer requests, faith reflections, milestones, reading plans. Today's verse cached 24h per user (`:176-194`); other data live; insight via `get_module_insight('faith')`.
- **Reading Plans / Progress / Study Tools / Journey:** live progress tracking; Journey (`faith/journey/`) emits engagement signals (resumed/completed) and tracks last-visited.

### Journal

- **Journal Home** `/journal/` (`journal/views.py:769`): stats row, AI insight card, recent entries, mood distribution, daily prompt (rotates by day-of-year, faith-aware), popular tags. Live-compute; insight from cache.
- **Entry List** `/journal/entries/` (`:67`): list/calendar/page/book views, filters. **Prompts** `/journal/prompts/` (`:592`) with HTMX random-prompt endpoint.

### Goals / Purpose

- **Purpose Home** `/purpose/` (`purpose/views.py:61`): annual direction card (word/theme/anchor quote), stats grid, three-column Life Goals / Change Intentions / Habit Goals, recent reflections, AI insight. Live-compute.
- **Goal List** `/purpose/goals/` (`:262`): status/domain filters, bulk delete, goals grouped by domain.

### Organization / Life (Tasks)

- **Life Home** `/life/` (`life/views.py:81`): AI insight (48h window via `get_module_insight('life')` `:183`), today's events, quick stats, active projects, Now/Soon task buckets, upcoming events, overdue count. Stale task priorities refreshed via `_refresh_stale_task_priorities()` (`:96`).
- **Task List** `/life/tasks/` (`:317`): search, status/priority filters, time-horizon grouping (`classify_time_status` :414).
- **Routine List** `/life/routines/` (`:3405`): **reads canonical `build_routine_state()` (SAE)** (`:3421`) + live `evaluate_all_routine_health()`. Adherence drilldown `/life/routines/adherence/` (`:3711`) live-computes via behavior_score_engine.

### Calendar

- **Time Command Center** `/calendar/` (`calendar_engine/views.py:145`): Life Balance bar, today's timeline, NLP quick-add, smart suggestions, Day/3-Day/Week/Agenda/Month toggle. Balance is **precomputed** (`metrics.get_today/week_balance()`); event range expansion (recurrence) is live (`_get_events_in_range` :78-130).
- **APIs (AJAX):** `/calendar/api/nlp_create/`, `/api/today/`, `/api/range/`, `/api/month/`, `/api/metrics/balance/`, `/api/suggestions/gaps/`, `/accept/`, `/decline/`, `/api/events/...`, `/api/events/<id>/move/`.

### Capture

- **Capture List** `/capture/` (`capture/views.py:280`): recording stats, category/search filters, local-recordings recovery banner (IndexedDB/service worker), entries table. Detail `/capture/<uuid>/` shows BLUF summary + audio player. **Polling:** `/capture/status/<uuid>/` for transcription status; submit/cloudinary-upload/retry/pending endpoints.

### Relationships

- **Person List** `/relationships/` (`relationships/views.py:36`): people card grid (avatar, relationship badge, interaction count, last-interaction date), search + type filter, bulk-action bar. Detail `/relationships/<id>/` shows interaction timeline + recency analytics (`RelationshipAnalyticsService`). `/relationships/insights/` dashboard. Autocomplete + quick-create + contact-import endpoints. Live-compute per-person analytics.

### AI Chat UI (Chief of Staff)

- **Surface:** persistent chat (mounted under `/assistant/`, `apps/ai/urls.py`). Two paths per CLAUDE.md streaming-parity rule:
  - **Non-streaming** `POST /assistant/api/chat/` (`ai/views.py:732`) — supports image uploads; synchronous full response; calls `get_personal_assistant(user).send_message()` (`apps/ai/personal_assistant.py`).
  - **Streaming SSE** `POST /assistant/api/chat/stream/` (`ai/views.py:1058`) — dispatches Celery `run_chat_generation.delay()`, relays token/done/error events via `chat_stream_bus`. Background generation means navigation no longer abandons the response (recent commit 50fb57e5).
  - **Resume** `GET /assistant/api/chat/stream/resume/<job_id>/` (`ai/views.py:1160`) — replays cached snapshot.
- **Supporting endpoints:** `/api/history/`, `/api/clear/`, `/api/feedback/`, `/api/priorities/`, `/api/opening/`, `/api/wake/` (pre-warm context), `/api/briefing/` (proactive), `/api/session-start/` (deterministic, no-LLM decision: briefing / lightweight_alignment / drift_intervention / none).
- **Orchestrator pipeline:** intent detection → CoS deterministic router → action handlers → Claude generation → background post-response intelligence (learning/pattern/correction extraction). Per MEMORY: Beth consumes composed deterministic briefings, not raw signals.
- **CoS Settings** `/assistant/cos/settings/` (CosSettingsView): Learning Mode toggle, display name, accountability style — backed by `PersonalOperatingBlueprint`.

### Settings

- **Preferences** `/user/preferences/` (`users/urls.py:42`, PreferencesView): UserPreferences, theme selection (`/preferences/theme/`), preference toggle (`/preferences/toggle/`). Module flags (`health_enabled`, `journal_enabled`, etc.) read here and in `apps/core/context_processors.py`.

### Reports / Intelligence Surfaces

- **Intelligence Command Center (ICC)** `/intelligence/` (`core/views_intelligence_center.py:27`): unified hierarchy — System Maturity, Domain Coverage, Proactive Intelligence (7-day), Current State (SAE/UserState), Active Guidance (GuidanceItem), Daily Briefing (DBE), Weekly Report (WIRE), Recent Deliveries (DNE), Predictions (PRIE), Observability (staff). **Note:** ICC live-computes user-scoped maturity via `compute_all_maturity_scores(user)` (`:112`) on the request path — unlike the Ops Wall which is cache-only (see Gaps).
- **AI Insights Inbox (PIE)** `/insights/` (`core/ai_insights/views.py:13`): status-filtered Insight cards.
- **AI Guidance Inbox (PGE)** `/guidance/` (`core/ai_guidance/views.py:26`): GuidanceItem lifecycle (active/acknowledged/dismissed/snoozed/acted).
- **Daily Briefing (DBE):** rendered embedded in ICC (`core/views_intelligence_center.py:189`, model `core/ai_briefing/models.py::DailyBriefing`, queried `briefing_date=today`); also served proactively via chat `/assistant/api/briefing/`. **Reads persisted briefing row** generated each morning by background engine. Explainability link to E3.
- **Weekly Intelligence Reports (WIRE)** `/intelligence/weekly/` + `/<id>/` (`core/ai_weekly_report/views.py:14`): paginated history (12/page) + detail with engagement tracking (`record_briefing_opened`). **Reads persisted report rows.**
- **Evidence & Explainability (E3)** `/intelligence/explain/<engine>/<type>/<id>/` (`core/ai_explain/views.py:16`): per-output evidence (GuidanceItem / DailyBriefing / WeeklyIntelligenceReport), lookup-or-create ExplainRecord.
- **Delivery & Notification (DNE)** `/intelligence/delivery/settings/` + `/history/`: notification prefs + DeliveredNotification audit.

### Operator Surfaces (admin_console / Ops Wall)

- **Admin Console Dashboard** `/admin-console/` (`admin_console/views.py:242`): site stats, recent activity, maturity scores + recommendations, domain coverage, 30-day trend, regression detection. Live-computes maturity (`compute_all_maturity_scores` :278).
- **Operations Wall v2 (Ops Wall / Vegas layer)** `/admin-console/ops/` (`core/ai_observability/ops_views.py:42`): system maturity header, maturity trend deltas, life-impact breakdown, domain coverage, proactive-intelligence stats, canonical-query compliance, domain-registry health. **Strict cache-reader compliance:** explicitly "NEVER computes maturity on the request path. Reads from cache populated by SAME cycle every 60s" (`:100`); reads `cache.get("wlj:ops:maturity_scores")` and returns empty/pending on miss (`:121-126`).
- **Ops Wall Stream** `/admin-console/ops/stream/` (`ops_views.py:255`): JSON poll endpoint, **reads `OPS_STREAM_CACHE_KEY` only**, returns `{"status": "pending"}` on miss (`:277`) — zero telemetry computation on request path.
- **Diagnostics Console** `/admin-console/diagnostics/` (`core/ai_observability/diagnostics_views.py`): trace/log inspection (Truth layer).
- **Security Dashboard (CISO)** `/security/dashboard/` (`security/views.py:71`): latest scores (CVSS/BitSight/risk/maturity), 30-run trend graphs, runs table, finding trends, remediation metrics. `@staff_member_required`, access logged to SecurityAuditLog. Reads SecurityRun/Score/Test/Finding models directly.

---

## Cache-vs-Live Compliance Summary (WLJ rule: heavy analytics precomputed in background, request path reads cache/snapshots only)

**Compliant — read precomputed snapshots / cache:**
- Main Dashboard v3 (composer reads SAE snapshots + execution contract, freshness-guarded; never live-computes heavy builders — `composer.py:646-667`).
- Dashboard v2 (section cache `DashboardV2CacheService`).
- Health Home (SAE module state) and Health Intelligence (DailyHealthSummary).
- Routine List (`build_routine_state` SAE).
- **Ops Wall + Ops Stream** — strictest compliance, explicit cache-only with pending fallback (`ops_views.py:100,121-126,277`).
- WIRE / DBE — read persisted report/briefing rows generated by background engines.

**Live model reads (lightweight rows — generally acceptable; not heavy analytics):**
- Insights Inbox, Guidance Inbox, Delivery history, Security Dashboard — read indexed model rows on request path.
- Most CRUD list surfaces (journal, purpose, life tasks/projects/inventory, capture, relationships) — live querysets with filters; no heavy aggregation.

**Notable live-compute on request path (heavier):**
- **Intelligence Command Center** `/intelligence/` live-computes `compute_all_maturity_scores(user)` (`core/views_intelligence_center.py:112`) — the same maturity computation the Ops Wall deliberately moved to the SAME background cycle. ICC is user-scoped (not the 200-user system-wide compute the rule's 524-timeout origin describes), but it is still a request-path compute of an analytic that exists in cache form elsewhere.
- **Admin Console Dashboard** `/admin-console/` live-computes maturity (`admin_console/views.py:278`).
- Fitness Home "best suggestion" does a ~20-query Python-side frequency lookup on the request path (`health/views.py:1596-1641`).

(These are documented objectively; no recommendation implied.)

---

## Notable Gaps / Observations

1. **Cache-pattern asymmetry:** The Ops Wall (`/admin-console/ops/`) is the model citizen for the "never live-compute on request path" rule, but the **Intelligence Command Center** (`/intelligence/`) and the **Admin Console Dashboard** (`/admin-console/`) both call `compute_all_maturity_scores()` synchronously on render — the same metric the Ops Wall reads from the 60s SAME-cycle cache.
2. **Daily Briefing has no standalone page:** it is only rendered embedded in ICC (`/intelligence/`) and served proactively through the chat briefing endpoint (`/assistant/api/briefing/`); there is no dedicated `/briefing/` route.
3. **AI Chat is not a standalone page in the URL map** — it is API-only (`/assistant/api/chat/`, `/stream/`, `/resume/`) consumed by a persistent chat panel; the `/assistant/` root is a legacy redirect.
4. **Three dashboards coexist** with active dispatch logic; v1/v2/v3 all remain reachable. The active surface is gated solely by the `DASHBOARD_V3_DEFAULT` env flag, enabling instant rollback without code change.
5. **Modules present but not separately catalogued here** (out of the requested core set): `apps/meals` (`/meals/`), `apps/finance` (`/finance/`), `apps/billing`, `apps/sports`, `apps/notes`, `apps/medical`, `apps/brain_training`, `apps/scan`, `apps/owner_finance` (`/owner/finance/`, superuser), `apps/sms` — each has its own home/list surface following the same per-app `views.py` + template pattern.

---

*Catalog generated from read-only inspection. Active dashboard: **dashboard_v3** (`DASHBOARD_V3_DEFAULT=True`).*
