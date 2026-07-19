# 00 · NEXT CHAT STARTUP  (read me first — the bootloader)

**You are starting a WLJ Chief of Staff session. This is the only file to read before you begin.** It is the **one temporary document** in this package; everything else here is permanent institutional memory.

## Do this now
1. **Read the rest of this package, in order:** `01_READ_FIRST…ARCHITECTURE` → `02_WLJ_CONSTITUTION` → `03_ENGINEERING_OPERATING_GUIDE` → `04_DANNY_WORKING_PREFERENCES` → `98_SESSION_TRANSITION_PROTOCOL` → `99_REFERENCE_INDEX`.
2. **Those documents are the authoritative source of truth** — every permanent decision, principle, rule, and preference is already folded into them. **Do not summarize them back.** Read, absorb, act.
3. **Do not revisit constitutional decisions** unless a change genuinely requires a **Constitutional Review** (`02 §3`, default NO, Danny's explicit written approval).
4. Continue from the live sprint state below.

*Regenerated at the end of every chat by `@WLJ_SYSTEM_PROMPTS/99_PREPARE_NEXT_CHAT.md`. Live sprint state only — nothing constitutional, architectural, or duplicated.*

**Last regenerated:** 2026-07-19 (**Truth Validation Center built — complete enough to pause.** Sprint pivots to **Chief of Staff conversational-capability validation.**)

---

## ✅ What last session established (now PERMANENT — folded, do not re-derive)
- **Truth Validation Center** — the deterministic Owner-2 instrument (CoS answer vs WLJ truth; no model grades a model; failure classified by layer; object resolved by the app's own rule; resolved/natural modes): `01 §5`, `03 §3c`, `docs/WLJ_TRUTH_VALIDATION_CENTER.md`.
- **By-name provider rule** — every multi-entity `DomainTruth.describe_one` must cover ALL its entity types via `_entity_by_identity`; CI-locked (`test_truth_by_name_audit.py`): `03 §3c`. The whole by-name defect class is eliminated.
- **The altitude lesson** — layer-level validation is the *engineering diagnostic*, NOT the operator's certification of the conversation: `01 §6`. This lesson *is* why the sprint pivots below.

## 🎯 The live sprint — validate the Chief of Staff through NATURAL CONVERSATION
Not field validation. Not developer diagnostics. The question: **"Does my Chief of Staff behave like a knowledgeable Chief of Staff?"**

**First deliverable:** a reusable, domain-by-domain **conversational testing suite** — **ONE artifact per WLJ domain**, each in **its own copy box**, **independently executable** (no giant combined doc). Each contains natural questions a real user would ask their Chief of Staff.

- **Question philosophy:** sound exactly like a real user — *"What do I currently weigh?"*, *"Tell me everything you know about Heather."*, *"What did I eat yesterday?"*, *"What's on my calendar today?"* **Never** database/field/developer terms (not *"the value of body_fat_percentage"*). The point is to validate the **experience**, and to naturally expose Truth-Layer, retrieval, grounding, and reasoning gaps **without referencing implementation**.
- **Domains (start with Health & Vitals, then proceed one by one):** Health & Vitals · Nutrition · Fitness · Medications · Goals · Habits · Journal · Faith · People & Relationships · Legacy · Calendar · Tasks · Projects · Capture · Notes · Brain Training · Medical.
- **Loop:** produce a domain guide → Danny runs it against the production CoS → any CoS failure is **reproduced**, then becomes an engineering work item (fix at the first failing layer, `03 §3c`).

**Immediate next step:** produce the **Health & Vitals** conversational testing guide (its own copy box), then proceed domain by domain.

## 📊 CoS status (carry forward)
Truth Layer **matured**; Object Resolution **matured**; **provider failures dramatically reduced**. Remaining engineering weight is expected in **conversational grounding · retrieval quality · capability completeness · natural conversational behavior** — exactly what this sprint is built to surface. The prior intuition-ranked field backlog (`docs/WLJ_CERTIFICATION_BACKLOG.md`) is now *re-validated through conversation*, not driven by it; known-open items (glucose/BP trends, nutrition date-scoped retrieval) remain valid and will resurface.

## 🔀 Concurrency — coordinate, do not collide (Danny runs parallel sessions on the SAME tree)
Commit **only your own files by explicit path**; the changelog is contended — re-check its top immediately before each commit and **defer your line if a foreign entry appeared**. Active parallel threads seen this week: **Meal Intelligence** (canonical nutrition truth — owns nutrition work) and **assistant-panel/nutrition-form UI**.

## ⏳ Waiting on Danny (operator — Claude has no prod access)
- **Run each domain's conversational testing guide** against the production CoS and report failures (this sprint's evidence engine).
- **Deploy topology:** the CoS/Truth Validation runs in **`wlj-worker`**; `/_health/` reports only web — verify the worker is on the tested commit before trusting a production CoS result.

## 🔮 Deferred / carried (DO NOT implement without opening as its own initiative)
- **WLJ Certification Platform** — first type now built (Truth Validation Center); remaining types (CRUD/Reasoning/Executive/Check-in/Domain) plug into the same engine. Still deferred: `docs/WLJ_CERTIFICATION_PLATFORM_FUTURE.md`.
- **UTC-vs-user-local calendar-day attribution** — a truth-model decision (ingest vs summaries/trends), not a code fix. Carried.
- **WLJ Operations (separate operator-gated track)** — Phase II recovery shipped dark; open action is operator-run (confirm O2), then OPS-8a. Not the CoS thread's priority: `docs/WLJ_OPERATIONS_VISION.md`.
