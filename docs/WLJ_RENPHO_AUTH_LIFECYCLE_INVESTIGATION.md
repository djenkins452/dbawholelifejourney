# Renpho Authentication & Session Lifecycle — Engineering Investigation

**Status:** Investigation only. No implementation, no code, no models, no pipeline design.
**Date:** 2026-07-19
**Companion to:** `docs/WLJ_RENPHO_INTEGRATION_INVESTIGATION.md`
**Question:** *Can WLJ maintain a persistent, secure, invisible, non-disruptive authenticated connection to Renpho without interfering with the user's normal use of the Renpho mobile app?*

---

## TL;DR — Success Criteria Answers

| # | Question | Answer |
|---|---|---|
| 1 | Can multiple authenticated sessions coexist? | **UNKNOWN (evidence conflicting — leans PARTIAL).** Cached session tokens are demonstrably reused for hours alongside normal use, but a *fresh login* is documented to invalidate the app's session. Must be settled empirically. |
| 2 | Will WLJ log the user out of the Renpho app? | **YES — at the moment of each fresh login** (documented in two independent clients). **Not continuously** — a reused token does not appear to boot the app. Disruption is proportional to *login frequency*, which we control. |
| 3 | Can auth be done once and reused? | **PARTIALLY.** Reuse the cached `terminal_user_session_key` across all polls; only re-authenticate when it actually fails (HTTP status `40302`). |
| 4 | Is periodic re-auth required? | **Only on token expiry/invalidation (`40302`), not per poll.** No fixed TTL is documented; tokens empirically survive many hours of hourly polling. |
| 5 | Recommended cadence? | **Once daily** (body circumferences change slowly; daily minimizes login events → minimizes disruption and rate-limit exposure). |
| 6 | Recommended auth architecture? | **Persistent stored session token, reused; encrypted credential vault used only to re-auth on `40302`; one low-frequency jittered daily poll; explicit opt-in with a "may sign you out of the Renpho app" disclosure; circuit-breaker + user-visible connection state.** |
| 7 | Production-ready? | **The mechanism is not *officially* production-ready** (unofficial, drift, invalidation ambiguity). It is **production-*acceptable* as an opt-in, fail-soft, low-frequency source** — **after** one empirical validation test (below) resolves the coexistence question. |
| 8 | Remaining risks? | Session ping-pong/invalidation ambiguity; API drift (already breaking for some); no refresh token; credential custody; multi-user single-IP rate-limiting; the community itself migrated away from the cloud API to local Bluetooth. |

**The one thing web evidence cannot settle:** whether the *user's normal phone activity* rotates the account session and invalidates WLJ's cached token — which would trigger a WLJ re-auth that then boots the phone, i.e. a disruptive **ping-pong**. Evidence leans against this (token reuse works over hours), but it must be **empirically validated on a real account before committing to build.**

---

## 1. Authentication Flow

- **Email + password only. No OAuth, no access/refresh-token pair, no PKCE.** A single sign-in returns one opaque session token.
- Endpoint: `POST https://renpho.qnclouds.com/api/v3/users/sign_in.json?app_id=Renpho`, body: `email`, **client-side-encrypted** `password`, `secure_flag=1`.
- Response: `terminal_user_session_key` (the session token) + `user_id` + bound devices. This key is passed as a query param on every subsequent authenticated request.
- **Session lifetime:** not documented by Renpho and not fixed in any client. Empirically the token is **long-lived enough to reuse across many hours** of polling — it is *not* a short-lived access token that needs minute-by-minute refresh. There is **no refresh-token mechanism**; renewal = a full fresh sign-in.

## 2. Session Behavior (the crux)

Evidence is **genuinely mixed**, and the honest conclusion is a nuance rather than a clean YES/NO:

**Evidence that a fresh login is disruptive (single-session-ish):**
- Two independent Home Assistant clients (`neilzilla/hass-renpho`, `antoinebou12/hass_renpho`) carry the explicit warning: **"logging in will log you out of the app."**
- Community/product guidance around multi-device use describes session/data conflicts when two clients are active — QNCloud (Renpho's backend, shared with other scale brands) behaves as though an account has very limited concurrent "terminal" sessions.

**Evidence that existing sessions coexist and are stable (against aggressive invalidation):**
- `antoinebou12/hass_renpho` **caches the session token and reuses it across polls**, re-authenticating *only* when it receives status `40302`. If every phone action invalidated the integration's token, the integration would be re-authing (and re-logging-out the phone) constantly — users do **not** report that.
- A community deployment runs the REST cloud integration **hourly (3600s) with a stored session and reports no continuous-logout problem.**

**Reconciliation (best-supported model):** QNCloud issues a session token per login; **a new *login event* rotates/supersedes and boots other sessions, but an already-issued token continues to work** for a long time without being invalidated by the other party's ongoing normal use. Therefore **disruption is a function of how often WLJ performs a fresh login, not how often it polls.** Minimize logins → minimize disruption. Whether the *phone's own* periodic re-auth silently rotates the account session (invalidating WLJ's token) is the unresolved variable.

- **Different devices receive independent session tokens:** YES (each sign-in yields its own key).
- **Existing session tokens keep working after another login:** **UNKNOWN** — this is exactly the ping-pong question to test.

## 3. Token Management

- **Lifetime:** undocumented; empirically hours-to-longer; reused, not per-request.
- **Refresh:** none. No refresh token, no silent renewal endpoint. "Renewal" = a fresh sign-in (a *login event*, with the disruption cost above).
- **Expiration signal:** HTTP status **`40302`** — the canonical "session expired/invalid, re-auth" signal used by the maintained client.
- **Re-auth requirement:** event-driven (on `40302`), **not** scheduled.

## 4. Polling / Synchronization Strategy — comparison

| Strategy | User disruption | Server load / rate-limit | Verdict |
|---|---|---|---|
| **Login every poll** | **Worst** — every poll is a login event → repeatedly boots the phone | High | ❌ Never |
| **Login once, reuse token, re-auth only on `40302`** | **Best** — login events are rare (only on genuine expiry) | Low | ✅ **Recommended** |
| Refresh token | N/A — Renpho has none | — | ❌ Not available |
| Cached session (persist token across restarts) | Best | Low | ✅ Pair with the above |
| Local Bluetooth (BLE) instead of cloud | None (no login) | None | ⚠️ Not viable for WLJ — requires device proximity; can't do server-side automated pull of a complete session |

**Recommended:** persist one session token per user, reuse it for every poll, and perform a fresh login **only** when a request returns `40302`. Poll **once daily**, jittered per-user.

## 5. Failure Modes & Graceful Recovery

| Failure | Behavior | Graceful recovery |
|---|---|---|
| **Password changed** | Stored credentials rejected on next `40302` re-auth | Mark connection **"needs re-authentication,"** stop polling, prompt user to reconnect. Never loop-retry a rejected credential (lockout risk). |
| **Token expired** | `40302` on a request | Single re-auth using vaulted credentials, retry the one request, resume. Back off if re-auth also fails. |
| **Renpho API changed** (endpoint/crypto drift) | Unexpected 4xx/5xx or shape change | **Fail soft:** surface "circumferences temporarily unavailable," open circuit-breaker, alert operator. **Never corrupt Body truth.** (Drift is real — one community user reports the old endpoint no longer works with the newer app.) |
| **Renpho cloud unavailable** | Timeout/5xx | Backoff + retry next cycle; keep last-known truth; no user-facing error beyond a stale-data indicator. |
| **Auth rejected / possible lockout** | Repeated 401/40302 | **Circuit-break immediately;** do not hammer. Require manual reconnect. Protects the user's account. |

## 6. How existing clients handle auth — comparison

| Client | Auth handling | Signal for WLJ |
|---|---|---|
| **`antoinebou12/hass_renpho`** (maintained) | **Caches token, reuses across polls, re-auths only on `40302`.** | **The correct pattern** — reuse-first, re-auth-on-failure. |
| `neilzilla/hass-renpho` / `RJ0088/homeassist-renpho` (older) | Simpler login-then-poll; default 60s loop; carry the **"logging in logs you out of the app"** warning. | Confirms the disruption exists; 60s cadence is too aggressive. |
| `danvaneijck/renpho-api` (recent, Feb 2026) | Login → store token in `self.token` → reuse; AES `crypto.py`. | Good client template; no persistence across process restarts by itself. |
| HA community REST deployment | Stored session, **hourly** poll, no continuous-logout reports. | Real-world evidence that reuse + low cadence is tolerated. |
| Community's newest solution (May 2026) | **Abandoned the cloud API for local Bluetooth BLE.** | ⚠️ The community migrated *away* from the cloud API — a fragility signal, though BLE can't serve WLJ's server-side pull. |

## 7. Production Recommendation

**Can WLJ safely maintain a long-term authenticated connection to Renpho? — Conditionally YES, as a fail-soft opt-in source; NOT as an invisible always-guaranteed link.**

The connection can be made **reliable, persistent, and secure** with the reuse-first architecture below. It **cannot be made 100% guaranteed-invisible** to the app, because a fresh *login event* is documented to disrupt the app's session — but WLJ controls how rare those events are, and with daily polling + token reuse they become infrequent (only on genuine expiry).

**Recommended authentication architecture (design only — do NOT implement):**
1. **Explicit opt-in connection** with an upfront disclosure: *"Connecting may occasionally sign you out of the Renpho app; just log back in."* Honesty converts a silent trust-breaker into an accepted, understood behavior.
2. **Encrypted credential vault** (per user, encrypted at rest, revocable) — used **only** to obtain/refresh a session token, never on the request path.
3. **Persistent session-token store** — one token per user, reused for every poll; survives worker restarts.
4. **Reuse-first, re-auth-on-`40302`-only** — a fresh login happens solely when the cached token fails. This minimizes login events → minimizes app disruption.
5. **One daily, jittered background poll** (Celery/worker; never request-path per `WLJ_REQUEST_PATH_SAFETY`), incremental via `last_updated_at`.
6. **Circuit-breaker + backoff + `HealthIngestionRun`-style run record** — fail soft, operator-visible, never corrupts Body truth (Administrator Experience: start/stop/monitor/recover/understand).
7. **User-visible connection health** — connected / needs-reauth / temporarily-unavailable.

**Mandatory pre-build validation (the one open variable):** Before committing engineering, run a controlled test on a real Renpho account:
- Log in via the API, obtain a token, then use the phone app **normally** for 24–48h while WLJ reuses its token on a daily poll.
- Observe: (a) does the phone actually get logged out, and how often? (b) does WLJ's cached token survive normal phone use, or does phone activity rotate the session and force WLJ to re-auth (the ping-pong)? (c) how frequently does `40302` occur?

This test resolves Success-Criteria #1 definitively; **web evidence alone cannot.** If the token survives normal phone use (leans likely), the architecture is production-acceptable. If normal phone use constantly rotates the session, the experience degrades to a mutual logout loop and the value proposition weakens — at which point revisit whether the complete-session value still justifies the friction.

## 8. Remaining Risks

- **Session ping-pong (primary open risk)** — unresolved until the empirical test; could turn "invisible" into "mutually logs each other out."
- **API drift** — unofficial private API; endpoints/crypto already breaking for some users on newer app versions. Treat the client as a replaceable seam; expect maintenance.
- **No refresh token** — every renewal is a full login (a disruption event); there is no gentler path.
- **Credential custody** — WLJ holds Renpho credentials; a real security escalation vs HealthKit's device-local, no-credential model.
- **Rate-limit / IP block** — many users polling from one server IP can get the app blocked; daily + jitter + circuit-breaker required.
- **Community migrated to BLE** — the ecosystem's own trajectory away from the cloud API is a durability warning.

---

## Evidence / Sources
- Reverse-engineering Renpho auth (`sign_in.json`, `terminal_user_session_key`) — https://neilgaryallen.dev/blog/reverse-engineering-the-renpho-app , https://neilgaryallen.dev/blog/renpho-to-home-assistant
- `antoinebou12/hass_renpho` — **token caching + re-auth only on `40302`**; girths endpoints — https://github.com/antoinebou12/hass_renpho
- `neilzilla/hass-renpho` — **"logging in will log you out of the app"** warning; rate-limit caution — https://github.com/neilzilla/hass-renpho
- Home Assistant community Renpho thread — **hourly (3600s) stored-session polling, no continuous-logout reports; old endpoint breaking on newer app; May-2026 migration to local BLE** — https://community.home-assistant.io/t/renpho-custom-integration/693771 , https://community.home-assistant.io/t/renpho-smart-scale-local-ble-custom-integration-with-multi-user-support/1008933
- `danvaneijck/renpho-api` (recent client, token reuse, AES) — https://github.com/danvaneijck/renpho-api
- Renpho multi-user / multi-device behavior — https://renpho.com/blogs/wellness-fitness-blog/how-to-use-your-smart-scales-multiple-users-feature
