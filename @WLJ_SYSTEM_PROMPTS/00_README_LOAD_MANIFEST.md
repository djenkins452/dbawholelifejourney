# WLJ Prompt Library — Load Manifest

```text
Version:      2.1
Last updated: 2026-08-24 (mode prompts RETIRED — `WLJ_MASTER_PROMPT.md` is the single boot authority)
Authority:    Danny Jenkins
Applies to:   Every new WLJ session with any conversational model
Load class:   Read this first (it tells you what else to load)
```

> ## 🧭 THE BOOT AUTHORITY IS `WLJ_MASTER_PROMPT.md` (repo root)
>
> **Retired 2026-08-24:** every `WLJ MASTER PROMPT — … MODE.md` file in `01_CHATGPT_MODES/` and
> `02_CLAUDE_MODES/` (and the two that lived at the repo root) taught the **retired** architecture —
> "LLM-last", deterministic engines as the reasoning authority, narration as the CoS's role, and
> "Beth" as a system identity. **Do not load them.** Each is now a deprecation notice pointing here.
>
> **Boot every session — ChatGPT or Claude — by pasting `WLJ_MASTER_PROMPT.md` (repo root) as the
> first message, then declaring a mode (Investigate / Debug / Architect / Build / Review) from its §5.**
> It is the only active boot authority. This manifest tells you what *reference material* to add.

> ## ⭐ START HERE: drag in ONE folder
>
> For a brand-new ChatGPT or Claude session, drag in the single folder
> **`00_WLJ_CHIEF_OF_STAFF_STARTUP/`** — nothing else. It is self-contained. Read `00_NEXT_CHAT_STARTUP.md`
> first; it points you at the rest in order:
> - `00_NEXT_CHAT_STARTUP.md` — **START HERE** · the bootloader (current sprint/priorities only; the one temporary file; regenerated each transition; shrinks over time)
> - `01_READ_FIRST_WLJ_CHIEF_OF_STAFF_ARCHITECTURE.md` — **WHAT** WLJ is
> - `02_WLJ_CONSTITUTION.md` — **WHAT MUST NOT CHANGE** (+ Constitutional Review)
> - `03_ENGINEERING_OPERATING_GUIDE.md` — **HOW TO BUILD SAFELY**
> - `04_DANNY_WORKING_PREFERENCES.md` — **HOW TO WORK WITH DANNY**
> - `98_SESSION_TRANSITION_PROTOCOL.md` — **HOW TO CLOSE A CHAT**
> - `99_REFERENCE_INDEX.md` — **WHERE EVERYTHING IS**
>
> At the **end** of a chat, drop **`99_PREPARE_NEXT_CHAT.md`** (kept at this `@WLJ_SYSTEM_PROMPTS/` root,
> never loaded into a new chat) — it updates the package + supporting docs and rewrites the bootloader.
>
> Everything else here is **legacy load-guidance** for the specialized reference folders
> (`03_`–`08_`), kept for on-demand use. (`01_CHATGPT_MODES/` and `02_CLAUDE_MODES/` are **retired** —
> see the boot-authority note above.) The three old `00_CORE_STARTUP/` files were migrated +
> rewritten into the package and archived under `_ARCHIVE_SUPERSEDED_STARTUP/` — do not load them.
>
> ### The permanent startup / transition workflow
> ```
> Working chat
>    │  drop  99_PREPARE_NEXT_CHAT.md   (at end of chat)
>    ▼
> Claude updates: startup package · supporting docs · changelog
>    ▼
> Claude rewrites: 00_NEXT_CHAT_STARTUP.md   (+ Transition Audit)
>    ▼
> New chat  ──drag in ONE folder──►  00_WLJ_CHIEF_OF_STAFF_STARTUP/
>    ▼
> ChatGPT reads 00_NEXT_CHAT_STARTUP.md, then the rest in order → immediate continuity.
> ```

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

**The always-load set is the startup package** — the single folder `00_WLJ_CHIEF_OF_STAFF_STARTUP/` (read `00_NEXT_CHAT_STARTUP.md` first, then the six evergreen docs). That folder is self-contained: current priorities, architecture, Constitution, engineering guide, Danny's preferences, session-transition doctrine, and the reference index.

| File | Folder | Notes |
|------|--------|-------|
| The six startup-package files | `00_WLJ_CHIEF_OF_STAFF_STARTUP/` | The permanent onboarding package. Drag the folder in. |
| `WLJ_ARCHITECTURE_LAWS.md` | **`docs/` (main repo)** | Also always-load for engineering. **Load the `docs/` copy — it is authoritative** (v1.4+, carries Law 0 and Amendment A). ⚠️ The `03_CANON_REFERENCE/WLJ ARCHITECTURE LAWS.md` copy is **stale (v1.2, 2026-06-07, pre-Amendment-A)** — do **not** load it. |

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

> **`WLJ_ARCHITECTURE_LAWS.md` is unique: it is both ALWAYS LOAD *and* CANON.** It
> is the only document that is simultaneously the operating rules every session
> runs under and authoritative production truth — so it appears in both the
> Always-Load table above and the canon set here. **Always use `docs/WLJ_ARCHITECTURE_LAWS.md`;**
> the `03_CANON_REFERENCE/` copy is a stale pre-Amendment-A snapshot kept for history.

---

## LOAD BY WORK TYPE

Pick the row matching your task; load those **in addition to** the Always-Load set.

| Work type | Also load |
|-----------|-----------|
| **Architecture / design** (any model) | `WLJ_MASTER_PROMPT.md` → mode **ARCHITECT** + `03_CANON_REFERENCE/WLJ DOMAIN REGISTRY.md` + `WLJ SIGNAL ONTOLOGY.md` |
| **Bug / runtime debugging** (any model) | `WLJ_MASTER_PROMPT.md` → mode **DEBUG** + `docs/WLJ_RUNTIME_TRACE_DEBUGGING.md` (in main repo) |
| **Multi-module / pipeline mystery** | `WLJ_MASTER_PROMPT.md` → mode **INVESTIGATE** + `docs/WLJ_CONDUCTOR_DEVELOPMENT_MODEL.md` (in main repo) |
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
| `01_CHATGPT_MODES/` | `01_CHATGPT` | **RETIRED 2026-08-24 (don't load)** — deprecation notices → `WLJ_MASTER_PROMPT.md` |
| `02_CLAUDE_MODES/` | `02_CLAUDE` | **RETIRED 2026-08-24 (don't load)** — deprecation notices → `WLJ_MASTER_PROMPT.md` |
| `03_CANON_REFERENCE/` | `03_REFERENCE` | CANON |
| `04_DISCOVERY_REFERENCE/` | `04_DISCOVERY` | REFERENCE_ONLY |
| `05_READINESS_REFERENCE/` | `05_READINESS_AUDIT` | REFERENCE_ONLY |
| `06_COS_DESIGN_REFERENCE/` | `06_COS_REASONING_ARCHITECTURE` | SPECIALIZED_ON_DEMAND |
| `07_COS_TOOLS_REFERENCE/` | `07_DAY1_TOOL_CATALOG` | SPECIALIZED_ON_DEMAND |
| `08_IMPLEMENTATION_TRACKER/` | `08_IMPLEMENTATION` | SPECIALIZED_ON_DEMAND |

---

## Loading examples

**New debugging session (a CoS mismatch bug):**
```
Paste:  WLJ_MASTER_PROMPT.md        (repo root — declare mode DEBUG)
Load:   00_WLJ_CHIEF_OF_STAFF_STARTUP/   (the whole package)
        docs/WLJ_RUNTIME_TRACE_DEBUGGING.md
```

**New architecture session (proposing a new domain):**
```
Paste:  WLJ_MASTER_PROMPT.md        (repo root — declare mode ARCHITECT)
Load:   00_WLJ_CHIEF_OF_STAFF_STARTUP/   (the whole package)
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
