# Unified Intake System — Full Architectural Proposal v2

**Date:** 2026-04-05
**Status:** Proposal — Pending Approval
**Author:** Claude (Architecture Mode)

## Executive Summary

This proposal replaces the Medicine-named models with properly named Intake models across the entire WLJ stack. The audit found **130+ files** referencing Medicine models across 15 architectural layers. This is a high-risk, high-reward foundational correction.

---

## ARCHITECTURAL CHALLENGES (Raised Before Proceeding)

### Challenge 1: We just deployed intake_type/priority on Medicine
The fields from the initial implementation are now in production (migrations 0080-0082). This proposal subsumes that work. The new migration plan BUILDS on those migrations rather than fighting them — the intake_type and priority fields stay, the model gets renamed around them.

### Challenge 2: Model name — `Intake`, not `IntakeDefinition`
Django convention: short model names. `Intake.objects.filter(...)` beats `IntakeDefinition.objects.filter(...)` in every query across 130+ files. The suffix "Definition" adds cognitive overhead with zero semantic value. The model IS the intake item, not a "definition of" one.

**Decision: `Intake`, `IntakeSchedule`, `IntakeLog`**

### Challenge 3: intake_type should be 2 values + category, not 3+ types
The prompt suggests `medication`, `supplement`, `performance` as separate intake_types. This creates three-way branching in every consumer (state builder, CoS context, execution engine, signals, compliance).

**Counter-proposal:** Keep `intake_type` as the high-level axis (`medication` / `supplement`). Add `category` for finer classification:

| intake_type | category | Examples |
|-------------|----------|----------|
| medication | prescription | Metformin, Lisinopril |
| medication | otc | Advil, Tums |
| supplement | vitamin | Vitamin D, B12 |
| supplement | mineral | Magnesium, Zinc |
| supplement | amino_acid | Creatine, L-Glutamine |
| supplement | performance | Pre-workout, Protein |
| supplement | hormonal | DHEA, Melatonin |
| supplement | herbal | Ashwagandha, Turmeric |

**Why this is better:**
- Two-way branching everywhere (medication vs supplement)
- Category is informational — drives UI grouping and Beth's vocabulary, not system-level branching
- "Performance" items ARE supplements — they have the same adherence, the same priority model, the same signal pipeline
- Future categories (prenatal, cycle support) are just new category values, no code changes

### Challenge 4: URL rename breaks the iOS app
The Swift/SwiftUI wrapper uses URL-based navigation. Renaming `/physical/medicine/` → `/physical/intake/` breaks deep links.

**Decision:** Keep URL paths as `/physical/medicine/` initially. Add `/physical/intake/` as the canonical path with the old path redirecting. Full URL migration happens when the iOS app is updated.

### Challenge 5: This is a 130+ file refactor
The blast radius is enormous. This MUST be phased, not done in one commit. Each phase must be independently deployable and reversible.

---

## STEP 1: AUDIT RESULTS

### File Count by Layer

| Layer | Files | Key Files |
|-------|-------|-----------|
| Models & migrations | 30+ | `apps/health/models.py`, 29 migration files |
| Views & URLs | 2 | `apps/health/views.py` (26 view classes), `apps/health/urls.py` |
| Forms | 1 | `apps/health/forms.py` (4 form classes) |
| Templates | 15 | `templates/health/medicine/` (10), dashboard tiles (5) |
| Services & utilities | 8+ | `medicine_utils.py`, `physical_decision.py`, `conflict_detection.py`, `daily_summary_builder.py` |
| State builder (SAE) | 2 | `state_builder.py`, `operating_profile.py` |
| Signal aggregation | 1 | `signal_aggregation.py` |
| Event adapters | 1 | `adapters/medication.py` |
| CoS context | 4+ | `cos_context.py`, `specificity_block.py`, `signal_prioritizer.py`, `diagnostic_context.py` |
| AI intents & handlers | 6+ | `action_handlers.py`, `intent_service.py`, `medicine_intents.py`, `quick_reply_handlers.py`, `deterministic_router.py`, `search_service.py` |
| Behavior & compliance | 5+ | `domain_medication.py`, `behavior_score_engine.py`, `correction_service.py`, compliance adapter |
| Execution engine | 4+ | `today_execution.py`, `today_engine.py`, `execution_truth_engine.py`, `action_prioritizer.py` |
| Admin | 1 | `apps/health/admin.py` (3 model registrations + inline) |
| Tests | 15+ | `test_medicine.py`, `test_medicine_adherence.py`, adapter tests, compliance tests |
| Dashboard | 5+ | Dashboard v1/v2 views, services, cache, signals |
| Calendar | 2 | `projection.py`, health signals |
| SMS/Notifications | 3+ | `scheduler.py`, `services.py`, management commands |
| Fixtures & docs | 5+ | Release notes, help topics, teaching destinations, AI prompts |
| Data export | 1 | `data_export.py` |
| Scan | 2 | `vision.py`, `views.py` |
| Routine bridge | 1 | `_routine_internal.py` |

### Foreign Key Chain
```
User ──1:N──→ Intake (was Medicine)
                ├──1:N──→ IntakeSchedule (was MedicineSchedule) ──CASCADE
                │              └──1:N──→ IntakeLog.schedule ──SET_NULL
                └──1:N──→ IntakeLog (was MedicineLog) ──CASCADE
```

### Signal Dependencies
- `post_save` on IntakeSchedule → CalendarEngine projection
- `post_delete` on IntakeSchedule → CalendarEngine cleanup
- Domain event `health.medication.taken` emitted on dose logging

---

## STEP 2: DOMAIN DEFINITION

### What IS Intake?
Any structured, dosage-based substance intentionally consumed on a schedule or as-needed.

### What is NOT Intake?
| Not Intake | Reason | Correct Domain |
|-----------|--------|---------------|
| Meals / food | Nutrition domain — caloric, macros, recipes | `apps/meals/` |
| Water / fluids | Hydration domain — volume-based, coefficient-adjusted | `apps/health/` WaterEntry |
| Electrolyte drinks | Hydration domain — volume counts toward fluid goal | WaterEntry (drink_type='electrolyte') |

### Electrolyte Exception (IMPORTANT)
An electrolyte drink (Liquid IV, Gatorade) is 16oz of fluid that counts toward hydration goals. It's volume-based, tracked by the hydration coefficient system (1.05x), and belongs in WaterEntry. An electrolyte *supplement* (capsule, powder without water) belongs in Intake. The distinction is form factor, not substance.

**Decision:** Electrolyte DRINKS stay in hydration. Electrolyte SUPPLEMENTS (capsules) go in Intake with `category='mineral'`.

---

## STEP 3: NEW CANONICAL MODELS

### Intake (replaces Medicine)

```python
class Intake(UserOwnedModel):
    """
    A tracked intake item — medication, supplement, or performance substance.

    This is the unified intake system. All dosage-based substances are tracked
    here with intake_type for classification and category for fine-grained grouping.
    """

    # ── Classification ──
    INTAKE_TYPE_MEDICATION = "medication"
    INTAKE_TYPE_SUPPLEMENT = "supplement"
    INTAKE_TYPE_CHOICES = [
        (INTAKE_TYPE_MEDICATION, "Medication"),
        (INTAKE_TYPE_SUPPLEMENT, "Supplement"),
    ]

    PRIORITY_CRITICAL = "critical"
    PRIORITY_OPTIMIZATION = "optimization"
    PRIORITY_CHOICES = [
        (PRIORITY_CRITICAL, "Critical"),
        (PRIORITY_OPTIMIZATION, "Optimization"),
    ]

    CATEGORY_CHOICES = [
        ("prescription", "Prescription"),
        ("otc", "Over-the-Counter"),
        ("vitamin", "Vitamin"),
        ("mineral", "Mineral"),
        ("amino_acid", "Amino Acid"),
        ("performance", "Performance"),
        ("hormonal", "Hormonal"),
        ("herbal", "Herbal"),
        ("other", "Other"),
    ]

    # All existing Medicine fields preserved:
    # name, purpose, dose, frequency, is_prn, start_date, end_date,
    # intake_status (was medicine_status),
    # paused_at, paused_reason,
    # current_supply, refill_threshold, refill_requested, refill_requested_at,
    # prescribing_doctor, pharmacy, rx_number,  (blank=True, hidden for supplements)
    # instructions, notes, grace_period_minutes,

    # Classification fields (already exist from initial deployment):
    # intake_type, priority,

    # NEW:
    category = CharField(max_length=20, choices=CATEGORY_CHOICES, default="other")
    dosage_unit = CharField(max_length=20, blank=True,
        help_text="Unit of measurement (mg, g, IU, mcg, ml)")
```

### IntakeSchedule (replaces MedicineSchedule)
Same fields as MedicineSchedule. No structural changes needed.

### IntakeLog (replaces MedicineLog)
Same fields as MedicineLog. `source` field already present.

---

## STEP 4: MIGRATION PLAN

### Phase A: Add New Models as Proxies (Zero Risk)
1. Create `Intake` as a proxy model of `Medicine` (no table change)
2. Create `IntakeSchedule` as a proxy of `MedicineSchedule`
3. Create `IntakeLog` as a proxy of `MedicineLog`
4. All new code can import from either name
5. **Deployable independently. Reversible: just delete proxy models.**

### Phase B: Add New Fields
1. Add `category` field to Medicine (default='other')
2. Rename `medicine_status` → `intake_status` (with both accessors for backward compat)
3. Add `dosage_unit` field
4. **Deployable independently. Reversible: remove fields.**

### Phase C: Rename Database Tables (Core Migration)
```python
migrations.RenameModel(old_name='Medicine', new_name='Intake')
migrations.RenameModel(old_name='MedicineSchedule', new_name='IntakeSchedule')
migrations.RenameModel(old_name='MedicineLog', new_name='IntakeLog')
```
Django's `RenameModel` handles:
- Table rename (`health_medicine` → `health_intake`)
- FK references on related models
- ContentType updates
- **Does NOT require re-creating indexes or constraints**

**Risk mitigation:** Run on staging first. Verify all FKs resolve. Test with production data dump.

### Phase D: Code Refactor (The Big One)
Update all 130+ files in dependency order:
1. Models (imports, class names)
2. Forms
3. Admin
4. Views & URLs
5. Services & utilities
6. State builder
7. Signal aggregation
8. Event adapters
9. CoS context
10. AI intents & handlers
11. Execution engine
12. Behavior & compliance
13. Templates
14. Tests
15. Fixtures & docs

### Phase E: URL Migration
1. Add new `/physical/intake/` URL patterns
2. Keep `/physical/medicine/` as redirects
3. Update iOS app in next release
4. Remove redirects after iOS adoption

### Creatine Handling (Already Done)
- Removed from hydration in initial deployment ✅
- Seeded as Intake supplement ✅
- Historical WaterEntry rows preserved ✅
- No legacy write paths remain ✅

---

## STEP 5: SYSTEM-WIDE CHANGES

### State Builder
```python
def build_intake_state(user):  # was build_medicine_state
    state['active_medications'] = [...]  # intake_type='medication'
    state['active_supplements'] = [...]  # intake_type='supplement'
    state['medication_count'] = N
    state['supplement_count'] = N
    state['medication_adherence_7d'] = X
    state['supplement_adherence_7d'] = Y
    # Per-dose detail includes intake_type, priority, category
```

### Signal Layer
| Signal | Source | Computation |
|--------|--------|------------|
| `medication_adherence` | IntakeLog where intake_type='medication' | taken/expected (existing) |
| `supplement_adherence` | IntakeLog where intake_type='supplement' | taken/expected (already implemented) |
| `intake_taken` | IntakeLog on create | Event emission (new) |

### Execution Engine
- `medication_dose` items: importance='foundational', escalates to overdue
- `supplement_dose` items: importance='standard', NO overdue escalation (unless priority='critical')
- Separate groups in Action Center: "Morning Medications" / "Morning Supplements"

### CoS Context
Beth receives:
```json
{
  "medication_adherence_state": {"adherence_pct": 92, "taken_today": 3, "total_scheduled": 4},
  "supplement_adherence_state": {"adherence_pct": 78, "supplement_count": 3, "active_supplements": ["Creatine", "Vitamin D", "Fish Oil"]},
  "pending_medications": [...]
}
```
Each item in `pending_medications` includes `intake_type` + `priority` for deterministic Beth behavior.

### AI Intents
| Intent | Triggers | Handler |
|--------|----------|---------|
| `take_medication` | "took my metformin", "took my pills" | Filters intake_type='medication' |
| `take_supplement` | "took my creatine", "took vitamins" | Filters intake_type='supplement' |
| `take_intake` | Ambiguous: "took my stuff" | Searches all, fallback |
| `take_intake_by_time` | "took my morning everything" | All intake types for time window |

---

## STEP 6: UI CHANGES

### Display Label Strategy
| Location | Current | Proposed |
|----------|---------|----------|
| Navigation menu | "Medicine" | "Medicine & Supplements" |
| Page title (all items) | "Medicines" | "Medicine & Supplements" |
| Page title (filtered) | N/A | "Medications" / "Supplements" |
| Add button | "Add Medicine" | "Add Medication" / "Add Supplement" |
| Action Center groups | "Morning Medications" | "Morning Medications" / "Morning Supplements" |

### Intake Creation Form
```
Step 1: What type?
  [Medication]  [Supplement]

Step 2: Dynamic form
  Medication → show prescription fields, default priority=critical
  Supplement → hide prescription fields, default priority=optimization
              show category dropdown (vitamin/mineral/amino_acid/performance/herbal/other)

Step 3: Schedule
  Same for both — time_of_day, days_of_week, dosage
```

### Action Center
Two possible groups per time window (only shown if items exist):
1. **Medications** (foundational importance, overdue escalation)
2. **Supplements** (standard importance, no escalation unless critical)

Performance items appear under "Supplements" (they ARE supplements with category='performance').

---

## STEP 7: FUTURE-PROOFING

The `category` field handles all future intake types without code changes:

| Future Need | category Value | intake_type | Notes |
|-------------|---------------|-------------|-------|
| Prenatal vitamins | `vitamin` | `supplement` | Just a vitamin |
| Cycle support | `hormonal` | `supplement` | Category handles it |
| Testosterone therapy | `hormonal` | `medication` | Prescribed = medication |
| CBD oil | `herbal` | `supplement` | |
| Insulin | `prescription` | `medication` | |
| Protein powder | `performance` | `supplement` | |

No new intake_type values needed. No new code paths. Category is purely for grouping and vocabulary.

---

## STEP 8: RISK ANALYSIS

| Risk | Severity | Likelihood | Mitigation |
|------|----------|-----------|------------|
| **Migration data loss** | Critical | Low | RenameModel is atomic; tested on staging first; full backup before deploy |
| **FK reference breakage** | Critical | Low | Django RenameModel handles FK updates; verified with `makemigrations --check` |
| **iOS deep link breakage** | High | Certain | Keep old URLs as redirects; update iOS in parallel |
| **Admin bookmark breakage** | Low | Certain | Minor inconvenience; admin users can update bookmarks |
| **Test failures** | Medium | High | Expected — ~15 test files need import updates; batch fix |
| **CoS confusion during rollout** | Medium | Low | intake_type field provides deterministic classification; no inference needed |
| **Signal double-counting** | High | Low | intake_type filters already implemented in signal aggregation |
| **130-file refactor regression** | High | Medium | Phased deployment; each phase independently testable |
| **Calendar projection breakage** | Medium | Low | Signal handlers updated in same migration |
| **Compliance scoring disruption** | Medium | Low | domain string stays 'medication'; only model names change |

---

## STEP 9: VERIFICATION PLAN

### Unit Tests
- [ ] Create supplement with category='performance' → verify intake_type='supplement'
- [ ] Create medication with category='prescription' → verify intake_type='medication'
- [ ] Log supplement dose → verify IntakeLog created with correct intake_type
- [ ] Adherence calculation: medication-only → supplements excluded
- [ ] Adherence calculation: supplement-only → medications excluded
- [ ] Signal aggregation produces separate medication_adherence + supplement_adherence snapshots

### Integration Tests
- [ ] Full lifecycle: create supplement → schedule → log → signal → state → CoS
- [ ] Action Center: supplements appear in separate group
- [ ] Action Center: supplement overdue does NOT escalate (optimization priority)
- [ ] Action Center: critical supplement DOES escalate

### CoS Behavior Tests
| Prompt | Expected Response |
|--------|------------------|
| "What supplements am I taking?" | Lists intake_type='supplement' only |
| "What medications am I taking?" | Lists intake_type='medication' only |
| "Did I take everything this morning?" | Includes both, labels separately |
| "What have I missed today?" | Critical items get urgent language, optimization items get gentle language |
| "Did I take creatine?" | Checks IntakeLog for creatine supplement |

### Migration Verification
- [ ] `RenameModel` migration applies cleanly on staging
- [ ] All FK references resolve after rename
- [ ] ContentType entries updated
- [ ] Admin site loads correctly
- [ ] No orphaned data

### Regression Suite
- [ ] `apps.health.tests.test_medicine` passes (renamed to test_intake)
- [ ] `apps.ai.tests.test_intent_registration` passes
- [ ] `apps.core.ai_events.tests.test_medication_adapter` passes
- [ ] `apps.dashboard_v2.compliance.tests` passes
- [ ] Full medicine/supplement CRUD works in browser

---

## IMPLEMENTATION PHASES (Deployment Order)

### Phase A: Proxy Models + Category Field (Low Risk)
- Add proxy models for Intake/IntakeSchedule/IntakeLog
- Add `category` and `dosage_unit` fields
- New code can start using `Intake` import immediately
- **1 migration, ~5 files changed**

### Phase B: RenameModel Migration (Medium Risk)
- Django RenameModel for all 3 models
- Rename `medicine_status` → `intake_status`
- **1 migration, tested on staging first**

### Phase C: Code Refactor — Backend (High Volume)
- Update all imports, class names, function names across 130+ files
- Keep backward-compatible aliases where needed
- **~130 files, done in batches by layer**

### Phase D: Code Refactor — Frontend (Medium Volume)
- Update templates, display labels, form layouts
- Add category-aware form behavior
- **~15 templates + form changes**

### Phase E: URL Migration (iOS-Dependent)
- Add new URL patterns
- Keep old patterns as redirects
- Update iOS app
- Remove redirects after adoption

---

## RECOMMENDATION

**Proceed with Phase A immediately.** It's zero-risk (proxy models + new fields) and unblocks new code to use Intake naming. Phase B (RenameModel) should be tested on a staging database before production. Phase C is the bulk of the work and can be done incrementally.

The `category` field approach (instead of 3+ intake_types) prevents the three-way branching problem while supporting all future intake categories. Performance intake, hormonal, herbal — all just category values on a supplement.
