# WLJ Prompt Library — Load Manifest

```text
Version:      1.0
Last updated: 2026-06-26
Authority:    Danny Jenkins
Applies to:   Every new ChatGPT / Claude WLJ session
Load class:   Read this first (it tells you what else to load)
```

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

> *(No documents are currently ARCHIVE or DEPRECATED — the corrupted Preferences
> file was rebuilt, not archived.)*

---

## ALWAYS LOAD (every session)

| File | Folder | Notes |
|------|--------|-------|
| `WLJ ARCHITECTURE LAWS.md` | `03_CANON_REFERENCE/` | **Overrides all other instructions.** Non-negotiable. |
| `WLJ MASTER CONTEXT — CONTINUATION SESSION.md` | `00_CORE_STARTUP/` | System primer + operating + continuity rules. |
| `WLJ MASTER PROMPT — DANNY'S PREFERENCES.md` | `00_CORE_STARTUP/` | Collaboration contract (tone, decisiveness, deploy). |
| `WLJ CLAUDE OPUS 4.8 EXECUTION PLAYBOOK.md` | `00_CORE_STARTUP/` | **Claude sessions only** — pre-write gate, red lines. |

> The three persona-neutral / persona-specific always-load files live together in
> `00_CORE_STARTUP/` so the startup set is one folder. Architecture Laws stay in
> `03_CANON_REFERENCE/` (canon) but are always-load.

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
| `00_CORE_STARTUP/` | `00_CONTEXT` (+ moved-in always-load files) | CORE_STARTUP |
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
  03_CANON_REFERENCE/WLJ ARCHITECTURE LAWS.md
  00_CORE_STARTUP/WLJ MASTER CONTEXT — CONTINUATION SESSION.md
  00_CORE_STARTUP/WLJ MASTER PROMPT — DANNY'S PREFERENCES.md
  00_CORE_STARTUP/WLJ CLAUDE OPUS 4.8 EXECUTION PLAYBOOK.md
  02_CLAUDE_MODES/WLJ MASTER PROMPT — CLAUDE DEBUGGING MODE.md
```

**New ChatGPT architecture session (proposing a new domain):**
```
Load:
  03_CANON_REFERENCE/WLJ ARCHITECTURE LAWS.md
  00_CORE_STARTUP/WLJ MASTER CONTEXT — CONTINUATION SESSION.md
  00_CORE_STARTUP/WLJ MASTER PROMPT — DANNY'S PREFERENCES.md
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
