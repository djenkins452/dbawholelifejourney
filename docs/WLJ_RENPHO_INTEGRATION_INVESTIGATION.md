# Renpho Direct Integration — Engineering Investigation

**Status:** Investigation only. No implementation. No models. No architecture changes.
**Date:** 2026-07-19
**Question:** *Can WLJ automatically retrieve **complete** body-measurement sessions (all ~12 tape-measure circumferences) directly from a user's Renpho account?*

---

## TL;DR

| Question | Answer |
|---|---|
| Is fully automatic Renpho sync possible? | **YES** |
| Does it retrieve the **complete** tape-measure session (not just waist)? | **YES** — the cloud API has a dedicated `girths` endpoint covering neck, shoulder, chest, waist, hip, abdomen, arm, thigh, calf (incl. left/right), and WHR |
| Official API? | **NO** — unofficial, reverse-engineered private cloud API |
| Reliable enough for production **as-is**? | **NO — not without a resilient, isolated, per-user, fail-soft design.** The mechanism works today but is unsanctioned, undocumented, and can break or lock out the user's app |
| Recommendation | **Build it — as a NEW opt-in ingestion source that runs *parallel* to HealthKit, not a replacement.** It is the *only* path that yields a complete body-measurement session |

The core finding: **HealthKit is structurally incapable of ever carrying a complete session** (Apple Health has no schema for bicep/thigh/calf/neck/chest circumference — only Waist Circumference exists as a native type). So the "Renpho → Apple Health → HealthKit → WLJ" pipeline can *never* be completed by improving the HealthKit side. The truth simply isn't in HealthKit. The Renpho cloud is the only place the full session exists off-device.

---

## 1. Is there an official developer API?

**No.** Renpho publishes no public developer API, no OAuth, no documented endpoints, and no partner program for direct data access. Third-party aggregators (Terra, Spike) resell Renpho access, but they themselves ride the same private cloud — they are a commercial wrapper, not an official Renpho product, and add a paid dependency and a data-processor relationship we don't want for a Personal Truth Platform.

## 2. Does Renpho store measurements in the cloud?

**Yes.** The RENPHO Health app syncs all device data — scale *and* Smart Tape Measure — to Renpho's private cloud at **`renpho.qnclouds.com`** (QNCloud, Renpho's backend vendor). The tape measure also buffers offline on-device and flushes to the app, which uploads to the cloud. So the cloud holds the authoritative history, including circumference sessions.

## 3. How does the app synchronize?

Device → Bluetooth → RENPHO Health app → HTTPS POST/GET to `renpho.qnclouds.com` (versioned REST, `/api/v2` and `/api/v3`, JSON). Auth is email + client-side-encrypted password → a `terminal_user_session_key` session token passed on every subsequent request. There is **no webhook / push** — it is a **pull/poll** model.

## 4. Is authenticated retrieval technically possible?

**Yes, and it is proven by multiple independent clients.** The flow:

1. `POST https://renpho.qnclouds.com/api/v3/users/sign_in.json?app_id=Renpho`
   body: `email`, encrypted `password`, `secure_flag=1` → returns `terminal_user_session_key` + `user_id` + bound devices.
2. Authenticated GETs (session key + `user_id` + `last_updated_at` unix cursor + `locale` as query params):
   - `/api/v2/measurements/list.json` — scale body-composition history
   - **`/api/v3/girths/list_girth.json` — the tape-measure circumference sessions** ← the data HealthKit cannot carry
   - `/api/v3/girth_goals/list_girth_goal.json` — circumference goals
   - `/api/v3/scale_users/list_scale_user`, `/device_binds/get_device.json`, `/growth_records/…` — supporting truth

**Password encryption note:** the password is *not* sent plaintext — clients encrypt it client-side before POST. The exact scheme has **drifted across app versions** (older clients show simpler hashing; the current `renpho-api` client ships a dedicated AES `crypto.py` module; some builds use RSA against a Renpho public key). This drift is itself a maintenance signal (see risks).

## 5. What data is actually available (girths)?

From the `girths` endpoint, the following circumference fields are exposed (matches the Smart Tape Measure's advertised body parts):

`neck, shoulder, chest, waist, abdomen, hip, arm (left/right), thigh (left/right), calf (left/right)` **+ waist-to-hip ratio (WHR)**, each with a **timestamp** and **unit**, and **full history** paged by a `last_updated_at` cursor. Goals are separately available. **This is a complete measurement session** — exactly the truth Body Intelligence needs and exactly what HealthKit drops on the floor.

## 6. Open-source Renpho clients — evaluation

| Client | What it proves | Maturity / Maint. | Girths? | License | Verdict |
|---|---|---|---|---|---|
| **`antoinebou12/hass_renpho`** (Home Assistant) | **Documents & implements the `girths/list_girth` + `girth_goals` endpoints and full field list** — the strongest evidence tape data is retrievable | Community HA component, actively evolved | **YES (explicit)** | MIT | **Primary reference** for endpoint/field shape |
| **`danvaneijck/renpho-api`** (PyPI `renpho-api`) | Clean modern Python client; login, device discovery, AES `crypto.py`, measurements → JSON/CSV | v0.1.0 **released Feb 2026** (recent), CI present, but tiny (~7★, single maintainer) | Scale composition only (no girths yet) | check repo | **Best code template** for the auth/crypto seam; would need girths added |
| **`forkerer/RenphoGarminSync-CLI`** | Proves end-to-end "read Renpho measurements, sync elsewhere"; the seed the Python client reverse-engineered from | Small (few commits), GPL-3.0 | "body measurements + weight" (partial) | **GPL-3.0** ⚠️ | Reference only — **do not vendor** (GPL contamination risk) |
| `neilzilla/hass-renpho`, `RJ0088/homeassist-renpho` | Original HA integrations; document auth + the two operational warnings below | Older, lightly maintained | Weight-centric | mixed | Historical evidence |
| `StartupBros/renpho-mcp-server` | Same private API behind an MCP server | New, niche | Composition | — | Corroboration |

**Two operational warnings surfaced repeatedly in these projects (critical):**
1. **Single active session** — logging in via the API can **log the user out of the Renpho mobile app** (and vice-versa can invalidate our session). This is a real UX landmine: an automated poller can silently boot the user out of their own app.
2. **Rate-limiting / blocking** — polling too aggressively "can trigger blocks from Renpho's servers." Integrations recommend conservative intervals (minutes+, realistically hourly/daily for this data).

## 7. Could a Django app authenticate as the user and retrieve automatically?

**Yes** — it is a plain HTTPS/JSON client (`requests`), no SDK, no device presence required (cloud pull). WLJ would store the user's Renpho credentials (encrypted at rest) or a session key, and a background worker would authenticate and pull girths on a schedule. Nothing about the mechanism is Django-hostile.

## 8. Polling vs webhook?

**Polling only.** No webhook/event push exists. Use the `last_updated_at` incremental cursor to pull only new sessions. Cadence should be **low-frequency** (e.g. every few hours or daily), respecting both the rate-limit and the single-session caveat — body circumferences change slowly; there is zero product value in tight polling.

## 9. Is it robust enough for production?

**Robust enough to build — NOT robust enough to depend on silently.** It works reliably *today*, but every risk below is real:

### Technical risks
- **Unsanctioned private API** — no contract, no SLA, no deprecation notice. Renpho can change endpoints, the encryption scheme, or block server-side scraping at any time. Encryption has *already* drifted across app versions.
- **Single-session lockout (highest-UX risk)** — automated login may sign the user out of their phone app. Must be designed around (reuse/refresh a stored session; never race the app; make cadence low; make it clearly opt-in).
- **Credential custody** — direct-auth means we hold the user's Renpho email+password (or a long-lived session). This is a security-sensitive escalation vs. HealthKit's device-local, no-credential model. Encrypt at rest, isolate, allow revocation.
- **Rate-limit / IP block** — one shared server IP polling many users can get the whole app blocked. Needs conservative, jittered, per-user scheduling and circuit-breaking.
- **Silent schema drift** — field names/units can change; ingestion must validate and fail *soft* (surface a `HealthIngestionRun`-style "needs attention", never corrupt Body truth).
- **ToS exposure** — reverse-engineered access likely runs against Renpho's terms; acceptable for a personal/self-hosted-style tool, a genuine consideration at product scale.

### What makes it acceptable
All of the above are **containable** with a fail-soft, isolated, opt-in ingestion source. None of them are worse than the alternative, which is **permanent, structural incompleteness** — HealthKit will *never* carry the full session no matter what we build.

---

## Architectural Recommendation (design only — do NOT implement)

**Build it as a new, opt-in "Renpho Body Measurements" ingestion source that runs *parallel to* HealthKit — not a replacement.** HealthKit stays the primary path for weight/body-composition and everything else it does carry; Renpho-direct becomes the *only* source of the complete circumference session.

**1. Where it belongs.** A new provider under the existing **ingestion-source pattern** (the same conceptual layer as HealthKit's `HealthIngestionRun`). It is a *Layer-1 Truth ingestion path*, feeding Body Intelligence — **not** a CoS/reasoning feature. Follow the certified Layer-1 domain framework: circumferences become canonical Body measurement truth with provenance `source=renpho_cloud`.

**2. Authentication.** User opts in and enters Renpho credentials in a dedicated, isolated connection surface. **Do not store the plaintext password** in the app DB in the clear — encrypt at rest, and prefer storing the **refreshable session key** over the password where possible. Provide explicit **disconnect/revoke**. Surface the single-session caveat to the user *before* they connect ("connecting may sign you out of the Renpho app").

**3. Synchronization.** Background **poller** only (Celery/worker — this is heavy I/O and must never touch the request path per `WLJ_REQUEST_PATH_SAFETY`). Low cadence (hours/daily), **per-user jitter**, incremental via `last_updated_at`, **circuit-breaker + backoff** on 4xx/blocks, and a **`HealthIngestionRun`-style run record** so the operator/user sees *needs-attention* on failure (Administrator Experience: start / stop / monitor / recover / understand). Never live-fetch on a page load.

**4. Flow into Body Intelligence.** Pulled girths → validate/normalize units → **dedup against existing HealthKit-derived waist** (waist arrives from *both* paths; Renpho-cloud is authoritative for a session, so reconcile, don't double-count) → write canonical Body circumference truth with provenance and timestamp → the existing Body Intelligence / Current Context surfaces consume it unchanged. A complete session becomes retrievable truth the CoS can narrate.

**5. Guardrails to decide before building.**
- Reference **`antoinebou12/hass_renpho`** (MIT) for endpoint/field shape and **`danvaneijck/renpho-api`** (recent, AES seam) as the client template. **Avoid GPL-licensed `RenphoGarminSync-CLI` code** in anything vendored.
- Treat the whole client as a **replaceable seam** behind one interface (endpoints/crypto *will* change).
- **Fail soft, always** — a Renpho breakage must degrade to "circumferences temporarily unavailable," never corrupt or block Body truth.

**Bottom line:** Yes, build it — it is the *only* way WLJ ever obtains a complete body-measurement session, and the risks are real but containable behind an isolated, opt-in, fail-soft, low-frequency background ingestion source. Do **not** frame it as "replace Apple Health"; frame it as "the complete-session source Apple Health structurally cannot be."

---

## Evidence / Sources
- Reverse-engineering the Renpho app (auth flow, `sign_in.json`, session key) — https://neilgaryallen.dev/blog/reverse-engineering-the-renpho-app , https://neilgaryallen.dev/blog/renpho-to-home-assistant
- `antoinebou12/hass_renpho` — **girths / girth_goals endpoints + full circumference field list**, MIT — https://github.com/antoinebou12/hass_renpho/blob/master/docs/README.md
- `danvaneijck/renpho-api` (PyPI, v0.1.0 Feb 2026, AES crypto) — https://github.com/danvaneijck/renpho-api , https://pypi.org/project/renpho-api/
- `forkerer/RenphoGarminSync-CLI` (GPL-3.0, reverse-engineering seed) — https://github.com/forkerer/RenphoGarminSync-CLI
- `neilzilla/hass-renpho` (single-session logout + rate-limit warnings) — https://github.com/neilzilla/hass-renpho/blob/master/info.md
- `RJ0088/homeassist-renpho` (auth flow, `app_id=Renpho`, 60s poll default) — https://github.com/RJ0088/homeassist-renpho/blob/master/RenphoWeight.py
- Renpho Smart Tape Measure (12 body parts, app + Apple Health sync) — https://renpho.com/products/smart-tape-measure
- Commercial wrappers (not official): Terra — https://tryterra.co/integrations/renpho ; Spike — https://www.spikeapi.com/integrations/renpho
