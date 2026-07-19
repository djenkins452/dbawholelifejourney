# WLJ Configuration Governance

**Status:** **OPS-13 (Foundation) IMPLEMENTED & DEPLOYED report-only** (2026-07-19). **Architecture RATIFIED 2026-07-19** — the initiative is decomposed by blast radius into milestones OPS-13…OPS-17 (§10); OPS-14+ are approval-gated and **not** started.
**Kind:** Governing operational document for production configuration truth (the single responsibility for *configuration* governance — see §11 for its place in the broader Platform Capability Verification vision).
**Authority:** The one canonical configuration contract is code: `apps/core/config_governance/contract.py`. Do **not** hard-code configuration requirements anywhere else. Every monitor, startup check, and this document derive from that file.
**Non-negotiable:** WLJ owns deterministic configuration truth; the language model never decides validity. **No secret VALUE is ever read for monitoring, logged, persisted, or displayed** — only *presence* (present / empty / absent).
**Ratified architectural decisions (2026-07-19):** (1) blast-radius milestone decomposition (§10); (2) explicit **service classes** — runtime / build / administrative (§1A); (3) **UNKNOWN** is a first-class, aggregation-level state, never coerced to Healthy/Critical (§4A); (4) capability-first **vision** — Configuration Governance is one deterministic contributor to Platform Capability Verification, composing existing authorities, never a new one (§11); (5) self-reporting **manifests are the primary authority**; Railway API may only ever be an optional secondary (§4).

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

## 1A. Service classification (RATIFIED — an explicit architectural concept)

A service's **class** determines *which* verification it participates in. This is a first-class architectural concept, not an incidental implementation detail: it must be declared, not inferred from "whatever process happened to import Django."

| Class | Definition | Participates in | Examples |
|---|---|---|---|
| **Runtime** | Long-running service that serves customers continuously | **Runtime Configuration Integrity** (+ `_MUST_RUN`; a missing manifest → UNKNOWN) | Web, Worker, Beat, Chat Worker, future runtime services |
| **Build** | Transient build/release-phase process that runs then exits | **Deployment / preflight validation only** (OPS-16) — never the runtime verdict | Railway Build Runner |
| **Administrative** | On-demand admin tool, not always-on | **Excluded from runtime operational health** (validated ad-hoc when used) | DB Admin |

**Why Build Runner is excluded from runtime integrity.** It is fundamentally different from Web/Worker/Beat: its config needs are *build-time*, not runtime. The incident proves the point — the Cloudinary vars were shared to Build Runner but *not* to Worker/Beat; **a build service holding a variable tells you nothing about whether runtime has it**, and counting it as "a service that has Cloudinary" could *mask* a runtime gap. Build Runner belongs to **deployment validation** (verify the release environment *before* rollout), a separate concern. Its manifest may still be *collected as informational*, but it never contributes to the runtime health verdict.

**Why DB Admin is excluded from runtime integrity.** It is an on-demand administrative tool, not a customer-serving runtime service. It is usually *not running*, so treating it as runtime would make its (legitimately absent) manifest read as UNKNOWN → chronic false alarms on a service that is healthy by being idle. Administrative tooling readiness, if ever needed, is validated ad-hoc — never as a continuous runtime-health input, and never in `_MUST_RUN`.

**Implication for `_MUST_RUN`:** only **runtime**-class services belong in it. A missing or stale manifest from a build or administrative service must **never** drive the system to UNKNOWN.

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

**Manifest authority (RATIFIED).** The self-reporting manifest is the **primary authority** and reflects **runtime truth** — what each process *actually loaded*, which is strictly stronger than what a Railway API would report (deployment *intent* in the dashboard). A variable can be "configured" yet not injected, overridden, or shadowed by a service-local copy; the manifest sees what the process is really running on. Railway API interrogation is **not** the primary mechanism (provider lock-in + a new secret-bearing token = a fresh attack surface, and it answers the weaker question); it may **later become an *optional secondary* validation layer** — only ever to help close the boot-crash blind spot below — and must **never replace** runtime verification.

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

## 4A. UNKNOWN policy (RATIFIED — first-class, aggregation-level state)

**UNKNOWN means "the system cannot currently verify this."** It is first-class and must **never** be coerced into Healthy, Critical, or any fabricated certainty. Coercing to Healthy hides risk; coercing to Critical fabricates an outage. This is the same discipline as the CoS rule *"honest rejection, never fabricate,"* applied to operations.

**UNKNOWN is a property of *aggregation*, not of self-knowledge.** A *running* service always knows its own configuration (its `os.environ` is directly readable — present/missing, never unknown). The *monitoring* system, aggregating across services, may legitimately not know (a service isn't reporting a fresh manifest). Therefore UNKNOWN exists only at the monitor/aggregation layer — **never at startup validation**, where a process has complete knowledge of itself.

**Propagation policy** (this governs the OPS-15 wiring; decide it *before* config influences operations state):

| Surface | UNKNOWN behavior | Rationale |
|---|---|---|
| **Operations score / status** | Caps status **below Healthy** (carries an "unverified" annotation); does **not** trigger Critical | Honors "never Healthy when verification unavailable" without fabricating an outage |
| **CoS awareness (customer banner)** | **Does not surface** | Unverifiable config is an *operator* concern — unactionable and alarming to customers; the banner reflects *confirmed* customer-impacting states only |
| **Incident generation** | Only on **persistence** (unverified beyond a threshold), with dedup + hysteresis | A transient manifest miss during a deploy must not spam incidents; *persistent* unverifiability is a real concern |
| **Recovery behavior** | **Never auto-acts** | One cannot safely remediate what cannot be verified (acting on a false premise); UNKNOWN → human investigation (consistent with the R0 observe-only default) |
| **Startup validation** | **N/A** | A process knows its own env directly; UNKNOWN does not exist at startup |

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
- **Add a new service:** add the `SERVICE_*` key + label in `contract.py`, **declare its class** (§1A: runtime / build / administrative), and include it in `RUNTIME_SERVICES`/`_MUST_RUN` **only if it is runtime-class**. Ensure it publishes a manifest (any process importing `apps.core` does automatically). Update §1. A build- or admin-class service must never contribute to the runtime verdict.

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

## 10. Milestone roadmap (RATIFIED 2026-07-19 — decomposed by blast radius)

The initiative is **not** one large effort. It is decomposed into milestones ordered by *deployment blast radius*, so capability grows without growing risk. Each milestone ships at its own risk-appropriate pace; read-only visibility never waits on high-risk enforcement.

| Milestone | Scope | Blast radius | Status |
|---|---|---|---|
| **OPS-13 Foundation** | Contract + drift detection + report-only `config_integrity` monitor | None (read-only) | **DONE** (deployed report-only, prod-verified) |
| **OPS-14 Configuration Visibility** | Ops Wall Configuration Integrity **card** — pure read-only display of the section's own status | None | **NEXT** (awaiting approval) |
| **OPS-15 Configuration → Operations State** | `CONFIG_DRIFT` anomaly into SAME → executive/global status + incident lifecycle (dedup/recovery) **and** the CoS awareness banner | Medium — config now influences operations posture | approval-gated |
| **OPS-16 Configuration Enforcement** | Startup-fatal (flag flip after proving) + deployment preflight / rollout gating (report-only first) | **High** — can block boots/deploys | approval-gated; split preflight out if it proves hairy |
| **OPS-17 Continuous Governance** | Contract expansion (evidence-driven); optional Railway-API secondary cross-check; optional salted fingerprints for value-consistency | Low, incremental | ongoing |
| *Operational runbook* | **Railway Configuration Cleanup** (§9) — execute the cleanup plan | Manual, reversible | **not a software milestone**; Danny executes |

**Architectural couplings recorded during planning:**
- **The Ops Wall card (OPS-14) is decoupled from global status** — it renders the section's own status, so it ships safely on its own.
- **CoS awareness and incident generation are ONE step (OPS-15), not two** — the CoS banner consumes `executive.overall_status`, so surfacing config in it *requires* config to flow into the executive summary via `CONFIG_DRIFT`, which is the same wiring as incident generation. They cannot be separate milestones.
- **OPS-16 (enforcement) is the only high-blast-radius milestone.** The deployment preflight must be report-only first and must not become "a brittle blocker that causes more outages than it prevents." Consider splitting startup-enforcement and preflight if either destabilizes.
- **The Railway cleanup is an operational runbook, not code** — tracked, human-executed, out of the software milestone sequence.

**Before OPS-14 begins (ratified prerequisites):** the §1A service-class taxonomy and the §4A UNKNOWN propagation policy are architectural givens; the OPS-15 wiring must respect the UNKNOWN policy (esp. "UNKNOWN caps below Healthy but never triggers Critical," and "does not surface to the customer banner").

**Non-negotiables (permanent):** deterministic truth (no model decides validity); never expose/log/persist secret values; one canonical contract (no parallel authority); no automatic Railway reorg; report-only first; never Healthy when verification is unavailable; increase capability without increasing deployment risk.

---

## 11. Long-term vision — Platform Capability Verification

**Configuration Governance keeps its name and remains the implementation initiative.** But its *architectural North Star* is broader than variables. The real question WLJ is learning to answer, deterministically and per service, is:

> **Can WLJ actually perform the capabilities it claims to support?**

Configuration presence is the **first precondition class** for a capability; it is not the only one. A capability (durable-media processing, AI chat, background processing) is available on a service iff *all* its preconditions hold:

- **configuration present** — Configuration Governance (this doc);
- **dependency reachable** — can the service actually connect to Cloudinary/Redis/Postgres/OpenAI, not just hold the URL?
- **package installed** — ffmpeg, `pdfplumber`, …;
- **schema/migrations applied**;
- **external provider healthy**.

WLJ **already** monitors most of these — `upstream_health` (OpenAI), `storage`, `db_health`, `media_persistence`, scheduler/recovery. So **Platform Capability Verification is not a new subsystem to build** — it is a **thin deterministic rollup** that, per capability, composes the verdicts those existing authorities already produce (keyed by the `capability` field the contract already carries). Configuration Integrity is **one deterministic contributor** among several.

**Guardrails (so the vision expands the framing, not the build):**
- **Do NOT create a new authority.** The capability layer *composes* existing deterministic monitors; it never re-derives or overrides them (WLJ Architecture Law III.1).
- **Do NOT build it as a monolith now.** Grow it capability-by-capability, evidence-driven (the same bottom-up discipline as Truth Retrieval Certification) — only when a real gap justifies it.
- **Keep the current build narrowly on configuration.** The reframe is conceptual/documentation; no capability-verification code is in scope until separately approved.
