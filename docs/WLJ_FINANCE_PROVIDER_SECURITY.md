# WLJ Finance — Provider (Plaid) Security Posture

> **Purpose:** the durable record behind every security statement WLJ makes about a
> financial-data provider integration. Each section names the control, where it lives, and
> the test that proves it is active rather than merely present.
> **Last updated:** 2026-08-25

---

## 1. Credentials are environment-only

`PLAID_CLIENT_ID` / `PLAID_SECRET` / `BANK_TOKEN_ENCRYPTION_KEY` are read from the
environment with empty defaults (`config/settings.py:1006-1011`). `.env` is gitignored
(`.gitignore:41`) and has never been committed (`git log --all -- .env` is empty). Only
`.env.example` is tracked, and it carries no provider value. No credential reaches a
template or JavaScript — the browser receives only Plaid's short-lived `link_token`.

## 2. Token encryption fails closed

`apps/finance/services/encryption.py` raises `EncryptionNotConfigured` when the key is
missing or invalid. **The `UNENCRYPTED:` plaintext fallback is gone**: a provider token
can no longer be written unencrypted by any code path.

A *legacy* plaintext value remains **readable** on purpose. It may be the only credential
capable of revoking a live provider Item, and refusing to read it would strand that
access permanently — strictly worse than reading it once to revoke and re-encrypt.

- Deploy-time validation: `apps/finance/checks.py` — a Django system check (which runs
  before `migrate` on every Railway deploy) **errors** when Plaid is configured in a
  non-DEBUG environment without a usable key.
- Configuration governance: declared `SEV_CRITICAL`, `SOURCE_SHARED`, required on web and
  worker (`apps/core/config_governance/contract.py`).
- Operator evidence: `GET /admin-console/api/claude/finance-audit/` reports
  `bank_token_encryption_configured` and `credentials.legacy_plaintext_tokens` — booleans
  and counts, never a key or a token.

## 3. Webhook authenticity is cryptographically verified

`apps/finance/services/plaid_webhook_verification.py` performs Plaid's documented
verification: **ES256 pinned** (defeating `alg: none` and algorithm substitution), the JWK
fetched by `kid` from `/webhook_verification_key/get` and cached for a bounded 24 hours,
signature verified, `iat` inside a 300-second window, `request_body_sha256` compared to
the exact raw body in constant time, and a one-shot replay guard keyed on
`kid + body hash + iat`.

**Every failure path rejects**, including missing configuration. The previous
implementation decoded with `verify_signature: False` and accepted anything whose body
hash and `iat` looked plausible — both attacker-controlled — and returned `True` outright
when Plaid was unconfigured.

Nothing sensitive is logged: no header, token, signature, claim, or body — only a reason
code.

## 4. Disconnection revokes before it forgets

`apps/finance/services/provider_disconnect.py` is the ONE path:

1. ask the provider to remove the Item **first**;
2. clear the local token **only** after the provider confirms;
3. on failure, keep the encrypted token, mark `revocation_pending`, and return **502** —
   never "disconnected";
4. `ITEM_NOT_FOUND` / `INVALID_ACCESS_TOKEN` mean the Item is already gone → treated as
   revoked, so retries are idempotent;
5. `retry_pending_revocations()` retries safely and repeatedly.

Deletion cannot bypass this. `BankConnection.delete()` and `.soft_delete()` **refuse**
while provider access is live, and `assert_no_live_provider_access(user)` guards account
closure. Those guards deliberately **refuse rather than call out to the network** — an
external request inside a delete path or a user-deletion cascade is exactly the fragile
coupling that strands state.

## 5. Access is an explicitly granted capability

`apps/finance/access.py` turns `UserPreferences.finances_enabled` (default **False**,
`apps/users/models.py:341`) into a real gate on every Finance surface: provider connect,
token exchange, sync, disconnect, attribution, opportunities, and entity setup.
**Signing up grants nothing.** Granting is a staff-only operation
(`python manage.py finance_access --grant <email> --by <staff-email>`).

**No identity is hardcoded** — no name, address, or user id appears in executable code
(AST-asserted). The trial population is whoever has been explicitly approved.

Webhooks are deliberately **not** user-authenticated: they are machine-authenticated by
signature verification plus the replay guard.

## 6. Re-authentication and rate limits are active

Connect, complete (token exchange), re-auth, sync, and disconnect each carry
`@finance_enabled_required` + `@requires_recent_auth(15)` + `@finance_rate_limit(...)`
(`apps/finance/views.py`). Limits: `bank_connect` 5/hour, `bank_disconnect` 10/hour,
`bank_sync` 10/hour (`apps/finance/security.py`). A test reads the source around each view
and fails if a decorator is removed — the audit's original finding was that these controls
existed and were applied to nothing.

## 7. What Finance shares with the conversational model — stated plainly

This is a WLJ privacy obligation, not a Plaid checkbox, and it is described accurately
rather than flatteringly.

**Never leaves WLJ:** Plaid credentials, access tokens, `plaid_transaction_id`, full
account numbers, routing numbers, raw provider payloads, institution logos/colors, import
internals. The truth layer's exposure list is explicit
(`apps/finance/services/finance_domain_truth.py`), and the attribution evidence store is a
**whitelist** capped at 12 keys (`apps/finance/services/attribution.py`).

**Intentionally shared as financial context** when the user asks the Chief of Staff a
Finance question: transaction date, amount, direction, category, payee/description,
account **name**, institution name, and account **last4**, plus entity attribution facts.

These are **deliberately shared minimum facts, not "redacted" data** — the product cannot
answer "which Beacon expenses came off my personal card" without them. Exposure follows
the same Finance enablement as everything else: a user without the capability has no
Finance truth to expose. Logs record neither prompt contents nor these values.

## 8. Auditability

`GET /admin-console/api/claude/finance-audit/` (operator key) reports aggregates only —
counts, booleans, versions, and the resolved dependency set. A test asserts no
description, payee, amount, account number, institution, last4, or email can appear in the
payload.

**Tests:** `apps/finance/tests/test_plaid_trial_security.py` (41), plus
`test_finance_audit.py` and `test_finance_read_only_contract.py`.
