# WLJ Integrations & Personalization Inventory

> READ-ONLY knowledge extraction. Every claim is grounded with `path:line`. No code was modified.

---

## Integration Inventory

### Summary Table

| Integration | Direction | Config (`config/settings.py`) | Canonical Storage | Sync Approach |
|---|---|---|---|---|
| Apple Health / HealthKit | Inbound | — (Bearer-token mobile API) | Per-metric health models (`StepsEntry`, `WeightEntry`, `SleepEntry`, `GlucoseEntry`, `WorkoutSession`, etc.) + `HealthIngestionRun` audit | iOS app POSTs batches; server upserts by `sync_id` |
| Dexcom / CGM glucose | Inbound (OAuth) — **deprecated, now via HealthKit** | `settings.py:1031-1038` | `GlucoseEntry` (`apps/health/models.py:1054`), `DexcomCredential` (`apps/health/models.py:3996`) | OAuth + manual/triggered sync; tokens encrypted at rest |
| Google Calendar | Inbound/Outbound (OAuth) | `settings.py:919-927` | `GoogleCalendarCredential` (`apps/life/models.py:1507`) | OAuth; `auto_sync_enabled` flag; encrypted tokens |
| Gmail (life integration) | Inbound (OAuth) | `GMAIL_CLIENT_ID/SECRET/REDIRECT_URI` (read via `getattr`) | OAuth credential dict (encrypted) | `apps/life/services/gmail.py:34` |
| Email — transactional (outbound) | Outbound (SMTP) | `settings.py:680-693` | Django mail backend | SMTP `mail.privateemail.com:587` TLS |
| Email — "Automate" intake (inbound) | Inbound (IMAP) | `settings.py:1380-1383` | `AdminTask` | IMAP poll of `INBOX/Automate` 3×/day → AdminTask → move to `INBOX/New Requests` |
| SMS (Twilio) | Inbound + Outbound | `settings.py:1001-1007` | `SMSNotification`, `SMSResponse` (`apps/sms/models.py`) | Outbound via Twilio REST; inbound webhook; nightly batch + signal-driven |
| Phone verification (Twilio Verify) | Outbound | `TWILIO_VERIFY_SERVICE_SID` (`settings.py:1004`) | `UserPreferences.phone_verified` (`apps/users/models.py:853`) | Twilio Verify v2 service |
| Push notifications (APNs) | Outbound | `settings.py:1018-1022` | `MobileDevice.push_token` (`apps/mobile/models.py:93`) | APNs via `apns_sender.py`; token registered through mobile API |
| Stripe / billing | Outbound + webhook | `settings.py:1314-1330` | `BillingProfile` (`apps/billing/models.py:277`), `PaymentAuditLog` | Checkout sessions + webhook event handlers |
| Authentication (django-allauth) | — | `settings.py:626-660` | `User` (`apps/users/models.py:82`) | Email-only login, mandatory verification, custom adapter |
| MFA (email code + WebAuthn) | — | enforced via middleware | `MFAEmailCode` (`apps/users/models.py:1402`), `WebAuthnCredential` (`apps/users/models.py:1347`) | Email 6-digit code or Face/Touch ID |
| OpenAI API | Outbound | `settings.py:79-88` | n/a (LLM calls) | Shared client in `apps/ai/services.py:88` |
| OpenAI Vision | Outbound | `OPENAI_VISION_MODEL` (`settings.py:81`) | scan/nutrition/recipe results | Per-feature service clients |
| reCAPTCHA v3 | Outbound | `settings.py:1280-1285` | signup audit (`SignupAttempt`) | Token verify on signup |
| Sentry | Outbound | `settings.py:1305,1386` | external | Error + performance telemetry (prod only) |
| Open-Meteo (weather/geocode) | Outbound | — | n/a | `apps/ai/web_search_service.py:287,321` |

---

### Detail

#### Apple Health / HealthKit (`apps/mobile`)
- iOS WKWebView wrapper at `ios/WLJWrapper/`; HealthKit queried by `HealthKitManager.swift` (per `docs/CLAUDE_IOS.md:13`).
- **Auth:** Bearer token, not session — added by `MobileAuthenticationMiddleware` (`docs/CLAUDE_IOS.md:39`). Token exchange flow: web session → one-time code → API token.
  - `MobileTokenExchangeCode` one-time codes, 5-min expiry, single use (`apps/mobile/models.py:250`, `create_code` at `:303`, `consume` at `:311`).
  - `MobileAPIToken` stores **SHA-256 hash + 8-char prefix only**, raw token returned once; 90-day default expiry (`apps/mobile/models.py:122`, `create_token` at `:188`, `validate_token` at `:210`).
  - `MobileDevice` — one per device, keyed `(user, device_id)`; per-device revocation via `is_active` (`apps/mobile/models.py:38`).
- **Endpoints** (`docs/CLAUDE_IOS.md:26-34`): `POST /api/mobile/generate-code/`, `POST /api/mobile/token/exchange/`, `POST /api/mobile/health/ingest/`, `GET /api/mobile/health/sync-status/`, `POST /api/mobile/push/register/`, `POST /api/mobile/push/unregister/`.
- **Inbound data — 23 HealthKit types** (`docs/CLAUDE_IOS.md:42-51`) routed to canonical models: Steps/calories/distance/flights/exercise/stand → `StepsEntry`; Weight/BodyFat/LeanMass → `WeightEntry`; Sleep/HR/RespRate/HRV/VO2/Caffeine/Mindful → `SleepEntry`; Blood Glucose → `GlucoseEntry`/`BloodGlucoseReading`; Water → `WaterEntry`; Workouts → `WorkoutSession`; BP → `BloodPressureEntry`; Temp → `BodyTemperatureEntry`.
- **Audit / sync log:** every ingestion logged in `HealthIngestionRun` with counts (received/created/updated/skipped), status, payload size, validation errors (`apps/mobile/models.py:327`). Dedup is by `sync_id` (HealthKit UUID) on the target models.

#### Dexcom / CGM glucose (`apps/health`)
- **Config:** `DEXCOM_CLIENT_ID/SECRET/REDIRECT_URI/USE_SANDBOX` at `config/settings.py:1031-1038`. Settings comment (`~:1029`) marks **direct integration deprecated — glucose now arrives via HealthKit.**
- **OAuth flow:** `DexcomService` (`apps/health/services/dexcom.py:33`): `get_authorization_url()` (`:64`, CSRF state), `exchange_code_for_credentials()` (`:102`), `refresh_access_token()` (`:163`). Views `DexcomConnectView/CallbackView/SyncView/DisconnectView` (`apps/health/views.py:6487,6519,6603,6644`); URLs at `apps/health/urls.py:169-172`.
- **Token storage:** `DexcomCredential` (one-to-one per user, `apps/health/models.py:3996`) — `access_token`/`refresh_token` encrypted at rest; decrypted via `access_token_decrypted` (`:4067`) / `set_access_token` (`:4105`). Encryption key `OAUTH_TOKEN_ENCRYPTION_KEY` (`settings.py:970`).
- **Canonical storage:** `GlucoseEntry` (`apps/health/models.py:1054`) with `source` choices (manual/dexcom/apple_health/imported, `:1076`), Dexcom fields `dexcom_record_id`, `sync_id`, `trend`, `trend_rate`, `display_device` (`:1130`).
- **Known ~3h write lag is upstream of WLJ** — Dexcom's delayed write into Apple Health; not a WLJ pipeline bug (corroborated by project memory + deprecation note).

#### Calendar & Gmail (`apps/life`)
- **Google Calendar:** OAuth config `GOOGLE_CALENDAR_CLIENT_ID/SECRET/REDIRECT_URI` (`settings.py:919-927`). `GoogleCalendarCredential` (`apps/life/models.py:1507`) stores encrypted `access_token`/`refresh_token`/`client_secret`; fields `selected_calendar_id` (`:1543`), `auto_sync_enabled` (`:1580`); helpers `set_access_token`/`set_refresh_token` (`:1664-1672`), `as_credentials_dict` (`:1682`). Callback URL `/life/calendar/google/callback/`.
- **Gmail:** `GmailService` (`apps/life/services/gmail.py:34`) — reads `GMAIL_CLIENT_ID/SECRET/REDIRECT_URI` via `getattr` (`:51-53`); OAuth `get_authorization_url()` (`:69`), `exchange_code_for_credentials()` (`:102`); scoped credentials stored as encrypted dict.

#### Email — outbound + inbound "Automate" intake
- **Outbound (transactional):** SMTP backend `mail.privateemail.com:587` TLS in prod, console backend in DEBUG (`settings.py:680-693`). Billing emails via `apps/billing/email_service.py:20` (`send_billing_email`).
- **Inbound "Automate" intake:** IMAP poll of `INBOX/Automate` (`apps/admin_console/email_intake.py:11-20`), config `EMAIL_INTAKE_HOST/PORT/USER/PASSWORD` (`settings.py:1380-1383`, default `mail.privateemail.com:993`). Driven by management command `apps/admin_console/management/commands/process_email_tasks.py`, **runs 3×/day**. Each email → `AdminTask` → email moved to `INBOX/New Requests` → confirmation email sent.

#### SMS — Twilio (`apps/sms`)
- **Config:** `TWILIO_ACCOUNT_SID/AUTH_TOKEN/PHONE_NUMBER/VERIFY_SERVICE_SID/TEST_MODE` (`settings.py:1001-1007`).
- **Outbound:** `TwilioService` (`apps/sms/services.py:50`); `send_sms()` calls `client.messages.create(...)` (`apps/sms/services.py:182`). Test mode logs instead of sending.
- **Phone verification:** Twilio Verify v2 — `send_verification()` (`apps/sms/services.py:247`), `check_verification()` (`:299`); result lands on `UserPreferences.phone_verified` (`apps/users/models.py:853`).
- **Inbound:** `TwilioIncomingWebhookView` (`apps/sms/views.py:200`) validates HMAC-SHA1 signature (`apps/sms/services.py:322`), parses replies (`D`=done, `R[min]`=remind, `N`=skip) via `SMSResponse.parse_reply()` (`apps/sms/models.py:354`).
- **Canonical storage:** `SMSNotification` (`apps/sms/models.py:35`, includes `twilio_sid`, status lifecycle) and `SMSResponse` (`:232`).
- **Sync/scheduling:** nightly batch `SMSScheduler.schedule_for_all_users()` (`apps/sms/scheduler.py:106`) **plus** real-time post-save signals (`apps/sms/signals.py:231-272`). Quiet-hours enforcement at `apps/sms/services.py:545`.

#### Push notifications — APNs (`apps/core/ai_delivery/apns_sender.py`)
- **Config:** `APNS_TEAM_ID/KEY_ID/AUTH_KEY/BUNDLE_ID/USE_SANDBOX` (`settings.py:1018-1022`).
- **Registration:** token stored on `MobileDevice.push_token` + `push_enabled` (`apps/mobile/models.py:93-101`), registered via `POST /api/mobile/push/register/`.
- **Delivery:** `send_push_notification(push_token, title, body, ...)` (`apps/core/ai_delivery/apns_sender.py:69`) builds JWT from `.p8` key.
- **Operational note (project memory):** proactive PUSH does not reach the owner because no `MobileDevice` is registered for him; in-app delivery works. Not a code defect.

#### Stripe / billing (`apps/billing`)
- **Config:** `STRIPE_PUBLIC_KEY/SECRET_KEY/WEBHOOK_SECRET`, dj-stripe settings, and 5 price IDs (`settings.py:1314-1330`).
- **Subscription/entitlement model:** `BillingProfile` (one-to-one user, `apps/billing/models.py:277`) — `pricing_tier` (free/faith_only/student/adult/founding), `subscription_status`, `billing_cycle`, `stripe_customer_id`, `stripe_subscription_id`, period timestamps, `account_credit`, referral fields. Access gates: `is_subscribed`, `has_access`, `is_founding_member` (`:491-575`). Pricing singleton `BillingConfiguration` (`:42`).
- **Checkout:** `StripeService.create_checkout_session()` (`apps/billing/services.py:105`); customer portal `:187`. Price keys map to env vars at `apps/billing/services.py:57-63`.
- **Webhooks:** endpoint `stripe_webhook()` (`apps/billing/webhooks.py:23`) verifies signature and dispatches `checkout.session.completed`, `invoice.paid`, `invoice.payment_failed`, `customer.subscription.updated`, `customer.subscription.deleted` (`:64-77`).
- **Entitlement granting:** `handle_checkout_completed()` (`apps/billing/services.py:255`) sets tier/cycle/status; founding = lifetime. `handle_subscription_updated()` maps Stripe status → local (`:396`). All actions logged to immutable `PaymentAuditLog` (`apps/billing/models.py:1003`). Lifetime grants without payment via `VIPPromoCode` (`:1108`).

#### Authentication & Security (`django-allauth`, `apps/security`, `apps/users`)
- **allauth config** (`settings.py:626-660`): `AUTHENTICATION_BACKENDS` = ModelBackend + allauth backend (`:626`); `ACCOUNT_ADAPTER = apps.users.adapters.WLJAccountAdapter` (`:651`); `ACCOUNT_LOGIN_METHODS = {"email"}` (`:647`); `ACCOUNT_EMAIL_VERIFICATION = "mandatory"` (`:639`); custom `ACCOUNT_FORMS` (`:654`).
- **Custom adapter** `WLJAccountAdapter` (`apps/users/adapters.py:60`): admin emails bypass email verification via `is_email_verified()` (`:71`); honeypot field (`:99`); reCAPTCHA v3 score logging, fails open (`:224`); signup attempts logged with hashed email/IP + captcha score (`:260`).
- **MFA:** `MFAEmailCode` 6-digit, 10-min, 5/hr rate limit (`apps/users/models.py:1402`); `WebAuthnCredential` Face/Touch ID with `sign_count` replay protection (`:1347`). Enforced by `MFAEnforcementMiddleware` (`apps/users/middleware.py:191`) — required for staff/superusers + `MFA_REQUIRED_EMAILS`; owner exempt; `is_app_review_account` bypass (`apps/users/models.py:113`).
- **Security app** (`apps/security/models.py`): security assessment + audit models — `SecurityRun` (`:195`), `SecurityScore` (`:325`), `SecurityTest` (`:407`), `SecurityFinding` (`:494`), `SecurityAuditLog` (`:758`, logs view/export/run/modify/delete), `AcknowledgedFinding` (`:657`). Sensitive fields encrypted via `EncryptedTextField`/`EncryptedJSONField` (`:113,152`) using `SECURITY_DATA_ENCRYPTION_KEY` (fallback `OAUTH_TOKEN_ENCRYPTION_KEY`).
- **Other guards (`apps/users/models.py`):** `TermsAcceptance` (`:1530`), `IPBlocklist` (`:1557`), `DisposableEmailDomain` (`:1637`).

#### OpenAI API (`apps/ai`, `apps/core/ai_config.py`)
- **Where the API key + model are configured:** `config/settings.py:79-88`
  - `OPENAI_API_KEY = os.environ.get('OPENAI_API_KEY')` — `settings.py:79`
  - `OPENAI_MODEL = ...default 'gpt-4o'` — `settings.py:80`
  - `OPENAI_VISION_MODEL` default `gpt-4o` — `settings.py:81`
  - `OPENAI_MINI_MODEL` default `gpt-4o-mini` — `settings.py:82`
  - `COS_MODEL = os.environ.get('COS_MODEL', 'gpt-4o')` — `settings.py:88` (Chief-of-Staff assistant always uses `gpt-4o` for quality).
- **Client:** shared singleton `OpenAI(api_key=settings.OPENAI_API_KEY)` in `apps/ai/services.py:83-89`; default model bound at `apps/ai/services.py:170` (`self.model = settings.OPENAI_MODEL`).
- **CoS chat** uses `COS_MODEL`: `apps/ai/personal_assistant.py:5129` (non-streaming) and `:5906` (streaming).
- **Threshold config** is DB-backed singleton `AIThresholdConfig` (`apps/core/ai_config.py:39`) — confidence/capacity/budget/fatigue/cache TTLs; access via `get_ai_config()`/`get_threshold()` (`:243,248`). Note: this file holds **engine thresholds, not the API key/model** (those live in `settings.py`).
- **Vision / other OpenAI consumers:** capture transcription/summarization, scan vision, nutrition AI, recipe import, notes embeddings, TTS (`apps/ai/tts_service.py`), web search (`apps/ai/web_search_service.py:214`).

#### Other external APIs
- **reCAPTCHA v3:** `RECAPTCHA_V3_SITE_KEY/SECRET_KEY`, threshold 0.6 (`settings.py:1280-1285`); verified in signup adapter.
- **Sentry:** `SENTRY_DSN`, init at `settings.py:1386` (prod only), 10% trace/profile sampling.
- **Open-Meteo:** weather (`api.open-meteo.com`) + geocoding (`geocoding-api.open-meteo.com`) called from `apps/ai/web_search_service.py:287,321`.

---

## Personalization Architecture

### User model (custom, email-based) — `apps/users/models.py`
- `User(AbstractBaseUser, PermissionsMixin)` (`:82`); `email` is the unique identifier, **no username** (`:89-93`). Custom `UserManager.create_user/create_superuser` (`:54-79`).
- Profile fields: `first_name`/`last_name` (`:94-95`), `avatar` ImageField (`:98`), `date_of_birth` for COPPA age check (`:106`), `is_app_review_account` (`:113`), `is_staff` (`:118`), `date_joined` (`:127`).
- `UserPreferences` is one-to-one, auto-created via signal on user creation (`:23`, class at `:170`).

### UserPreferences — key fields (`apps/users/models.py:170`)
- **Theme / appearance:** `theme` (`:247`), `accent_color` (`:252`), custom theme colors `custom_primary/accent/background/surface/text` (used when `theme='custom'`, `:257+`), `hide_nav_on_scroll`, `desktop_nav_collapsed`.
- **Timezone:** `timezone` IANA field (`:750`) with legacy-name conversion via `timezone_iana` property (`:1203`).
- **AI consent/settings:** `ai_enabled` (`:579`), `ai_data_consent` + `ai_data_consent_date` (`:586,590`), `personal_assistant_enabled` (`:667`), `personal_assistant_consent` + date (`:674,678`), `assistant_confirm_actions` (`:686`).
- **Proactive check-ins:** `assistant_proactive_checkins` (`:710`) + per-domain toggles `assistant_medicine/workout/journal/mood_checkins` (`:714-726`); `ASSERTIVENESS_CHOICES` (`:731`).
- **SMS:** `phone_verified` (+`_at`) (`:853,857`), `sms_enabled` (`:864`), `sms_consent` (+date) (`:868`), per-category toggles `sms_medicine_reminders`/`sms_task_reminders`/`sms_event_reminders`/`sms_prayer_reminders`/`sms_fasting_reminders`/`sms_significant_event_reminders`/`sms_milestone_reminders` (`:879-907`), quiet hours `sms_quiet_hours_enabled`/`sms_quiet_start`/`sms_quiet_end` (`:913-921`), `intelligence_sms_enabled` (`:1058`).

### Notification preferences (`apps/users/models.py`)
- Master toggles: `notifications_enabled` (`:930`), `email_notifications_enabled` (`:934`), `email_notification_frequency` (`:944`).
- **In-app** per-category: `notify_inapp_medicine/task/event/prayer/reading_plan/milestone/significant_event/finance/journal/capture` (`:964-1000`).
- **Email** per-category: `notify_email_medicine/task/event/prayer/reading_plan/milestone/significant_event/...` (`:1006-1030+`).
- **SMS** per-category covered under SMS prefs above.

### Feature flags

**Module flags** (template booleans, injected by `theme_context` in `apps/core/context_processors.py:125`). Anonymous defaults come from `ModuleDefinition` catalog (`:50-79`); authenticated values from `get_user_module_enablement_map(user)` (one batched query, `:184-196`).

| Template flag | Source (`context_processors.py`) | Default (anon) |
|---|---|---|
| `journal_enabled` | `:139` / `:186` | True |
| `faith_enabled` | `:140` / `:187` | False |
| `health_enabled` | `:141` / `:188` | True |
| `life_enabled` | `:142` / `:189` | True |
| `purpose_enabled` | `:143` / `:190` | True |
| `finance_enabled` | `:144` / `:191` | False |
| `relationships_enabled` | `:145` / `:192` | True |
| `capture_enabled` | `:146` / `:193` | True |
| `documents_enabled` | `:147` / `:194` | True |
| `meals_enabled` | `:148` / `:195` | True |
| `sports_enabled` | `:149` / `:196` | False |
| `ai_enabled` | `:198` (from `prefs.ai_enabled`) | False |
| `ai_data_consent` | `:199` | False |
| `personal_assistant_enabled` | `:201` | False |
| `personal_assistant_consent` | `:202` | False |

**Sub-feature flags** (`features.<module>.<key>`, built at `context_processors.py:293-304`; opt-out model — default True). Definitions live on `UserPreferences` class dicts:

| Module key | Dict (`apps/users/models.py`) | Example keys |
|---|---|---|
| `features.health.*` | `HEALTH_FEATURES` (`:427`) | `weight`, `heart_rate`, `blood_pressure`, `glucose`, `intake`, `workouts`, `steps`, `sleep`, `nutrition`, `fasting`, `providers`, `hrv`(off), `vo2_max`(off), `body_temperature`(off) |
| `features.organize.*` | `ORGANIZE_FEATURES` (`:450`) | `tasks`, `calendar`, `projects`, `inventory`, `pets`, `recipes`, `maintenance`, `documents`, `significant_events`, `routines` |
| `features.goals.*` | `GOALS_FEATURES` (`:463`) | `goals`, `habit_goals`, `annual_direction`, `intentions`, `reflections` |
| `features.faith.*` | `FAITH_FEATURES` (`:471`) | `scripture`, `reading_plans`, `study_tools`, `prayers`, `milestones`, `reflections`, `memory_verses`, `devotionals` |
| `features.journal.*` | `JOURNAL_FEATURES` (`:482`) | `prompts`, `mood_tracking`, `tags`, `ai_reflections` |

Resolution logic: `UserPreferences.is_feature_enabled(module, feature)` (`apps/users/models.py:489`) — first checks the **parent module flag** (`:501-510`), then the per-user override dict, falling back to the catalog default; unknown keys default to enabled (`:526-527`).

There is also a small server-side `feature_flags` context (template `{{ feature_flags.NAME }}`) exposing `WLJ_ACTION_CENTER_CHRONOLOGICAL` (`apps/core/context_processors.py:82-94`).

### Assistant / Chief of Staff name configuration
- **Stored field:** `UserPreferences.cos_display_name` — `CharField(max_length=50, default='', blank=True)` (`apps/users/models.py:694`).
- **Resolver:** `UserPreferences.get_cos_name()` returns the trimmed custom name, or `'Chief of Staff'` if blank (`apps/users/models.py:701-703`).
- **Template exposure:** `theme_context` injects `cos_display_name = prefs.get_cos_name()` and `cos_has_custom_name` (`apps/core/context_processors.py:203-204`).
- The name is **fully user-configurable** (examples in help text: "Max", "Jarvis"). "Beth" is one user's personal value of `cos_display_name`, not a hardcoded default. Default in code/UI is "Chief of Staff".

### Other personalization surfaces
- **Module catalog & ordering:** `UserModulePreference` / `ModuleDefinition` drive nav (`apps/core/context_processors.py:468-590`); `initialize_for_user()` idempotently seeds prefs.
- **Calibration & alignment:** CoS calibration state and alignment score injected into context (cached) when `personal_assistant_enabled` (`context_processors.py:210-285`).
- **Favorites / quick links / external links:** `FavoritePage`, `PageView`, `ExternalLink` feed nav personalization (`context_processors.py:337-465`).

---

## Notable Gaps / Caveats
- **Dexcom direct OAuth is deprecated** — `DexcomService`/`DexcomCredential` code remains, but glucose now flows through HealthKit; settings comment (`settings.py:~1029`) is the source of truth. The ~3h staleness is Dexcom→Apple Health write delay, upstream of WLJ.
- **APNs push has no registered owner device** in practice — proactive push silently no-ops for the owner; in-app path works. Infrastructure exists; it's a data/registration gap, not code.
- **`MobileDevice.push_token`** is described in-model as "scaffold for future" (`apps/mobile/models.py:92`), yet `apns_sender.py` consumes it — registration endpoints exist but push enablement is per-device opt-in (`push_enabled` default False).
- **OpenAI key vs threshold config split:** `apps/core/ai_config.py` holds *thresholds only* (DB-backed singleton). The API key and model names live in `config/settings.py:79-88` — do not look for them in `ai_config.py`.
- **Two outbound email lanes share one mailbox host** (`mail.privateemail.com`): transactional SMTP (`:587`) and IMAP intake (`:993`) — distinct credentials (`EMAIL_HOST_USER` vs `EMAIL_INTAKE_USER`).
- **No dedicated calendar *push* sync model surfaced** beyond `GoogleCalendarCredential.auto_sync_enabled`; Gmail integration stores credentials but its read/sync cadence is service-driven, not a scheduled-beat entry confirmed in this pass.
