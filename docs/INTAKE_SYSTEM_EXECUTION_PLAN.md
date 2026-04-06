# Unified Intake System — Phased Execution Plan

**Date:** 2026-04-05
**Status:** Pending Approval — Do Not Implement Until Approved
**Author:** Claude (Architecture + Execution Planning Mode)

---

## FINAL ARCHITECTURAL DECISIONS

### 1. Canonical Model Names
- `Intake` (replaces `Medicine`)
- `IntakeSchedule` (replaces `MedicineSchedule`)
- `IntakeLog` (replaces `MedicineLog`)

### 2. Behavioral Axis: intake_type (2 values only)
- `medication` — prescribed or taken to treat/manage/prevent a medical condition
- `supplement` — taken to optimize health, performance, or fill nutritional gaps

Category does NOT replace intake_type. Priority does NOT replace intake_type. These are independent axes.

### 3. Classification Axis: category (secondary)
- `prescription` — prescribed medications (Metformin, Lisinopril, Insulin)
- `otc` — over-the-counter medications (Advil, Tums, Benadryl)
- `vitamin` — vitamins (Vitamin D, B12, prenatal vitamins)
- `mineral` — minerals and electrolyte supplements in capsule/powder form (Magnesium, Zinc, Calcium)
- `amino_acid` — amino acids (Creatine, L-Glutamine, BCAAs)
- `performance` — pre-workout, post-workout, protein powder
- `hormonal` — hormonal support (DHEA, Melatonin, testosterone therapy if OTC, cycle support)
- `herbal` — herbal supplements (Ashwagandha, Turmeric, CBD)
- `probiotic` — gut health (probiotics, digestive enzymes)
- `other` — anything that doesn't fit above

### 4. Priority Axis (operational — how Beth treats it)
- `critical` — health consequences if missed; urgent language; overdue escalation
- `optimization` — supports goals; gentle language; no escalation unless user overrides

### 5. Future-Proofing Validation

| Substance | intake_type | category | priority (default) | Notes |
|-----------|-------------|----------|--------------------|-------|
| Metformin | medication | prescription | critical | Prescribed |
| Advil | medication | otc | optimization | As-needed OTC |
| Insulin | medication | prescription | critical | Life-critical |
| Vitamin D | supplement | vitamin | optimization | Standard supplement |
| Prenatal vitamins | supplement | vitamin | critical | User may set critical |
| Creatine | supplement | amino_acid | optimization | Performance |
| Protein powder | supplement | performance | optimization | Post-workout |
| Pre-workout | supplement | performance | optimization | Pre-workout |
| Magnesium | supplement | mineral | optimization | Mineral |
| Ashwagandha | supplement | herbal | optimization | Herbal |
| Melatonin | supplement | hormonal | optimization | Sleep support |
| DHEA | supplement | hormonal | optimization | Hormonal |
| Testosterone (prescribed) | medication | prescription | critical | Prescribed = medication |
| CBD oil | supplement | herbal | optimization | Herbal |
| Probiotics | supplement | probiotic | optimization | Gut health |
| Electrolyte capsules | supplement | mineral | optimization | Not a drink |
| Electrolyte drinks | NOT INTAKE | — | — | Stays in WaterEntry |

No new intake_type values needed for any of these. No new code paths. Category is purely informational.

---

## FINAL INTAKE DOMAIN BOUNDARY

### IS Intake
Any structured, dosage-based substance intentionally consumed on a schedule or as-needed basis.

### IS NOT Intake
| Item | Reason | Correct Domain |
|------|--------|----------------|
| Meals / food | Caloric, macros, recipes | `apps/meals/` NutritionEntry |
| Water / fluids | Volume-based, coefficient-adjusted | `apps/health/` WaterEntry |
| Electrolyte drinks | 16oz fluid counting toward hydration goal | WaterEntry (drink_type='electrolyte') |
| Topical applications | Not ingested | Future consideration, not Intake |

---

## CANONICAL URL PLAN

### New URL Structure (replaces `/physical/medicine/`)

All URLs move from `physical/medicine/` to `physical/intake/`.

| Current Path | New Canonical Path | URL Name Change |
|-------------|-------------------|-----------------|
| `physical/medicine/` | `physical/intake/` | `medicine_home` → `intake_home` |
| `physical/medicine/list/` | `physical/intake/list/` | `medicine_list` → `intake_list` |
| `physical/medicine/add/` | `physical/intake/add/` | `medicine_create` → `intake_create` |
| `physical/medicine/<pk>/` | `physical/intake/<pk>/` | `medicine_detail` → `intake_detail` |
| `physical/medicine/<pk>/edit/` | `physical/intake/<pk>/edit/` | `medicine_update` → `intake_update` |
| `physical/medicine/<pk>/delete/` | `physical/intake/<pk>/delete/` | `medicine_delete` → `intake_delete` |
| `physical/medicine/<pk>/pause/` | `physical/intake/<pk>/pause/` | `medicine_pause` → `intake_pause` |
| `physical/medicine/<pk>/resume/` | `physical/intake/<pk>/resume/` | `medicine_resume` → `intake_resume` |
| `physical/medicine/<pk>/complete/` | `physical/intake/<pk>/complete/` | `medicine_complete` → `intake_complete` |
| `physical/medicine/<pk>/schedules/` | `physical/intake/<pk>/schedules/` | `medicine_schedules` → `intake_schedules` |
| `physical/medicine/<mpk>/schedules/<spk>/delete/` | `physical/intake/<mpk>/schedules/<spk>/delete/` | `medicine_schedule_delete` → `intake_schedule_delete` |
| `physical/medicine/<mpk>/schedules/<spk>/activate/` | `physical/intake/<mpk>/schedules/<spk>/activate/` | `medicine_schedule_activate` → `intake_schedule_activate` |
| `physical/medicine/<pk>/supply/` | `physical/intake/<pk>/supply/` | `medicine_update_supply` → `intake_update_supply` |
| `physical/medicine/<pk>/take/<spk>/` | `physical/intake/<pk>/take/<spk>/` | `medicine_take` → `intake_take` |
| `physical/medicine/<pk>/skip/<spk>/` | `physical/intake/<pk>/skip/<spk>/` | `medicine_skip` → `intake_skip` |
| `physical/medicine/<pk>/undo/<spk>/` | `physical/intake/<pk>/undo/<spk>/` | `medicine_undo` → `intake_undo` |
| `physical/medicine/bulk-take/<tod>/` | `physical/intake/bulk-take/<tod>/` | `medicine_bulk_take` → `intake_bulk_take` |
| `physical/medicine/bulk-skip/<tod>/` | `physical/intake/bulk-skip/<tod>/` | `medicine_bulk_skip` → `intake_bulk_skip` |
| `physical/medicine/prn/` | `physical/intake/prn/` | `medicine_prn_log` → `intake_prn_log` |
| `physical/medicine/history/` | `physical/intake/history/` | `medicine_history` → `intake_history` |
| `physical/medicine/<pk>/history-take/<spk>/` | `physical/intake/<pk>/history-take/<spk>/` | `medicine_history_take` → `intake_history_take` |
| `physical/medicine/<pk>/history-skip/<spk>/` | `physical/intake/<pk>/history-skip/<spk>/` | `medicine_history_skip` → `intake_history_skip` |
| `physical/medicine/log/<pk>/edit/` | `physical/intake/log/<pk>/edit/` | `medicine_log_edit` → `intake_log_edit` |
| `physical/medicine/adherence/` | `physical/intake/adherence/` | `medicine_adherence` → `intake_adherence` |
| `physical/medicine/quick-look/` | `physical/intake/quick-look/` | `medicine_quick_look` → `intake_quick_look` |
| `physical/medicine/<pk>/request-refill/` | `physical/intake/<pk>/request-refill/` | `medicine_request_refill` → `intake_request_refill` |
| `physical/medicine/<pk>/clear-refill/` | `physical/intake/<pk>/clear-refill/` | `medicine_clear_refill` → `intake_clear_refill` |

### Dashboard V2 URLs

| Current | New | Name Change |
|---------|-----|-------------|
| `actions/medicine/<id>/log/` | `actions/intake/<id>/log/` | `medicine_log` → `intake_log` |
| `actions/medicine/group/<tod>/log/` | `actions/intake/group/<tod>/log/` | `medicine_group_log` → `intake_group_log` |

### Scan URLs

| Current | New | Name Change |
|---------|-----|-------------|
| `barcode/medicine/` | `barcode/intake/` | `medicine_lookup` → `intake_lookup` |

### Temporary Redirects
During Phase III only, add catch-all redirect:
```python
path("physical/medicine/<path:rest>", RedirectView.as_view(url="/health/physical/intake/%(rest)s", permanent=False))
```
Remove after Phase V validation confirms no lingering references.

---

## PHASE 0 — FINAL AUDIT AND DESIGN LOCK

### Goal
Confirm every reference, lock the domain boundary, lock the category list, and identify all hidden assumptions. No code changes.

### Deliverables
1. Complete file-by-file inventory (DONE — see audit results above)
2. Confirmed category list: `prescription, otc, vitamin, mineral, amino_acid, performance, hormonal, herbal, probiotic, other` (10 values)
3. Confirmed URL structure (see table above — 28 health URLs + 2 dashboard_v2 URLs + 1 scan URL)
4. Hidden assumptions surfaced:
   - `get_module_state(user, 'medicine')` — 4 call sites (cos_context.py x3, deterministic_router.py x1)
   - `MODULE_BUILDERS['medicine']` in state_builder.py
   - `DOMAIN_MEDICATION` / `BUCKET_MEDICATION` constants in compliance
   - `domain='medication'` in EventRecord and event adapter registry
   - `'medication'` key in expected_map.py
   - `medicine_status` field on model (rename to `intake_status`)
   - `verbose_name = "medicine"` on all 3 model Meta classes
   - `commitment_level='non_negotiable'` for ALL calendar projections (should be conditional on priority)
   - SMS category constants: `CATEGORY_MEDICINE`, `CATEGORY_MEDICINE_REFILL`
   - Entity resolver: `_resolve_medicine()` function

### Blast Radius
None — audit only.

### Validation
- [ ] Every file in the audit has been accounted for
- [ ] Category list covers all substances in the future-proofing table
- [ ] No medicine-named concept survives as the architectural end state

### Completion Criteria
This document, reviewed and approved.

---

## PHASE I — BACKEND RENAME FOUNDATION

### Goal
Rename the 3 Django models, their database tables, the `medicine_status` field, and add `category` + `dosage_unit` fields. All data preserved. All FKs intact.

### Changes

**Migration 0083: Add category and dosage_unit fields**
```python
AddField('medicine', 'category', CharField(max_length=20, choices=CATEGORY_CHOICES, default='other'))
AddField('medicine', 'dosage_unit', CharField(max_length=20, blank=True, default=''))
```

**Migration 0084: RenameModel + RenameField**
```python
RenameModel(old_name='Medicine', new_name='Intake')
RenameModel(old_name='MedicineSchedule', new_name='IntakeSchedule')
RenameModel(old_name='MedicineLog', new_name='IntakeLog')
RenameField(model_name='intake', old_name='medicine_status', new_name='intake_status')
```

**Migration 0085: Backfill categories for existing data**
```python
RunPython: Set category='prescription' for all intake_type='medication' rows
RunPython: Set category='amino_acid' for name__icontains='creatine'
```

**Model file changes (apps/health/models.py):**
- Rename class `Medicine` → `Intake`
- Rename class `MedicineSchedule` → `IntakeSchedule`
- Rename class `MedicineLog` → `IntakeLog`
- Rename field `medicine_status` → `intake_status` (add backward-compat property)
- Add `category` and `dosage_unit` fields
- Update all internal method references (`is_active_medicine` → `is_active`)
- Update docstrings and verbose_name/verbose_name_plural
- Update ForeignKey field names: `IntakeLog.medicine` → `IntakeLog.intake` (RenameField in migration)
- Update `related_name` values if needed

**Backward compatibility layer (temporary, removed in Phase II):**
```python
# apps/health/models.py — at bottom of file
Medicine = Intake  # Backward compat — remove after Phase II
MedicineSchedule = IntakeSchedule
MedicineLog = IntakeLog
```

### Files Changed
- `apps/health/models.py` — model renames, field renames
- `apps/health/migrations/0083_*.py` — new fields
- `apps/health/migrations/0084_*.py` — RenameModel + RenameField
- `apps/health/migrations/0085_*.py` — backfill categories
- `apps/health/admin.py` — update registrations

### Dependencies
- Phase 0 must be approved
- No other phases depend on this completing first (but all subsequent phases need it)

### Blast Radius
- Database table renames (atomic via Django RenameModel)
- Admin interface (model names change)
- Backward compat aliases prevent import breakage temporarily

### Risks and Mitigations
| Risk | Mitigation |
|------|-----------|
| RenameModel fails on production | Test on local DB with production data dump first. Django RenameModel is well-tested. |
| FK references break | Django RenameModel updates all FKs and ContentTypes automatically |
| Imports break across 130+ files | Backward compat aliases (`Medicine = Intake`) prevent immediate breakage |
| medicine_status → intake_status breaks queries | Add `@property` shim: `medicine_status` returns `intake_status` |

### Validation
- [ ] `python3 manage.py makemigrations --check --dry-run` — clean
- [ ] `python3 manage.py migrate` — succeeds
- [ ] `python3 manage.py check` — no errors
- [ ] Admin loads: can view/edit Intake entries
- [ ] `Intake.objects.count()` matches pre-migration `Medicine.objects.count()`
- [ ] All FK relationships resolve (IntakeLog → Intake, IntakeSchedule → Intake)
- [ ] Backward compat aliases work: `from apps.health.models import Medicine` still resolves

### Branch / Merge / Deploy Discipline
- **Branch:** `claude/intake-phase-1-models`
- **Merge to main:** After validation passes
- **Changelog:** Updated in this commit
- **Docs:** `docs/INTAKE_SYSTEM_ARCHITECTURE.md` updated with "Phase I: COMPLETE"
- **Push:** Immediately after merge
- **Rollback:** Reverse migration (`python3 manage.py migrate health 0082`)

---

## PHASE II — QUERY, SERVICE, SIGNAL, AND STATE REFACTOR

### Goal
Update all backend consumers to use `Intake`/`IntakeSchedule`/`IntakeLog` directly. Remove backward compat aliases. Ensure medication vs supplement behavior is deterministic everywhere.

### Changes by Sub-Layer

**II-A: Import updates (all files)**
Replace every `from apps.health.models import Medicine` with `from apps.health.models import Intake` (and Schedule/Log variants). Approximately 50+ files.

**II-B: State builder**
- `apps/core/ai_state/state_builder.py`: Rename `build_medicine_state` → `build_intake_state`
- `MODULE_BUILDERS` dict: key `'medicine'` → `'intake'`
- `apps/core/ai_state/state_validator.py`: Update contract schema key `'medicine'` → `'intake'`

**II-C: Signal aggregation**
- `apps/core/ai_eae/signal_aggregation.py`: imports already use `Intake` via compat alias; update to direct
- `apps/core/execution/expected_map.py`: `'medication'` key stays (it maps to the signal, not the model)
- Add `'supplement'` key to expected_map for supplement signal

**II-D: Event adapter**
- Rename `apps/core/ai_events/adapters/medication.py` → `apps/core/ai_events/adapters/intake.py`
- Update `_DOMAIN_ADAPTERS` registry in `resolver.py`: key `'medication'` → `'intake'`
  - Also add `'medication'` as alias pointing to same adapter (backward compat for EventRecord consumers)
- Update `_MISSED_DOMAINS` and `_TIMELINE_DOMAINS` tuples

**II-E: CoS context**
- `apps/core/ai_orchestrator/cos_context.py`: `get_module_state(user, 'medicine')` → `get_module_state(user, 'intake')`
- Update `_BRIEF_WINDOW_NAMES` and `_BRIEF_SUPPLEMENT_WINDOW_NAMES`
- Rename `_group_medications_for_brief` → `_group_intake_for_brief`

**II-F: Services and utilities**
- Rename `apps/health/medicine_utils.py` → `apps/health/intake_utils.py`
- Update all function names: `calculate_medicine_adherence` → `calculate_intake_adherence`
- `apps/health/services/physical_decision.py`: update imports
- `apps/health/services/conflict_detection.py`: update imports
- `apps/health/services/daily_summary_builder.py`: update imports

**II-G: Behavior and compliance**
- Rename `apps/core/behavior/domain_medication.py` → `apps/core/behavior/domain_intake.py`
- `apps/dashboard_v2/compliance/constants.py`: `DOMAIN_MEDICATION` → `DOMAIN_INTAKE`, `BUCKET_MEDICATION` → `BUCKET_INTAKE`
- Rename `apps/dashboard_v2/compliance/adapters/medication.py` → `apps/dashboard_v2/compliance/adapters/intake.py`
- Update reconciliation.py

**II-H: Execution engine**
- `apps/core/execution/today_execution.py`: update `_collect_medication_items` → `_collect_intake_items`
- `apps/core/decision_engine/action_prioritizer.py`: update medicine_groups references

**II-I: Entity resolver**
- `apps/core/ai_orchestrator/entity_resolver.py`: `_resolve_medicine` → `_resolve_intake`

**II-J: Calendar projection signals**
- `apps/health/signals.py`: update sender references from `'health.MedicineSchedule'` to `'health.IntakeSchedule'`
- `apps/calendar_engine/services/projection.py`: rename `upsert_from_medicine_schedule` → `upsert_from_intake_schedule`

**II-K: SMS**
- `apps/sms/models.py`: `CATEGORY_MEDICINE` → `CATEGORY_INTAKE`, `CATEGORY_MEDICINE_REFILL` → `CATEGORY_INTAKE_REFILL`
- `apps/sms/scheduler.py`: update references

**II-L: Dashboard**
- `apps/dashboard_v2/services/cockpit_service.py`: `'medicine'` → `'intake'` in DOMAIN_SAE_MAP
- `apps/dashboard_v2/services/dashboard_service.py`: update imports
- `apps/dashboard/cache.py`: update imports

**II-M: Scan**
- `apps/scan/services/medicine_lookup.py` → `apps/scan/services/intake_lookup.py`
- `apps/scan/views.py`: update MedicineLookupView → IntakeLookupView

**II-N: Data export**
- `apps/users/services/data_export.py`: update model references

**II-O: Remove backward compat aliases**
- Delete `Medicine = Intake` aliases from `apps/health/models.py`

### Files Changed
~80+ Python files (imports, function names, variable names, string keys)

### Dependencies
- Phase I must be complete and deployed

### Blast Radius
- Every backend file that imports or references Medicine models
- State engine module key change (`'medicine'` → `'intake'`) — any cached state with old key will miss until refreshed
- Event domain adapter registry key change

### Risks and Mitigations
| Risk | Mitigation |
|------|-----------|
| Missed import causes runtime error | Run `python3 manage.py check` + grep for remaining `Medicine` imports |
| Cached state with old key | SAE state refreshes every 60s via SAME cycle; worst case is 60s stale |
| Event adapter registry breaks | Add `'medication'` as alias key pointing to intake adapter |
| Compliance domain string change | Update ComplianceEvent rows if needed, or keep `'medication'` as domain value |

### Validation
- [ ] `grep -r "from apps.health.models import Medicine" apps/` returns zero results
- [ ] `grep -r "get_module_state.*'medicine'" apps/` returns zero results
- [ ] `python3 manage.py test apps.health.tests.test_medicine -v 1 --failfast` passes
- [ ] `python3 manage.py test apps.ai.tests.test_intent_registration -v 1 --failfast` passes
- [ ] `python3 manage.py test apps.core.ai_eae.tests -v 1 --failfast` passes
- [ ] `python3 manage.py test apps.core.behavior.tests -v 1 --failfast` passes
- [ ] State builder produces correct output with `'intake'` key
- [ ] CoS context includes `medication_adherence_state` and `supplement_adherence_state`

### Branch / Merge / Deploy Discipline
- **Branch:** `claude/intake-phase-2-backend`
- **Merge to main:** After all validation passes
- **Changelog:** Updated with all renamed files and functions
- **Push:** Immediately after merge
- **Rollback:** Git revert (no migration changes in this phase)

---

## PHASE III — UI / URL / FORMS / TEMPLATES REFACTOR

### Goal
Rename all URLs from `medicine_*` to `intake_*`, update all template references, rename template directories, update navigation labels, and implement the dynamic intake creation form.

### Changes

**III-A: URL patterns**
- `apps/health/urls.py`: All 28 URL patterns renamed (paths and names)
- `apps/dashboard_v2/urls.py`: 2 URL patterns renamed
- `apps/scan/urls.py`: 1 URL pattern renamed
- Add temporary redirect: `physical/medicine/<path:rest>` → `physical/intake/<rest>`

**III-B: View class renames**
- All 26 `Medicine*View` classes → `Intake*View` (in `apps/health/views.py`)
- `MedicineLogAction` → `IntakeLogAction` (in `apps/dashboard_v2/views.py`)
- `MedicineGroupLogAction` → `IntakeGroupLogAction`
- `MedicineLookupView` → `IntakeLookupView` (in `apps/scan/views.py`)

**III-C: Form renames**
- `MedicineForm` → `IntakeForm`
- `MedicineScheduleForm` → `IntakeScheduleForm`
- `MedicineLogForm` → `IntakeLogForm`
- `MedicineLogEditForm` → `IntakeLogEditForm`
- Add dynamic form behavior: hide prescription fields when intake_type='supplement'
- Add category dropdown (shown for supplements, hidden for medications with default='prescription')

**III-D: Template file renames**
- Move `templates/health/medicine/` → `templates/health/intake/`
- Rename all template files from `medicine_*` to `intake_*`
- Update all `{% url %}` tags from `health:medicine_*` to `health:intake_*`
- Update dashboard tile templates
- Update navigation template (`templates/components/navigation.html`)

**III-E: Display label updates**
| Location | Old | New |
|----------|-----|-----|
| Navigation menu item | "Medicine" | "Intake" |
| Navigation sub-items | "Medicine List" | "All Intake" |
| Page titles | "Medicines" | "Intake" |
| Add button | "Add Medicine" | "Add Intake" |
| Empty state | "No medicines yet" | "No intake items yet" |
| Action Center groups | "Morning Medications" | "Morning Medications" / "Morning Supplements" |
| Adherence page | "Medicine Adherence" | "Intake Adherence" |
| History page | "Medicine History" | "Intake History" |

**III-F: Python `reverse()` and `redirect()` updates**
- Update all ~25 `reverse('health:medicine_*')` calls in views.py
- Update all `reverse('health:medicine_*')` calls in scan views/services
- Update all `reverse('dashboard_v2:medicine_*')` calls in execution engine
- Update `reverse()` calls in search_service.py, generate_health_reminders.py

**III-G: Fixture and hardcoded path updates**
- `apps/help/fixtures/teaching_destinations.json`: update URLs and keywords
- `apps/admin_console/services/__init__.py`: update hardcoded URL paths
- `apps/core/management/commands/generate_health_reminders.py`: update action_url

### Files Changed
~40 files (URLs, views, forms, 15 templates, fixtures, navigation)

### Dependencies
- Phase II must be complete (backend uses Intake names)

### Blast Radius
- Every page that links to medicine URLs
- Navigation across the entire app
- Teaching destinations and help context
- SMS reminder links

### Risks and Mitigations
| Risk | Mitigation |
|------|-----------|
| Broken links | Temporary redirect catches `/physical/medicine/*` |
| Template not found errors | Rename directory atomically; update all `template_name` attributes |
| Missing URL reverse | `python3 manage.py check` catches reverse errors at startup |
| Help topic URLs broken | Update teaching_destinations.json in same commit |

### Validation
- [ ] Every page loads without 404/500
- [ ] Navigation links work on all pages
- [ ] Add Intake form works for both medication and supplement
- [ ] Action Center renders correctly with "Medications" / "Supplements" groups
- [ ] `grep -r "medicine_home\|medicine_list\|medicine_create\|medicine_detail" templates/` returns zero results
- [ ] `grep -r "health:medicine_" apps/` returns zero results (except the redirect)
- [ ] Teaching destinations load correctly
- [ ] Temporary redirect works: `/health/physical/medicine/` → `/health/physical/intake/`

### Branch / Merge / Deploy Discipline
- **Branch:** `claude/intake-phase-3-ui`
- **Merge to main:** After browser validation
- **Changelog:** Updated
- **Push:** Immediately after merge
- **Rollback:** Git revert (URL redirect catches any missed references)

---

## PHASE IV — AI / ACTION CENTER / EXECUTION BEHAVIOR

### Goal
Update all AI intents, action handlers, deterministic routing, and ensure Beth distinguishes medications from supplements correctly using structured data only.

### Changes

**IV-A: Intent renames**
- Rename `apps/ai/intents/medicine_intents.py` → `apps/ai/intents/intake_intents.py`
- Intent names: `take_medicine` → `take_medication` (semantic correction — it was never "take a medicine")
- Keep `take_supplement` (already correct)
- `take_medicines_by_time` → `take_intake_by_time` (handles both types)
- `email_medicine_list` → `email_intake_list`
- Add `take_intake` as generic fallback for ambiguous inputs

**IV-B: Intent registration (5-point checklist per new/renamed intent)**
1. Tool definition in `apps/ai/intents/intake_intents.py`
2. Handler map in `apps/ai/intents/__init__.py`
3. Engine category in `apps/core/ai_orchestrator/intent_engine.py`
4. Execute dispatcher in `apps/ai/intent_service.py`
5. Action handler in `apps/ai/action_handlers.py`
6. Action policy in `apps/core/ai_orchestrator/action_policy.py`
7. System prompt examples in `apps/ai/intent_service.py`

**IV-C: Action handler updates**
- `handle_take_medicine` → `handle_take_medication`
- `handle_take_supplement` — already exists
- `handle_take_medicines_by_time` → `handle_take_intake_by_time`
- `handle_email_medicine_list` → `handle_email_intake_list`
- Add `handle_take_intake` — generic handler that searches all intake_types

**IV-D: Deterministic router**
- `apps/ai/deterministic_router.py`: update medicine keyword matching to intake
- `apps/ai/search_service.py`: update search result URLs
- `apps/ai/quick_reply_handlers.py`: update quick reply references
- `apps/ai/assistant_intelligence.py`: update proactive mention logic
- `apps/ai/situational_awareness.py`: update medicine state references

**IV-E: System prompt updates**
- Update all Beth examples to use intake/medication/supplement language
- Add supplement-specific examples
- Ensure Beth knows: intake_type drives vocabulary, priority drives tone

**IV-F: Execution engine behavior confirmation**
- Medication doses: `importance='foundational'`, escalates to overdue
- Supplement doses with `priority='optimization'`: `importance='standard'`, NO overdue escalation
- Supplement doses with `priority='critical'`: `importance='foundational'`, DOES escalate
- Already implemented in Phase 1 deployment — validate, don't re-implement

### Files Changed
~15 files (intents, handlers, router, search, quick replies, system prompt)

### Dependencies
- Phase III must be complete (URLs renamed)

### Blast Radius
- All AI conversation handling for intake-related queries
- Action Center grouping and priority behavior
- Beth's response language for medication vs supplement

### Risks and Mitigations
| Risk | Mitigation |
|------|-----------|
| Intent registration incomplete | Run `test_intent_registration` — catches missing registrations |
| Beth says "medicine" for supplements | intake_type field is deterministic; system prompt updated |
| Old intent names in conversation history | Intent matching is per-message; old history doesn't affect new routing |

### Validation
- [ ] `python3 manage.py test apps.ai.tests.test_intent_registration -v 2 --failfast` passes
- [ ] "Took my metformin" → `take_medication` intent
- [ ] "Took my creatine" → `take_supplement` intent
- [ ] "Took my morning stuff" → `take_intake_by_time` intent
- [ ] "What supplements am I taking?" → lists supplements only
- [ ] "What medications am I taking?" → lists medications only
- [ ] "Did I take everything this morning?" → includes both, labels separately
- [ ] "What have I missed today?" → critical items get urgent language, optimization items get gentle language

### Branch / Merge / Deploy Discipline
- **Branch:** `claude/intake-phase-4-ai`
- **Merge to main:** After intent registration tests pass and Beth validation prompts verified
- **Changelog:** Updated
- **Push:** Immediately after merge
- **Rollback:** Git revert

---

## PHASE V — DOCUMENTATION / CHANGELOG / FINAL VALIDATION

### Goal
Update all documentation, help text, context-aware help, fixture data, and run the complete regression suite.

### Changes

**V-A: User-facing docs**
- `apps/core/fixtures/release_notes.json`: Add release note for Intake system rename
- `apps/help/fixtures/help_topics.json`: Update all medicine references to intake
- `apps/help/fixtures/teaching_destinations.json`: Update URLs, names, keywords
- Reset fixture loader for all 3 fixtures

**V-B: Technical docs**
- `docs/INTAKE_SYSTEM_ARCHITECTURE.md`: Mark all phases COMPLETE
- `docs/INTAKE_SYSTEM_EXECUTION_PLAN.md`: Mark all phases COMPLETE
- `docs/wlj_claude_features.md`: Update Medicine section to Intake
- `docs/ENGINE_COS_REFERENCE.md`: Update medicine references
- `CLAUDE.md`: Update any medicine references in quick reference

**V-C: Changelog**
- Single comprehensive changelog entry covering all 5 phases

**V-D: Remove temporary redirect**
- Remove `physical/medicine/<path:rest>` redirect from urls.py
- This is the final cleanup confirming no references remain

**V-E: Test renames**
- Rename `test_medicine.py` → `test_intake.py`
- Rename `test_medicine_adherence.py` → `test_intake_adherence.py`
- Update all test class names and method names
- Update all `reverse('health:medicine_*')` in tests to `reverse('health:intake_*')`

### Files Changed
~25 files (fixtures, docs, tests, changelog)

### Dependencies
- All previous phases complete

### Blast Radius
- User-visible help content
- Developer documentation
- Test suite

### Validation — COMPLETE REGRESSION SUITE
- [ ] `python3 manage.py test apps.health.tests.test_intake -v 1 --failfast`
- [ ] `python3 manage.py test apps.health.tests.test_intake_adherence -v 1 --failfast`
- [ ] `python3 manage.py test apps.ai.tests.test_intent_registration -v 1 --failfast`
- [ ] `python3 manage.py test apps.core.ai_eae.tests -v 1 --failfast`
- [ ] `python3 manage.py test apps.core.behavior.tests -v 1 --failfast`
- [ ] `python3 manage.py test apps.core.ai_events.tests.test_medication_adapter -v 1 --failfast` (renamed to test_intake_adapter)
- [ ] `python3 manage.py test apps.dashboard_v2.compliance.tests -v 1 --failfast`
- [ ] `python3 manage.py check`
- [ ] `python3 manage.py makemigrations --check --dry-run` — clean
- [ ] `grep -rn "Medicine\b" apps/ --include="*.py" | grep -v migration | grep -v "\.pyc" | grep -v "# "` — zero results (excluding comments/migrations)
- [ ] `grep -rn "medicine_home\|medicine_list\|medicine_create" apps/ templates/` — zero results
- [ ] `grep -rn "/physical/medicine/" apps/ templates/` — zero results

### Beth Validation Prompts (Manual Test)
| Prompt | Expected |
|--------|----------|
| "What supplements am I taking?" | Lists only intake_type='supplement' |
| "What medications am I taking?" | Lists only intake_type='medication' |
| "Did I take everything this morning?" | Both types, labeled separately |
| "What have I missed today?" | Critical = urgent, optimization = gentle |
| "Did I take creatine?" | Checks IntakeLog for creatine supplement |
| "Show me my intake" | Shows all items |
| "Add a new supplement" | Opens intake create form with supplement selected |

### Branch / Merge / Deploy Discipline
- **Branch:** `claude/intake-phase-5-docs`
- **Merge to main:** After full regression passes
- **Changelog:** Final comprehensive entry
- **Push:** Immediately after merge
- **Rollback:** Git revert

---

## PHASE VI — MERGE AND RELEASE DISCIPLINE (Per-Phase)

### Branch Strategy
Each phase gets its own branch off main. No phase branches off another phase branch.

```
main ──→ claude/intake-phase-1-models ──→ merge to main ──→ push
main ──→ claude/intake-phase-2-backend ──→ merge to main ──→ push
main ──→ claude/intake-phase-3-ui ──→ merge to main ──→ push
main ──→ claude/intake-phase-4-ai ──→ merge to main ──→ push
main ──→ claude/intake-phase-5-docs ──→ merge to main ──→ push
```

### Per-Phase Checklist
For EVERY phase, before merge:
1. All validation items checked
2. `python3 manage.py makemigrations --check --dry-run` — clean
3. `python3 manage.py check` — no errors
4. Scoped tests pass
5. Changelog entry appended to `docs/wlj_claude_changelog.md`
6. Commit message describes the phase clearly

For EVERY phase, after merge:
1. `GIT_SSH_COMMAND="ssh -p 443" git push git@ssh.github.com:djenkins452/dbawholelifejourney.git main`
2. Verify Railway deploy succeeds (watch for migration errors)
3. Spot-check one page in browser

### Rollback Plan Per Phase
| Phase | Rollback Method |
|-------|----------------|
| I (models) | `python3 manage.py migrate health 0082` + revert commit |
| II (backend) | Git revert (no migrations) |
| III (UI/URLs) | Git revert + temporary redirect catches broken links |
| IV (AI) | Git revert (no migrations) |
| V (docs) | Git revert (no migrations) |

---

## GLOBAL RISK MATRIX

| Risk | Phase | Severity | Likelihood | Mitigation |
|------|-------|----------|-----------|------------|
| RenameModel migration failure | I | Critical | Low | Test locally first; Django RenameModel is atomic |
| Import breakage across 130+ files | II | High | Medium | Backward compat aliases in Phase I; systematic grep verification |
| Broken links after URL rename | III | High | Medium | Temporary redirect; `python3 manage.py check` catches reverse errors |
| Beth says wrong type label | IV | Medium | Low | intake_type is deterministic; system prompt updated |
| Cached state with old module key | II | Medium | Low | SAE refreshes every 60s; no user impact beyond brief window |
| Test suite needs 15+ file updates | V | Medium | High | Batch rename; known scope |
| Calendar projection signals break | II | Medium | Low | Update sender string in same commit |
| Compliance domain key change | II | Medium | Low | Constants updated atomically |
| SMS category rename | II | Low | Low | Simple string constant update |
| Help topic URLs broken | III | Low | Medium | Updated in same commit as URL rename |
