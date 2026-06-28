# WLJ CLAUDE OPUS 4.8 EXECUTION PLAYBOOK

*How to use Opus 4.8 capabilities while building WLJ. Additive and deletable. Subordinate to WLJ Architecture Laws — they remain the source of truth; this file never restates or overrides them.*

## 1. Prime Directive

**Aggressive execution inside protective boundaries — never aggressive architectural mutation.**

> Read speed is free; write speed is earned.
>
> **Investigate broadly. Mutate surgically.**

Go hard on understanding the system. Go slow on changing it. Velocity comes from collapsing investigation time, not from skipping the gate before a write.

And one measure sits above all the rest: **every change exists to make Beth a Chief of Staff that paying customers trust enough to rely on every day.** Correct engineering, passing tests, and clean architecture are necessary but never sufficient — they are the means; a *more trusted Beth* is the end. The implementation is not the product. **Beth is the product.** Optimize the product, not a subsystem in isolation (enforced at §5, the Acceptance Gate).

## 2. Default Operating Mode

**Work sequentially by default.** A single agent, one step at a time, is the right tool for most WLJ tasks. Reach for heavier machinery only when complexity clearly justifies it:

| Escalate to… | When |
|---|---|
| **Subagents (parallel)** | A read/audit spans many files or modules and would flood context, or you need independent verification of a finding. |
| **Workflow (fixed sequence)** | The path is known and repeatable (e.g. the debug loop) and you'll run it more than once. |
| **/goal (completion conditions)** | Work is multi-step or long-running and "done" should be checkable, not judged. |
| **Long-running / supervisory** | A large audit or sweep outlives one context window. |

If none of these triggers fire, stay sequential. Don't spin up subagents for a two-file lookup or a `/goal` for a one-line fix.

## 3. Capabilities at a Glance

| Capability | Use for | Don't use for | Hard boundary |
|---|---|---|---|
| **Subagents** | Repo discovery, dependency mapping, multi-module audits, independent verification | Any state-mutating work; sharing fast-changing context | **Read-only by default. Never fan out concurrent writers.** Children return `file:line` evidence; the parent owns every decision and every write. |
| **Workflows** | The debug loop, regression sweeps, scoped test+deploy cycles | Open-ended design; steps needing a human call | Sequences existing modes; never skips the Pre-Write Gate. |
| **/goal** | Multi-step or long-running tasks | Trivial fixes | Conditions set *before* work; scaled to the task (see below). Never mark done on a failed condition — HALT. |
| **Long-running / agent view** | Big audits, staged work | Unattended piles of unreviewed writes | Investigation may run unattended; **changes checkpoint and stay reviewable.** One orchestrator per goal; the supervisor verifies, never mutates. |

A `/goal` defines, scaled to the work at hand (investigation, debugging, architecture, or implementation):

- **Proof of success** — the concrete evidence the goal is met (`file:line` for a root cause, a passing check, a confirmed answer).
- **Scoped validation** — the narrowest test or verification that proves it; never the full suite unless asked.
- **Rollback confidence** — when the goal changes code, a revertible path. Omit when nothing is mutated.
- **Expected outcome** — the user-visible result or system behavior that should follow.

Don't bolt on deploy gates when deployment isn't part of the goal. Keep conditions lightweight and matched to the task.

## 4. Pre-Write Gate

Before any code change, all five must hold — otherwise keep investigating or escalate:

1. **Root cause proven** with `file:line` evidence (no speculative fixes).
2. **Blast radius mapped** — every reader/caller audited (use subagents).
3. **Minimal change** — smallest diff that fixes the proven cause; modify before adding.
4. **Complies with WLJ Architecture Laws** (phase boundaries, schema/streaming parity, no silent failures, deterministic rendering/decisioning).
5. **Rollback path + verification plan** — revertible; scoped tests only; expected user/CoS/telemetry behavior stated.

## 5. Acceptance Gate — The Three Gates of Done

*The Pre-Write Gate (§4) decides whether to **start** a change. This gate decides whether work is actually **finished**.* It is mandatory before recommending any implementation, declaring any sprint complete, or advising Danny to move on. All three must hold:

1. **Engineering Quality** — correctness, safety, maintainability, scoped tests green, complies with the Architecture Laws.
2. **Product Quality** — real customer value, less friction, more trust, a better overall experience — not just a greener subsystem.
3. **Chief-of-Staff Quality** — does Beth behave more like an *elite* Chief of Staff? Would tomorrow morning's conversation with a paying customer be better? Does this move WLJ closer to indispensable?

**Gate 3 is not optional, and Engineering + Product being green does not override it.** A technically excellent, well-tested change that does not materially improve Beth's ability to function as a trusted Chief of Staff is **not done** — name that gap *before* recommending further work or advising Danny to move on. If a sprint passed its tests but Beth is no more trustworthy, say so.

**Self-check (internal — these shape the recommendation; normally do NOT echo them back to Danny):**
- Does this make Beth more trustworthy?
- Would a paying customer notice and value this improvement?
- Does it improve the actual conversational experience?
- Does it reduce false, stale, irrelevant, or misleading responses?
- Am I optimizing a subsystem instead of the overall product experience?
- Am I solving the *governing* problem or only a local implementation problem?
- If this shipped today, would Beth feel more like an exceptional human Chief of Staff?

Run these silently before every "this is complete" or "move on" recommendation. If you find yourself optimizing architecture without improving Beth, **pause and re-evaluate before recommending anything** — every subsystem exists only to improve Beth's ability to serve the customer.

## 6. Incremental Adoption

We're still learning Opus 4.8. Bias toward the left column.

**Go aggressive (high value, low risk):**
- Repo discovery and "where is X used" mapping
- Dependency / caller graphs
- Multi-module audits and consistency checks
- Regression verification and scoped test runs
- Root-cause debugging (trace + audit)
- Performance investigation (find the slow path; don't refactor it yet)

**Hold off — propose, don't autonomously change (protected):**
- Beth / CoS reasoning and narration
- Signal pipeline and the deterministic renderer
- SAE / state engines and the three-phase execution path (UAIO is sole writer)
- Health / medical logic
- Core architecture, governance docs, and the laws themselves

In the right-column areas, use Opus aggressively to *investigate*, then bring a proven, minimal proposal rather than a finished mutation.

## 7. Escalate to Danny when…

- A fix would touch a protected area's behavior (especially Beth's).
- Root cause can't be proven and the next step is a change to protected code.
- **The blast radius is unclear.**
- Scope is creeping past the proven root cause.
- A migration is irreversible or a destructive operation seems needed.
- Two valid fixes have materially different architectural tradeoffs.
- A prompt instruction conflicts with an Architecture Law (state it, recommend the compliant path).

## 8. Red Lines (never autonomous)

- Editing or "tidying" the Architecture Laws, Domain Registry, or Signal Ontology.
- Letting an LLM/Beth fabricate state or turn a rollup into per-item truth.
- Adding a second writer to the execution path or bypassing UAIO.
- `except Exception: pass` on a critical path; making a safety gate fail open.
- Concurrent state-mutating subagents.
- **Broad refactors without explicit Danny approval** (no "while I'm here" modernization or expansion).
- Running the full ~4,400-test suite unprompted, or skipping scoped tests / migration check / changelog before deploy.
- Destructive git/DB ops (force-push, reset --hard, drop tables) or skipping hooks.
- Deploying on unproven root cause, or marking a `/goal` done on a failed condition.
- Declaring a sprint complete or advising Danny to move on when the **Chief-of-Staff gate (§5, Gate 3)** is unmet — even with Engineering and Product gates green.

---

*Subordinate to WLJ Architecture Laws. Additive — delete with zero effect on existing prompts. Last updated: 2026-06-28 (added §5 Acceptance Gate — the three Gates of Done, anchored on "Beth is the product").*
