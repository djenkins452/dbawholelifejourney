# WLJ Prompt Library — Load Manifest

```text
Version:      2.0
Last updated: 2026-07-11 (startup package became the primary onboarding experience)
Authority:    Danny Jenkins
Applies to:   Every new WLJ session with any conversational model
Load class:   Read this first (it tells you what else to load)
```

> ## ⭐ START HERE (2026-07-11): the onboarding package is one folder
>
> **`00_WLJ_CHIEF_OF_STAFF_STARTUP/`** is the permanent onboarding package. For a brand-new
> ChatGPT or Claude session, **load that one folder** and nothing else is required:
> 1. `00_READ_FIRST_WLJ_CHIEF_OF_STAFF_ARCHITECTURE.md` — what/why/architecture/maturity/lessons
> 2. `01_WLJ_CONSTITUTION.md` — protected Articles + Constitutional Review
> 3. `02_ENGINEERING_OPERATING_GUIDE.md` — how to engineer safely (Claude especially)
> 4. `03_DANNY_WORKING_PREFERENCES.md` — how to work with Danny
> 5. `99_NEXT_CHAT_STARTUP.md` — current priorities & open work (bootloader)
> 6. `99_REFERENCE_INDEX.md` — master TOC of every governing/supporting doc
>
> Everything below is **legacy load-guidance** for the specialized reference folders
> (`01_`–`08_`), kept for on-demand use. The three old `00_CORE_STARTUP/` always-load files
> were **migrated + rewritten** into the package above and archived under
> `_ARCHIVE_SUPERSEDED_STARTUP/` — do not load them.

> **⚠ AUTHORITATIVE GOVERNING HIERARCHY (2026-07-09) — load in this order, always:**
> 1. `docs/WLJ_PRODUCT_VISION.md` — the product *why* (WLJ is a Personal Truth Platform,
>    not an AI; the model reasons, WLJ knows; users choose a default **AI Relationship**).
> 2. `docs/WLJ_ARCHITECTURE_LAWS.md` — the constitution, **Laws 0–5** (the `docs/` copy is
>    authoritative; the `03_CANON_REFERENCE/` prompt-library copy points to it).
> 3. `docs/WLJ_LLM_TRUTH_ACTION_CONTRACT.md` — the truth/action/AI-Relationship contract
>    (fabrication = derive-don't-invent; actions are **stateful**; provider-agnostic).
> 4. `docs/WLJ_EXECUTIVE_CONTEXT_ENVELOPE_DESIGN.md` — Phase II design (the envelope).
> 5. Reference architecture (folders `04`–`07`) → implementation (folder `08`).
>
> **This hierarchy supersedes the framing of the pre-pivot canon below.** Everything in
> folders `06`–`08` (and the CoS tool/standing-context contract in `03_CANON_REFERENCE/`)
> is *superseded in framing* and reads under the pivot: **"ChatGPT"** = the
> provider-agnostic conversational model; **"understanding"** = reasoning; **"Beth"** =
> a user display name only; **personalization/assistant name** = the first-class **AI
> Relationship** domain; **"standing/always-loaded context"** = the **Executive Context
> Envelope** (Phase II). A new first-class **AI Relationship** domain should be added to
> the domain registry. Program phases: **I / I.5 / I.6 (docs) done; Phase II next.**

**Purpose:** When you start a new WLJ chat, this file tells you — deterministically
— which documents to load. Folder names encode *topic*; this manifest encodes
*load behavior*. When in doubt, load the **Always Load** set and the one mode
prompt that matches your work.

---

## Classification levels

| Level | Meaning |
|-------|---------|
| **CORE_STARTUP** | Load into nearly every WLJ session. |
| **CANON** | Authoritative truth. Load Architecture Laws always; load the others for architecture/signal/CoS-tool work. |
| **SPECIALIZED_ON_DEMAND** | Load only for a specific kind of work (debugging, design, CoS transition…). |
| **REFERENCE_ONLY** | Dated evidence / history. Don't bulk-load; open one file to prove a claim. |
| **ARCHIVE** | Superseded but preserved. Don't load. |
| **DEPRECATED** | Slated for removal. Don't load. |

> *(ARCHIVE as of 2026-07-11: the three former `00_CORE_STARTUP/` startup files are in
> `_ARCHIVE_SUPERSEDED_STARTUP/` — superseded by the `00_WLJ_CHIEF_OF_STAFF_STARTUP/` package.)*

---

## ALWAYS LOAD (every session)

**The always-load set is the startup package** — `00_WLJ_CHIEF_OF_STAFF_STARTUP/` (all six files above). That folder is self-contained: architecture, Constitution, engineering guide, Danny's preferences, current priorities, and the reference index.

| File | Folder | Notes |
|------|--------|-------|
| The six startup-package files | `00_WLJ_CHIEF_OF_STAFF_STARTUP/` | The permanent onboarding package. Drag the folder in. |
| `WLJ ARCHITECTURE LAWS.md` | `03_CANON_REFERENCE/` | Also always-load for engineering; the `docs/WLJ_ARCHITECTURE_LAWS.md` copy is authoritative. |

> The old `00_CORE_STARTUP/` always-load files (Continuation, Danny's Preferences,
> Execution Playbook) were migrated + rewritten into the startup package and archived.

---

## CANON DOCUMENTS

**Purpose:** These documents represent **authoritative production truth.** When any
other document (or the model's memory) disagrees with canon, canon wins; when canon
disagrees with current code, the code wins and canon is updated to match. All live
in `03_CANON_REFERENCE/`. Load them for architecture / signal / CoS-tool work (they
are not all always-load — see the note on Architecture Laws below).

- `WLJ DOMAIN REGISTRY.md` — the canonical life domains and their classification.
- `WLJ SIGNAL ONTOLOGY.md` — the canonical signal model, producers, and renderer contract.
- `WLJ COS TOOL & STANDING CONTEXT CONTRACT.md` — the as-built ChatGPT CoS tool surface and standing-context schema.

> **`WLJ ARCHITECTURE LAWS.md` is unique: it is both ALWAYS LOAD *and* CANON.** It
> is the only document that is simultaneously the operating rules every session
> runs under and authoritative production truth — so it appears in both the
> Always-Load table above and the canon set here.

---

## LOAD BY WORK TYPE

Pick the row matching your task; load those **in addition to** the Always-Load set.

| Work type | Also load |
|-----------|-----------|
| **Architecture / design (ChatGPT)** | `01_CHATGPT_MODES/…CHATGPT ARCHITECTURE MODE.md` + `03_CANON_REFERENCE/WLJ DOMAIN REGISTRY.md` + `WLJ SIGNAL ONTOLOGY.md` |
| **Architecture / design (Claude)** | `02_CLAUDE_MODES/…CLAUDE ARCHITECTURE MODE.md` + the two canon refs above |
| **Bug / runtime debugging (ChatGPT)** | `01_CHATGPT_MODES/…CHATGPT DEBUGGING MODE.md` |
| **Bug / runtime debugging (Claude)** | `02_CLAUDE_MODES/…CLAUDE DEBUGGING MODE.md` |
| **Multi-module / pipeline mystery** | `01_CHATGPT_MODES/…SYSTEM INVESTIGATION MODE.md` |
| **Signal / renderer work** | `03_CANON_REFERENCE/WLJ SIGNAL ONTOLOGY.md` + `04_DISCOVERY_REFERENCE/03_Engine_Catalog.md` |
| **ChatGPT-CoS tool / integration work** | `03_CANON_REFERENCE/WLJ COS TOOL & STANDING CONTEXT CONTRACT.md` + `08_IMPLEMENTATION_TRACKER/` (+ `06`/`07` for design rationale) |
| **Domain deep-dive** | the relevant `04_DISCOVERY_REFERENCE/02a–02c` domain catalog |
| **Engine / scheduler work** | `04_DISCOVERY_REFERENCE/03_Engine_Catalog.md` + `docs/ENGINE_COS_REFERENCE.md` (in main repo) |

---

## REFERENCE ONLY (don't bulk-load)

Open a single file to verify a specific claim; never load the whole folder into a chat.

- **`04_DISCOVERY_REFERENCE/`** (11 files) — point-in-time architecture discovery, dated **2026-06-23**. `file:line`-grounded evidence base.
- **`05_READINESS_REFERENCE/`** (5 files) — ChatGPT-CoS readiness audit, dated **2026-06-23**. Operationally superseded by the shipped Phases 0–7, preserved as the proof basis.
- **`03_CANON_REFERENCE/WLJ PROMPT LIBRARY INDEX.md`** — legacy navigation; superseded by this manifest (kept for history).

---

## SPECIALIZED — CoS transition (design + status)

These describe the ChatGPT CoS transition. The system is **built and deployed**
(Phases 0–7); these are now **as-built design reference**, not a forward plan. The
production contract is `03_CANON_REFERENCE/WLJ COS TOOL & STANDING CONTEXT CONTRACT.md`.

- **`06_COS_DESIGN_REFERENCE/`** (7 files) — reasoning architecture (11-stage loop, evidence tiers, epistemic states).
- **`07_COS_TOOLS_REFERENCE/`** (7 files) — Day-1 tool/standing-context/action catalog.
- **`08_IMPLEMENTATION_TRACKER/`** (4 files) — live phase status, backlog, migration gates.

---

## Folder map (renamed 2026-06-26)

| Folder | Was | Load class |
|--------|-----|------------|
| `00_WLJ_CHIEF_OF_STAFF_STARTUP/` | *new (2026-07-11)* | **CORE_STARTUP — the package** |
| `_ARCHIVE_SUPERSEDED_STARTUP/` | `00_CORE_STARTUP/` files | ARCHIVE (don't load) |
| `01_CHATGPT_MODES/` | `01_CHATGPT` | SPECIALIZED_ON_DEMAND |
| `02_CLAUDE_MODES/` | `02_CLAUDE` | SPECIALIZED_ON_DEMAND |
| `03_CANON_REFERENCE/` | `03_REFERENCE` | CANON |
| `04_DISCOVERY_REFERENCE/` | `04_DISCOVERY` | REFERENCE_ONLY |
| `05_READINESS_REFERENCE/` | `05_READINESS_AUDIT` | REFERENCE_ONLY |
| `06_COS_DESIGN_REFERENCE/` | `06_COS_REASONING_ARCHITECTURE` | SPECIALIZED_ON_DEMAND |
| `07_COS_TOOLS_REFERENCE/` | `07_DAY1_TOOL_CATALOG` | SPECIALIZED_ON_DEMAND |
| `08_IMPLEMENTATION_TRACKER/` | `08_IMPLEMENTATION` | SPECIALIZED_ON_DEMAND |

---

## Loading examples

**New Claude debugging session (a CoS mismatch bug):**
```
Load:
  00_WLJ_CHIEF_OF_STAFF_STARTUP/   (the whole package)
  02_CLAUDE_MODES/WLJ MASTER PROMPT — CLAUDE DEBUGGING MODE.md
```

**New ChatGPT architecture session (proposing a new domain):**
```
Load:
  00_WLJ_CHIEF_OF_STAFF_STARTUP/   (the whole package)
  01_CHATGPT_MODES/WLJ MASTER PROMPT — CHATGPT ARCHITECTURE MODE.md
  03_CANON_REFERENCE/WLJ DOMAIN REGISTRY.md
  03_CANON_REFERENCE/WLJ SIGNAL ONTOLOGY.md
```

**Working on the ChatGPT CoS tool surface:**
```
Load:
  (Always-Load set)
  03_CANON_REFERENCE/WLJ COS TOOL & STANDING CONTEXT CONTRACT.md
  08_IMPLEMENTATION_TRACKER/PHASED_ROLLOUT_TRACKER.md
  (06_/07_ for design rationale if needed)
```

---

*Maintained alongside the library. When a document's load class changes, update the
tables above and bump the version.*
