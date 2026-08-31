# Terra vs Direct Renpho — Engineering Evaluation

**Status:** Investigation only. No code, no accounts, no WLJ changes.
**Date:** 2026-07-19
**Primary question:** *Can Terra become the canonical ingestion path for complete Smart Tape body-circumference sessions?*
**Answer:** **NO.** Terra's normalized data model has **zero** circumference fields.

---

## The decisive evidence (authoritative, not marketing)

I read Terra's own published OpenAPI v2 spec (`tryterra/openapi` → `dist/core/v2-bundled.yaml`,
9,903 lines) and enumerated the entire Body model.

- **`MeasurementDataSample`** (the per-measurement record inside Terra's Body payload) has exactly
  these fields:
  `measurement_time, BMI, BMR, RMR, estimated_fitness_age, skin_fold_mm, bodyfat_percentage,
  weight_kg, height_cm, bone_mass_g, muscle_mass_g, lean_mass_g, water_percentage, insulin_units,
  insulin_type, urine_color, user_notes, visceral_fat_level, visceral_fat_category`.
- **`MeasurementsData`** adds only day-averages of those same body-composition metrics.
- **`grep -ciE "circumference|girth"` over the entire 9,903-line spec = `0`.**

There is **no** neck, shoulder, chest, waist, abdomen, hip, arm, forearm, thigh, calf, or
waist-to-hip field **anywhere** in Terra's schema. Terra normalizes every provider into this
unified model; a value with no field in the model is not delivered. **Therefore Terra structurally
cannot represent a Smart Tape circumference session, regardless of which Renpho app it connects to.**

This is dispositive and makes several sub-questions moot — but they're answered below for completeness.

---

## Success-criteria answers

| # | Question | Answer |
|---|---|---|
| 1 | Terra supports current **RENPHO Health** platform? | **UNKNOWN** (Terra docs don't state app-version; the Renpho integration is described only as "body composition from Renpho **smart scales**"). **Moot** — see #2. |
| 2 | Terra supports **Smart Tape** measurement **sessions**? | **NO.** No circumference fields exist in Terra's model; the Renpho connector is documented as smart-**scale** body-composition only. |
| 3 | All body **circumference** measurements available? | **NO** — none of them. |
| 4 | Complete sessions or individual values? | **Neither, for circumferences.** Terra exposes body-**composition** samples (weight/fat/lean/BMI/BMR…) keyed by `measurement_time`, plus day-averages. Zero girth data at any granularity. |
| 5 | Eliminates need to reverse-engineer RENPHO Health? | **NO** for the actual goal. Terra would only re-supply weight/body-composition — which **Apple Health already provides for free**. It does nothing for the circumferences that motivated this entire effort. |
| 6 | Recommend Terra over our own integration? | **NO.** It doesn't carry the data we need, and it adds a **$400–500/mo floor + vendor lock-in** to deliver data we already get from HealthKit. |
| 7 | If Terra can't provide complete Smart Tape data, what's missing? | **Every circumference:** neck, shoulder, chest, waist, abdomen, hip, left/right arm, left/right forearm, left/right thigh, left/right calf, WHR — plus their timestamps, units, record/session identifiers, and device/source metadata for girth. |

## What Terra *does* provide (and why it's the wrong problem)

Weight, body-fat %, lean/muscle/bone mass, BMI, BMR/RMR, water %, visceral fat — i.e. Renpho
**scale** body composition. WLJ **already receives** the scale's body composition (and Waist
Circumference) via Apple Health today. Terra would replace a working, free path with a paid one and
**still leave the circumference gap 100% open.** The one metric HealthKit carries (Waist) is coincidentally
the one Terra also lacks a dedicated field for — Terra models waist only as `bodyfat`/composition, not girth.

## Authentication (for completeness)

- Users connect via Terra's **widget/SDK**; Terra brokers the provider connection and holds the
  provider session. **WLJ would never store Renpho credentials** — WLJ holds only a Terra `user_id`
  and receives Terra webhooks. (Good property — but moot here.)
- Refresh/token handling is Terra's responsibility, opaque to WLJ.

## Synchronization (for completeness)

- **Push webhooks** (Renpho → Terra → POST normalized JSON to your endpoint) **plus** pull with
  `start_date`/`end_date` for historical/backfill. Incremental + historical both supported.
  All irrelevant given the payload lacks circumferences.

## Pricing (why it's also economically wrong here)

- **No free tier.** **Floor ≈ $399/mo (annual) to $499/mo (Quick Start).** 100k credits/mo included;
  overage $0.005/credit (→$0.003 above 1M). Billed on **authenticated users**; first 400 events/user free.
- Rough WLJ cost (dominated by the monthly floor at low scale):
  - **100 users:** ~**$399–499/mo** (floor) — ~$4–5/user/mo for data we already get free.
  - **1,000 users:** ~**$500/mo** (still near floor; well within 100k credits).
  - **10,000 users:** low-to-mid **four figures/mo** once events exceed the free allowance.
  - **50,000 users:** solidly **four–five figures/mo**.
  - Paying **anything** for a source that omits the target data is a non-starter.

## Operational risk — Terra vs direct

| Dimension | Terra | Direct RENPHO Health |
|---|---|---|
| Carries the needed data | **No (fatal)** | TBD (pending capture gate) |
| API stability | High (documented, versioned) | Low (unofficial, drifts) |
| Vendor lock-in | High (paid intermediary) | None |
| Maintenance | Low (Terra maintains) | High (we maintain) |
| Security | Good (no creds in WLJ) | Sensitive (creds/session custody) |
| Engineering effort | Low | High |
| **Net for our goal** | **Disqualified — wrong data** | **Only path that could carry circumferences** |

Terra wins every engineering dimension **except the only one that matters**: it does not carry
Smart Tape circumferences.

## Architecture note (moot, but as requested)

Had Terra carried girths, the clean fit would have been: Terra webhook → a thin WLJ ingestion
adapter (peer of the HealthKit path) → normalize into canonical Body circumference truth →
Body Intelligence consumes it unchanged. WLJ still owns deterministic truth; Terra is just another
arrival source. **This is exactly how a future direct-RENPHO adapter should also plug in** — the
ingestion seam is the same; only the source differs.

---

## Recommendation — **not Terra**

Of the three options:

1. ~~Use Terra~~ — **rejected.** Proven by Terra's own schema to omit all circumference data.
3. Investigate another aggregator — **low value.** Aggregators (Spike, etc.) normalize wearables
   into body-**composition** schemas just like Terra; anthropometric girths are niche and almost
   certainly absent there too. Not worth a dedicated gate unless one explicitly advertises tape/girth.
2. **Continue the direct RENPHO Health investigation — the only path that can carry the data.**

**Recommendation: (2), with eyes open.** The direct path is already gated on the HTTPS-capture
pinning check we staged. Two honest outcomes:
- **No pinning** → the Health backend/girths endpoint can likely be reproduced read-only → viable.
- **Pinning** → complete Smart Tape sessions may not be safely automatable at all, and the pragmatic
  fallback is: keep Waist via HealthKit + **manual entry** for the other circumferences until Renpho
  (or a future integration) exposes them. That would be a legitimate product decision, not a failure.

**Bottom line:** Terra cleanly solves the *body-composition* problem we don't have (HealthKit already
does) and does nothing for the *circumference* problem we do have. Do not adopt Terra for this.

---

## Evidence / Sources
- Terra OpenAPI v2 spec (authoritative field list; `grep circumference|girth = 0`) — https://github.com/tryterra/openapi/blob/master/dist/core/v2-bundled.yaml
- Terra Body data model reference — https://docs.tryterra.co/reference/health-and-fitness-api/data-models
- Terra Renpho integration (scale body-composition, webhook + pull) — https://tryterra.co/integrations/renpho
- Terra pricing (floor, credits, overage, per-authenticated-user) — https://docs.tryterra.co/health-and-fitness-api/pricing , https://tryterra.co/pricing
- Terra auth widget/SDK (Terra brokers provider connection) — https://docs.tryterra.co/health-and-fitness-api/user-authentication
