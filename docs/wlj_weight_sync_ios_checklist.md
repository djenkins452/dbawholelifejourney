# Apple Health Weight Sync — iOS Troubleshooting Checklist

**Context (2026-05-28):** Dashboard/Beth reported "No weight entry in 25 days"
while the weight screen's latest entry was May 3, 2026. Investigation proved
the read layer is correct (weight screen, SAE state, and the accountability
rule all read the same `WeightEntry` / `recorded_at` / `status=active` query
and agree). The failing layer is **ingestion**: WLJ receives weight via a
**push-only** path (the iOS app POSTs to `/api/health/ingest/`) — there is no
server-side pull. So if the phone stops POSTing, weight silently stops with no
server error.

## What Danny needs to check on the iPhone

Work top-to-bottom; the most common cause is #1 or #2.

1. **WLJ app sign-in / token expiry.** Mobile auth tokens expire
   (`MobileAuthToken.expires_at`). If the token expired, the app's health
   POSTs get rejected and nothing arrives.
   → Open the WLJ app. If it shows a login/re-auth prompt, sign in again to
   mint a fresh token.

2. **Apple Health permission for Weight.** iOS Settings → Privacy & Security
   → Health → WLJ → confirm **Weight (Body Mass)** read access is ON.
   (Also check it under the WLJ app's own Health settings.)
   → If it was turned off, turn it on. iOS may require re-granting after an
   app update.

3. **Open the app to force a sync.** Background delivery can stop if the app
   hasn't been foregrounded in a while. Open WLJ and pull-to-refresh / visit
   the Health section to trigger a fresh ingest POST.

4. **Scale → Apple Health link.** Confirm the third-party scale app is still
   writing to Apple Health (Health app → Browse → Body Measurements → Weight
   → check for entries after May 3). If the scale itself stopped writing to
   Apple Health, fix that first — WLJ can only ingest what reaches Apple
   Health.

5. **Re-link if needed.** If 1–4 look fine but no data flows, sign out of the
   WLJ app and sign back in to fully re-establish the device + token + HealthKit
   authorization.

## How to confirm it's fixed

After re-establishing sync, open WLJ `/dashboard/` (or the weight screen). Once
a new entry ingests:
- the weight screen shows an entry dated after May 3,
- the dashboard/Beth gap message clears,
- SAE `weight_sync_stale` flips back to `false`.

## Server-side evidence

The read-only diagnostic migration `apps/mobile/migrations/0002_diagnostic_weight_sync.py`
logs (grep deploy logs for `[WEIGHT_SYNC_DIAG]`):
- latest `WeightEntry` overall + per source (manual vs apple_health),
- entry counts in the last 30 days,
- last 10 `HealthIngestionRun` rows (status, timestamps, metrics created),
- `MobileDevice` active/last-seen and `MobileAuthToken` expiry/last-used.

Read those lines to pinpoint **why** the push stopped (expired token vs.
revoked permission vs. app not opened).

## Regression protections now in place

- **Source-aware accountability:** when recent weight came from Apple Health
  and a device is active, a multi-day gap is reported as
  *"Apple Health weight sync may have stopped (last synced …)"* — NOT
  *"you haven't logged weight."* (`MissingWeightLoggingRule`,
  `apps/health/services/weight_sync.py`.)
- **Staleness signal in SAE:** `health.weight_sync_stale`,
  `weight_last_synced_at`, `weight_sync_source`, `weight_sync_gap_days` —
  one canonical signal both dashboard and Beth read, so a future gap is
  surfaced proactively and the two surfaces can never disagree.
