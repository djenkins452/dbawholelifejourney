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
| Medications (`medicine`) | 6 | 6 | `current_context` (no meds page summary) | pending | **MECH CERTIFIED** |
| Goals (`goals`) | 6 | 6 | — (momentum verdict deliberately NOT cataloged) | pending | **MECH CERTIFIED** |
| Habits (`habits`) | 4 | 4 | — | pending | **MECH CERTIFIED** |
| Calendar (`calendar`) | 5 | 5 | `current_context` (per page) | pending | **MECH CERTIFIED** |
| Tasks (`tasks`) | 5 | 5 | — (Decision Authority owns "what now") | pending | **MECH CERTIFIED** |
| People (`relationships`) | 6 | 6 | — | pending | **MECH CERTIFIED** |
| Legacy (`legacy`) | 3 | 3 | — | pending | **MECH CERTIFIED** |
| Medical (`medical`) | 6 | 6 | — | pending | **MECH CERTIFIED** |
| Brain Training (`brain_training`) | 5 | 5 | — | pending | **MECH CERTIFIED** |
| Projects (`projects`) | 1 | 1 | history/trend (no project-history surface) | pending | **MECH CERTIFIED** (thin) |
| Notes (`notes`) | 1 | 1 | analysis/search (thin surface) | pending | **MECH CERTIFIED** (thin) |
| Capture (`capture`) | 1 | 1 | — (inbox facts only) | pending | **MECH CERTIFIED** (thin) |
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
