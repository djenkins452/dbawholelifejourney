# WLJ Chief-of-Staff Certification Ledger

**The one program-wide view of Chief-of-Staff domain certification.** Deterministic
certification is COMPUTED by `python manage.py certify_questions <domain>` against the live
capability registries — this ledger records that state plus the natural-conversation and
operator-validation gates. Update it as each domain closes. Governing standard:
`docs/WLJ_COS_DOMAIN_CERTIFICATION_STANDARD.md` (the 5 steps). Certify customer QUESTIONS,
not implementation components.

**Legend — Status:** `ACTIONABLE COMPLETE` = every actionable question certified +
naturally certified; `MECH CERTIFIED` = deterministic catalog 100% + routing surfaces
exist, natural-cert pending; `DEFERRED` = a question gated on a workspace/product that does
not yet exist. Natural cert = run through the real CoS on Danny's production data.

_Last updated: 2026-08-14._

| Domain | Questions | PASS | Deferred | Natural Cert | Status |
|---|---:|---:|---|---|---|
| Health | 91 | 90 | `body_temperature.current_context` (no Temperature workspace) | ✅ (P1–P5) | **ACTIONABLE COMPLETE** |
| Fitness (in Health) | 20 | 20 | per-exercise progression, plan-adherence (product-future) | ✅ 4/4 grounded | **ACTIONABLE COMPLETE** (eng) |
| Medications (`medicine`) | 6 | 6 | `current_context` (no meds page summary) | ✅ real meds + adherence (45%/68%, 6 overdue) | **ACTIONABLE COMPLETE** |
| Goals (`goals`) | 6 | 6 | — (momentum verdict deliberately NOT cataloged) | ✅ real goals + progress, NO verdict | **ACTIONABLE COMPLETE** |
| Habits (`habits`) | 4 | 4 | — | ✅ clean honest-empty (no habits) | **ACTIONABLE COMPLETE** |
| Calendar (`calendar`) | 5 | 5 | `current_context` (per page) | ✅ honest-empty (no events) | **ACTIONABLE COMPLETE** |
| Tasks (`tasks`) | 5 | 5 | — (Decision Authority owns "what now") | ✅ real overdue tasks + completion trend | **ACTIONABLE COMPLETE** |
| People (`relationships`) | 6 | 6 | — | ◐ no data; model confabulated on empty (minor) | **MECH CERTIFIED** (honesty-on-empty residual) |
| Legacy (`legacy`) | 3 | 3 | — | pending | **MECH CERTIFIED** |
| Medical (`medical`) | 6 | 6 | — | ✅ real labs + flags (Glucose 134 H, ALT 35 H, GFR 87 L) | **ACTIONABLE COMPLETE** |
| Brain Training (`brain_training`) | 5 | 5 | — | ✅ clean honest-empty (no games) | **ACTIONABLE COMPLETE** |
| Projects (`projects`) | 1 | 1 | history/trend (no project-history surface) | pending | **MECH CERTIFIED** (thin) |
| Notes (`notes`) | 1 | 1 | analysis/search (thin surface) | pending | **MECH CERTIFIED** (thin) |
| Capture (`capture`) | 1 | 1 | — (inbox facts only) | pending | **MECH CERTIFIED** (thin) |

**Natural-cert results (live worker `06b42bce`, Danny's production data):** Medicine/Goals/
Tasks/Medical ground in Danny's REAL records (medications by name + adherence %; goals by
name + milestone %; overdue tasks + completion trend; labs by name + value + reference-range
flags) with no fabrication and no verdict leakage (Goals reported progress %, never a
momentum/pace verdict). Calendar/Habits/Brain Training correctly returned honest-empty on
absent data. **People** has zero data for Danny (0 people, 0 birthdays); the model gave a
vague/confabulated answer instead of a clean "no people recorded" — a minor honesty-on-empty
residual (NOT a truth-exposure gap; the surfaces return empty deterministically). Legacy /
Projects / Notes / Capture natural-cert pending (thin or low-data).
| Faith (`faith`) | — | — | — | ✅ prior arc | prior CoS Domain Cert |
| Nutrition / Journal / Meals | — | — | — | ✅ prior arcs | prior CoS Domain Cert |

**Program method (repeat per domain):** inventory `DomainTruth.supports()` → author/extend
the Question Catalog (reuse capabilities; expose before invent; never a verdict) → `certify`
→ close the first failing layer of each gap (usually Current Context or an exposure) →
scoped tests → deploy (web + `wlj-worker`) → natural cert on real data (WATCH for fabricated
entities / invented numbers / evidence lost in synthesis) → update this ledger → next domain.

**Deferrals (workspace/product-gated, honest — not chased for 100%):**
`health.body_temperature.current_context`, `medicine.current_context`, per-domain
`current_context` where no meaningful page summary exists yet, project/note history where the
domain has no history surface, per-exercise strength progression, workout-plan adherence.

**Ownership invariant (every domain):** WLJ owns facts/records/dates/relationships/state/
history/deterministic calculations/actions; OpenAI owns interpretation/prioritization/
judgment/advice. A deterministic function can still emit an I.4 verdict — Goals `momentum`
and pace/strategic labels are deliberately NOT cataloged as truth (the removed
executive-verdict class).
