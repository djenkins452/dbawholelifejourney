# 00 · NEXT CHAT STARTUP  (read me first — the bootloader)

**You are starting a WLJ Chief of Staff session. This is the only file to read before you begin.** It is the **one temporary document** in this package; everything else here is permanent institutional memory.

## Do this now
1. **Read the rest of this package, in order:** `01_READ_FIRST…ARCHITECTURE` → `02_WLJ_CONSTITUTION` → `03_ENGINEERING_OPERATING_GUIDE` → `04_DANNY_WORKING_PREFERENCES` → `98_SESSION_TRANSITION_PROTOCOL` → `99_REFERENCE_INDEX`.
2. **Those documents are the authoritative source of truth.** Every permanent decision, principle, rule, and preference is already folded into them. **Do not summarize them back.** Read, absorb, act.
3. **Do not revisit constitutional decisions** unless a change genuinely requires a **Constitutional Review** (`02 §3`, default NO, Danny's explicit written approval).
4. Continue from the live sprint state below.

*Regenerated at the end of every chat by `@WLJ_SYSTEM_PROMPTS/99_PREPARE_NEXT_CHAT.md`. Live sprint state only — nothing constitutional, architectural, or duplicated.*

**Last regenerated:** 2026-07-20 (**Faith First Light + Prayer shipped (gated to Danny); Health Sync truth fixed; Timestamp Precision Phase 1 foundation. Next: Timestamp Precision Phase 2 + continue CoS Domain Certification.**)

---

## ✅ What last session established (now PERMANENT — folded, do not re-derive)
- **Faith "First Light" experience + Prayer as a first-class pillar** — shipped, **flag-gated to Danny** (`faith_features.first_light`, migration `0093`; `FAITH_FIRST_LIGHT_DEFAULT=False`) — **AWAITING production validation before GA / What's-New.** Verse-centered immersive reader, atmosphere + typographic hierarchy, progressive disclosure, procedural journey artwork, discoverable Mirror; **Prayer integrated into Today · Reader · Mirror** with a deterministic **Reading↔Prayer bridge**, a **testimony** experience, and the lifecycle **On Your Heart · Praise · Set Aside** (archive/reopen; categories; detail redesign; First-Light prayer wall; full CRUD). Wording made truth-honest ("Done for Today"; "You completed today's reading"). **Durable principle folded into `01 §6`:** *WLJ records what happened; it never interprets what happened between the user and God — a Faith surface states deterministic truth only.*
- **Health Sync truth fixed (production, `6ce967a3`).** Two runtime-traced bugs eliminated: a **future "Newest data · 12:00 PM"** (heart-rate date-only ingest fabricated noon) and **"Syncing Normally" + "Last synced Never"** (health inferred from record presence). Fix: real sample time preserved; the truth surface never emits a future instant; the badge and "Last synced" both derive from a **verified completed run**; migration `health/0105` repairs existing future rows.
- **Timestamp Precision — Phase 1 foundation (`25c21f30`).** New reusable model `apps/core/truth/precision.py` (sibling of `temporal.py`): `Precision` vocabulary + `infer_precision` + `resolve_instant` (real time verbatim; date-only at noon **clamped ≤ now**, never future) + `format_instant`. Heart-rate + weight ingest dogfood it. **Principle folded into `03 §7`;** doc `docs/WLJ_TIMESTAMP_PRECISION.md`.

## 🎯 Live work — pick your track (Danny runs several in parallel; reconcile which you're driving before starting)
- **Timestamp Precision Phase 2/3** (this session's direct follow-on). **Phase 2** = persist an `observed_precision` beside each observed timestamp, **per-domain, certification-gated** (Health first — 8 remaining noon-fabricating ingest sites: glucose, blood pressure, body-temperature, body-comp, sleep, generic daily, blood-oxygen, HR-events; the Phase-1 adopters already *compute* the precision). **Phase 3** = presentation adopts (Health Sync JSON emits precision; iOS `HealthSyncDate` renders DAY without a clock time; web/CoS call `format_instant`). Full inventory + rollout: `docs/WLJ_TIMESTAMP_PRECISION.md`. **Do NOT big-bang it.**
- **CoS Domain Certification** (RATIFIED 5-step, `03 §3d`; `docs/WLJ_COS_DOMAIN_CERTIFICATION_STANDARD.md`). Nutrition ✅ Journal ✅ prod-complete; **Faith close-out shipped, AWAITING Danny prod validation.** **Next domain: Fitness**, then Medications · Goals · Habits · People · Legacy · Calendar · Tasks · Projects · Capture · Notes · Brain Training · Medical.
- **Parallel tracks other sessions own (do not collide):** Structured Confirmation Framework (reusable multimodal confirmation renderer — seam map in memory `measurement_session_capture` + changelog `b65ef94a`/`f02dadd9`) · Journal Experience redesign · Configuration Governance · Conversation State deterministic-writer governance (`13fc9564`).

## 🔮 Deferred / carried (open as its own step before implementing)
- **Timestamp Precision Phase 2/3** and the **remaining Health precision rollout** (above).
- **Remaining Faith refinements** from First Light (product polish, none blocking): structured relationship/goal/event pickers for Prayer; reminder-scheduling UI; a Collection model; longitudinal journal-theme analysis in the Mirror; grounded "because you…" recommendation reasons; a Current Context page-summary provider for Faith Today.
- **Journal genuinely-new-truth:** "goals discussed in my journal" (cross-domain), "people mentioned most often in my journal" (no ranked surface) — require NEW deterministic truth, not exposure.
- **WLJ Certification Platform** remaining types · **UTC-vs-user-local calendar-day attribution** · **WLJ Operations** operator-gated Phase II → OPS-8a (`docs/WLJ_OPERATIONS_VISION.md`).
- **Long-term product idea ONLY — intentionally tabled, NOT active work:** Faith **Life Seasons / Life Chapters / narrative organization.** Do not open without Danny's explicit go.
- **Renpho direct / Terra — CLOSED** (dead ends; superseded by Measurement Session Capture; reports untracked in `docs/WLJ_RENPHO_*.md`). Do not reopen.

## ⏳ Waiting on Danny (operator — Claude has no prod access)
- **Validate in production:** Faith First Light (renders / edits persist / prayer lifecycle on real data), the Health Sync fix (screen shows honest status), and the Faith domain certification.
- **Deploy topology:** the CoS runs in **`wlj-worker`**; `/_health/` reports only the web commit — verify the worker is on the tested commit before trusting a production CoS result.

## 🔀 Concurrency — coordinate, do not collide (Danny runs MANY parallel sessions on the SAME tree)
Commit **only your own files by explicit path.** The changelog and shared files (`apps/core/truth/domain.py`, this bootloader) are heavily contended: re-check the changelog top **immediately before each commit**, defer your line if a foreign entry appeared, isolate your hunk from foreign uncommitted work, and verify the push is a fast-forward (never lose a foreign commit). Active parallel threads: Structured Confirmation Framework · CoS Domain Certification (Fitness next) · Journal Experience · Configuration Governance · Conversation State.
