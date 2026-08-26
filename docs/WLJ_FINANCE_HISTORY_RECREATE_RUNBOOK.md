# Runbook — obtaining a longer transaction-history window

> **Status:** PREPARED, NOT EXECUTED. Requires Danny's explicit authorization.
> **Destructive:** yes — it revokes provider access to a real bank Item.
> **Date:** 2026-08-26

---

## The invariant this exists to work around

Plaid decides an Item's transaction-history window **once, when the Item is created**, from
`transactions.days_requested` on the Link token. After the Transactions product initializes on that Item,
**`days_requested` has no effect** — not on a later sync, and **not through Link update mode**.

- https://plaid.com/docs/api/products/transactions/
- https://plaid.com/docs/transactions/troubleshooting/

**Update mode repairs an Item; it does not widen history.** Plaid will still *accept* an update-mode Link
token carrying `days_requested`, which is exactly the trap: a `200` proves the request was well-formed and
says nothing about coverage. WLJ therefore never sends it in update mode, and never offers an
"extend history" action, because the operation does not exist.

**Consequence:** a longer window for an existing Item means **a new Item** — remove the old one, connect
again. That is destructive and externally revokes access, so it is a runbook, not a button.

---

## Current versus desired

| | |
|---|---|
| Requested at creation | **90 days** (the provider default — `days_requested` was never sent) |
| Actually imported | **73 transactions, 2026-05-29 → 2026-08-24 (87 days)** |
| Complete for that window | **Yes** — `has_more=false`, durable cursor, successful update |
| Desired | 2025 + 2026 → **730 days** (the provider maximum) |
| Reachable without a new Item | **No** |

New Items already request 730 (`TRANSACTION_HISTORY_DAYS_REQUESTED`), so this is a one-time correction for
the Item created before that fix.

---

## Before anything is removed

1. **Inventory** — `python manage.py finance_reset` (dry-run; deletes nothing) plus
   `GET /admin-console/api/claude/finance-audit/`. Confirm exactly **one** connection and **four** accounts.
2. **Attribution loss check** — count `TransactionAttribution` rows with `user_confirmed=True` and
   `AttributionRule` rows. **Any confirmed attribution or rule is human work that the recreate destroys**,
   because it is anchored to transactions that will be deleted. At the time of writing there are **zero** of
   each, which is why now is the cheapest possible moment. If that is ever non-zero, stop and reconsider.
3. **Trial quota** — removing an Item does **not** return its slot: Plaid's Free Trial counts Items
   *created*, not currently active. Recreating therefore consumes **a second of the ten**. Confirm the live
   number on the Plaid dashboard (Team Settings → Billing / Usage) before proceeding; if the dashboard shows
   the quota is tight, the 87-day window may be the better trade.

---

## The operation, in order

Order is not cosmetic. **Revoke first, delete second.** Deleting locally before Plaid confirms revocation
strands the provider's access to a real bank with the only revocation credential destroyed.

1. **Revoke at the provider** — `provider_disconnect.revoke_and_disconnect(connection)`. This calls
   `/item/remove` and clears the local token **only** on confirmation; on failure it keeps the token, marks
   `revocation_pending`, and raises. **Do not continue past a failure.**
2. **Verify revocation** — connection status `disconnected`, `access_token_encrypted` empty.
3. **Delete local provider-derived data** — `python manage.py finance_reset --confirm RESET-FINANCE --by <staff email>`.
   Removes accounts, transactions, imports, cursor, connection, entities, assignments, attributions, rules,
   opportunities, insights, notifications, and the SAE finance key; **refuses to run while any provider token
   remains**, which is the safety interlock for step 1.
4. **Preserved by that command, verified by test:** all users and auth · `finances_enabled` · the 21 global
   categories · encryption keys and Plaid configuration · migrations · every non-Finance domain · one
   redacted audit row recording the reset.
5. **Reconnect** — ordinary Link at `/finance/connections/`. The new Item requests **730 days** at creation.
   No special flow; the OAuth return route handles First Horizon's redirect.
6. **Let the institution decide.** 730 is what WLJ *asks* for. Many banks expose less regardless, so the
   result may be under two years — that is the institution's limit, not a bug, and the recorded coverage
   will state whatever actually arrived.

---

## Verification after reconnecting

- exactly **one** connection; **no duplicate accounts** (distinct `plaid_account_id` == account count);
- token stored **encrypted**;
- cursor present and durable; a second sync adds **nothing** (idempotency);
- coverage reported as counts + earliest/latest date only;
- `history_days_requested = 730` recorded, and the UI showing *Initial data loaded* until a genuine
  `HISTORICAL_UPDATE` webhook arrives — **never** relabelled complete before then;
- webhook signature verified on the first genuine delivery (still unproven against live Plaid).

---

## What is deliberately NOT built

- **No "extend history" action.** It cannot work, and a button that quietly does nothing is worse than none.
- **No `days_requested` in update mode.** Sending it would encode a promise the provider does not make.
- **No `/transactions/refresh`.** Separately billed, and it refreshes *recency*, not the history window.
