# WLJ HealthKit Coverage Audit & Roadmap

**Status:** Investigation → **Phase A in progress.** Telemetry parity + CI agreement contract landed 2026-07-15.
**Date:** 2026-07-15

> **As-built progress log**
> - **2026-07-15 — Phase A #1 (telemetry parity + categories + CI contract):** `HEALTH_SYNC_TYPES` expanded
>   12 → 37 so every ingested type has freshness/health telemetry; added category grouping (10 categories) as the
>   Health Sync UI foundation; hoisted the canonical `HEALTH_METRIC_HANDLERS` map; added
>   `test_health_sync_registry_contract` enforcing handler-map ↔ registry agreement in CI. Closes §2c gap #1.
>   *Remaining Phase A:* iOS producer gaps (waist, height), characteristic reads (DOB/sex/blood type), sleep-stage
>   end-to-end proof, grouped Health Sync UI rendering.
**Author:** Chief Architect (audit)
**Architectural goal (stated):** *"WLJ should ingest every meaningful HealthKit data type that HealthKit allows for read access."* The product may choose not to surface or actively use a metric today, but it should be available as **deterministic truth** for future capabilities whenever practical.

> This document is a **comparison + gap analysis + roadmap**, produced so we can make intentional, batched product decisions instead of adding metrics one at a time. It does not add any data types.

---

## 1. Method & sources (what was traced, not assumed)

The "current WLJ" side is taken from the **actual code**, not the Health Sync UI screenshots:

| Layer | File | What it establishes |
|---|---|---|
| iOS read authorization | `ios/WLJWrapper/WLJWrapper/Services/HealthKitManager.swift:16-240` (`readTypes`) | The exact `HKObjectType` set passed to `requestAuthorization(toShare:read:)` — **53 `types.insert` calls** |
| iOS fetch functions | same file, `fetch*` funcs (`:543`–`:2360`) | Which authorized types are actually queried |
| Server ingest | `apps/mobile/views.py::process_health_metric:648-754` (`handlers` dict) | The **39 `metric_type` keys** the backend accepts + persists |
| Sync telemetry registry | `apps/health/services/health_sync_status.py::HEALTH_SYNC_TYPES:71-97` | The **12 types** with freshness/health monitoring surfaced to the Health Sync screen |
| Storage models | `apps/health/models.py` | The Django models each metric persists to |

**HealthKit surface** is enumerated against the current SDK (through iOS 18): quantity, category, characteristic, workout, correlation, series, clinical (FHIR), ECG, audiogram, vision, and state-of-mind types.

---

## 2. Current WLJ coverage (authoritative)

### 2a. iOS authorizes 53 read types

**Quantity (46):** `stepCount`, `bodyMass`, `heartRate`, `restingHeartRate`, `bloodGlucose`, `oxygenSaturation`, `dietaryWater`, `activeEnergyBurned`, `distanceWalkingRunning`, `basalEnergyBurned`, `flightsClimbed`, `appleExerciseTime`, `appleStandTime`, `bodyFatPercentage`, `leanBodyMass`, `bodyMassIndex`, `respiratoryRate`, `heartRateVariabilitySDNN`, `vo2Max`, `dietaryCaffeine`, `bloodPressureSystolic`, `bloodPressureDiastolic`, `bodyTemperature`, `walkingAsymmetryPercentage`, `walkingSpeed`, `walkingStepLength`, `walkingDoubleSupportPercentage`, `stairAscentSpeed`, `stairDescentSpeed`, `sixMinuteWalkTestDistance`, `headphoneAudioExposure`, `environmentalAudioExposure`, `appleWalkingSteadiness`, + nutrition: `dietaryEnergyConsumed`, `dietaryProtein`, `dietaryCarbohydrates`, `dietaryFatTotal`, `dietaryFiber`, `dietarySugar`, `dietarySodium`, `dietaryCholesterol`, `dietaryFatSaturated`, `dietaryPotassium`, `dietaryCalcium`, `dietaryIron`, `dietaryVitaminD`.

**Category (6):** `sleepAnalysis`, `mindfulSession`, `highHeartRateEvent`, `lowHeartRateEvent`, `irregularHeartRhythmEvent`, `appleWalkingSteadinessEvent`.

**Workout (1):** `HKObjectType.workoutType()`.

### 2b. Server ingests 39 metric keys

`steps, weight, sleep, heart_rate, blood_glucose, blood_oxygen, water, active_calories, distance, resting_calories, flights_climbed, exercise_minutes, stand_hours, body_fat, bmi, waist, workout, lean_body_mass, respiratory_rate, hrv, vo2_max, caffeine, mindful_minutes, blood_pressure, body_temperature, walking_asymmetry, walking_steadiness, walking_speed, step_length, double_support_time, stair_ascent_speed, stair_descent_speed, six_min_walk, high_heart_rate_event, low_heart_rate_event, irregular_rhythm_event, headphone_audio, environmental_audio, dietary_nutrients`

(`dietary_nutrients` is one payload carrying all 13 authorized macro/micro nutrients.)

### 2c. Three internal gaps found (fix before expanding — see §5 quick wins)

1. **Telemetry gap (biggest):** 39 metric types are ingested, but only **12** are in `HEALTH_SYNC_TYPES` (steps, active_calories, distance, weight, sleep, heart_rate, blood_glucose, blood_oxygen, water, blood_pressure, body_temperature, workout). The other **~27 ingested types have no freshness/health monitoring** — we can't deterministically answer "is HRV / VO2 max / nutrition actually flowing?" This is the same class as the Steps investigation. *Wiring existing-ingest types into the registry is near-zero effort and pure gain.*
2. **`waist` dead path:** the server accepts `waist` (`WaistEntry`), but iOS never authorizes `HKQuantityTypeIdentifierWaistCircumference` and never sends it. Either finish the iOS side or remove the handler.
3. **`bmi` asymmetry:** `bodyMassIndex` is authorized + ingested but not in the telemetry registry; `height` (its natural companion, and a BMI/BSA input) is neither read nor ingested.

**No characteristics read.** WLJ reads **zero** `HKCharacteristicType` — no date of birth, biological sex, blood type, skin type, or wheelchair use. These are one-time static reads with outsized value for personalization and correct calculations (age-adjusted HR zones, sex-specific reference ranges).

---

## 3. Gap analysis (five buckets)

| Bucket | Count (approx) | Summary |
|---|---|---|
| **A. Already synchronized** | 53 read → 39 ingested | Steps, energy, distance, weight/body-comp, HR/resting HR/HRV, SpO₂, BP, respiratory rate, body temp, VO₂ max, sleep, mindful minutes, glucose, water, caffeine, full mobility suite, HR events, audio exposure, macros + key micros, workouts. Strong, above-average coverage. |
| **B. Available in HealthKit, not synchronized** | ~90+ | Characteristics; `height`; `walkingHeartRateAverage`; sport-specific distance/speed/power (cycling, swimming, running dynamics, wheelchair, snow/paddle); `appleMoveTime`; `timeInDaylight`; `uvExposure`; `numberOfTimesFallen`; `appleSleepingWristTemperature`; spirometry; the long micronutrient tail; `insulinDelivery`; `activitySummary` (rings); `lowCardioFitnessEvent`; audio-exposure **events**; `basalBodyTemperature`. |
| **C. Intentionally excluded (today)** | — | See §6. Chiefly the sensitive **reproductive-health** category, and metrics with no plausible near-term WLJ use whose collection would add permission-prompt friction (e.g., snow-sport distances for most users). Excluded ≠ forbidden — revisit per goal. |
| **D. Not appropriate for WLJ** | small | Deprecated identifiers (`nikeFuel`); niche hardware metrics WLJ can't act on. |
| **E. Requires additional architecture** | ~7 families | Clinical records (FHIR + Apple entitlement), ECG voltage series, workout **routes** (GPS series), heartbeat series (beat-to-beat), audiograms, **State of Mind** (iOS 18 mood/emotion), vision prescriptions. Each is a *new sample shape*, not a new row in the existing pipeline. |

---

## 4. Missing-type detail (grouped by domain)

Columns: **ID** = HealthKit identifier (minus the `HKQuantityTypeIdentifier`/`HKCategoryTypeIdentifier` prefix) · **R/RW** = HealthKit read vs read+write (all are readable; RW noted where WLJ could also write) · **Value** = expected business value · **Pri** = High/Med/Low. Long tails (micronutrients, sport variants, symptoms, reproductive) are batched — listing 200 individual rows would obscure the decisions.

### 4a. Characteristics — static, one-time read (HIGH value, trivial effort)

| ID | Name | Domain | Units | R/RW | Value | Pri |
|---|---|---|---|---|---|---|
| `DateOfBirth` | Date of birth → Age | Characteristic | date | R | Age-adjusts HR zones, VO₂max percentile, risk framing; removes manual entry | **High** |
| `BiologicalSex` | Biological sex | Characteristic | enum | R | Sex-specific reference ranges (body-comp, labs, HR) | **High** |
| `BloodType` | Blood type | Characteristic | enum | R | Medical profile completeness (Medical module) | Med |
| `FitzpatrickSkinType` | Skin type | Characteristic | enum | R | UV/sun-exposure context | Low |
| `WheelchairUse` | Wheelchair use | Characteristic | bool | R | Switches activity model to push/wheelchair metrics | Med |
| `ActivityMoveMode` | Move mode (rings) | Characteristic | enum | R | Interprets Move ring as kcal vs minutes | Low |

### 4b. Body measurements

| ID | Name | Units | R/RW | Value | Pri |
|---|---|---|---|---|---|
| `Height` | Height | m/ft | RW | BMI/BSA inputs, ties off the `bmi` asymmetry | **High** |
| `WaistCircumference` | Waist | cm/in | RW | Central-adiposity trend; **server already has the handler** | **High** |
| `AppleSleepingWristTemperature` | Sleeping wrist temp | °F/°C | R | Illness/cycle early-warning; nightly | Med |

### 4c. Cardiac / vitals

| ID | Name | Units | R/RW | Value | Pri |
|---|---|---|---|---|---|
| `WalkingHeartRateAverage` | Walking HR avg | bpm | R | Fitness/recovery signal; cheap add next to HR | **High** |
| `BasalBodyTemperature` | Basal body temp | °F/°C | RW | Fertility/illness; overlaps reproductive privacy | Low |
| `PeripheralPerfusionIndex` | Perfusion index | % | R | Rarely populated; niche | Low |
| `AtrialFibrillationBurden` | AFib burden (iOS 16) | % | R | Cardiac risk; only for AFib-flagged users | Low |
| `LowCardioFitnessEvent` | Low cardio-fitness event | event | R | Pairs with VO₂max already synced | Med |

### 4d. Activity / fitness — everyday (Med) + sport-specific long tail (Low, batch)

| ID | Name | Units | Value | Pri |
|---|---|---|---|---|
| `AppleMoveTime` | Move time | min | Move-ring completeness for non-kcal mode | Med |
| `DistanceCycling` | Cycling distance | mi/km | Cyclists' activity truth | Med |
| `DistanceSwimming` / `SwimmingStrokeCount` | Swimming | m / count | Swimmers | Med |
| `TimeInDaylight` (iOS 17) | Daylight time | min | Circadian/mood/sleep context | Med |
| `NumberOfTimesFallen` | Falls | count | Safety/older-adult signal | Med |
| `DistanceWheelchair` / `PushCount` | Wheelchair activity | mi / count | Accessibility (pairs with `WheelchairUse`) | Med |
| **Running dynamics** (`RunningSpeed, RunningPower, RunningStrideLength, RunningVerticalOscillation, RunningGroundContactTime`) | Running form (iOS 16) | various | Serious runners | Low |
| **Cycling dynamics** (`CyclingSpeed, CyclingPower, CyclingCadence, CyclingFunctionalThresholdPower`) | Cycling power (iOS 17) | various | Serious cyclists | Low |
| **Snow/paddle/row/skate** distance+speed (iOS 18) | Niche sports | various | Small user share | Low |
| `UnderwaterDepth` / `WaterTemperature` | Diving (iOS 16) | m / °C | Very niche | Low |
| `PhysicalEffort` (iOS 17) | Physical effort | MET | Effort context | Low |

### 4e. Nutrition — micronutrient long tail (batch, Low unless nutrition push)

Already synced: energy, protein, carbs, total fat, saturated fat, fiber, sugar, sodium, cholesterol, potassium, calcium, iron, vitamin D, caffeine, water. **Not synced (batch as "full micronutrient panel"):** `DietaryFatMonounsaturated`, `DietaryFatPolyunsaturated`, `DietaryVitaminA/C/E/K/B6/B12/Thiamin/Riboflavin/Niacin/Folate/Biotin/PantothenicAcid`, `DietaryMagnesium`, `DietaryZinc`, `DietaryPhosphorus`, `DietaryCopper`, `DietaryManganese`, `DietarySelenium`, `DietaryChromium`, `DietaryMolybdenum`, `DietaryIodine`, `DietaryChloride`. **R/RW** (WLJ could write). **Value:** completeness for a future nutrition-intelligence feature. **Pri:** Low now (High *if* a micronutrient feature ships) — cheap because `dietary_nutrients` is already a single extensible payload.

### 4f. Respiratory / environmental

| ID | Name | Units | Value | Pri |
|---|---|---|---|---|
| `ForcedVitalCapacity`, `ForcedExpiratoryVolume1Second`, `PeakExpiratoryFlowRate`, `InhalerUsage` | Spirometry / asthma | L, L/min, count | Respiratory-condition users (Medical module) | Med |
| `UVExposure` | UV exposure | count | Sun-safety context | Low |
| `EnvironmentalSoundReduction` (iOS 16) | Noise reduction | dB | Hearing context | Low |
| `HeadphoneAudioExposureEvent`, `EnvironmentalAudioExposureEvent` | Loud-audio events | event | Hearing alerts (levels already synced) | Med |

### 4g. Mental / sleep

| ID | Name | Domain | Value | Pri |
|---|---|---|---|---|
| `StateOfMind` (iOS 18, `HKStateOfMindType`) | Mood / emotion logging | Mental (new class) | Directly feeds WLJ mood/journal/faith intelligence | **High** (but §E architecture) |
| `SleepAnalysis` stage granularity | Core/Deep/REM/Awake | Sleep | Already authorized — verify stages are parsed, not just in-bed vs asleep | **High** (verify) |

### 4h. Symptoms — 40 category types (batch)

`Fatigue, Headache, Nausea, Dizziness, Fever, Chills, Coughing, ShortnessOfBreath, ChestTightnessOrPain, Heartburn, Bloating, Constipation, Diarrhea, MoodChanges, SleepChanges, HotFlashes, NightSweats, MemoryLapse, …` (~40). **Domain:** symptoms. **R/RW.** **Value:** structured symptom tracking that would plug into the Medical module and CoS health reasoning. **Pri:** Med as a **batch** (one symptom-tracking model + a category-type loop), Low individually.

### 4i. Reproductive health — sensitive (batch, product+privacy decision)

`MenstrualFlow, IntermenstrualBleeding, Irregular/Infrequent/ProlongedMenstrual*, OvulationTestResult, CervicalMucusQuality, SexualActivity, Contraceptive, Pregnancy, PregnancyTestResult, Lactation, ProgesteroneTestResult, BasalBodyTemperature`. **Value:** significant for a subset; **requires an explicit privacy/product stance** (extra Info.plist usage strings, sensitive-data handling). **Pri:** Deferred — decision, not effort.

### 4j. Requires additional architecture (new sample shapes)

| ID / type | Name | Why it's not a pipeline row | Value | Pri |
|---|---|---|---|---|
| `HKClinicalType` (allergy, condition, immunization, labResult, medication, procedure, vitalSign, coverage, clinicalNote) | Clinical records (FHIR) | Needs Apple **Health Records entitlement** + FHIR parsing + provenance model | Very high for Medical module | Med (big) |
| `HKElectrocardiogramType` | ECG | Voltage-series sample + classification, not scalar | Cardiac | Low (big) |
| `HKWorkoutRoute` | Workout GPS route | Location series tied to workout | Maps/insights (WLJ has Places) | Med (big) |
| `HKHeartbeatSeriesType` | Beat-to-beat series | High-frequency series storage | Advanced HRV | Low (big) |
| `HKAudiogramSampleType` | Audiogram | Frequency/ear structured sample | Hearing health | Low (big) |
| `HKVisionPrescriptionType` (iOS 16) | Glasses/contacts Rx | Structured prescription | Medical profile | Low (big) |
| `HKActivitySummary` | Move/Exercise/Stand ring goals | Summary object, not a sample query | Ring completion truth (partly derivable) | Med (small–med) |

---

## 5. Recommendations grouped by implementation effort

### Tier 0 — Quick wins (hours; no new architecture) — **do these first**
1. **Wire the ~27 already-ingested types into `HEALTH_SYNC_TYPES`** so every synced metric has freshness/health telemetry (closes the §2c #1 gap; same class as the Steps blind-spot). Pure registry rows.
2. **Characteristics flow** (DOB, biological sex, blood type, skin type, wheelchair use): a small one-time static read on authorize → store on the user/health profile. High personalization payoff.
3. **`Height`** + **finish `WaistCircumference`** on iOS (server handler already exists). Closes the BMI/waist asymmetry.
4. **`WalkingHeartRateAverage`**, **`AppleMoveTime`**: trivial adds beside existing HR/energy.
5. **Verify sleep-stage parsing** (Core/Deep/REM/Awake) is actually captured, not collapsed to asleep/in-bed.

### Tier 1 — Small (existing pipeline: identifier + handler + model field + registry row)
- Everyday activity: `DistanceCycling`, `DistanceSwimming`/`SwimmingStrokeCount`, `DistanceWheelchair`/`PushCount`, `TimeInDaylight`, `NumberOfTimesFallen`, `AppleSleepingWristTemperature`, `LowCardioFitnessEvent`, audio-exposure **events**.
- **Full micronutrient panel** via the existing `dietary_nutrients` payload (cheap; gate on a nutrition feature).
- `InsulinDelivery` (pairs with existing glucose/Dexcom).

### Tier 2 — Medium (new model or structured sample class)
- **Symptoms** (one symptom model + 40-type category loop) → Medical module + CoS reasoning.
- **State of Mind** (iOS 18 mood/emotion) → mood/journal/faith intelligence. New sample class.
- **Spirometry** (`ForcedVitalCapacity`, `FEV1`, `PeakExpiratoryFlowRate`, `InhalerUsage`).
- **Running/cycling dynamics** as an opt-in "advanced training" batch.
- `HKActivitySummary` (rings) reader.

### Tier 3 — Large (new architecture / entitlements / product+privacy stance)
- **Clinical records (FHIR)** — needs Apple Health Records entitlement; highest medical value, biggest lift.
- **ECG**, **Workout routes (GPS)**, **Heartbeat series**, **Audiograms**, **Vision prescriptions**.
- **Reproductive health** — a privacy/product decision before any code.

---

## 6. Roadmap (phased, so decisions are batched)

- **Phase A — Instrument what we already have.** Tier 0 #1 (registry) + #5 (sleep-stage verify). Zero new permissions; makes current coverage trustworthy and observable. *This is the direct continuation of the Steps investigation.*
- **Phase B — Complete the "obvious" body & activity truth.** Characteristics, height, waist, walking HR, move time, everyday distances. One coordinated iOS auth-set expansion + server handlers + registry rows.
- **Phase C — Batch the long tails as opt-in domains.** Full micronutrient panel (with a nutrition feature), symptoms (with Medical), advanced training dynamics. Each shipped as a *domain*, not individual metrics.
- **Phase D — New sample shapes.** State of Mind, spirometry, activity summary.
- **Phase E — Heavy architecture / decisions.** Clinical/FHIR (entitlement), ECG, routes, audiograms, reproductive health (privacy stance first).

### Guardrails (so "ingest everything" stays safe)
- **Permission friction:** every new read type widens the HealthKit prompt. Group additions into deliberate auth-set revisions (Phases B–D), each with the required `Info.plist` usage strings — don't drip single types.
- **Request-path safety:** all ingest stays in the async sync path; new types must not add request-path compute (per `docs/WLJ_REQUEST_PATH_SAFETY.md`).
- **Telemetry is mandatory:** no new ingested type ships without a `HEALTH_SYNC_TYPES` row (the fix in Phase A becomes the standing rule).
- **Sample-time integrity:** body-composition-style types must preserve the real HealthKit sample instant (`_sample_dt`), never a noon default (see `healthkit_sample_timestamp` precedent).
- **Sensitive data:** reproductive health and clinical records require an explicit privacy decision and their own consent copy before implementation.

---

## 7. Bottom line

WLJ's HealthKit coverage is already **strong** (53 authorized reads, 39 ingested) — well beyond most consumer apps. The highest-leverage next step is **not** more metrics; it's **Phase A: making the metrics we already ingest observable** (wire the ~27 orphaned ingest types into the telemetry registry) and **closing the three internal gaps** (characteristics, height/waist, BMI). After that, expansion toward the stated "ingest everything readable" goal should proceed **in batched domain phases** (B → E), each a single deliberate auth-set revision with mandatory telemetry — never one metric at a time.
