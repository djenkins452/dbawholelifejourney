# WLJ Domain & Data Catalog — Part A (Health, Medical, Meals, Faith, Journal)

> **Scope:** Grounded, read-only knowledge extraction for five WLJ domains. Every claim is proven with `file:line` references against the live codebase at `/Users/dannyjenkins/Projects/dbawholelifejourney`. Where the framing docs (`docs/DOMAIN_INTELLIGENCE_ARCHITECTURE.md`, `docs/DOMAIN_TRUTH_CONTRACTS.md`, `docs/DOMAIN_SIGNAL_CHECKLIST.md`, `@WLJ_SYSTEM_PROMPTS/03_REFERENCE/WLJ DOMAIN REGISTRY.md`) claim something not found in code, it is flagged as **"claimed in docs, not located in code."**
>
> **Method note:** Models, services, signal rules, URLs, templates, and cross-domain imports were located via `grep`/`Read` against the actual source. `.bak` / `.bak2` files were ignored. Line numbers reflect the state of the repo at extraction time.

---

## Table of Contents

1. [HEALTH](#1-health) — `apps/health/`
2. [MEDICAL](#2-medical) — `apps/medical/`
3. [MEALS](#3-meals) — `apps/meals/`
4. [FAITH](#4-faith) — `apps/faith/`
5. [JOURNAL](#5-journal) — `apps/journal/`
6. [Cross-Domain Map (consolidated)](#6-cross-domain-map-consolidated)
7. [Notable Gaps (docs claims vs. code)](#7-notable-gaps-docs-claims-vs-code)

---

# 1. HEALTH

**App:** `apps/health/` · **Registry classification:** Behavioral Domain · **Signal renderer priority:** `foundational` (`apps/core/signals/signal_renderer.py:53`)

## 1.1 Purpose

Health is the largest WLJ domain (`apps/health/models.py` is ~6,395 lines) and tracks the full physical-wellness surface: weight, body composition, sleep, glucose/CGM, vitals (BP, HR, SpO2, temperature, respiratory rate), activity/steps, hydration, nutrition/food logging, fasting, fitness/workouts, medicine & supplements ("Intake"), menstrual cycle, and a transformation-protocol overlay. It computes composite daily scores (health score, recovery score) and exposes deterministic snapshot/summary state for the Chief of Staff (CoS) pipeline. It is the only domain in Part A with native UAIO intents and PRIE predictions registered in code.

## 1.2 Primary Models (`apps/health/models.py`)

| Model | Line | Key fields |
|-------|------|-----------|
| `WeightEntry` | 519 | `value`, `unit` (lb/kg), `recorded_at`, `body_fat_percentage`, `lean_body_mass`, `notes` |
| `FastingWindow` | 598 | `fasting_type`, `started_at`, `ended_at`, `target_hours`, `notes`, `is_active` (prop) |
| `HeartRateEntry` | 713 | vitals pattern (value, recorded_at, source) |
| `StepsEntry` | 760 | activity pattern |
| `WaterEntry` | 874 | hydration pattern |
| `GlucoseEntry` | 1054 | `value`, `unit`, `context` (fasting/before_meal/after_meal/cgm), `recorded_at`, `source` (manual/dexcom/apple_health), `dexcom_record_id`, `trend`, `trend_rate` |
| `BloodPressureEntry` | 1232 | `systolic`, `diastolic`, `pulse`, `context`, `arm`, `position`, `recorded_at` |
| `BodyTemperatureEntry` | 1344 | vitals pattern |
| `BloodOxygenEntry` | 1436 | vitals pattern |
| `Exercise` | 1538 | canonical exercise catalog |
| `WorkoutSession` | 1660 | `date`, `name`, `duration_minutes`, `session_mode`, `intensity`, `workout_type`, `calories_burned`, `distance_miles`, `avg_heart_rate`, `started_at`, `completed_at`, `from_template`, `source` |
| `WorkoutExercise` | 1854 | join WorkoutSession↔Exercise |
| `ExerciseSet` | 1905 | `set_number`, `weight`, `reps`, `duration_seconds`, `bodyweight_used`, `is_warmup`, `is_pr` |
| `PersonalRecord` | 2087 | `exercise`, `weight`, `reps`, `duration_seconds`, `achieved_date`, `workout_session`, `pr_type`, `previous_value` |
| `WorkoutTemplate` | 2175 | reusable workout blueprint |
| `Intake` | 2282 | **unified medication + supplement** model: `name`, `dose`, `purpose`, `frequency`, `intake_type` (medication/supplement), `category`, `priority`, `status` |
| `IntakeSchedule` | 2609 | scheduling metadata for Intake |
| `IntakeLog` | 2732 | dose taken, time, adherence |
| `FoodItem` | 3032 | canonical food DB |
| `CustomFood` | 3182 | user-defined foods |
| `FoodEntry` | 3230 | `food_item` (FK), `food_name`, `food_brand`, `quantity`, `logged_date`, `meal_type`, `source`, snapshot nutrition fields |
| `DailyNutritionSummary` | 3512 | per-day macro/micro aggregate |
| `MedicalProvider` | 3619 | doctor/specialist contacts (note: lives in **health**, not medical) |
| `ProviderStaff` | 3816 | provider staff directory |
| `NutritionGoals` | 3894 | `daily_calorie_target`, `daily_protein_target_g`, `daily_carb_target_g`, `daily_fat_target_g`, `daily_fiber_target_g`, `daily_sodium_limit_mg`, `daily_sugar_limit_g` |
| `DexcomCredential` | 3996 | CGM API auth |
| `SleepEntry` | 4161 | `sleep_date`, `bedtime`, `wake_time`, sleep-stage minutes, `quality`, `source` |
| `BodyCompositionEntry` | 4592 | `metric_name`, `value`, `unit`, `measurement_date`, `source` |
| `InsightResult` | 4863 | persisted insight + rule metadata |
| `TransformationProtocol` | 4932 | `name`, `protocol_type`, `start_date`, `target_end_date`, `is_active`, `goal_weight`, `goal_body_fat`, `life_goal` (FK→purpose.LifeGoal) |
| `WorkoutPlan` | 5063 | transformation planning |
| `WorkoutSchedule` | 5124 | recurring workout days |
| `WorkoutScheduleLog` | 5177 | workout schedule execution |
| `MealTemplate` | 5305 | saved meal blueprint |
| `MobilityEntry` | 5475 | flexibility / ROM |
| `HeartRateEventEntry` | 5623 | elevated/anomalous HR events |
| `AudioExposureEntry` | 5703 | environmental noise |
| `DietaryNutrientEntry` | 5801 | micronutrient tracking |
| `DailyHealthSummary` | 5956 | **canonical daily rollup** — `summary_date`, `recovery_score`, `recovery_drivers`, `health_score`, `health_score_drivers`, per-domain `has_*` completeness |
| `MealGlucoseResponse` | 6306 | meal→glucose correlation |
| (cycle) `CycleSettings` 18 · `CycleDailyLog` 183 · `Cycle` 301 · `CyclePrediction` 402 | — | menstrual cycle tracking |

> **Note on the medicine/medication split:** there is **no `Medication` model** in either `apps/health` or `apps/medical`. Medications and supplements are unified under `Intake` (`apps/health/models.py:2282`), differentiated by `intake_type`.

## 1.3 Canonical State / "current state" computation

**Composite scores & daily rollup (background-computed, deterministic):**
- `HealthScoreService.compute()` — `apps/health/services/health_score.py:41` — composite 0–100 health score (sleep/recovery/glucose/weight/workout/nutrition/activity weights); returns `(score, drivers)`.
- `RecoveryScoreService.compute()` — `apps/health/services/recovery_score.py:30` — 0–100 recovery score (sleep, HRV, resting HR, training load, glucose); returns `(score, drivers)`.
- `DailyHealthSummaryBuilder.build_for_date()` — `apps/health/services/daily_summary_builder.py:39` — aggregates ~15 source tables into one `DailyHealthSummary` row per user/date (idempotent upsert). `build_range()` at `:145`.
- `ScorePipeline.compute_scores()` — `apps/health/services/score_pipeline.py:20` — orchestrates recovery + health score after summary build.

**Snapshot builders (CoS / SAE-facing deterministic state):**
- `build_glucose_latest()` `:102`, `build_glucose_summary()` `:168`, `build_glucose_proxy_answer()` `:319` — `apps/health/services/glucose_snapshot.py` (latest reading hard-split from 7/14/30/90-day aggregates; no fallback).
- `build_body_composition_snapshot()` — `apps/health/services/body_composition_snapshot.py:150` — latest vs prior deltas + trend.
- `compute_body_composition_trend()` — `apps/health/services/body_composition_signal.py:58` — fat-loss quality / muscle-loss risk / plateau verdict + evidence.
- `build_cos_health_intelligence()` `:21` and `build_cos_health_summary_text()` `:239` — `apps/health/services/cos_health_context.py` — CoS health context + briefing text.

**Truth-contract query classes (per `docs/DOMAIN_TRUTH_CONTRACTS.md`):**
- `WorkoutQueries.completed_on()` / `completed_in_range()` — `apps/health/services/workout_queries.py:57`.
- `FastingQueries.current_active()` `:17`, `compliance_score_7d()` `:52` — `apps/health/services/fasting_queries.py`.
- `NutritionQueries.entries_on_date()` `:76`; `build_meal_signals()` `:20` — `apps/health/services/nutrition_queries.py`.
- `calculate_medicine_adherence()` `:19`, `calculate_medicine_adherence_rate()` `:188` — `apps/health/medicine_utils.py`.

## 1.4 Signal Outputs

**PIE insight rules:**
- `apps/core/ai_insights/rules_health.py` — `WeightTrendUpRule:26`, `WeightTrendDownRule:102`, `MissingWeightLoggingRule:174`.
- `apps/core/ai_insights/rules_body_composition.py` — `MissingBodyCompRule:53`, `BodyFatChangeRule:114`.
- `apps/core/ai_insights/rules_transformation.py` — `NutritionCalorieTrendRule:29`, `ProteinDeficitRule:100`, `CarbGlucoseCorrelationRule:163`, `FastingConsistencyRule:252`, `WorkoutConsistencyRule:351`, `StrengthPlateauRule:451`, `TransformationMomentumRule:744`.
- `apps/core/ai_insights/rules_labs_vitals.py` — `RepeatedOutOfRangeRule:17` (vitals path; also serves Medical labs).

**PRIE prediction rules:**
- `WeightProjectionRule` — `apps/core/ai_predictions/prediction_rules_health.py:19` (30/60/90-day linear projection). **Confirmed present in code** (docs claim verified).
- `BodyFatProjectionRule:22`, `LeanMassProjectionRule:107` — `apps/core/ai_predictions/prediction_rules_bodycomp.py`.

**Composed signal builders (`apps/core/signals/health_signals.py`):**
- `build_health_signals()` `:468` (entry) → `_signal_med_adherence()` `:94`, `_signal_sleep_recovery()` `:155`, `_signal_activity_momentum()` `:209`, `_signal_cardio_stability()` `:265`, `_signal_body_composition()` `:338`, `_signal_metabolic_efficiency()` `:422`.

**Django model signals (`apps/health/signals.py`):**
- `handle_medicine_schedule_saved()` `:24` / `_deleted()` `:42` — projects `IntakeSchedule` to calendar_engine.
- `handle_workout_schedule_saved()` `:57` / `_deleted()` `:75` — projects `WorkoutSchedule` recurring calendar event.
- `resolve_stale_weight_insights_on_new_entry()` `:90` — dismisses `missing_weight_logging` on new `WeightEntry`.

**Signal renderer entries:** `apps/core/signals/signal_renderer.py` maps `("health", "glucose_high"/"glucose_elevated"/"glucose_low"/"blood_pressure_high", …)` (around `:130`+).

## 1.5 Major Services

`command_center_api.py` (`CommandCenterAPI.get_dashboard_data` `:25`) · `body_composition_intelligence.py` (`compute_daily_intelligence` `:1184`) · `body_composition_insight_builder.py` (`build_body_comp_insight` `:27`) · `correlation_service.py` (`CorrelationService.compute` `:63`, glucose↔nutrition) · `protein_service.py` · `trend_analyzer.py` · `double_progression.py` · `fitness_progression.py` · `conflict_detection.py` · `dexcom.py` (CGM API) · `fatsecret.py` (food DB) · `weight_sync.py` · `health_priority_service.py` · `health_coaching_builder.py`.

## 1.6 APIs / Endpoints (`apps/health/urls.py`)

Routes are nested under `/health/physical/` (legacy `/health/*` 301-redirects). Representative view names: `HealthHomeView`, `WeightListView` / `WeightCreateView` / `WeightUpdateView`, `SleepListView` / `SleepCreateView` / `SleepQuickCreateView`, REST sleep API (`SleepEntryListCreateView`, `SleepEntryDetailView`, `SleepStatsView`), glucose log/dashboard, `BloodPressureListView`, fitness hub (`FitnessHomeView`, `WorkoutSessionListView`, `StartWorkoutView`), nutrition hub (`NutritionHomeView`, `FoodEntryCreateView`), fasting (`FastingListView`, `StartFastView`), intake (`IntakeHomeView`, `IntakeLogCreateView`), and `HealthIntelligenceView` / rebuild. (URL table populated from `apps/health/urls.py`; route ordering begins ~`:77`.)

## 1.7 Dashboards / UI

**Templates** (`templates/health/`): landing/home/intelligence pages plus per-metric list+form pairs (weight, sleep, glucose, blood_pressure) and subdirectories `fitness/`, `nutrition/`, `intake/`, `cycle/`, `email/`; shared `_health_disclaimer.html`, `entry_form.html`, `health_profile_form.html`.

**Dashboard views** (`apps/health/views_dashboards.py`): `BloodPressureDashboardView:22`, `BloodOxygenDashboardView:94`, `HeartRateDashboardView:137`, `HRVDashboardView:180`, `VO2MaxDashboardView:222`, `RespiratoryRateDashboardView:264`, `BodyTemperatureDashboardView:304`, `CaffeineDashboardView:357`, `MindfulMinutesDashboardView:397`, `ActivityDashboardView:439`.

## 1.8 Relationships to Other Domains

- **→ Medical:** `health_data.py:186,365,379` and `views.py:671` import `LabResult` (medical) for lab integration / display.
- **→ Journal:** `services/insight_engine.py:305` imports `JournalEntry` for contextual insights.
- **→ calendar_engine:** `signals.py` projects `IntakeSchedule` + `WorkoutSchedule` as commitments.
- **← Meals:** `apps/meals` writes a `FoodEntry` (health) for restaurant receipts — see [§3.8](#38-cross-domain-relationships).
- **Internal correlation:** glucose↔nutrition via `correlation_service.py:63` + `CarbGlucoseCorrelationRule` (`rules_transformation.py:163`).

## 1.9 Observability Path

- **Persisted snapshot:** `DailyHealthSummary` (`models.py:5956`) is the central DB aggregation point with per-domain `has_*`/`*_score` completeness fields.
- **JSON snapshot builders:** glucose (`glucose_snapshot.py`) and body-comp (`body_composition_snapshot.py`) emit dicts consumed by SAE `health.*` keys.
- **No explicit `cache.get`/`cache.set` keys** were located in the core scoring/snapshot services (`health_score.py`, `daily_summary_builder.py`, `glucose_snapshot.py`, `body_composition_snapshot.py`) — these run deterministic direct queries.

---

# 2. MEDICAL

**App:** `apps/medical/` · **Registry classification:** Behavioral Domain · **Signal renderer priority:** `foundational` (`apps/core/signals/signal_renderer.py:54`)

## 2.1 Purpose

Medical is a self-contained clinical-data ingestion domain centered on **lab results**. It ingests lab PDFs (text + OCR), parses multiple portal/table formats, maps raw test names to a canonical catalog, deduplicates via SHA-256 fingerprints, records per-row import errors, and serves trend/panel/education views — all under HIPAA-style audit logging with no PHI in logs. It provides educational (non-advice) content per lab test.

## 2.2 Primary Models (`apps/medical/models.py`)

| Model | Line | Key fields |
|-------|------|-----------|
| `LabTestCatalog` | 37 | `name` (unique), `short_name`, `category` (hematology/chemistry/lipids/thyroid/diabetes/…), `default_unit`, `default_range_low/high`, `loinc_code`, `is_system_seeded`, `needs_review`, `sort_order` |
| `LabTestAlias` | 130 | `alias` (unique) → `canonical_test` (FK→LabTestCatalog) |
| `LabEducationContent` | 164 | OneToOne→LabTestCatalog; `what_it_measures`, `what_it_reflects`, `low/high_general_associations`, `common_influencing_factors`, `typical_panel`, `is_system_generated` (educational, non-advice) |
| `LabPanel` | 236 | `panel_type` (cbc/cmp/bmp/lipid/thyroid/a1c/…), `name`, `collected_at`, `provider`; props `result_count`, `abnormal_count` |
| `MedicalDocument` | 306 | OneToOne→`life.Document` (category='medical'); `original_filename`, `file_hash` (SHA-256), `page_count`, `extracted_text`, `extraction_method` (text/ocr/mixed) |
| `ImportBatch` | 369 | `status` (pending/processing/completed/failed/partial), `total_rows_found`, `rows_imported`, `rows_skipped_duplicate`, `rows_failed`, `started_at`, `completed_at`, `error_summary` |
| `ImportErrorRow` | 433 | `row_number`, `raw_test_name/value/unit/range/line`, `error_type`, `error_message` |
| `LabResult` | 495 | `canonical_test` (FK), `raw_test_name`, `value_text`, `value_numeric`, `unit`, `range_low/high`, `range_text`, `abnormal_flag`, `collected_at`, `reported_at`, `date_estimated`, `panel`/`medical_document`/`import_batch` (FKs), `result_status` (final/preliminary/pending_review), `provider`, `fingerprint` (SHA-256) |
| `MedicalAuditLog` | 731 | `action` (upload/import/view/delete_doc/delete_results/export/merge_test), `detail` (non-PHI), `ip_address` |

**`LabResult.abnormal_flag` choices (`ABNORMAL_CHOICES` `apps/medical/models.py:503`):** `""`→Normal, `"L"`→Low (`:505`), `"H"`→High (`:506`), `"LL"`→Critical Low (`:507`), `"HH"`→Critical High (`:508`), `"A"`→Abnormal (unspecified). **Matches docs exactly.** Flag auto-computed in `_compute_abnormal_flag()` (`:692`) when unset; `compute_fingerprint()` at `:665`; `status_label` prop `:703`; `is_abnormal` prop `:723`.

## 2.3 Canonical State / Services (`apps/medical/services/`)

- `importer.py` — `ingest_lab_pdf(user, uploaded_file, ip_address)` `:59` is the full pipeline orchestrator (extract→parse→map→dedup→persist→error-record→audit); `IngestionResult` dataclass `:43`; 20 MB limit `:40`; re-import guard on `file_hash` `:87`.
- `lab_parser.py` — `parse_lab_text()` `:47` dispatches to `_parse_portal_format()` `:105`, `_parse_table_format()` `:352`, `_parse_generic_lines()` `:504`; `parse_numeric_value()` `:645`; `ParsedResult` dataclass `:24`.
- `mapper.py` — `normalize_test_name()` `:16`, `map_to_catalog()` `:43` (alias-first, auto-create on miss), `guess_panel_type()` `:152`.
- `ocr_extractor.py` — `OCRExtractor` `:14` (pdf2image + pytesseract); `extract_with_fallback()` `:82` (text first, OCR fallback).
- `pdf_text_extractor.py` — `PDFTextExtractor` `:16` (pdfplumber); static `compute_file_hash()`.
- `duplicate_detector.py` — `compute_fingerprint()` `:15`, `is_duplicate()` `:37`, `check_batch_duplicates()` `:50`.
- `error_reporter.py` — `record_error()` `:16`, `export_errors_csv()` `:33`, `get_error_summary()` `:63`.

## 2.4 Signal Outputs

- **PIE:** `RepeatedOutOfRangeRule` — `apps/core/ai_insights/rules_labs_vitals.py:17` (module="medical"; filters `abnormal_flag__in=["L","H","LL","HH"]` `:36`; appends an educational/non-advice disclaimer `:10`).
  - **Observed defect (factual):** the rule queries `status="active"` at `apps/core/ai_insights/rules_labs_vitals.py:37`, but `LabResult` defines `result_status` (`models.py`), not `status`. Reported here as an as-found observation only.
- **PRIE:** `LabMarkerTrendRule` — `apps/core/ai_predictions/prediction_rules_labs.py:16` (module="labs"; 90-day projection via `calculate_linear_projection()`; flags projected out-of-range). **Confirmed present.**
- **Signal renderer:** medical has a priority entry (`:54`) but **no medical-specific templates in `SIGNAL_RENDER_MAP`** — medical signals fall back to legacy rendering.

## 2.5 APIs / Endpoints (`apps/medical/urls.py`)

| Pattern | View | Line |
|---------|------|------|
| `""` | `LabsSummaryView` | 17 |
| `upload/` | `LabUploadView` | 19 |
| `import/<uuid:pk>/` | `ImportDetailView` | 21 |
| `import/<uuid:pk>/errors/csv/` | `ImportErrorCSVView` | 22 |
| `result/<uuid:pk>/` | `ResultDetailView` | 24 |
| `trend/<uuid:test_id>/` | `TestTrendView` | 26 |
| `panel/<uuid:pk>/` | `PanelDetailView` | 28 |
| `document/<uuid:pk>/` | `DocumentDetailView` | 30 |
| `education/<uuid:test_id>/` | `EducationDetailView` | 32 |
| `document/<uuid:pk>/rename/` | `DocumentRenameView` | 34 |
| `document/<uuid:pk>/delete/` | `DocumentDeleteView` | 36 |
| `import/<uuid:pk>/delete/` | `ImportDeleteView` | 37 |
| `result/<uuid:pk>/delete/` | `ResultDeleteView` | 38 |

## 2.6 Dashboards / UI

**Templates** (`templates/medical/`): `labs_summary.html`, `upload.html`, `import_detail.html`, `result_detail.html`, `test_trend.html`, `panel_detail.html`, `document_detail.html`, `partials/`.

**Views** (`apps/medical/views.py`): `MedicalAccessMixin:39`, `LabUploadView:53`, `ImportDetailView:94`, `ImportErrorCSVView:119`, `LabsSummaryView:164`, `ResultDetailView:259`, `EducationDetailView:288`, `PanelDetailView:317`, `DocumentDetailView:335`, `DocumentRenameView:355`, `TestTrendView:391`, `DocumentDeleteView:413`, `ImportDeleteView:456`, `ResultDeleteView:505`.

## 2.7 Relationships to Other Domains

- **→ Life:** `MedicalDocument` OneToOne→`life.Document` (`models.py:316`).
- **← Health / core:** `LabResult` is imported by `apps/core/ai_insights/rules_labs_vitals.py:28` and `apps/core/ai_predictions/prediction_rules_labs.py:34`, and by health (`§1.8`). **Medical imports nothing from health.**
- Medication adherence is handled in `apps/core/behavior/` + `apps/core/signals/health_signals.py` against `Intake` (health) — not in medical.

## 2.8 Observability Path

- **Audit:** `MedicalAuditLog` (`models.py:731`) records every action (upload/import/view/delete/export/merge) with IP, no PHI.
- **Dedup fingerprints:** file-level `file_hash` (`models.py:327`) + result-level `fingerprint` (`models.py:665`).
- **In-memory:** `panels_cache` dict during a single import (`importer.py:289`). No durable cache keys, snapshots, or telemetry beyond audit logs.

---

# 3. MEALS

**App:** `apps/meals/` · **Registry classification:** Behavioral Domain · **Signal renderer priority:** `important` (`apps/core/signals/signal_renderer.py:56`) · Registry marks Meals as **Phase 2 legacy bespoke rendering**.

## 3.1 Purpose

Meals is a household-scoped food-intelligence domain: it manages ingredients, recipes (recipes themselves live in `life.Recipe`), pantry inventory with confidence decay, weekly meal-plan generation, receipt ingestion (OCR + Vision), and pantry-photo detection. It gates intelligence behind a progressive-activation threshold and routes confirmed receipts to the correct downstream domain (pantry vs. health nutrition vs. finance).

## 3.2 Primary Models (`apps/meals/models.py`)

| Model | Line | Key fields |
|-------|------|-----------|
| `Ingredient` | 35 | canonical ingredient; `nutrition_source` FK→`health.FoodItem` (`:88`), category, storage type, substitution group, shelf life |
| `RecipeIngredient` | 171 | FK→`life.Recipe` (`:208`), FK→`Ingredient` (`:213`), quantity, unit, prep notes, parse confidence |
| `Household` | 274 | `primary_user`, `grocery_cycle_days`, `meals_activated_at` |
| `HouseholdMembership` | 310 | user role (admin/member) |
| `DietaryProfile` | 345 | `carb_limit_daily`, `protein_target_daily`, `calorie_target`, `fat_limit_daily`, `dietary_flags`, `diabetes_sensitive` |
| `PantryItem` | 405 | quantity, `confidence_score` (decays), `storage_location`, `expiration_date_estimated`; `decay_confidence()` `:494`, `is_expired` `:482`, `days_until_expiration` `:488` |
| `InventoryTransaction` | 508 | audit trail; `source` (manual/receipt/meal_plan/expiration/correction/photo_scan/barcode), `delta_quantity` |
| `StorageOverride` | 552 | global product_name→storage mapping |
| `MealPlan` | 597 | household plan for date range; `projected_cost`, `confidence_score`; `day_count` `:633` |
| `MealPlanEntry` | 637 | `meal_type`, recipe FK, `serving_count`, `inventory_impact_snapshot` (JSON), `score` |
| `Receipt` | 694 | OCR/Vision receipt; type GROCERY/RESTAURANT/RETAIL/UNKNOWN, status PROCESSING→…→CONFIRMED, `receipt_hash` (SHA-256), `duplicate_of`, FK→`scan.ScanLog` (`:866`) |
| `ReceiptItem` | 885 | `raw_name`/`raw_price`, quantity, unit, `ingredient` FK, `match_confidence`, category |
| `PantryScanSession` | 950 | `location_type`, `overall_confidence`, `items_detected`, `items_confirmed` |
| `PantryPhotoUpload` | 1005 | image, `processed`, `raw_detection_json` |
| `PantryPhotoDetection` | 1043 | `detected_label`, `matched_ingredient` FK, `confidence_score`, `suggested_quantity`, `confirmed`/`rejected` |

## 3.3 Canonical State / Services (`apps/meals/services/`)

- `meal_scoring.py` — `score_recipe()` `:62` (multi-factor: inventory, expiration urgency, carb/protein alignment, time, grocery avoidance, frequency); `rank_recipes()` `:245`.
- `activation.py` — `get_activation_status()` `:64` (gate: ≥5 pantry items + ≥3 recipes; caches 5 min, key `meal_activation_{user.id}` `:71`); `invalidate_activation_cache()` `:112`.
- `inventory_gap.py` — `analyze_recipe_gaps()` `:47`, `find_pantry_expiring_soon()` `:161`, `decay_all_pantry_confidence()` `:176`.
- `weekly_optimizer.py` — `generate_meal_plan()` `:43`, `save_meal_plan()` `:172`.
- `recipe_nutrition.py` — `calculate_recipe_nutrition()` `:62` (aggregates RecipeIngredient→FoodItem; cache key `meal_recipe_nutrition:{recipe.id}` TTL 3600 `:27`); `get_recipe_macro_summary()` `:159`.
- `advanced_intelligence.py` — `get_emotional_overlay()` `:36` (reads journal mood), `get_faith_calendar_constraint()` `:147`, `predict_grocery_needs()` `:232`, `get_todays_nudges()` `:316`.
- `receipt_routing.py` — `ReceiptRoutingService.route_receipt()` `:40`; restaurant path creates a `health.FoodEntry` and emits `nutrition.logged` (`:179`–`:227`, emit at `:220`); `_emit_restaurant_nutrition_event()` `:341`.
- `pantry_ingestion.py` — `finalize_pantry_item()` `:75` (emits pantry domain event on commit `:169`); `_emit_pantry_event()` `:183`.
- Supporting: `ingredient_matching.py` (`match_ingredient_name` `:27`), `ingredient_parser.py` (`parse_ingredient_line` `:182`), `receipt_parser.py` (`parse_receipt_text` `:41`), `receipt_vision.py` (`compute_receipt_hash` `:179`), `storage_classifier.py` (`determine_storage_location` `:282`), `substitution_engine.py` (`find_substitutions` `:31`), `unit_conversion.py`.

## 3.4 Signal Outputs

- **PIE** (`apps/core/ai_insights/rules_meals.py`): `MealFrequencyRule:20`, `PantryWasteRule:114`, `NutritionGapRule:246`.
- **PRIE** (`apps/core/ai_predictions/prediction_rules_meals.py`): `GroceryNeedsProjection:20`, `MealPlanAdherenceProjection:151`.
- **PGE** (`apps/core/ai_guidance/guidance_rules_meals.py`): `DinnerSuggestionGuidance:23`, `PantryAlertGuidance:118`, `MealPlanReminderGuidance:215`.
- **Domain events:** `pantry.ingested` (`pantry_ingestion.py:220`) and `nutrition.logged` (`receipt_routing.py:220`) via the `safe_emit_event` bus.

Matches `docs/DOMAIN_SIGNAL_CHECKLIST.md` claim of **3 PIE / 2 PRIE / 3 PGE** exactly.

## 3.5 APIs / Endpoints (`apps/meals/urls.py`)

`MealsDashboardView` `:9`, `MealsSetupView` `:11`, `DinnerSuggestionsView` `:13`, `PantryView` `:15`, `PantryConfirmView` `:17`, `PantryMarkUsedView` `:22`, `PantryUpdateView` `:27`, `PantryBarcodeLookupView` `:32`, `MealPlanView` `:37`, `GeneratePlanView` `:38`, `ReceiptUploadView` `:40`, `ReceiptDetailView` `:42`, `ReceiptConfirmView` `:47`, `ReceiptProcessingStatusView` `:52`, `ReceiptDeleteView` `:57`, `RecipeIntelligenceDetailView` `:63`, `PantryScanStartView` `:68`, `PantryScanConfirmView` `:70`, `PantryScanStatusView` `:75`, `PantryScanSessionsView` `:81`. (View classes in `apps/meals/views.py`, e.g. `MealsDashboardView:95`, `ReceiptUploadView:745`, `PantryScanStartView:1648`.)

## 3.6 Dashboards / UI

**Templates** (`templates/meals/`): `dashboard.html`, `setup.html`, `suggestions.html`, `pantry.html`, `pantry_scan_confirm.html`, `pantry_scan_sessions.html`, `meal_plan.html`, `receipts.html`, `receipt_upload.html`, `receipt_detail.html`, `receipt_confirm.html`, `recipe_detail.html`. Base access mixin `MealsHouseholdMixin` (`apps/meals/views.py:59`).

## 3.7 Major Services

(See §3.3 — meals is service-heavy; views call services rather than the DB directly.)

## 3.8 Cross-Domain Relationships

- **→ Health:** `Ingredient.nutrition_source` FK→`health.FoodItem` (`models.py:88`); restaurant receipts create a `health.FoodEntry` and emit `nutrition.logged` (`receipt_routing.py:179`–`227`). **Grocery receipts route to pantry only — meal planning does NOT auto-create a `FoodEntry`.**
- **→ Scan:** `Receipt.scan_log` FK→`scan.ScanLog` (`models.py:866`).
- **→ Life:** recipes are `life.Recipe` (FK from `RecipeIngredient:208`, `MealPlanEntry:660`).
- **→ Journal:** `advanced_intelligence.py:42` reads recent `JournalEntry` mood for the emotional overlay.

## 3.9 Observability Path

- **Caches:** `meal_recipe_nutrition:{recipe.id}` (TTL 3600, `recipe_nutrition.py:27`), `meal_activation_{user.id}` (TTL 300, `activation.py:71`).
- **Snapshots (JSON):** `MealPlanEntry.inventory_impact_snapshot` (`models.py:668`), `PantryPhotoUpload.raw_detection_json` (`:1028`), `ReceiptItem.parsed_json`.
- **Celery tasks** (`apps/meals/tasks.py`): `process_pantry_scan_task` `:36`, `process_receipt_image_task` `:125` (staged progress UPLOAD→…→COMPLETE).

---

# 4. FAITH

**App:** `apps/faith/` · **Registry classification:** Influence Domain · **Signal renderer priority:** `important` (`apps/core/signals/signal_renderer.py:60`; "foundational personally, tier-2 in priority math").

## 4.1 Purpose

Faith tracks spiritual practice: scripture/saved verses, daily verses, prayer requests, faith milestones, structured Bible reading plans (and a richer "Journey" subdomain with arcs/days and tiered commentary), Bible study tools (highlights, bookmarks, notes), and a biblical-calendar overlay. Canonical faith state unifies reading-plan progress with the routine→faith completion bridge so faith metrics cannot diverge from the dashboard/routine engine.

## 4.2 Primary Models (`apps/faith/models.py`)

| Model | Line | Key fields |
|-------|------|-----------|
| `ScriptureVerse` | 58 | reference, text, translation, book_name/order, chapter, verse_start/end, themes (JSON), contexts (JSON), is_active |
| `DailyVerse` | 117 | `date` (unique), `verse` FK, theme, reflection_prompt |
| `PrayerRequest` | 151 | title, description, is_personal, priority, `is_answered`, `answered_at`, answer_notes, remind_daily |
| `SavedVerse` | 214 | reference, text, translation, book fields, themes (JSON), notes, `is_memory_verse` |
| `FaithMilestone` | 277 | title, `milestone_type`, date, description, scripture_reference |
| `ReadingPlanTemplate` | 326 | title, slug (unique), description, category, difficulty, source, series, allowed_emails (JSON) |
| `ReadingPlanDay` | 451 | plan FK, day_number, scripture_references (JSON), scripture_content (JSON), commentary tiers (beginner/intermediate/advanced) |
| `UserReadingPlan` | 544 | template FK, `plan_status` (active/completed/paused/abandoned), started_at, completed_at, current_day, reminder_time |
| `UserReadingProgress` | 618 | user_plan FK, plan_day FK, `is_completed`, completed_at, notes |
| `ReadingPlanAssessment` | 676 | assessment definition |
| `UserAssessmentResponse` | 759 | assessment FK, user_plan FK, responses (JSON), total_score |
| `BibleHighlight` | 851 | reference, book fields, color |
| `BibleBookmark` | 907 | reference, book fields, title, notes |
| `BibleStudyNote` | 960 | reference, book fields, title, content, tags (JSON) |

**Journey subdomain** (`apps/faith/journey/models.py`): `JourneyPath`, `JourneyArc`, `JourneyDay` (scripture refs/content + 3 commentary tiers + key_insight/reflection/application), `UserJourney` (status, preferred_difficulty, momentum_score), `UserJourneyDayProgress`.

## 4.3 Canonical State / Services

**`apps/faith/services/faith_queries.py` (truth contract `FaithQueries`):**
- `active_reading_plans()` `:29`, `reading_completed_on()` `:41`, `has_reading_on()` `:51`.
- `is_bible_complete_on()` `:98` and `bible_completion_dates()` `:109` — **canonical** truth unifying reading-plan progress + routine→faith bridge; `_routine_bible_completed_on()` `:80`.
- `unanswered_prayers()` `:153`, `answered_prayers()` `:158`, `urgent_prayers()` `:163`, `faith_task_completed_on()` `:170`.

**`apps/faith/services/faith_metrics.py`:** `get_faith_metrics()` `:20` (combines SAE state + Execution Truth + direct queries); `_get_sae_faith()` `:72` (reads `core.ai_state.UserState`, falls back to direct queries).

**Other:** `engagement.py` `is_faith_engaged_today()` `:16`, `get_faith_engagement_details()` `:37`. `biblical_calendar.py` `compute_easter()` `:30`, `get_biblical_day()` `:105`, `BIBLICAL_DAYS` constant `:63`. Journey services (`apps/faith/journey/services.py`): `get_active_journey()` `:112`, `get_current_day()` `:160`, `mark_day_complete()` `:192` (atomic; advances arc; fires arc.completed; auto-completes routines).

## 4.4 Signal Outputs

- **Model signals** (`apps/faith/signals.py`): `handle_reading_plan_saved()` `:24` (projects to calendar_engine), `handle_reading_progress_saved()` `:42` (auto-completes matching Bible/faith routine schedules), `handle_reading_plan_deleted()` `:78`.
- **Journey observability events** (`apps/faith/journey/signals.py`): `journey.started` (`:65`), `journey.day.completed` / `journey.application.committed` (`:102`), plus `emit_arc_completed()` `:130`, `emit_confusion_flagged()` `:140`, `emit_resumed()` `:150`. These are internal events — **no PGE/PRIE/coaching** attached.
- **PIE:** `ScriptureReadingDropOffRule` — `apps/core/ai_insights/rules_scripture.py:15` (3–12 day reading-gap detection).
- **Signal renderer mappings** (`apps/core/signals/signal_renderer.py`): `("faith","reading_streak")→"faith_reading_streak"` (`:94`), `("faith","missed_prayer")→"faith_prayer_missed"` (`:95`); presentations at `:176` and `:182`.

> Per `docs/DOMAIN_SIGNAL_CHECKLIST.md` Faith = "2 PIE / 0 PRIE / 0 PGE." In code, **one** formal PIE rule class (`ScriptureReadingDropOffRule`) was located; the remaining "signals" are Django model signals + renderer mappings, not registered PIE/PRIE/PGE rule classes. See [§7](#7-notable-gaps-docs-claims-vs-code).

## 4.5 APIs / Endpoints (`apps/faith/urls.py` + `apps/faith/journey/urls.py`)

**Main (`apps/faith/urls.py`, namespace `faith`):** home `:21`; verses — `TodaysVerseView:24`, `ScriptureListView:25`, `ScriptureSaveView:26`, `ScriptureDetailView:27`, saved-verse edit/delete/toggle/bulk `:28`–`:31`; prayers — list/answered/create/detail/update/answered/delete/bulk `:34`–`:41`; milestones `:44`–`:48`; reflections `:51`–`:52`; reading plans — list/detail/start/progress/mark-complete/pause/resume/abandon/delete/assessment/difficulty `:57`–`:67`; study tools — home/highlights/bookmarks/notes (+bulk) `:73`–`:93`; Bible API proxy (status/bibles/books/chapters/verses/verse/passage/search) `:98`–`:105`.

**Journey (`apps/faith/journey/urls.py`, namespace `journey`):** `health:17`, `today:20` (canonical entry), `start:23`, `settings:26`, `review_day:29`, `complete_day:32`, annotation highlight/bookmark/save_verse/note `:35`–`:38`, `confusion_flagged:41`.

## 4.6 Dashboards / UI

**Templates** (`templates/faith/`): `home.html`, `todays_verse.html`, `scripture_list.html`, prayer/milestone/reflection sets, `reading_plans/{list,detail,progress}.html`, `study_tools/*`, and `journey/{day,settings,no_journey,no_day,_dashboard_card,_reading_plans_card,_roadmap}.html`. Gate mixin `FaithRequiredMixin` (`apps/faith/views.py:78`) checks `user.preferences.faith_enabled`.

## 4.7 Relationships to Other Domains

- **→ Journal:** `apps/faith/views.py` imports `JournalEntry` + `JournalEntryForm` for `FaithReflectionsView` (faith reflections reuse journal).
- **→ calendar_engine / life routines:** reading-plan saves project calendar events; reading-progress saves auto-complete faith `RoutineSchedule` items (`signals.py:42`).
- **→ core.ai_insights:** imports `get_module_insight`. No `apps.capture` import was located in faith.

## 4.8 Observability Path

- **State:** `faith_metrics.py:72` reads `core.ai_state.UserState`; Execution Truth bridge in `faith_queries.py:80`–`106` keeps faith metrics consistent with routine completion (trust contract 2026-06-16).
- **No explicit faith-service cache keys** were located.

---

# 5. JOURNAL

**App:** `apps/journal/` · **Registry classification:** Behavioral Domain · Registry marks Journal as **Phase 2 legacy bespoke rendering** (no entry in `signal_renderer.py`).

## 5.1 Purpose

Journal handles reflection and emotional state: dated entries with a 5-value mood, free-form emotions (M2M), categories/tags, and prompts. It runs NLP/keyword content intelligence (themes, sentiment, recurring concerns) and an OpenAI-backed signal extractor that writes `JournalSignal` rows (behavioral signals attributed to other domains). It feeds the CoS context and fires the intelligence chain on entry creation; it also extracts people (relationships) and auto-completes journal routines.

## 5.2 Primary Models (`apps/journal/models.py`)

| Model | Line | Key fields |
|-------|------|-----------|
| `Emotion` | 36 | name, slug, emoji, description, order, is_active |
| `JournalPrompt` | 57 | text, category FK, is_faith_specific, scripture_reference/text, is_active |
| `JournalEntry` | 93 | `title`, `body`, `entry_date`, `mood` (great/good/okay/low/difficult), `categories` (M2M), `tags` (M2M), `emotions` (M2M→Emotion), `prompt` FK, `word_count` |
| `JournalSignal` | 207 | `entry` FK, `signal_type`, `domain`, `confidence`, `extracted_text`, `created_at` |
| `EntryLink` | 248 | `source` FK→JournalEntry, `target_type`, `target_id`, `link_type` (cross-module references) |

> `JournalEntry` carries **both** `mood` (string, 5 choices) and `emotions` (M2M); the entry's content/body field is `body` (not `content`). No `GratitudeEntry` model exists despite being referenced in `capabilities.py:9` — see [§7](#7-notable-gaps-docs-claims-vs-code).

## 5.3 Canonical State / Services

- **`apps/journal/services/journal_queries.py` (truth contract `JournalQueries`):** `on_date()` `:26`, `has_entry_on()` `:31`, `recent()` `:36`, `with_mood()` `:47`, `last_entry()` `:60`. (Truth rule: an entry existing = the user journaled that day.)
- **`apps/journal/services/metrics.py`:** `get_journal_metrics()` `:23` (totals, week/month, streak, dominant mood, recent), `calculate_journal_streak()` `:91` (**canonical** streak), `_get_sae_journal()` `:122` (reads `UserState`).
- **`apps/journal/services/content_intelligence.py`:** `extract_themes()` `:121`, `compute_sentiment_score()` `:147`, `detect_recurring_concerns()` `:168`, `get_sentiment_trajectory()` `:207`, `analyze_journal_for_cos()` `:296` (CoS entry point; prefers NLP `JournalSignal`, falls back to keywords).
- **`apps/journal/services/signal_extractor.py`:** `JournalSignalExtractor.extract_signals()` `:111` (OpenAI; idempotency + min-word gates), `_call_openai()` `:177`, `_validate_and_create()` `:224`, `extract_emotion_signals()` `:271` (deterministic, from Emotion M2M, confidence 1.0). Signal taxonomy at `:33` (health_activity, medication_adherence, faith_practice, emotional_stress/low_mood/positive, etc.).

## 5.4 Signal Outputs

- **PIE** (`apps/core/ai_insights/rules_journal.py`): `JournalStreakPositiveRule:14` (severity positive; 14-day consecutive check), `JournalDropOffRule:76` (info; gap ≥3 days). **2 PIE rules; no PRIE/PGE for journal located.**
- **Post-save signal** (`apps/journal/signals.py`): `extract_people_from_journal()` `:27` — on create, runs people extraction (`apps.core.ai_relationships`, `:62`), routine auto-complete (`apps.life.services.routine_helpers`, `:83`), signal-extraction dispatch `:94`, emotion-signal extraction `:100`; async dispatch helper `_dispatch_signal_extraction()` `:106` (Celery `:122`, sync fallback `:140`).
- **No `signal_renderer.py` entry** for journal (Phase 2 legacy bespoke, consistent with the registry).

`docs/DOMAIN_SIGNAL_CHECKLIST.md` claims Journal = 3 PIE / 0 PRIE / 1 PGE. In code, **2 PIE** rule classes were located; the PGE rule was not located (see [§7](#7-notable-gaps-docs-claims-vs-code)).

## 5.5 APIs / Endpoints (`apps/journal/urls.py`)

Home `:11`; lists/views — `EntryListView:14`, `CalendarView:15`, `PageView:16`, `BookView:17`, `ArchivedEntryListView:18`, `DeletedEntryListView:19`; CRUD — `EntryCreateView:22`, `EntryDetailView:23`, `EntryUpdateView:24`, archive/restore/delete/permanent-delete `:27`–`:30`, bulk delete/archive `:33`–`:34`; prompts `:37`–`:38`; tags `:41`–`:43`; HTMX entry-form/mood-select/tag-create `:46`–`:48`.

## 5.6 Dashboards / UI

**Templates** — main user-facing set in `templates/journal/`: `home.html`, `entry_list.html`, `entry_detail.html`, `entry_form.html`, `calendar_view.html`, `page_view.html`, `book_view.html`, `archived_list.html`, `deleted_list.html`, `prompt_list.html`, `tag_list.html`, `tag_form.html`, `partials/{tag_create_modal,tag_selector}.html`. App-local `apps/journal/templates/journal/` holds `journalprompt_list.html`, `prompt_list.html`.

**Views** (`apps/journal/views.py`): `EntryListView:67`, `PageView:122`, `BookView:136`, `CalendarView:169`, `EntryDetailView:295`, `EntryCreateView:320` (fires intelligence `:398`, emits event `:400`, milestone detection `:419`), `EntryUpdateView:494`, archive/restore/delete `:525`/`:540`/`:555`, `PermanentDeleteEntryView:575`, `PromptListView:592`, `RandomPromptView:631`, tag views `:662`–`:691`, HTMX `:708`–`:730`, `JournalHomeView:769` (uses `get_module_insight(user,'journal')` `:821`).

## 5.7 Cross-Domain Relationships

- **→ Relationships:** people extraction (`signals.py:62`).
- **→ Life:** routine auto-complete (`signals.py:83`).
- **→ core.ai_orchestrator:** fires intelligence chain (`views.py:397`).
- **→ Purpose:** milestone detection on create (`views.py:419`).
- **→ Meals:** journal mood is read by meals' emotional overlay (`apps/meals/services/advanced_intelligence.py:42`).
- **No direct mood→health link** — `mood` is a plain string field; it reaches other domains only through PIE rules / `JournalSignal` / CoS context.

## 5.8 Observability Path

- **No cache keys or durable snapshots** located in journal; SAE `UserState` is the state source (`metrics.py:122`).
- **Celery tasks** (`apps/journal/tasks.py`): `extract_journal_signals(entry_id)` `:24` (async OpenAI extraction), `backfill_journal_signals()` `:63` (one-time backfill, sync fallback).

---

# 6. Cross-Domain Map (consolidated)

| From | To | Mechanism | Anchor |
|------|----|-----------|--------|
| Health | Medical | imports `LabResult` for lab state/display | `apps/health/services/health_data.py:186`; `apps/health/views.py:671` |
| Health | Journal | imports `JournalEntry` for insight context | `apps/health/services/insight_engine.py:305` |
| Health | calendar_engine | projects `IntakeSchedule`/`WorkoutSchedule` | `apps/health/signals.py:24,57` |
| Medical | Life | `MedicalDocument`→`life.Document` | `apps/medical/models.py:316` |
| Meals | Health | `Ingredient.nutrition_source`→`health.FoodItem`; restaurant receipt → `health.FoodEntry` + `nutrition.logged` | `apps/meals/models.py:88`; `apps/meals/services/receipt_routing.py:179,220` |
| Meals | Scan | `Receipt.scan_log`→`scan.ScanLog` | `apps/meals/models.py:866` |
| Meals | Life | recipes are `life.Recipe` | `apps/meals/models.py:208,660` |
| Meals | Journal | reads `JournalEntry` mood (emotional overlay) | `apps/meals/services/advanced_intelligence.py:42` |
| Faith | Journal | reuses `JournalEntry`/`JournalEntryForm` for reflections | `apps/faith/views.py` |
| Faith | Life/calendar | reading progress auto-completes faith routines | `apps/faith/signals.py:42` |
| Journal | Relationships | people extraction from entry text | `apps/journal/signals.py:62` |
| Journal | Life | routine auto-complete on create | `apps/journal/signals.py:83` |
| Journal | Purpose | milestone detection on create | `apps/journal/views.py:419` |

---

# 7. Notable Gaps (docs claims vs. code)

1. **Journal PGE rule — not located.** `docs/DOMAIN_SIGNAL_CHECKLIST.md` lists Journal as "3 PIE / 0 PRIE / 1 PGE." Only **2 PIE** rule classes were found (`JournalStreakPositiveRule` `rules_journal.py:14`, `JournalDropOffRule:76`). No third PIE rule and no journal PGE rule class located. *(Claimed in docs, not located in code.)*

2. **Journal `GratitudeEntry` / `add_gratitude` / `mood_declining` / `mood_trend` — not located.** `apps/journal/capabilities.py:9` declares `primary_models=['JournalEntry','GratitudeEntry']` and `proactive_signals=['journal_gap','concern_recurring','mood_declining']`, but there is **no `GratitudeEntry` model** in `apps/journal/models.py` and no `mood_trend`/`mood_declining` rule. The registry's `gratitude_signal` / `mood_trend` examples have no code counterpart. *(Claimed in docs/capabilities, not located in code.)*

3. **Faith PIE count.** Docs say "2 PIE." Only **one** registered PIE rule class (`ScriptureReadingDropOffRule` `rules_scripture.py:15`) was located; remaining faith "signals" are Django model signals (`apps/faith/signals.py`) and renderer mappings, not PIE/PRIE/PGE rule classes. The registry's `prayer_streak`/`spiritual_growth`/`faith_learning` example signals were not found as rule classes. *(Partially claimed in docs, only one PIE class located.)*

4. **Medical `RepeatedOutOfRangeRule` query field mismatch.** The rule filters `status="active"` at `apps/core/ai_insights/rules_labs_vitals.py:37`, but `LabResult` defines `result_status` (`apps/medical/models.py`), not `status`. Recorded as an as-found factual observation (the soft-delete manager may inject `status`; not verified here). All documented `abnormal_flag` values (`L/H/LL/HH/A/""`) **were verified** at `apps/medical/models.py:503`.

5. **No `Medication` model anywhere.** Docs/registry discuss "medication adherence" as a Medical concern; in code, medications + supplements are the unified `Intake` model in **health** (`apps/health/models.py:2282`), and adherence lives in `apps/health/medicine_utils.py` + `apps/core/signals/health_signals.py`. Medical has no medication model. *(Domain attribution in registry differs from code location.)*

6. **`MedicalProvider` lives in health, not medical.** `MedicalProvider` (`apps/health/models.py:3619`) and `ProviderStaff` (`:3816`) are in the health app despite the registry listing "Medical providers / Appointments" under the MEDICAL domain. *(Registry attribution differs from code location.)*

7. **Health docs rules all verified.** `WeightProjectionRule` (`prediction_rules_health.py:19`), `MissingWeightLoggingRule` (`rules_health.py:174`), `BodyFatChangeRule` (`rules_body_composition.py:114`) and the transformation-rule family were all confirmed present — no health gaps found.

8. **Meals matches docs exactly** (3 PIE / 2 PRIE / 3 PGE all located). One clarification vs. a common assumption: **logging/planning a meal does not create a `health.FoodEntry`** — only restaurant-receipt routing does (`receipt_routing.py:179`).

---

*End of Part A.*
