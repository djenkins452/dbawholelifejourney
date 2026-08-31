# Renpho Auth Failure — First-Divergence Investigation

**Status:** Investigation only. No code modified, no POC changed, no fix attempted.
**Date:** 2026-07-19
**Symptom:** POC reaches Renpho, gets `HTTP 200`, body `status_code=50000`, `status_message="Email was not registered"` — for an account that exists and logs into the current mobile app.
**Companions:** `docs/WLJ_RENPHO_INTEGRATION_INVESTIGATION.md`, `..._AUTH_LIFECYCLE_INVESTIGATION.md`

---

## Verdict (first proven divergence)

**The POC authenticates against the WRONG ACCOUNT SYSTEM.** It targets the **legacy Renpho
app namespace** (`renpho.qnclouds.com`, `app_id=Renpho`). Danny's account lives in the
**new "RENPHO Health" system**, which is a *separate backend with separate credentials and a
separate API*. The legacy `sign_in` endpoint does an email lookup **in the legacy user table**,
does not find the address (it was never created there), and returns `50000 / "Email was not
registered."`

The divergence is **not** endpoint syntax, payload shape, encryption, or headers. It is the
**environment / account namespace** — the very first thing the request depends on, upstream of
everything else.

| Success-criteria question | Answer |
|---|---|
| 1. Correct endpoint? | **It is a *valid* legacy endpoint, but the *wrong system* for this account.** Not malformed — just pointed at the wrong user database. |
| 2. Payload still correct? | **Format is correct enough to be accepted and reach email lookup.** Payload is *not* the cause. |
| 3. Has Renpho changed its auth flow? | **YES — materially.** Renpho split into a new **RENPHO Health** app + backend with its own account system; the legacy `Renpho` app + `qnclouds` is a separate, older namespace. |
| 4. First confirmed divergence | **Account namespace / environment:** POC → legacy `qnclouds` `app_id=Renpho`; Danny's credential → new RENPHO Health backend. |
| 5. Category of fix | **Authentication flow / environment (account namespace)** — NOT payload / encryption / headers / config-typo. |
| 6. Evidence | Below — the error *semantics* + the documented two-system split. |

---

## Why the error semantics PROVE it (the decisive logic)

`"Email was not registered"` is an **application-level, post-parse, email-existence result**.
For the legacy server to return it, the request had to successfully:

1. **Hit a valid endpoint** — `sign_in.json?app_id=Renpho` was accepted (no 404 / route error).
2. **Parse the JSON body** — `secure_flag / email / password` were accepted (no malformed-request error).
3. **Reach the email-lookup stage** — and report *the email is absent from this namespace*.

Crucially, in the reference client's own auth handler the server distinguishes two failures
(confirmed by direct source read of `antoinebou12/hass_renpho :: api_renpho.py :: auth()`):

- `status_code == "50000"` + `"Email was not registered"` → **email absent from the namespace** (our case)
- `status_code == "500"` + `"Internal Server Error"` → **"Bad Password or Internal Server Error"**

We received the **email-stage** error, not the password-stage error. Therefore:

- **Endpoint, body shape, and headers are still accepted** by the legacy server — they cannot be
  the first divergence (a wrong one aborts *before* email lookup).
- **RSA/padding/encoding are not implicated** — password verification happens *after* the email is
  found; we never reached it. A broken cipher would surface at the password stage or as a generic
  500, **not** as a clean "email not registered."

The only remaining explanation consistent with a clean email-lookup miss is that **the account
does not exist in the namespace the POC is querying.**

## The documented two-system split (root cause corroboration)

The maintained community client states this explicitly (recurring, independent index text from
the `antoinebou12/hass_renpho` project):

> *"…uses the legacy Renpho cloud API (renpho.qnclouds.com) and the same account type as the older
> Renpho mobile app (**not Renpho Health**), as **credentials and APIs differ and Renpho Health is
> not supported.**"*

Reinforcing facts:
- **Two distinct apps exist:** legacy **"Renpho"** (bundle `com.qingniu.renpho`, QNCloud/Qingniu
  backend = `qnclouds.com`) vs the newer **"RENPHO Health"** (`com.renpho.health`), described as
  *"a separate application with different backend infrastructure and API endpoints."*
- Renpho's own FAQ confirms **account systems are siloed** ("The website and Renpho App are two
  different systems… you need to create a separate account in the App") — the same
  namespace-separation pattern.
- Danny's description — a **standard email/password login screen** on the **current** app — matches
  **RENPHO Health**, not the legacy app. The email works *there*, which is exactly why it does
  **not** exist in the legacy `qnclouds` namespace the POC queries.

## Ruled OUT as the first divergence (with reason)

| Candidate | Why it is NOT the first divergence |
|---|---|
| Endpoint URL syntax | Accepted (200, reached email lookup); not a 404/route error |
| Request body params (secure_flag/email/password) | Accepted; reached email lookup |
| RSA / public key / padding / encoding | Password stage never reached; would not yield an email-lookup miss |
| Missing headers (UA/Accept/Content-Type/proprietary) | Would abort before email lookup, or yield a different error |
| Signature / nonce / timestamp / client-id | Not required by the legacy endpoint (reference clients omit them and succeed for legacy accounts) |
| Password wrong / email typo / account absent | Explicitly excluded by the brief (app login proves account exists) — and the error is namespace-scoped, not credential-scoped |
| IP/region throttling | Produces empty data / HTTP errors / rejects, **not** a clean `50000 "Email was not registered"` |

## Subordinate possibility (same category)

Within the "wrong environment" class there is a lesser variant: **regional environment mismatch**
(Renpho runs US/EU/AU/JP/HK services). If the account were provisioned in a non-US regional
namespace, a US-endpoint lookup could also miss. This is the **same category** (wrong account
environment) and does **not** change the verdict. **Disambiguator:** the account almost certainly
lives in **RENPHO Health**, not merely a different legacy region — because Danny only ever used the
current (RENPHO Health) app, and the legacy app is a separate install he isn't using.

---

## Bottom line for implementation (diagnosis only — no fix here)

- The prior three investigations validated a mechanism against the **legacy** system. **Danny's
  account is not in that system.** That is the whole failure.
- **Forward implication (flag, not a fix):** the target is the **RENPHO Health** backend. The public
  reverse-engineering (qnclouds, RSA key, girths endpoints) is for the **legacy** app and is
  **not confirmed** to apply to RENPHO Health — the community explicitly reports Renpho Health as
  *unsupported / not reverse-engineered*. This **raises production risk** versus what the earlier
  reports assumed and should be resolved before committing to build:
  1. **Confirm the correct environment** — capture the RENPHO Health app's actual `sign_in` host,
     `app_id`, and payload (proxied HTTPS capture) and verify the email exists *there*; **or**
  2. **Test the legacy path fairly** — create/confirm an account in the **legacy "Renpho"** app and
     re-run the POC (proves the POC mechanics are sound, but ties production to a legacy app Danny
     doesn't use — likely a dead end long-term).
- **No POC change is warranted yet.** The POC is correct *for the legacy system*; the question is
  which system production must speak to — and today's evidence says it is one the public clients
  do **not** cover.

---

## Evidence / Sources
- Direct source read (this session): `antoinebou12/hass_renpho` `api_renpho.py :: auth()` — the
  `50000 "Email was not registered"` vs `500 "Bad Password"` branch — https://github.com/antoinebou12/hass_renpho
- hass_renpho project note: legacy qnclouds/legacy-app only; **Renpho Health not supported; credentials & APIs differ** — https://github.com/antoinebou12/hass_renpho , https://community.home-assistant.io/t/renpho-custom-integration/693771
- Two apps / two backends (legacy `com.qingniu.renpho` vs `com.renpho.health`) — https://renpho.com/pages/renpho-apps , https://neilgaryallen.dev/blog/reverse-engineering-the-renpho-app
- Renpho account-system separation ("two different systems… separate account in the App") — https://renpho.com/pages/faq
- Regional services (US/EU/AU/JP/HK) — https://renpho.com/pages/contact-us
