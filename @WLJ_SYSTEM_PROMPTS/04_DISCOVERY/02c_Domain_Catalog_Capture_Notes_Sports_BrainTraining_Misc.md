# WLJ Domain & Data Catalog — Part C (Capture, Notes, Sports, Brain Training, Owner Finance, Scan, Travel)

> READ-ONLY knowledge extraction. Every claim grounded with `file:line` against the codebase at
> `/Users/dannyjenkins/Projects/dbawholelifejourney`. Where the **WLJ DOMAIN REGISTRY** or
> `docs/wlj_camera_scan_architecture.md` make claims not found in code, this is flagged explicitly
> under "Doc vs Code".

Framing source: `@WLJ_SYSTEM_PROMPTS/03_REFERENCE/WLJ DOMAIN REGISTRY.md` (Capture §301, Notes §255,
Sports §357, Brain Training §217, Owner Finance §378, Travel §398, scan §451).

---

## 1. CAPTURE (`apps/capture`)

### Purpose
Audio-ingestion pipeline + cross-domain signal producer. User records/uploads audio → transcribed
(Whisper) → summarized (OpenAI BLUF) → stored → behavioral signals NLP-extracted and fed into the
cross-domain signal system.
- `apps/capture/models.py:1` — *"Capture models - Audio recordings, transcripts, and summaries."*
- `apps/capture/models.py:12-23` — 5-state workflow + S3 7-day signed-URL expiry.
- `apps/capture/apps.py:11` — `verbose_name = 'Audio Capture'`.
- Registry §303/§324 frames Capture as "records meetings, sermons, ideas, conversations" and "a
  cross-domain ingestion system that may produce signals affecting multiple domains." **Verified.**

### Primary Models (`apps/capture/models.py`)
- **`CaptureEntry(TimeStampedModel)`** — `models.py:11`. Main artifact. UUID PK `models.py:67`;
  `user` FK `related_name='capture_entries'` `models.py:75`; `audio_file_url` `models.py:96`;
  `audio_expires_at` (drives reminders) `models.py:102`; `transcript` `models.py:109`;
  `summary` (BLUF) `models.py:114`; `category`/`subcategory` `models.py:120,127`;
  **`status`** (`db_index=True`, default `uploading`) `models.py:135`; `pending_client_id`
  `models.py:163`.
  - Status choices `models.py:32-38`: `uploading, transcribing, summarizing, ready, failed`.
  - Category choices `models.py:44-47`: `faith, organize`. Subcategory `models.py:57-64`.
  - Error helpers: `get_error_type()` `models.py:177`, `get_user_friendly_error()` `models.py:201`,
    `can_retry()` `models.py:250`. Indexes `models.py:261-265`.
- **`PendingCapture(TimeStampedModel)`** — `models.py:273`. Client-side IndexedDB recording tracker
  for cross-device resilience. `client_id` `models.py:322`; **`status`** (default `pending`)
  `models.py:353`; `upload_attempts` `models.py:362`; `capture_entry` OneToOne→CaptureEntry
  `models.py:379`; `last_heartbeat_at` `models.py:389`; `is_partial` `models.py:401`.
  - Status choices `models.py:296-303`: `pending, uploading, uploaded, downloaded, completed, abandoned`.
  - `unique_together=['user','client_id']` `models.py:410`.
  - State methods: `mark_uploading/uploaded/completed/failed/downloaded/abandoned`,
    `update_heartbeat` `models.py:429-464`.
- **`CaptureSignal(models.Model)`** — `models.py:475`. Phase 5.5 NLP-extracted behavioral-signal
  candidate (validated intermediate; the LLM never writes signals directly). `entry` FK
  `related_name='extraction_signals'` `models.py:487`; `signal_type` `models.py:492`; `domain`
  (LifeDomain slug) `models.py:496`; `confidence` 0–1 `models.py:500`; `direction`
  positive/negative `models.py:506-511`; `extractor_type` `models.py:512`.

**Soft delete:** NONE on any Capture model (no `soft_delete`/`deleted_at`). Deletes are hard via
`CaptureDeleteView` `views.py:1087` — diverges from the project-wide soft-delete convention.

### Canonical State
- Per-entry state is the imperative `status` CharField (`models.py:135` / `:353`) — no computed status
  property; set by the pipeline + `mark_*` methods.
- **Canonical query layer:** `CaptureQueries` `services/capture_queries.py:13` — *"Canonical,
  deterministic capture queries. No instance state."* Classmethods: `pending_uploads()` `:16`,
  `ready_recent()` `:23`, `failed_recent()` `:35`, `today()` `:47`, `volume_recent()` `:57`,
  `stale()` `:68`.
- **Domain-level state for the intelligence layer:** `build_capture_state(user)`
  `apps/core/ai_state/state_builder.py:5023` consumes `CaptureQueries` (`:5030`) → intake pressure /
  backlog level (thresholds `state_builder.py:5048-5053`).
- Queue-wide counts: `get_processing_queue_status()` `tasks.py:399`.

### Signal Outputs (CRITICAL — Capture is a signal producer)
Capture does NOT directly emit PIE/PRIE/Insight/Prediction objects (grep of `apps/capture` for those
found no direct emitters). Its sole signal output is the `CaptureSignal` extraction record, later
*blended* into the signal pipeline by `apps/core`.

Producer functions:
1. `CaptureSignalExtractor.extract_signals(entry)` — `services/signal_extractor.py:101`. Two-phase:
   LLM proposes candidates (`_call_openai` `:170`) → deterministic validation
   (`_validate_and_create` `:217`) → creates `CaptureSignal` rows (`:269`). Gates: idempotency `:114`,
   transcript required `:122`, ≥15 words `:135`, confidence ≥0.6 `:248`. Domain mapped
   deterministically via `SIGNAL_TYPE_DOMAIN` `:46`, never from the LLM (`:263`). Valid signal types
   `:38-43`; extractor types `:60-67`.
2. `extract_capture_signals(entry_id)` Celery task — `tasks.py:528`.
3. `_dispatch_capture_signal_extraction(entry)` — `tasks.py:476` (called from main pipeline
   `tasks.py:169`).
4. `_run_targeted_recompute(entry, capture_signals)` — `tasks.py:505` → bridges to
   `TargetedSignalRecomputeService.recompute_for_capture(...)` (`tasks.py:513`).

Downstream blend (consumers):
- `apps/core/ai_eae/targeted_recompute.py:47` `recompute_for_capture()` → `_blend_capture_signals()`
  `:96`. Confidence discount `CAPTURE_CONFIDENCE_DISCOUNT = 0.6` (`:28`); negative direction →
  penalty `:104`; verified snapshots annotated, never overridden `:153-159`.
- Nightly safety-net blend `apps/core/ai_eae/signal_aggregation.py:1079-1086` (confidence ≥0.6).

This matches the project's "Beth = briefing consumer, not reasoner" rule: Capture emits validated
candidates into deterministic snapshots, not atomic signals for the LLM.

### Major Services (`apps/capture/services/`)
- `capture_queries.py:13` — canonical deterministic queries.
- `signal_extractor.py:91` — `CaptureSignalExtractor` (LLM-candidate + deterministic validation).
- `summarization.py:1-22` — OpenAI BLUF structured summarization (`summarize_transcript`).
- `transcription.py:1-18` — OpenAI Whisper transcription (S3 download, 25 MB compression).
- `docx_generator.py:1` / `pdf.py:1` — .docx / PDF export of entries.
- `email.py:1` — share-by-email. `expiration_reminder.py:1` — audio-expiry reminder emails.

### APIs / Endpoints (`apps/capture/urls.py`, `app_name='capture'`)
| Route | View | Line |
|---|---|---|
| `''` | `CaptureListView` | `urls.py:10` → `views.py:280` |
| `record/` | `CaptureRecordView` | `urls.py:11` → `views.py:38` |
| `upload/` | `CaptureUploadView` | `urls.py:12` → `views.py:50` |
| `submit/` | `CaptureSubmitView` | `urls.py:13` → `views.py:405` |
| `cloudinary-upload/<uuid:entry_id>/` | `CaptureCloudinaryUploadView` | `urls.py:14` → `views.py:656` |
| `status/<uuid:entry_id>/` | `CaptureStatusView` | `urls.py:15` → `views.py:847` |
| `<uuid:pk>/` | `CaptureDetailView` | `urls.py:16` → `views.py:359` |
| `<uuid:pk>/update-title/` | `CaptureUpdateTitleView` | `urls.py:17` → `views.py:730` |
| `<uuid:pk>/update-category/` | `CaptureUpdateCategoryView` | `urls.py:18` → `views.py:773` |
| `<uuid:pk>/pdf/` | `CaptureDownloadPDFView` | `urls.py:19` → `views.py:921` |
| `<uuid:pk>/email/` | `CaptureEmailView` | `urls.py:20` → `views.py:974` |
| `<uuid:pk>/delete/` | `CaptureDeleteView` | `urls.py:21` → `views.py:1087` |
| `<uuid:pk>/retry/` | `CaptureRetryView` | `urls.py:22` → `views.py:1039` |
| `pending/register/` | `PendingCaptureRegisterView` | `urls.py:25` → `views.py:1134` |
| `pending/heartbeat/` | `PendingCaptureHeartbeatView` | `urls.py:26` → `views.py:1182` |
| `pending/list/` | `PendingCaptureListView` | `urls.py:27` → `views.py:1221` |
| `pending/<uuid:pk>/abandon/` | `PendingCaptureAbandonView` | `urls.py:28` → `views.py:1265` |
| `pending/<uuid:pk>/status/` | `PendingCaptureUpdateStatusView` | `urls.py:29` → `views.py:1296` |
| `file-upload/` | `CaptureFileUploadView` | `urls.py:32` → `views.py:1346` |
| `sw-upload/` | `CaptureServiceWorkerUploadView` (CSRF-exempt) | `urls.py:35` → `views.py:1486` |

### UI Surfaces
`templates/capture/`: `capture_list.html`, `capture_detail.html`, `capture_record.html`,
`capture_upload.html`, `pdf_template.html`, `email/{expiration_reminder,processing_complete,share_capture}.html`.
Cross-domain pending banner: `templates/components/pending_capture_banner.html`.

### Relationships
- **Internal FKs only** to User + self (no FK to tasks/goals/people/journal). `CaptureEntry.user`
  `models.py:75`; `PendingCapture.capture_entry` `models.py:379`; `CaptureSignal.entry` `models.py:487`.
- **Cross-domain feeds (via signals, not FKs):**
  - → **EAE / Signal system** across domains health/faith/journal/brain_training/life/finance/
    relationships per `SIGNAL_TYPE_DOMAIN` `signal_extractor.py:46-57`; consumers
    `targeted_recompute.py:47/96`, `signal_aggregation.py:1079`.
  - → **SAE state** `state_builder.py:5023` (CoS context).
  - → **AI search** `apps/ai/search_service.py:1400`; **CoS revalidator**
    `apps/ai/personal_assistant.py:1507`; **Dashboard** `apps/dashboard/views.py:1174`;
    **Core context processor** (pending banner) `apps/core/context_processors.py:625`.
- **Async (`tasks.py`/`jobs.py`):** `process_capture_entry` `tasks.py:51`; `process_pending_captures`
  (Beat, 5 min) `tasks.py:245`; `extract_capture_signals` `tasks.py:528`;
  `send_expiration_reminders_task` (daily) `tasks.py:454`; `send_pending_capture_reminders_task`
  (hourly) `tasks.py:466`.

### Observability
- Loggers throughout `tasks.py`/`jobs.py`/`signal_extractor.py` (e.g. `tasks.py:79,160,209`;
  `signal_extractor.py:115,146,160`).
- Queue health: `get_processing_queue_status()` `tasks.py:399`.
- **Extraction telemetry (cache):** `update_extraction_telemetry('capture', ...)` from
  `tasks.py:520/560/566`, implemented `targeted_recompute.py:321`, cache key
  `wlj:ops:capture_extraction` (TTL 25h) `targeted_recompute.py:33-35`.
- **Admin:** only `CaptureEntryAdmin` registered `admin.py:8` (filters/search `:21-23`). `PendingCapture`
  and `CaptureSignal` are NOT in admin — limits observability of pending/extraction state.

---

## 2. NOTES (`apps/notes`)

### Purpose
General-purpose notes system serving as WLJ's long-term memory layer (`apps/notes/__init__.py:11-13`,
`models.py:5`). Notes stand alone or attach to any WLJ entity via GenericForeignKey. `services.py` is
a CoS-ready retrieval API with no `HttpRequest` dependency (`services.py:6-11`). Registry §257 frames
it as "Unified notes layer with attachments to other entities (tasks, goals, people, captures)."
**Partly verified** — attachment is real, but the attachable whitelist does NOT include people or
captures (see Relationships).

### Primary Models (`apps/notes/models.py`)
- **`Note(UserOwnedModel)`** — `models.py:19`. Inherits `user, status, deleted_at, ...` from
  `UserOwnedModel` (`models.py:27`); soft delete via `SoftDeleteModel` (`apps/core/models.py:86-126`,
  `status` `:108`, `soft_delete()` `:122`). Fields: `title` `:41`, `body` `:46`, `tags` M2M→`core.Tag`
  `:49`, `color` `:54`, `is_pinned` `:60`, `word_count` `:65`, `search_vector` (Postgres FTS) `:66`,
  `tags_text` `:67`, `attachments_text` `:73`, `embedding` (JSON) `:79`, `embedding_updated_at` `:84`.
  `save()` recomputes word_count + search_vector `:113-120`; FTS build (Postgres-guarded) `:153-170`.
- **`NoteAttachment`** — `models.py:195`. THE attachment mechanism (GenericForeignKey).
- **`NoteImage`** — `models.py:264`. Image attached to a note for AI vision analysis; linked to
  `apps.scan.models.ImageAnalysis` via ContentType in detail view (`views.py:131-142`).

### Canonical State
Notes have no derived "current state" — state is the persisted row. Canonical pieces are the
denormalized search fields (`tags_text`, `attachments_text`, `search_vector`, `embedding`) kept in sync
by signals/`save()`. CoS-facing canonical retrieval: `search_notes_cos()` `services.py:419` re-ranked
by `memory_scoring.score_note()` `memory_scoring.py:134`. Lifecycle status (active/deleted/archived)
from `SoftDeleteModel` `apps/core/models.py:108`.

### Relationships (CRITICAL — attachment mechanism)
GenericForeignKey via `NoteAttachment`: `content_type` FK `models.py:211`, `object_id` `:216`,
`attached_entity = GenericForeignKey(...)` `:219`; `unique_together=[note, content_type, object_id]`
`:224`. Attachable whitelist `ATTACHABLE_MODELS` (`apps/notes/utils.py:15-23`):
- `life.project` / `life.task` `utils.py:16-17`
- `purpose.lifegoal` / `purpose.habitgoal` `utils.py:18-19`
- `journal.journalentry` `utils.py:20`
- `calendar_engine.calendarevent` `utils.py:21`
- `faith.biblestudynote` `utils.py:22`

Validation/resolution: `resolve_attachment_target()` enforces whitelist + ownership `utils.py:35-52`.
**Doc vs Code:** Registry §257 says attachments include "people" and "captures" — NEITHER is in
`ATTACHABLE_MODELS`; no person/capture content type is attachable in code.

Separate rename-trigger registry `NOTE_INDEX_REGISTRY` (`index_registry.py:15-31`): `life.Task`,
`life.Project`, `purpose.LifeGoal`, `purpose.HabitGoal`, `journal.JournalEntry`. **Gap:** it omits
`calendar_engine.CalendarEvent` and `faith.BibleStudyNote`, so renames of those two attachable
entities do NOT reindex attached notes.

### Major Services
- `services.py` — CoS retrieval API: `search_notes()` `:151`, hybrid keyword+semantic
  `search_notes_cos()` `:419`, `get_note_detail()` `:287`, `get_related_notes_for_entity()` `:308`,
  `semantic_similarity_map()` `:392`, `refresh_notes_for_entity()` `:662` (rename signals), index
  integrity/repair `:790-913`.
- `embeddings.py` — OpenAI `text-embedding-3-small` producer: `update_note_embedding()` `:81`,
  `generate_embedding()` `:48`, `cosine_similarity()` `:118` (fail-safe, never raises).
- `memory_scoring.py` — deterministic 6-factor ranker (FTS .45 / semantic .25 / recency .15 / pinned
  .07 / entity .05 / tag .03 `:36-41`); `score_note()` `:134`.
- `index_registry.py:15` — rename-trigger map. `utils.py` — attachable whitelist + resolvers,
  `is_postgres()` `:94`.

### APIs (`apps/notes/urls.py`, `app_name="notes"`)
- `""` → `NoteListView` `urls.py:16` → `views.py:29`
- `new/` → `NoteCreateView` `urls.py:17` → `views.py:87`
- `<pk>/` → `NoteDetailView` `urls.py:18` → `views.py:113`
- `<pk>/edit/` → `NoteUpdateView` `urls.py:19` → `views.py:146`
- `<pk>/delete/` → `NoteDeleteView` (POST, soft delete) `urls.py:20` → `views.py:171`
- `<pk>/pin/` → `NoteTogglePinView` (POST) `urls.py:21` → `views.py:184`

List search (`views.py:54-66`) uses `icontains`; FTS/semantic ranking reserved for the CoS path.

### UI Surfaces
`templates/notes/`: `note_list.html`, `note_detail.html`, `note_form.html`.

### Observability (`apps/notes/signals.py`, wired `apps.py:9`)
`note_pre_save_capture` `:34` + `note_post_save_embedding` `:53`; `note_tags_changed` (m2m) `:85`;
`attachment_created` `:100` / `attachment_deleted` `:114`; registry-driven rename detection
`connect_rename_signals()` `:224` → `_entity_pre/post_save` `:161/185` → `refresh_notes_for_entity()`.
Embedding failures logged at ERROR (`signals.py:82,97,111,127`; `embeddings.py:77,114`).

---

## 3. SPORTS (`apps/sports`)

### Purpose
Read-only "context domain" for team tracking and game-day signals (`apps.py:11`,
`config/settings.py:193`). `GameEvent` is the declared SINGLE SOURCE OF TRUTH; signals/state are
derived downstream, never duplicated (`models.py:5-6,96-99`). All heavy work runs in background
workers, never on the request path (`tasks.py:4-5`, `views.py:34-38`).

### Primary Models (`apps/sports/models.py`)
- **`Sport`** `:13` — `name`, `slug`.
- **`League`** `:25` — FK→Sport; `abbreviation`, `is_college`.
- **`Team`** `:40` — FK→League; `external_id` (provider linkage `:?`), `logo_url`; record fields
  `wins`/`losses`/`record_season` `:50-52`; properties `record` `:66`, `is_record_stale` `:73`,
  `record_display` `:83`.
- **`GameEvent`** `:94` — TRUTH SOURCE. `home_team`/`away_team`; `start_time` `:121`; **`status`**
  (scheduled/live/final/postponed/cancelled `:101-113`, field `:122`); scores; `game_type`
  regular/postseason/tournament `:141`; baseball probable pitchers `:150-151`; `last_updated` `:153`.
  Methods `is_live`/`is_final` `:166-172`, `get_winner()` `:174`, `user_team_won/lost()` `:184-194`,
  `get_opponent()` `:196`, `get_score_display()` `:204`.
- **`UserTeamFollow`** `:211` — FK user + team; **`priority`** 1=Primary/2=Secondary/3=Casual `:236`;
  `is_active` `:237`; `unique_together(user, team)` `:241`.

### Canonical State
Two-stage derivation, all from `GameEvent`:
1. `GameTimeWindow` (`services/time_windows.py:22`) classifies temporal relevance via `window`
   property `:36-65` (ACTIVE/STARTING_SOON/TODAY/UPCOMING/PAST/FUTURE; starting-soon ≤60 min `:18`,
   upcoming ≤48 h `:19`; live <3 h past start still ACTIVE `:52-54`).
2. `sports_view_model.py` (84 KB) builds the page view model
   (`build_sports_view_model`/`build_sports_page_view`, used `views.py:63`, `tasks.py:97`).
- Streaks: `streaks.py` `compute_streak()` `:16`, `compute_streaks_for_teams()` `:66`.
- Canonical structured interface for downstream consumers: the `_contract` overlay in
  `state_builder.py` `build_sports_state()` `:5099` → `_build_sports_contract()` `:5160`; cache-first
  `:5124-5130`, bounded DB fallback `_build_sports_state_from_db()` `:5402`.

### Signal Outputs (CRITICAL)
**(a) Domain signal dicts** — `services/signal_generator.py` is the ONLY place sports signals are
created (`:18-19`). `generate_sports_signals(user)` `:50`. 7 signal types (constants `:33-39`):
`game_live` (emit `:119`), `game_starting_soon` (`:129`), `game_today` (`:134,139`), `game_upcoming`
(`:145`), `game_final` (`:178`), `win_streak` (threshold 3 `:47`, `:214-226`), `losing_streak`
(`:214-226`). Signal shape `_make_signal` `:231-241`. Strict gate: returns `[]` if `sports_enabled`
false or no active follows `:60-69`. Legacy aliases `game_completed/team_win/team_loss` `:42-44`,
consumed in `tasks.py:237-250`.
**(b) Django model signals** — `apps/sports/signals.py` (wired `apps.py:14-15`):
`invalidate_game_cache` (post_save GameEvent) `:17`, `invalidate_follow_cache` (post_save
UserTeamFollow) `:27` — pure cache invalidation, fail-safe.

### Routine Interpretation — DOC CLAIM NOT IMPLEMENTED
Registry §374: *"Sports signals modify expected behavior — late games shift evening routines,
game-day weekends affect workout/meal timing."* **No such code path exists.** Repo-wide search found
Sports consumed in exactly two AI-context-only places, neither of which alters routine/schedule/calendar:
1. CoS context — `apps/core/ai_orchestrator/cos_context.py:2818` `_build_sports_context()`
   (registered `:3202`), awareness-only behind a hard relevance gate (`:2862-2869`).
2. AI state — `state_builder.py:5099` `build_sports_state()` (registered `:5603`).
The CoS prompt lists sports as informational awareness only (`apps/core/cos/prompt_builder.py:146`).
The only "game-day" references elsewhere are `active_signals` additions `game_live`/`game_today`
(`state_builder.py:5479,5485`) and user-pref help text "game-day signals"
(`apps/users/models.py:368`). **Conclusion:** Sports feeds composed awareness state the CoS narrates
over; it does NOT modify routine interpretation. The "shift evening routines / game-day weekends"
behavior is planned in the registry but not implemented in code.

### Major Services (`apps/sports/services/`)
- `time_windows.py:22` — temporal classification. `streaks.py:16,66` — W/L streaks from finals.
- `signal_generator.py:50` — the 7 domain signals. `sports_view_model.py` (84 KB) — page view model.
- `cache_manager.py` — all cache read/write (keys `:14-19`, TTLs `:21-27`,
  `warm_view_model_for_user` lock-guarded `:71`, `set/get_sync_health` `:166/171`).
- `provider_adapter.py` — abstract `BaseSportsProvider` `:73`, normalized DTOs `:18/31/60`,
  `get_provider()` factory by `SPORTS_PROVIDER` `:131-157`, `FixtureSportsProvider` `:95`.
- `sync_service.py` — `sync_sports_data()` `:34`; team linking `_link_teams` `:158`; `_sync_games`
  upsert `:332`; minimal-write diff `_update_game_if_changed` `:420`; idempotent, skips fixture `:75-79`.
- `providers/espn_provider.py` (`EspnSportsProvider`) and `providers/api_sports_provider.py`
  (`ApiSportsProvider`).

### APIs (`apps/sports/urls.py`, `app_name="sports"`; mounted `config/urls.py:142`)
- `""` → `SportsHubView` `urls.py:9` → `views.py:32` (cache-first My Teams)
- `teams/` → `TeamSelectView` `urls.py:10` → `views.py:77`
- `teams/follow/` → `FollowTeamView` (POST) `urls.py:11` → `views.py:101`
- `teams/unfollow/<pk>/` → `UnfollowTeamView` (POST) `urls.py:12` → `views.py:123`
All gated by `SportsEnabledMixin` `views.py:22-29`.

### UI Surfaces
`apps/sports/templates/sports/`: `my_teams.html`, `team_select.html`, `_game_card.html`.

### Observability (`apps/sports/tasks.py`)
- `compute_sports_signals()` `:40` — background; generates signals + populates all 4 caches; bootstrap
  sync if 0 GameEvents `:53-58`; per-user try/except `logger.error(exc_info=True)` `:104-110`; writes
  sync-health telemetry `set_sync_health()` `:115-121`.
- `sync_games_from_provider` `@shared_task` `:277` (retries=2). `_build_summaries_from_signals()`
  `:130`. Sync-health also written `sync_service.py:133-142`, read via `cache_manager.get_sync_health()`
  `:171`.

---

## 4. BRAIN TRAINING (`apps/brain_training`)

### Purpose
Premium cognitive-fitness module, 5 puzzle games (`apps.py:1-18`): Sudoku, KenKen/Calcudoku,
Nonogram/Picross, Word Ladder, Memory Matrix. Model layer (`models.py:1-10`): game catalog, puzzle
instances with encrypted solutions, per-attempt sessions, aggregated stats. Subscription-gated
(`views.py:32` `check_subscription`). Registry §217 confirms cognitive-fitness framing.

### Primary Models (`apps/brain_training/models.py`)
- **`Game(TimeStampedModel)`** `:22` — catalog. `slug` `:43`, `category` (LOGIC/MATH/VISUAL/LANGUAGE/
  MEMORY `:29-41`, field `:56`), `difficulty_levels` JSON `:79`, `is_active` `:90`.
- **`Challenge(TimeStampedModel)`** `:108` — puzzle instance. `challenge_id` `:135`, `difficulty`
  (EASY/MEDIUM/HARD/EXPERT `:121-126`, field `:143`), `puzzle_data` (client) `:151`, `solution_hash`
  SHA-256 `:157`, `solution_data` (server-only) `:161`, metrics `:166-177`. `verify_solution` (HMAC
  constant-time) `:209`, `update_metrics` `:219`.
- **`GameSession(TimeStampedModel)`** `:234` — core engagement/analytics row. **`status`**
  (IN_PROGRESS/COMPLETED/ABANDONED/TIMEOUT `:242-252`, field `:281`); **`score`** (0–100) `:297`;
  `started_at`/`completed_at`/`time_spent_seconds` `:266-278`; `mistakes` `:287`; `hints_used` `:291`;
  `current_state` (resume) `:303`; `platform` `:310`. Score via `_calculate_score()` `:365-398`;
  `complete()` `:339`.
- **`DailyStats(TimeStampedModel)`** `:401` — per user/game/day; `unique_together` `:450`;
  `record_session()` `:493`.
- **`UserGameStats(TimeStampedModel)`** `:526` — lifetime per user/game; streaks
  `current/longest_streak`, `last_played_date` `:558-570`; `update_streak()` `:606`.
- **`UserOverallStats(TimeStampedModel)`** `:628` — OneToOne per user; streaks `:647-658`;
  `favorite_game` `:661`; `update_streak()` `:681`.
- **`ChallengeQueue(models.Model)`** `:699` — pre-fetched per-user/game queue; `get_next`/`queue_size`/
  `add_to_queue` `:743-782`.

### Canonical State
- Per-session score: `GameSession._calculate_score()` `:365` (base 100 + time bonus − mistake/hint
  penalties × difficulty multiplier easy 1.0…expert 2.0).
- Streaks (day-based): `UserGameStats.update_streak()` `:606`, `UserOverallStats.update_streak()` `:681`.
- Improvement/trend: `services/stats.py` — `get_improvement_stats()` `:15` (recent 14-day vs prior
  14-day; trend threshold ±5% `:96-101`); `get_daily_trend()` `:116`; `get_difficulty_distribution()`
  `:148`.

### Signal Outputs — DOES NOT EMIT signals/PIE/PRIE/Insight
No signal dispatch / PIE / PRIE emission anywhere in `apps/brain_training`. The only references are
declarative registry metadata: `capabilities.py:11-12` `proactive_signals=['training_streak_break']`,
`expected_signal_types=['cognitive_fitness']` (descriptors, not live emitters). AI integration is
PULL-based via `api_ai_summary` `views.py:463` (route `urls.py:36`).
**Drift:** `capabilities.py:9` declares non-existent `primary_models=['TrainingSession','TrainingScore']`
(actual: `GameSession`, etc.). The declared `_build_brain_training_context` lives in core, not this app:
`apps/core/ai_orchestrator/cos_context.py:2387` (registered `:3194`).

### Major Services (`apps/brain_training/services/`) — puzzle generators
- `generator.py:1-4,16-25` — factory mapping slug → generator/verifier (`GENERATORS`/`VERIFIERS`).
- `sudoku.py` (9×9, difficulty = revealed cells `:23`), `kenken.py` (math cages `:23`),
  `nonogram.py` (row/col clues, unique-solution verify `:23`), `word_ladder.py` (BFS path `:18`),
  `memory_matrix.py` (highlight→recall `:20`). `stats.py` — analytics (see Canonical State).

### APIs (`apps/brain_training/urls.py`, `app_name='brain_training'`)
- `''` → `hub` `urls.py:22` → `views.py:42`; `<slug>/play/` → `play` `urls.py:25` → `views.py:86`
- `api/<slug>/batch/` → `api_batch` `urls.py:28` → `views.py:116`
- `api/session/start/` `urls.py:29` → `views.py:193`; `api/session/complete/` `urls.py:30` →
  `views.py:242`; `api/session/<id>/update/` `urls.py:31` → `views.py:326`; `pause/` `urls.py:32` →
  `views.py:587`; `resume/` `urls.py:33` → `views.py:553`; `sessions/in-progress/` `urls.py:34` →
  `views.py:520`
- `api/stats/overview/` `urls.py:35` → `views.py:363`; `api/stats/ai-summary/` `urls.py:36` →
  `views.py:463`; `api/stats/<slug>/` `urls.py:37` → `views.py:411`; `stats/` → `stats_dashboard`
  `urls.py:40` → `views.py:628`

### UI Surfaces
`templates/brain_training/`: `hub.html`, `stats.html`, `games/{base_game,sudoku,kenken,nonogram,
word_ladder,memory_matrix}.html`. Help context `HEALTH_COGNITIVE_HUB` (`views.py:48,57`).

### Observability
**None.** Grep for `logger`/`logging.` across `apps/brain_training` (excl. tests) returned zero hits.
No `logging.getLogger` configured in views/models/services.

---

## 5. OWNER FINANCE (`apps/owner_finance`)

### Purpose
**Owner Financial Command Center** (`apps.py:7` verbose_name) — the app-owner's business cost /
LLM-spend telemetry + margin dashboard: third-party vendor costs, per-call LLM usage, subscription
revenue snapshots, daily cost rollups, budget guardrails, what-if simulation. Gated by `OwnerOnlyMixin`
(`views.py:13`, `mixins.py`). Registry §378-380 confirms: "Internal cost telemetry and operational
dashboards for the operator. Distinct from user-facing FINANCE." **NOT real-estate owner-financing.**
(Note: distinct app from `apps/finance`, the user-facing Plaid-backed personal finance module.)

### Primary Models (`apps/owner_finance/models.py`)
- **`ThirdPartyVendor`** `:7` — `name` `:23`, `category` (LLM/TTS/SMS/EMAIL/NUTRITION_API/HOSTING/
  ANALYTICS/FINANCE_API/HEALTH_API/OTHER `:10-21`, field `:24`).
- **`VendorBillingRecord`** `:37` — `vendor` FK `:45`, `period_start/end` `:49-50`, `cost_usd` `:51`,
  `cost_type` FIXED/VARIABLE `:40-43,52`.
- **`LLMPriceBook`** `:65` — per-model pricing by effective date (never hardcode). `vendor` `:68`,
  `model_name` `:72`, `effective_start/end` `:73-74`, `input/output_cost_per_1m_tokens_usd` `:75-76`,
  `is_active` `:77`; unique `(vendor, model_name, effective_start)` `:81`.
- **`LLMUsageEvent`** `:93` — **core telemetry ledger, one row per LLM call.** `user` (SET_NULL `:113`),
  `request_id` `:118`, `feature` (INTENT/MAIN_RESPONSE/TRANSCRIPTION/SUMMARIZATION/NUTRITION_AI/VISION/
  SCAN/HEALTHCARE_LOOKUP/JOURNAL_REFLECTION/DAILY_INSIGHT/WEEKLY_SUMMARY/COS_CHAT/EXEC_BRIEFING/OTHER
  `:96-111,119`), `engine` `:120`, `model_name` `:121`, `input/output_tokens` `:122-123`, `cost_usd`
  `:124`, `escalated` `:125`; indexes `:131-135`.
- **`UserSubscriptionSnapshot`** `:145` — tier snapshot for margin calc; `tier`
  (FREE/FAITH_ONLY/STUDENT/ADULT/FOUNDING/OWNER `:148-155,161`), `monthly_price_usd` `:162`.
- **`DailyCostRollup`** `:177` — pre-aggregated daily summary (honors "never compute on request path");
  unique `(date, user, feature)` `:192`.
- **`BudgetGuardrail`** `:202` — `scope` (TOTAL/PER_USER/PER_FEATURE `:205-209,216`), `budget_usd`
  `:221`, `period` DAILY/MONTHLY `:210-213,222`, `alert_threshold_pct` (default 80) `:223`.

### Canonical State
- Live cost state = `LLMUsageEvent` ledger `:93`, written best-effort by `telemetry.log_llm_usage`
  `telemetry.py:25`; cost computed at write time from current `LLMPriceBook` (date-bounded lookup
  `:52-64`, fallback `:67-73`, math `:75-86`); savepoint-wrapped, never raises `:95,109-110`.
- Aggregated state = `DailyCostRollup` `:177` + live aggregation in `OverviewView` `views.py:38`.
- Projected state = `simulator.simulate_scenario` `simulator.py:30` → `SimulationResult` dataclass
  `:10` (monthly LLM/non-LLM/total cost, revenue, gross margin %, per-user cost/revenue, break-even).

### Major Services (`apps/owner_finance/services/`)
- `simulator.py` — `simulate_scenario(...)` `:30`: monthly LLM cost from `LLMPriceBook` per model mix
  `:59-78`, escalation overhead `:81`, non-LLM cost from recent `VendorBillingRecord` `:85-93`, revenue
  from tier mix `:98-102`, margin/break-even `:104-113`. `DEFAULT_AVG_TOKENS` `:24`.
- `telemetry.py` — `log_llm_usage(...)` `:25`: single ingestion point writing `LLMUsageEvent` with
  auto-computed cost; active-pricing Q filter `:113`. **Best-effort by design** (swallows at `:109`,
  logs at debug). Callers: `apps/capture/services/summarization.py`, `apps/health/views.py`,
  `apps/health/services/ai_nutrition.py`, `apps/life/services/recipe_photo_import.py`, all 5 scan
  services, `apps/ai/services.py`.

### APIs (`apps/owner_finance/urls.py`, `app_name='owner_finance'`, all `OwnerOnlyMixin`-gated `views.py:13`)
- `''` → `OverviewView` `urls.py:9` → `views.py:29`; `users/` → `UserCostsView` `urls.py:10`;
  `features/` → `FeatureBreakdownView` `urls.py:11`; `vendors/` → `VendorLedgerView` `urls.py:12`
- `api/daily-chart/` → `DailyChartDataView` `urls.py:15`; `audit/` → `AuditLedgerView` `urls.py:16`;
  `export/` → `ExportCSVView` `urls.py:17`; `users/<int:user_id>/` → `PowerUserView` `urls.py:18`
- `simulator/` → `SimulatorView` `urls.py:21`; `budgets/` → `BudgetGuardrailsView` `urls.py:24`

### UI Surfaces
`apps/owner_finance/templates/owner_finance/`: `overview.html`, `users.html`, `features.html`,
`vendors.html`, `audit.html`, `power_user.html`, `simulator.html`, `budgets.html`.

### Observability
`telemetry.py` IS the app's observability ingestion layer (the LLM-spend ledger). Its own internal
logging is `logger.debug` only (`telemetry.py:89,110`) — per the project's own AI Engineering Rules
`logger.debug()` is invisible in production, so missing-pricebook and write-failure events are silent
in prod (by-design "best-effort, never raise", but an observability gap).

---

## 6. SCAN (`apps/scan`) — document / receipt / product scanning

### Purpose
Camera/image scanning: capture/upload image → OpenAI Vision → classify → route user to the right WLJ
module with pre-filled data. Privacy-first: raw images never stored, only metadata (`models.py:1-6`).
`views.py` implements scan flow + barcode/product/medicine lookups. Registry §451 lists scan as a
support app that "feeds Capture" — see Doc vs Code below.

### Doc vs Code (`docs/wlj_camera_scan_architecture.md`)
- Doc capture→`/scan/analyze/`→Vision→OpenAI→ScanLog, image discarded: **VERIFIED**
  (`ScanAnalyzeView.post` `views.py:221`, ScanLog created `views.py:290`, route `urls.py:17`,
  `services/vision.py`).
- Doc consent gate via `ai_data_consent=True` in preferences (`:139`): **PARTIAL/DRIFT** — code uses a
  dedicated `ScanConsent` model `models.py:187` checked via `.exists()` (e.g. `signals.py:39`).
- Doc file-structure section (`:287-312`): **OUTDATED** — claims a single `vision.py` service and one
  `ScanLog` model; actual `services/` has 6 files and `models.py` has 3 models.
- Doc decision-mapping table (`:230-239`): **VERIFIED & EXPANDED** — `vision.py` routes to more modules
  than documented (Life.* destinations absent from doc — see Relationships).
- `ImageAnalysis` model + comprehensive-vision flow: **NOT mentioned in the doc at all** (doc last
  updated 2025-12-30, predates that pipeline).
- Registry §451 "scan feeds Capture": **NOT FOUND in code** — scan feeds Health/Life/Journal/CoS, with
  no integration into the `capture` app (pantry/recipe "scan" templates live under `meals`/`life`, not
  `capture`).

### Primary Models (`apps/scan/models.py`)
- **`ScanLog(TimeStampedModel)`** `:18` — scan request metadata (no raw image). **`status`**
  (PENDING/SUCCESS/FAILED/TIMEOUT/RATE_LIMITED `:26-38,77`); **`category`** (FOOD/MEDICINE/SUPPLEMENT/
  RECEIPT/DOCUMENT/WORKOUT/BARCODE/UNKNOWN `:41-59,85`); `request_id` `:62`, `confidence` `:92`,
  `items_json` `:98`, `action_taken` `:104`, debug metadata `:111-133`. Lifecycle `mark_success/
  mark_failed/mark_timeout/record_action` `:150-184`.
- **`ScanConsent(TimeStampedModel)`** `:187` — OneToOne consent for AI image processing `:195`,
  `consented_at` `:202`, `consent_version` `:207`.
- **`ImageAnalysis(TimeStampedModel)`** `:221` — comprehensive AI analysis of any image, feeds CoS.
  UUID PK `:251`; **`source_type`** (chat/scan/inventory/pet/recipe/project/document/note/medical
  `:232-242,260`) + GenericForeignKey `source_object` `:261-265`; **`status`**
  (pending/analyzing/completed/failed `:244-249,267`); dedup `image_hash` `:272`; results
  `summary/detailed_description/category/confidence/objects_identified/text_detected/context_clues/
  relevance_tags/actionable_insights/raw_response` `:278-291`; denormalized `search_text` `:300`.

### Canonical State
- ScanLog: created PENDING `views.py:290`; rate-limit path `views.py:249`; resolved via `mark_*`
  `models.py:150-179`; user choice via `record_action` / `ScanRecordActionView.post` `views.py:399`.
- ImageAnalysis: pending→analyzing→completed/failed; populated by
  `comprehensive_vision_service.analyze()` `comprehensive_vision.py:68` (record `:112`), dedup against
  completed analyses `:90` (also `signals.py:51`).

### Signal Outputs (`apps/scan/signals.py`) — INBOUND consumer, not PIE/PRIE emitter
Scan consumes `post_save` from other domains to auto-run vision analysis (wired `apps.py:13-14`).
Common handler `_trigger_analysis()` `signals.py:16` gates on analyzable image + `ScanConsent` `:39` +
dedup hash `:51`, then `comprehensive_vision_service.analyze()` `:54-61`. Receivers:
`life.InventoryPhoto`→inventory `:67`, `life.Pet`→pet `:75`, `life.Recipe`→recipe `:82`,
`life.Document`→document `:89`, `notes.NoteImage`→note `:97`. Output: `ImageAnalysis` rows whose
`search_text`/`relevance_tags` feed CoS context (`comprehensive_vision.py:5-8`). No PIE/PRIE/Insight.

### Major Services (`apps/scan/services/`)
- `vision.py:1-11` — core OpenAI Vision; classifies image, builds `NextBestAction` module routes
  (`vision.py:273` `module`).
- `comprehensive_vision.py:1-9` — deep image analysis → persists `ImageAnalysis` for CoS.
- `barcode.py` — food barcode nutrition (local DB → Open Food Facts → OpenAI).
- `medicine_lookup.py` — RxNav (NIH) / FDA OpenData / OpenAI fallback.
- `product_lookup.py` — general product (UPC Item DB + OpenAI). `image_utils.py` — normalize/hash
  (`file_is_analyzable_image`, `image_field_to_base64`, `compute_image_hash`; used `signals.py:31,44,50`).

### APIs (`apps/scan/urls.py`, `app_name='scan'`)
- `''` → `ScanHomeView` `urls.py:11` → `views.py:151`; `consent/` → `ScanConsentView` `urls.py:14` →
  `views.py:187`; `analyze/` → `ScanAnalyzeView` `urls.py:17` → `views.py:213`
- `barcode/` → `BarcodeLookupView` `urls.py:18` → `views.py:452`; `barcode/product/` →
  `ProductLookupView` `urls.py:19` → `views.py:641`; `barcode/intake/` → `IntakeLookupView`
  `urls.py:20` → `views.py:757`
- `action/<uuid:request_id>/` → `ScanRecordActionView` `urls.py:21` → `views.py:392`; `history/` →
  `ScanHistoryView` `urls.py:24` → `views.py:420`

### UI Surfaces
`templates/scan/scan_page.html`, `templates/scan/history.html`. Embedded elsewhere:
`templates/life/recipe_scan.html`, `templates/meals/pantry_scan_confirm.html`,
`templates/meals/pantry_scan_sessions.html`.

### Relationships (domains scan feeds)
- **Health** — Nutrition/FoodLog `vision.py:631`, Intake/Medicine via `IntakeLookupView` +
  `medicine_lookup_service` `views.py:765`, Fitness `vision.py:815`.
- **Life** — Documents `vision.py:779`, Inventory `:860`, Recipes `:900`, Pets `:939`, Maintenance `:979`.
- **Journal** — receipts/documents prefill `vision.py:752,759,796`.
- **CoS / AI context** — via `ImageAnalysis.search_text`/`relevance_tags` `comprehensive_vision.py:5-8`.
- **Owner Finance telemetry** — every Vision/lookup service logs LLM spend via `log_llm_usage`.
- **No `capture` integration found** (contradicts Registry §451).

### Observability
Logging in `views.py` (3 calls) and `services/vision.py` (10 calls); `signals.py:13,63` warns on
auto-analysis failure. Privacy contract: no raw image data in logs (`models.py:135`).

---

## 7. TRAVEL (Future Domain) — PLANNED, NO APP / NO MODELS

Registry §398-422 describes a future Travel domain (raw data: Trips/Locations/Flights/Hotels/Travel
dates; example signals `travel_active`, `routine_disruption`, `timezone_shift`, `conference_mode`,
`vacation_mode`; example: `travel_active + workout_gap → expected behavior change`).

**Code status — confirmed:**
- **No `apps/travel` app** (`ls apps/ | grep -i travel` → none).
- **No Travel model** (no `class *Travel*(Model)` in any `models.py`).
- Travel exists ONLY as an **insight detection rule**, not a domain app:
  - `TravelActiveRule(BaseInsightRule)` — `apps/core/ai_insights/rules_context.py:503`,
    `rule_name="travel_active"` `:506`, `module="life"` `:507`, `insight_type="travel_active"` `:508`.
    Detects travel from journal keywords (`_TRAVEL_KEYWORDS_JOURNAL` `:44`), calendar strong keywords
    (`_TRAVEL_KEYWORDS_CALENDAR_STRONG` `:45`, applied `:543`), and sleep logs. Cooldown 48 h
    (`'travel_active': 48` in cooldown map `:58`).
  - Registered behavioral rule: `'travel_active'` in `apps/core/ai_insights/rules_behavior.py:232`.
- The domain registry's descriptor enum hints at Travel as future CONTEXT enrichment, with no concrete
  domain: `apps/core/domain_registry/descriptors.py:26` — `CONTEXT = 'context'  # Contextual
  enrichment (Travel, future)`.
- The only other "travel" code is unrelated: a health location enum value
  `LOCATION_TRAVEL = 'travel'` `apps/health/models.py:3321,3327`.

**Conclusion:** TRAVEL is a **planned future domain**. The single piece of working travel logic is the
`travel_active` insight rule (derived from journal/calendar/sleep), which lives under
`apps/core/ai_insights`, attributed to the `life` module — there is no Travel data model, app, signal
producer, or UI. The richer signals listed in the registry (`timezone_shift`, `conference_mode`,
`vacation_mode`, `routine_disruption`) are **not implemented**.

---

## Cross-Cutting Doc-vs-Code Divergences (summary)
1. **Notes attachments** — Registry §257 lists "people" and "captures" as attachable; code's
   `ATTACHABLE_MODELS` (`apps/notes/utils.py:15-23`) includes neither.
2. **Notes rename registry gap** — `calendar_engine.CalendarEvent` + `faith.BibleStudyNote` are
   attachable but absent from `NOTE_INDEX_REGISTRY` (`index_registry.py:15-31`); their renames don't
   reindex notes.
3. **Sports routine modification** — Registry §374 ("late games shift evening routines, game-day
   weekends affect workout/meal timing") is NOT implemented; Sports is awareness-only context.
4. **Brain Training capabilities** — `capabilities.py:9` names non-existent models
   `TrainingSession`/`TrainingScore`; no logging; no signal emission.
5. **Scan doc outdated** — `docs/wlj_camera_scan_architecture.md` omits `ScanConsent`/`ImageAnalysis`,
   the comprehensive-vision pipeline, inbound `post_save` handlers, and Life.* routes.
6. **Scan "feeds Capture"** — Registry §451 claim NOT found in code (scan feeds Health/Life/Journal/CoS).
7. **Owner Finance** — internal LLM-spend telemetry, NOT real-estate owner-financing; distinct from
   user-facing `apps/finance`.
8. **Travel** — planned only; sole working logic is the `travel_active` insight rule under
   `apps/core/ai_insights`.
