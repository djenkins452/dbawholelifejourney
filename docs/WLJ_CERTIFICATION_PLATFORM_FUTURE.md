# WLJ Certification Platform — DISCOVERED FUTURE INITIATIVE (deferred, not current work)

**Status:** 🔮 **Discovered architectural initiative. Intentionally deferred.** Recorded here so it is not lost — **not** to be implemented now. The current milestone (Chief of Staff Truth Certification) must be completed and production-validated first. Do NOT refactor Production Test Plans, the Admin Console, or generalize certification across subsystems yet.

---

## The discovery
Building the CoS Truth Certification system produced a pattern that is **not CoS-specific**. The same shape — deterministic-provider certification + live customer-experience certification, organised by capability, orchestrated by one evidence-capturing runner — applies to **every** WLJ subsystem. That strongly implies WLJ should eventually have **one unified Certification Platform**, not a proliferation of per-subsystem test frameworks.

## Architectural insights that led to it
1. **Certification has exactly two owners, composed as sequential layers.** Deterministic Truth (provider returns the right value, no model) → Customer Truth (real question → real pipeline → grounded answer) → Executive Judgment. Each layer gates the next. This ordering is domain-agnostic.
2. **A `QuestionSpec` is a reusable data unit**, not a framework. One spec serves BOTH owners (deterministic check + NL question). Any subsystem can contribute specs.
3. **Organise by CAPABILITY, not domain.** The 8 capabilities (current/historical/latest/timeline/list/count/existence/comparison) let every domain simply declare what it supports — the `capability_matrix()` becomes the cross-system planning artifact. UI/Infra/Integration subsystems would declare their own capability vocabularies.
4. **The orchestrator already exists in embryo** — the Acceptance Center runs suites, routes through the real production path, captures structured per-item evidence, attributes the **first failing layer**, and has the full operator lifecycle. That is the generalizable orchestration surface.
5. **Subsystems contribute certification PROVIDERS, not independent frameworks** — mirroring the `DomainTruth` registry: register fixtures + specs + an Owner-1 checker, and the subsystem participates automatically. No second test harness per team.
6. **First-failing-layer attribution is the universal diagnostic.** The most valuable output is not pass/fail but *which layer owns the failure* — proven when it distinguished a real defect from a test-env artifact without guesswork.
7. **Production Test Plans are the natural orchestration layer.** They already model "what must be true before release"; certification providers plug into them rather than replacing them.

## What the future platform would encompass
Production Test Plans (orchestration) · Release Readiness · **Chief of Staff Certification** · Heather Certification · Journal · Health · Goals · Legacy · People · Finance · UI · Infrastructure · Integration · Domain Coverage · System Maturity — each a **certification provider** contributing fixtures + specs + Owner-1/Owner-2 checks into one platform, one evidence model, one operator view.

## Design principles (for the future initiative, when opened)
- **One platform, not N frameworks.** Production Test Plans orchestrate; subsystems provide.
- **Reuse the proven primitives:** two-owner model, `QuestionSpec`, capability matrix, structured evidence + first-failing-layer, local-AND-production certification.
- **No subsystem builds its own certifier** — it registers a provider.
- **Evidence drives the roadmap** — the platform's job is to continuously answer "what did certification prove needs building next?"

## Recommended roadmap placement
- **AFTER** the CoS Truth Certification milestone is complete **and production-validated** (the slice-1 production re-cert + measured fixes). Generalizing before the pattern is proven across the first domain-set would repeat the exact "discover something bigger, abandon the current milestone" pattern we are deliberately avoiding.
- **As its own intentional architecture initiative** — peer to the Constitution and the Operations Vision — with its own governing doc, not bolted onto CoS work.
- **Prerequisites before opening it:** (1) CoS Truth slice-1 validated in production; (2) the two-owner pattern exercised on ≥2–3 domains so the provider contract is stable; (3) the Acceptance Center evidence model confirmed sufficient as the orchestration substrate.
- **Sequencing:** finish CoS Truth → validate in prod → certify 1–2 more domains via the same loop (proving the provider contract) → THEN open the "WLJ Certification Platform" initiative and design Production Test Plans as the orchestration layer.

---

*This document records a direction. It authorizes no implementation. The current mission remains: prove the Chief of Staff can reliably know and certify the truth of a user's life.*
