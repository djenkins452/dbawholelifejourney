# 98 · Session Transition Protocol

**Responsibility of this document:** how to **close a chat** — the doctrine of moving from one session to the next without losing continuity. It explains *what a good transition achieves and why*. It does **not** contain the runnable end-of-chat steps or the audit template — those live in the operational executor `@WLJ_SYSTEM_PROMPTS/99_PREPARE_NEXT_CHAT.md`, which implements this protocol.

---

## 1. The core idea

A session ends by **improving the permanent institutional memory**, not by writing a longer handoff. The startup package is the institutional memory of the WLJ Chief of Staff — it should become *richer* over time. `00_NEXT_CHAT_STARTUP.md` is temporary session state — it should become *smaller* over time.

> **Every session should improve the startup package.**
> **Every session should shrink `00_NEXT_CHAT_STARTUP.md`.**
> Every permanent lesson migrates into one of the permanent startup documents; the bootloader is never allowed to grow into another massive continuation prompt.

Continuity does not come from a big continuation prompt. It comes from durable knowledge living in the right permanent document, plus a short bootloader that says "here's what we're mid-way through."

## 2. Fold knowledge UP, don't pile it sideways

When a session establishes something durable, it belongs in a **permanent** document, not in the bootloader:

| If the session established… | It belongs in… |
|---|---|
| A new fact about what WLJ is / the architecture / a lesson | `01_READ_FIRST…ARCHITECTURE.md` |
| A protected principle or a change to one (Constitutional Review) | `02_WLJ_CONSTITUTION.md` |
| A durable engineering rule, gate, or discipline | `03_ENGINEERING_OPERATING_GUIDE.md` |
| A durable preference about working with Danny | `04_DANNY_WORKING_PREFERENCES.md` |
| A change to how transitions work | this document (`98`) |
| A detailed contract/runbook/coverage fact | the matching `docs/` supporting doc |
| **Only** transient sprint state (current work, open bugs, waiting-on) | `00_NEXT_CHAT_STARTUP.md` (the bootloader) |

Before writing any item into the bootloader, ask: **"Has this become a permanent truth?"** If yes, put it in the permanent doc and leave the bootloader pointing at it (or nothing).

## 3. What a transition must guarantee

1. **Nothing durable is lost.** Every lasting decision, principle, rule, or preference from the session is captured in a permanent document.
2. **No duplication.** A fact lives in exactly one place. Each document keeps its single responsibility (see `99_REFERENCE_INDEX.md`).
3. **Supporting docs stay honest.** Contracts, runbooks, coverage docs, changelog, and — only if user-visible — release notes reflect what actually changed (results, not intentions).
4. **The bootloader is lean and current.** `00_NEXT_CHAT_STARTUP.md` contains only live sprint state, nothing constitutional or architectural.
5. **The transition is auditable.** The executor produces a **Transition Audit** (checklist in `99_PREPARE_NEXT_CHAT.md`) so Danny can see, at a glance, exactly what moved and that nothing was dropped.
6. **Emerging preferences are persisted, not remembered.** Any durable working preference recognized *during* the session — including ones Danny stated in passing — is folded into the owning governing document at this transition. Danny should never have to remember to ask for it (see `04_DANNY_WORKING_PREFERENCES.md` → "auto-surface preference-persistence prompts").
7. **A session that pivoted is characterized by its architectural progression, not its starting task.** When a session *changes nature* midway — e.g. a debugging exercise that reframes into an architecture decision — the transition records the **progression** (what was learned, what class was identified, what direction was chosen), never a flat list of disconnected fixes that hides the pivot. The bootloader and changelog should let the next session see *why* the direction changed, so the pivot is a durable lesson rather than a surprise. *(Origin: the 2026-07-21 Journal session, which began as CSS layout debugging and ended as Journal Workspace Architecture — the Focus Compose / Workspace Dock direction; the development discipline that triggers such a pivot mid-session lives in `03 §6a`.)*

## 4. When it runs

**Prefer milestone boundaries over marathon sessions.** The best time to transition is when **one coherent milestone is complete and verified** — not when a chat has merely grown long. Waiting until reasoning quality degrades is a worse outcome than closing at a clean boundary: finish the milestone, verify it, run the executor, and begin the next milestone in a fresh chat. (This matches Danny's working preference; `04_DANNY_WORKING_PREFERENCES.md` → "Work in milestones, not marathons.") A chat becoming large is still a valid trigger — but the *milestone* is the primary one.

**Separate architecture sessions from implementation sessions — and close an architecture session at the moment it turns into implementation.** *(Learned 2026-07-21, the CoS-platform architecture arc.)* A discovery/architecture session should keep going only **while investigations are still changing the architecture** — while each answer reshapes the design. The natural boundary arrives when the architecture **stabilizes**: new investigations stop changing it and the remaining work has become *implementation* (building on the settled design) rather than *discovery*. **At that boundary, close the session and begin a fresh implementation-focused one** — do not roll straight from "we've settled the architecture" into building it in the same chat. Mixing the two in one marathon chat degrades both: architectural judgment gets rushed by the urge to build, and implementation inherits a bloated context full of settled-and-no-longer-relevant exploration. The tell that you have crossed the line: you catch yourself writing code that merely *applies* a decision already made, not testing whether the decision is right. When an architecture session produces a durable roadmap, the transition folds the *settled architecture* UP into the permanent docs and hands the next (implementation) session a bootloader whose primary focus is **"build milestone N on the certified foundation,"** not "keep exploring."

Danny runs the executor (`99_PREPARE_NEXT_CHAT.md`) at the **end** of the working chat. The next chat starts by dragging in the startup folder **plus** the regenerated `00_NEXT_CHAT_STARTUP.md`.

## 4a. The close-out improves itself

The transition is not a fixed checklist — it is **self-improving**. Every close-out (via `99_PREPARE_NEXT_CHAT.md`) runs a **Workflow Improvement Review**: *"what did we learn about the startup/transition workflow itself?"* Any lasting improvement is written back into this doctrine (`98`) or the executor (`99_PREPARE_NEXT_CHAT.md`) so Danny never has to remember it again. The executor also runs a **Deferred Work Review** (nothing postponed is silently lost) and a **Startup Package Integrity Review** (a fresh session using only the package would be missing nothing) before regenerating the bootloader.

## 5. Constitutional guardrail

A transition **may not** quietly change the architecture. If the session's work would alter a constitutional Article, that is a **Constitutional Review** (`02_WLJ_CONSTITUTION.md §3`, default NO, explicit written approval) — it is surfaced in the Transition Audit as a constitutional change, never folded in silently.

---

*This is the doctrine. The runnable procedure and the Transition Audit checklist are in `@WLJ_SYSTEM_PROMPTS/99_PREPARE_NEXT_CHAT.md`. The end-to-end workflow diagram is in `@WLJ_SYSTEM_PROMPTS/00_README_LOAD_MANIFEST.md`.*
