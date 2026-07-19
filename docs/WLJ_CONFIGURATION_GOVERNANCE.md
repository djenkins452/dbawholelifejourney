# WLJ Configuration Governance

**Status:** Phase-1 foundation IMPLEMENTED & DEPLOYED **report-only** (2026-07-19). Enforcement phases are staged and approval-gated (see §Rollout).
**Kind:** Governing operational document for production configuration truth.
**Authority:** The one canonical configuration contract is code: `apps/core/config_governance/contract.py`. Do **not** hard-code configuration requirements anywhere else. Every monitor, startup check, and this document derive from that file.
**Non-negotiable:** WLJ owns deterministic configuration truth; the language model never decides validity. **No secret VALUE is ever read for monitoring, logged, persisted, or displayed** — only *presence* (present / empty / absent).

Origin: a production incident where `wlj-worker` and `wlj-beat` crashed because the Cloudinary variables were shared only to `wlj-build-runner`, not to Worker/Beat; `wlj-web-app` stayed up on its own service-local copies. Once shared to Worker and Beat, both recovered. This system detects that class *before* the next outage.

---

## 1. Production service inventory (as-built, audited 2026-07-19)

Railway dashboard Custom Start Commands are the source of truth (the `Procfile` is reference-only). Repo-defined runtime services:

| Service (key) | Railway | Start command | Runtime config needed |
|---|---|---|---|
| **Web** (`web`) | wlj-web-app | `gunicorn config.wsgi` (+ inline migrate/collectstatic) | full |
| **Worker** (`worker`) | wlj-worker | `celery -A config worker` | full (executes media/AI tasks) |
| **Beat** (`beat`) | wlj-beat | `celery -A config beat` | full (imports settings → same hard requirements) |
| **Chat Worker** (`chatworker`, optional) | wlj-chat-worker | `celery -A config worker -Q chat` | full when deployed |

Auxiliary Railway services that exist on the platform but are **not repo-defined**: **wlj-build-runner**, **wlj-db-admin**. These do not run the app runtime; they must **not** be the *only* place a runtime variable is shared (the incident's root cause). The monitor learns the *actual* running services from their self-reported manifests (§4), so this inventory drift is itself observable.

---

## 2. The configuration contract (canonical)

`apps/core/config_governance/contract.py :: CONTRACT` — a tuple of `VariableSpec`. Each entry declares: name · classification (secret/config/public) · description · customer capability · required services · severity (critical/degraded/advisory) · environments · preferred source (shared/service) · empty-valid · fail-startup · remediation · duplicate-local-allowed · consistency-required.

Monitored set (Phase-1 focused on outage-causing variables; the full inventory is classified in §3 and expands into the contract as it earns monitoring):

| Variable | Class | Required services | Severity | Source | Capability |
|---|---|---|---|---|---|
| `SECRET_KEY` | secret | Web, Worker, Beat, ChatWorker | critical (fail-startup) | shared | Login/session/security integrity |
| `DATABASE_URL` | secret | Web, Worker, Beat, ChatWorker | critical (fail-startup) | shared | All data read/write |
| `REDIS_URL` | secret | Web, Worker, Beat, ChatWorker | critical | shared | Background processing + cache |
| `CLOUDINARY_CLOUD_NAME` | config | Web, Worker, Beat | critical (fail-startup) | shared (consistent) | Durable file/media processing |
| `CLOUDINARY_API_KEY` | secret | Web, Worker, Beat | critical (fail-startup) | shared (consistent) | Durable file/media processing |
| `CLOUDINARY_API_SECRET` | secret | Web, Worker, Beat | critical (fail-startup) | shared (consistent) | Durable file/media processing |
| `OPENAI_API_KEY` | secret | Web, Worker, ChatWorker | degraded | shared | AI assistant / chat |
| `CLAUDE_API_KEY` | secret | Web | advisory (empty-valid) | service | Internal operator automation |

`ALLOWED_HOSTS` and `CSRF_TRUSTED_ORIGINS` are **hardcoded in settings, not env vars** → intentionally excluded.

---

## 3. Full variable classification (audited inventory — reference)

Not all of these are monitored yet; they are classified so future contract growth is a data change. (Names only — never values.)

- **Platform runtime:** `SECRET_KEY`, `DEBUG`, `DJANGO_SETTINGS_MODULE`, `ADMIN_URL_PATH`, `DASHBOARD_V3_DEFAULT`.
- **Data infrastructure:** `DATABASE_URL`, `REDIS_URL`, `CELERY_BROKER_URL`, `CELERY_RESULT_BACKEND`, `CHAT_GENERATION_QUEUE`, `DISABLE_REDIS_CACHE`.
- **Durable media/storage:** `CLOUDINARY_CLOUD_NAME/_API_KEY/_API_SECRET`, `WLJ_ALLOW_EPHEMERAL_MEDIA`; capture-audio S3 (`CAPTURE_AWS_*`, `CAPTURE_AUDIO_BUCKET`, `CAPTURE_S3_ENDPOINT_URL`, …).
- **AI providers:** `OPENAI_API_KEY`, `OPENAI_MODEL/_VISION_MODEL/_MINI_MODEL`, `COS_MODEL`, `CLAUDE_API_KEY`.
- **External integrations:** Stripe (`STRIPE_*`), Plaid (`PLAID_*`, `BANK_TOKEN_ENCRYPTION_KEY`, `OAUTH_TOKEN_ENCRYPTION_KEY`), Google (`GOOGLE_CALENDAR_*`, `GMAIL_*`), Twilio/SMS/push (`TWILIO_*`, `APNS_*`, `SMS_*`), Dexcom (`DEXCOM_*`), email (`EMAIL_HOST_*`, `EMAIL_INTAKE_*`), `YOUVERSION_API_KEY`, `FATSECRET_*`, `SPORTS_*`, `RECAPTCHA_V3_*`, `SENTRY_*`.
- **Operations/recovery:** `OPS_RECOVERY_*`, the `WLJ_*` CoS behavior flags.
- **Build/deploy + admin tooling:** `RAILWAY_GIT_COMMIT_SHA`, `GITHUB_*`, `TEST_RESULTS_*`, `SCAN_*`.

---

## 4. How detection works (Option B — secret-safe self-report)

WLJ cannot read Railway's variable-sharing UI, and building a Railway-API integration would create a new secret-bearing surface. So each service **self-reports presence only**:

1. **Manifest** (`manifest.py`): at `AppConfig.ready()` every process computes a manifest — for each contract variable, a 3-state token `present | empty | absent` (from its own `os.environ`, **never a value**) + service identity (`RAILWAY_SERVICE_NAME` or argv heuristic) + commit + timestamp — and publishes it to shared Redis (26h TTL; the worker refreshes each SAME cycle).
2. **Evaluation** (`evaluator.py`): the SAME background cycle reads all manifests and evaluates them against the contract — pure, deterministic. Findings: `missing_required`, `inconsistent_across_services`, `service_unverified`.
3. **Telemetry** (`telemetry.py` → Ops payload section `config_integrity`): status + findings + affected services/capabilities + customer-language summary. The HTTP path only reads the cached payload (request-path-safe).

**Honesty limit (documented, not hidden):** a service that *crashes* on a fatal missing variable (e.g. the Cloudinary settings raise) self-reports nothing → it appears as **UNKNOWN / unverified**, correlated with `MISSED_RUN` for its tasks — never a false Healthy. Direct "missing on Worker" findings apply to services that boot far enough to report (soft gaps) and to any state constructed for testing. Closing the fatal-var-crash blind spot fully needs Railway API (Option A) or a pre-settings probe — deferred (§Rollout).

### Status model
- **Healthy** — every required variable present on every required service (all fresh).
- **Degraded** — a non-critical (degraded/advisory) gap or inconsistency; platform operational.
- **Critical** — a critical required variable missing or inconsistent on a required service.
- **Unknown** — a required service is not reporting a fresh manifest → cannot verify. **Never Healthy when verification is unavailable.**

---

## 5. Rules: shared vs service-local · secret handling

- **Runtime variables required by ≥2 services** belong in **Railway Shared Variables**, shared to **every** required runtime service (Web, Worker, Beat, and ChatWorker where applicable) — never to only build-runner/db-admin.
- **Service-local copies** are allowed unless `duplicate_local_allowed=False` (e.g. `SECRET_KEY` must be one shared value). Where `consistency_required=True` (Cloudinary), the value must be identical across services; the monitor flags presence inconsistency (it cannot compare values — by design).
- **Secrets** (`classification=secret`) are presence-checked only. Never logged, never in the manifest, never on the Ops Wall, never in audit, never in tests.

---

## 6. Startup validation

- The genuinely-fatal trio is **already** enforced by settings-import raises (`SECRET_KEY`, `DATABASE_URL`, `CLOUDINARY_*`) — unchanged.
- `startup.py :: run_startup_governance()` (called from `CoreConfig.ready()`) publishes the manifest and logs a **report-only** governance summary for this service's required set (plain language, no secrets). Fatal enforcement is gated behind `CONFIG_GOVERNANCE_ENFORCE_STARTUP` (default **False**) so it can never add a new startup crash.

---

## 7. Operations remediation runbook (Railway)

1. Identify the missing/ inconsistent variable + affected services from the Configuration Integrity section.
2. In Railway → the variable's canonical home (Shared Variables for shared vars).
3. **Share** it to every required runtime service (Web, Worker, Beat, ChatWorker).
4. Redeploy/restart the affected services; confirm they boot and report fresh manifests.
5. Confirm the Configuration Integrity status returns to Healthy on the next SAME cycle.
6. Do **not** remove service-local copies until the shared value is attached **and** verified present on all services (see §9 Cloudinary cutover).

**Emergency recovery:** if a runtime service is crash-looping on a fatal variable, share the variable (step 3) — that is the fix; no code deploy is required. `WLJ_ALLOW_EPHEMERAL_MEDIA=1` is a last-resort break-glass to let a service boot with non-durable media (accepts media loss) — never a steady state.

**Rotation:** rotate the value at the provider → update the Shared Variable → redeploy all required services together (consistency-required vars must never be half-rotated). Presence stays true throughout; the monitor will not flag a value change (it never sees values).

---

## 8. Extending the system

- **Add a new required variable:** add a `VariableSpec` to `CONTRACT` (name, classification, required_services, severity, capability, remediation). Nothing else changes — manifests, evaluator, telemetry, and this contract table pick it up. Add a test scenario.
- **Add a new service:** add the `SERVICE_*` key + label in `contract.py`, include it in `RUNTIME_SERVICES`/`_MUST_RUN` if it must run, and ensure it publishes a manifest (any process importing `apps.core` does automatically). Update §1.

---

## 9. Cleanup plan (Phase 12 — proposed, NOT executed; needs Danny's approval)

Configuration changes on Railway are Danny's to make; this is the reviewed plan.

| Variable | Current state (from incident) | Proposed action |
|---|---|---|
| `CLOUDINARY_*` | Shared to build-runner; Worker/Beat now shared (recovered); Web had service-local copies | **Verify** Web/Worker/Beat all resolve the shared value; **keep** Web's local copies until shared values are confirmed present on all three; then **remove** Web local copies in a deliberate cutover (never before). |
| `SECRET_KEY`, `DATABASE_URL`, `REDIS_URL` | Shared | Confirm shared to all runtime services; no local copies. |
| `OPENAI_API_KEY` | (verify) | Confirm shared to Web, Worker, ChatWorker. |
| Runtime vars shared to build-runner/db-admin only | Root-cause pattern | Audit that no *runtime-required* variable lives only on build-runner/db-admin. |

**Cloudinary cutover safety:** do not remove Web's local Cloudinary copies until (a) the shared values are attached to Web/Worker/Beat, (b) all three report `present`, and (c) a rollback (re-add local copy) is understood. Immediate stability outranks tidiness.

---

## Rollout (Phase 15) & deferred items

**Stage 1 (this increment, LIVE):** contract + manifests + evaluator + `config_integrity` Ops section, **report-only** — visible to operators, does **not** yet affect the global Operations score, the CoS banner, or startup.

**Deferred, approval-gated (each its own step):**
1. Wire `config_integrity` critical → a `CONFIG_DRIFT` anomaly in the SAME pipeline → global status + the CoS Operations banner (reuses the existing single authority; needs a model migration for the anomaly type + false-positive validation against real Railway config first).
2. Configuration change audit records with dedup/lifecycle (via the same OpsAnomaly lifecycle).
3. Flip `CONFIG_GOVERNANCE_ENFORCE_STARTUP` on after report-only proves no false positives.
4. Deployment preflight guard (Phase 10) — report-only first; block a deploy only after proven stable.
5. Railway API (Option A) or pre-settings probe to close the fatal-var-crash blind spot.
6. Contract expansion to the full §3 inventory.
7. Actual Railway variable cleanup (§9) — Danny executes after review.

**Non-negotiables honored:** deterministic truth (no model); never expose/log/persist secret values; one canonical contract (no parallel authority); no automatic Railway reorg; report-only first; never report Healthy when verification is unavailable; existing Operations behavior unchanged in this stage.
