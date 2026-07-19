# 00 · NEXT CHAT STARTUP  (read me first — the bootloader)

**You are starting a WLJ Chief of Staff session. This is the only file to read before you begin.** It is the **one temporary document** in this package; everything else here is permanent institutional memory.

## Do this now
1. **Read the rest of this package, in order:** `01_READ_FIRST…ARCHITECTURE` → `02_WLJ_CONSTITUTION` → `03_ENGINEERING_OPERATING_GUIDE` → `04_DANNY_WORKING_PREFERENCES` → `98_SESSION_TRANSITION_PROTOCOL` → `99_REFERENCE_INDEX`.
2. **Those documents are the authoritative source of truth.** Every permanent decision, principle, rule, and preference is already folded into them. **Do not summarize them back.** Read, absorb, act.
3. **Do not revisit constitutional decisions** unless a change genuinely requires a **Constitutional Review** (`02 §3`, default NO, Danny's explicit written approval).
4. Continue from the live sprint state below.

*Regenerated at the end of every chat by `@WLJ_SYSTEM_PROMPTS/99_PREPARE_NEXT_CHAT.md`. Live sprint state only — nothing constitutional, architectural, or duplicated.*

**Last regenerated:** 2026-07-19 (**Nutrition ✅ and Journal ✅ are production-complete. The CoS Domain Certification Standard is now RATIFIED. Next domain: Faith.**)

---

## ✅ What last session established (now PERMANENT — folded, do not re-derive)
- **The CoS Domain Certification Standard** — the RATIFIED 5-step per-domain process (verify truth → expose existing truth → validate routing → Danny production validation → close). Folded into **`03 §3d`**; canonical doc `docs/WLJ_COS_DOMAIN_CERTIFICATION_STANDARD.md`. Follow it for every domain.
- **Nutrition** and **Journal** are **production-complete** (both passed the standard end-to-end, validated by Danny in production).
- Durable rules proven this session (all in `03 §3d`): **exposure precedes new truth** (declare `analysis_subjects`/entities that reuse existing producers — the Meal lesson); **routing is a separate layer from truth** (investigate tool/domain/capability-discovery separately); **capability discovery must derive from ONE source** (`domain_semantics[d].analyzes` derived from `truth_analysis`, drift-proof); **WLJ never renders a verdict**; **retrieve vs. search vs. analyze are distinct discoverable tools**.

## 🎯 The live sprint — certify each CoS domain via the 5-step Standard
The Chief of Staff is being made "knowledgeable" domain-by-domain using `03 §3d`. Completed & prod-validated: **Nutrition, Journal.** Each domain: verify existing deterministic truth → expose it (not build it) → validate conversational routing → Danny validates in production → close.

**Next domain: Faith.** Begin at Step 1 (verify deterministic truth) — do NOT start by adding anything. Cert harness: drive natural questions through `CoSGateway.respond(surface=chat)` (`OPENAI_API_KEY` from `.env`), instrument `apps/ai/model_interface/service.py` tool fns to capture tool + args + status. Remaining domains after Faith: Fitness · Medications · Goals · Habits · People/Relationships · Legacy · Calendar · Tasks · Projects · Capture · Notes · Brain Training · Medical.

## 🔮 Deferred / carried (DO NOT implement without opening as its own step)
- **Journal — genuinely-new-truth items (NOT exposure/routing):** "goals discussed in my journal" (cross-domain + no structured goals-in-journal truth) and "people mentioned most often in my journal" (no ranked people-in-journal surface). Deferred because they require **new deterministic truth**, not exposure.
- **WLJ Certification Platform** — first type built (Truth Validation Center); remaining types (CRUD/Reasoning/Executive/Check-in/Domain) plug into the same engine. Deferred: `docs/WLJ_CERTIFICATION_PLATFORM_FUTURE.md`.
- **UTC-vs-user-local calendar-day attribution** — a truth-model decision (ingest vs summaries/trends), not a code fix. Carried.
- **WLJ Operations (separate operator-gated track)** — Phase II shipped dark; open action is operator-run (confirm O2), then OPS-8a: `docs/WLJ_OPERATIONS_VISION.md`.

## ⏳ Waiting on Danny (operator — Claude has no prod access)
- **Run the next domain's (Faith) conversational certification** in production and report failures — production validation is the gate (`03 §3d` step 4).
- **Deploy topology:** the CoS runs in **`wlj-worker`**; `/_health/` reports only web — verify the worker is on the tested commit before trusting a production CoS result.

## 🔀 Concurrency — coordinate, do not collide (Danny runs MANY parallel sessions on the SAME tree)
Commit **only your own files by explicit path.** The changelog and shared files (e.g. `apps/core/truth/domain.py`) are heavily contended: re-check the changelog top **immediately before each commit**, defer your line if a foreign entry appeared, and if a shared file mixes your hunk with foreign uncommitted work, isolate yours (stage by path; never commit foreign hunks). Active parallel threads this week: **Multimodal Intake Platform**, **Journal Experience redesign (Write/Talk Together)**, **Measurement Session Capture**, **Configuration Governance**.
