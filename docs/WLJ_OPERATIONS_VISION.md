# WLJ Operations — Subsystem Vision & Living Roadmap

> **This is the authoritative governing document for the entire WLJ Operations subsystem.**
> It is not a one-time design note — it is a **living engineering document**. Every completed
> milestone, every new phase, every architectural decision, and every deployment updates it.
> At any moment it must accurately answer: *What is WLJ Operations? Why does it exist? What
> principles govern it? What phases exist? What is done, in progress, remaining, or deferred?
> What decisions have been made? What future work is already envisioned?*
>
> Think of it exactly like `WLJ_PRODUCT_VISION.md` and the `WLJ_CONSTITUTION.md`: it evolves
> as the subsystem evolves, and it always represents reality.
>
> **Status:** CANONICAL · Living roadmap. **Established:** 2026-07-11.
> **Authority:** Governing (Operations subsystem). **Audience:** Engineer / Operator.
> **Governed by:** `WLJ_CONSTITUTION.md`, `WLJ_PRODUCT_VISION.md`,
> `WLJ_LLM_TRUTH_ACTION_CONTRACT.md`, `WLJ_REQUEST_PATH_SAFETY.md`.
> **Companion operational audit:** `WLJ_OPS_WALL_COVERAGE.md` (coverage matrix + OPS-N backlog).

---

## 1. What WLJ Operations Is

**WLJ Operations is a new Layer 1 Truth Domain.**

It is *not* an enhancement to the Chief of Staff. It is *not* a second reasoning engine. It is
*not* another conversational AI. It is a peer of Health, Finance, Meals, Journal, and
Relationships: a domain that owns **deterministic operational truth** about the running system.

Every other truth domain answers *"what is deterministically true about the user's life?"* — their
weight, their spending, their schedule. WLJ Operations answers the same shape of question about the
*platform itself*: *"what is deterministically true about the health of every critical production
component right now, what recovered automatically, and what still needs a human?"*

The Chief of Staff consumes Operations Truth **exactly as it consumes every other truth domain** —
through composed, evidence-backed briefings, never raw signals, never bespoke reasoning. This is the
whole point: by making Operations a truth domain instead of a CoS feature, we preserve every
architectural decision the CoS architecture has spent months earning, and we get operational
intelligence *for free* the same way the CoS gets health intelligence for free.

---

## 2. Mission

WLJ Operations is the **autonomous operational nervous system** of Whole Life Journey.

It continuously observes every critical production component, maintains deterministic operational
truth, attempts safe deterministic recovery whenever possible, verifies the outcome, records every
action, and escalates only when automation has reached its safe limit.

Its objective is simple:

> **Human intervention should become the exception, not the rule.**

WLJ Operations **never reasons.** It **never converses.** It **never becomes another AI assistant.**

It owns only:

- deterministic operational **truth**
- deterministic **recovery**
- deterministic **verification**
- deterministic **auditing**
- deterministic **escalation**

Nothing else.

---

## 3. Architectural Principles (Governing)

These are the non-negotiable laws of the subsystem. Any change to one is an architectural decision
that must be recorded in §10 (ADR Log).

1. **WLJ Operations is a Layer 1 Truth Domain** — a peer of Health, Finance, Meals, Journal, Relationships.
2. **WLJ Operations never performs reasoning.** Every statement is a deterministic reduction over evidence.
3. **WLJ Operations never converses.** It publishes truth; it does not talk.
4. **The Chief of Staff architecture remains unchanged.** Operations adds nothing to it and complicates nothing in it.
5. **The Chief of Staff simply consumes Operations Truth** — as composed briefings, exactly like every other domain.
6. **Every operational statement must be deterministic.** No probabilistic verdicts, no inference presented as fact.
7. **Every operational statement must be evidence-backed.** Numbers, timestamps, states — traceable to a source.
8. **Every monitor should define the safest deterministic recovery possible** — or explicitly declare that none is safe.
9. **Recovery must always be verified.** An unverified recovery is not a recovery; it is a guess.
10. **Every action must be audited.** Detection, diagnosis, recovery attempt, verification, and escalation are all recorded.
11. **Human intervention is the exception**, reached only when safe automation is exhausted.
12. **Engineering escalation occurs only after deterministic recovery is exhausted.**
13. **The Operations subsystem must continue functioning even if the Chief of Staff were removed.**
14. **The Chief of Staff must continue functioning even if the entire Operations subsystem were removed.**

Principles **13** and **14** together define a deliberate **independence requirement**: the two
subsystems share no runtime dependency in either direction. Operations observes and heals the
platform; the CoS reasons over the person's life. Operations *offers* truth to the CoS; the CoS
*chooses* whether to surface it. Neither may become load-bearing for the other.

### 3.1 Request-path safety (inherited law)

Operations is bound by `WLJ_REQUEST_PATH_SAFETY.md` without exception. **All observation, scoring,
diagnosis, recovery, and verification run in background workers** (the SAME cycle / Celery tasks).
HTTP request paths (the Command Center page, the 2s poll endpoint, any action endpoint) may **only**
read pre-computed cache/DB snapshots. If a snapshot is not yet available, the surface returns a
"pending" state — **never** a live computation. This is why the entire telemetry payload is assembled
inside `build_ops_stream_payload()` on the 60s SAME cycle and merely *read* by the view.

### 3.2 The "eliminate the class" posture (inherited law)

When Operations recovery is designed, the default question is **not** "how do we detect this failure
faster?" but "**can we remove the condition that makes this class of failure possible?**" A monitor
whose failure class can be structurally eliminated should prefer elimination over a recovery routine —
bounded by blast radius (per the Constitution). Recovery routines exist for the classes we cannot yet
eliminate.

---

## 4. Recovery Safety Classification (Governing)

Before any recovery code is written, every deterministic recovery action must be assigned to exactly
one of **five safety classifications**. The classification — not a developer's judgment in the moment —
decides whether an action may run automatically, whether it requires operator approval, or whether it
demands deliberate engineering. **No monitor may execute a recovery whose classification has not been
declared.** This is the single most important safety control in the subsystem.

| Class | Name | Automation | Retry / Verification | Examples |
|---|---|---|---|---|
| **R0** | **Observe Only** | **None.** Detection only. | No recovery exists; **engineering escalation required.** | Any condition with no safe deterministic fix (data corruption suspicion, unknown root cause, novel failure). |
| **R1** | **Safe Idempotent Recovery** | **Automatic.** | **Unlimited retries acceptable** *if verification succeeds.* Always verify. | Retry failed job · refresh cache · refresh snapshot · recompute derived data. |
| **R2** | **Low-Risk Service Recovery** | **Automatic.** | **Bounded by retry policy** (attempts + cooldown). **Always verify.** | Restart worker · restart scheduler · requeue work. |
| **R3** | **Stateful Recovery** | **Never automatic.** Requires **explicit operator approval.** | Verification still required after the approved action. | Restart Redis · restart PostgreSQL · restart a Railway service · restart infrastructure components. |
| **R4** | **Destructive Recovery** | **Never automated. Never approval-only.** Requires **deliberate engineering intervention.** | Verification required; performed by a human under change control. | Restore backup · delete data · rebuild indexes · repair corrupted data. |

**Governing rules:**
- The classification is a property of the **recovery action**, declared in the monitor's recovery policy (Phase III) and recorded in the ADR log when first assigned.
- **R1/R2 are the only classes the subsystem may execute autonomously.** R2 is always bounded; R1 may retry freely only because each attempt is idempotent *and* verified.
- **R3 requires a human to say yes** — Operations may *prepare* and *stage* the action and present it, but the execute step is gated on explicit operator approval.
- **R4 is never offered as a one-click action.** Operations escalates with full context; a human performs it deliberately under change control.
- When in doubt, **classify higher (safer).** An action is R2 only when it is provably safe and reversible-by-verification; otherwise it is R3.

---

## 5. Standard Recovery Lifecycle (Governing)

Every monitor — present and future — follows the **exact same** recovery sequence. This uniformity is
what lets recovery become configuration (Phase III) rather than bespoke control loops, and what makes
the audit trail (Principle 10) identical across the whole subsystem.

```
        ┌─────────┐
        │ Detect  │   (Phase I — already exists)
        └────┬────┘
             ▼
        ┌──────────┐
        │ Diagnose │   what specifically is wrong, from evidence
        └────┬─────┘
             ▼
          ╔══════╗
          ║ Safe?║   (recovery class R1/R2 AND within policy?)
          ╚══╤═══╝
        No ──┘   └── Yes
        ▼             ▼
  ┌──────────┐   ┌─────────┐
  │ Escalate │   │ Recover │   execute the single safest deterministic action
  └──────────┘   └────┬────┘
   (R0/R3/R4)         ▼
                 ┌─────────┐
                 │ Verify  │   deterministic check that health was restored
                 └────┬────┘
                      ▼
                  ╔════════╗
                  ║Healthy?║
                  ╚═══╤════╝
                Yes ──┘   └── No
                ▼             ▼
           ┌───────┐      ╔═══════╗
           │ Audit │      ║ Retry?║   (attempts left under retry policy?)
           └───┬───┘      ╚═══╤═══╝
               ▼         Yes ─┘   └── No
        ┌──────────────┐  ▼            ▼
        │ Close Incident│ (Recover   ┌────────────────────────┐
        └──────────────┘  again)     │ Engineering Escalation │
                                     └────────────────────────┘
```

**Sequence (canonical):** Detect → Diagnose → **Safe?** → (No → Escalate) / (Yes → Recover → Verify →
**Healthy?**) → (Yes → Audit → Close Incident) / (No → **Retry?** → Yes → Recover again / No →
Engineering Escalation).

**Invariants (non-negotiable):**
- **Every path is audited** — including "Safe? = No" (escalated without recovery) and every failed recovery attempt, not only the happy path.
- **Verify always follows Recover.** There is no path from Recover to Close that skips Verify (Principle 9).
- **A recovery never closes an incident on its own claim** — only a passing Verify closes it.
- **Retry is bounded by policy** (except R1's verified-idempotent case); exhausting retries routes to Engineering Escalation (Phase IV), never to silent close.
- **Safe?** is answered *only* by the recovery classification (§4) and the retry/cooldown policy (Phase III) — never by ad-hoc logic.

This lifecycle is a **required contract for every future monitor.** Phase III makes it declarative;
Phase II implements it for the first recovery classes.

---

## 6. Operational Maturity Model (Governing)

A long-term maturity scale for the subsystem, **independent of the implementation phases**. Phases are
*how we build*; maturity levels are *how capable the running system is*. A component can sit at a
different maturity level than the subsystem as a whole.

| Level | Name | Meaning | Phase alignment |
|---|---|---|---|
| **O0** | **Invisible** | Nothing is monitored; failures are discovered by users. | Pre–Phase I |
| **O1** | **Observable** | Problems are visible, evidence-backed, and explained. | **Current — Phase I** |
| **O2** | **Recoverable** | Deterministic recovery exists and is verified. | Phase II / III |
| **O3** | **Autonomous** | Self-healing succeeds without operator involvement. | Phase VI |
| **O4** | **Predictive** | Operations predicts incidents before they occur. | Phase VII |
| **O5** | **Self-Optimizing** | Operations continuously improves itself using deterministic operational history. | Beyond Phase VIII/IX |

**Current subsystem maturity: O1 (Observable).** The whole platform is visible; nothing yet
self-heals. Individual monitors advance up this ladder as recovery, autonomy, and prediction are added
to them — the subsystem's overall level is the *minimum* meaningful level across its critical monitors,
not the maximum any one has reached. **O5** is deliberately the summit: it depends on Operations Memory
(§7) — deterministic operational history rich enough to tell the subsystem which recoveries work and
which permanent fixes ended a recurring class.

---

## 7. Operations Memory (Future Capability)

> **Status: FUTURE.** Not built. Reserved architecture. Earliest natural home is Phase VIII
> (Operational Excellence) / the O5 maturity level.

**Operations Memory is NOT AI memory.** It is **deterministic operational history** — a structured,
queryable record of how each recurring incident class has behaved and been resolved over time. It is the
**institutional memory** of WLJ Operations: what turns a subsystem that recovers the *same* incident a
hundred times into one that recognizes the pattern and drives toward a permanent fix.

Each recurring incident class should eventually maintain deterministic facts such as:

- **Times observed** (count + first/last seen)
- **Average recovery time** (MTTR for this class)
- **Typical recovery method** (which R-class action usually resolves it)
- **Successful permanent fix** (the change that ended the class, if any)
- **Related ADRs** (architectural decisions taken because of it)
- **Related commits** (the SHAs that touched it)
- **Regression history** (did a "fixed" class return? when?)

**Why it matters:** it operationalizes the Constitution's *"eliminate the class"* posture with evidence —
a recurring R1 incident with a rising observation count and no permanent fix is exactly the signal that
the *condition* should be removed, not recovered forever. Operations Memory makes that argument in
deterministic numbers rather than intuition. It is also the substrate for O5 self-optimization: the
subsystem cannot improve itself without a factual record of what it has already tried.

**Explicitly out of scope for now:** any reasoning, prediction, or learning *over* this memory. Phase VII
may forecast from it and Phase VIII may measure with it, but Operations Memory itself is only the
deterministic ledger — never a mind.

---

## 8. Phased Roadmap

Nine phases carry WLJ Operations from *"know everything"* to a world-class autonomous operations
platform. Each phase below records **Purpose · Goals · Capabilities · Deliverables · Success Criteria ·
Dependencies · Future Expansion · Completion Status**. The authoritative checklist with dates, SHAs,
and test references is the **Living Status Section (§9)** — this section is the narrative; §9 is the ledger.

---

### Phase I — Operations Visibility

**Purpose:** Know everything. Nothing important happens in production without being visible.

**Goals:** A single deterministic operational surface that answers the five operator questions in ten
seconds — *Am I okay? / What's wrong? / Why? / Who's affected? / What next?* — with every claim
evidence-backed and computed off the request path.

**Capabilities:**
- Operations Command Center (single read-only surface at `/admin-console/ops/`, 2s poll)
- Executive Operations Summary (deterministic synthesis over all telemetry)
- Operational health scoring (0–100 System Integrity score with posture bands)
- Explainable scoring (per-component penalty breakdown — *why* the score is what it is)
- Incident detection (SAME anomaly engine, 11 detectors, 60s cadence)
- Incident history (persistent anomaly lifecycle: active → resolved)
- Customer impact (per-incident and worst-of roll-up)
- Root-cause evidence (dependency-graph root-cause chains)
- Trends (per-KPI direction/velocity from persisted KPI history)
- Dashboard (engine cards, narrative, subsystems, integrity)
- Historical reporting (snapshots for score, storage, narrative, maturity)

**Deliverables:** `apps/core/ai_observability/` (telemetry, SAME engine, executive synthesis, four new
monitors OPS-1…4), the Operations Command Center page + 2s stream endpoint, persistent observability
models, and the coverage audit `docs/WLJ_OPS_WALL_COVERAGE.md`.

**Success Criteria:** A component is observable **only if** it is a registered engine with a heartbeat
cadence, has a dedicated telemetry section, or is a scheduled Beat task tracked by the scheduled-task
monitor. Everything else running in production is honestly reported as *not covered* (see the OPS-5…10
backlog). The five operator questions are answerable from the Command Center in ten seconds.

**Dependencies:** Celery/Redis, the SAME 60s cycle, the engine registry, `WLJ_REQUEST_PATH_SAFETY.md`.

**Future Expansion:** The OPS-5…10 backlog (Postgres depth & DB admin, per-component `owner`, dead-job
detection, confirmation-queue/attachment/audit-lag health, build-runner/deploy observability, directly
measured Beat). Owner dimension is currently absent system-wide (OPS-6).

**Completion Status:** **Mostly Complete** — visibility surface and OPS-1…4 shipped; OPS-5…10 remain as
tracked backlog. See §9 for the exact ledger.

---

### Phase II — Deterministic Recovery

**Purpose:** Stop *reporting* problems; start *fixing* them.

**Goals:** Give each monitor the ability to attempt a safe, deterministic recovery and verify it —
turning a passive dashboard into an active healer for the classes where recovery is unambiguously safe.

**Capabilities:** Each monitor gains the five-verb lifecycle:
- `detect()` — is something wrong? (already exists as Phase I detection)
- `diagnose()` — what specifically is wrong, from evidence?
- `recover()` — the single safest deterministic action for this condition
- `verify()` — did the recovery actually restore the healthy state?
- `escalate()` — if not, hand off with full context

**Examples (candidate recoveries):** restart workers, restart schedulers, retry jobs, clear cache,
requeue work, refresh snapshots, recompute derived data — each **followed by verification before the
incident is closed.**

**Deliverables:** *(planned)* a per-monitor recovery interface, recovery attempt records, and
verification gates that block auto-close on unverified recovery.

**Success Criteria:** *(planned)* For every recovery class deemed safe, an incident is detected,
recovered, and verified with zero human action — and any unverified recovery escalates rather than
silently closing.

**Dependencies:** Phase I truth (detection + evidence), the audit model, `WLJ_REQUEST_PATH_SAFETY.md`
(recovery runs in workers, never on the request path).

**Future Expansion:** Feeds Phase III (standardization) and Phase VI (self-healing metrics).

**Completion Status:** **Planned** — not started. This milestone is documentation-only; no recovery
code exists yet.

---

### Phase III — Recovery Framework

**Purpose:** Standardize recovery so it becomes **configuration, not one-off code.**

**Goals:** Extract the Phase II per-monitor recovery patterns into a single declarative framework every
monitor owns a policy in.

**Capabilities:** Each monitor declares a **recovery policy**:
- **Retry policy** (how many attempts, backoff)
- **Cooldown** (minimum interval between recovery attempts — prevent thrash)
- **Verification** (the deterministic check that proves health was restored)
- **Escalation** (when to stop and hand to engineering)
- **Audit** (what is recorded for every attempt)

**Deliverables:** *(planned)* a recovery-policy schema + executor; migration of Phase II ad-hoc
recoveries onto it.

**Success Criteria:** *(planned)* Adding recovery to a new monitor is writing a policy, not writing a
control loop.

**Dependencies:** Phase II.

**Future Expansion:** Policies become the substrate for Phase VI autonomy and Phase VIII effectiveness
measurement.

**Completion Status:** **Planned.**

---

### Phase IV — Engineering Escalation

**Purpose:** When automation ends, engineering begins — and the handoff is deterministic and complete.

**Goals:** When safe recovery is exhausted, automatically assemble everything an engineer (or Claude)
needs to investigate, so no one starts a production incident from a blank page.

**Capabilities:** Automatically gather Logs · Metrics · Dependency graph · Runtime state · Recovery
attempts · Recent deployments · Recent commits · Engine health · Recent changes — and generate a
**deterministic prompt** for Claude, in one of several types:
- **Investigation** (diagnose an unknown failure)
- **Repair** (fix an identified defect)
- **Architecture Review** (a class of failure recurs — is the design wrong?)
- **Regression** (a previously-fixed condition returned)

**Deliverables:** *(planned)* an escalation-context assembler + prompt generator.

**Success Criteria:** *(planned)* Every escalation arrives with complete, deterministic context and a
typed, ready-to-run prompt — never "something is wrong, go look."

**Dependencies:** Phases I–III; the runtime-trace debugging standard (`WLJ_RUNTIME_TRACE_DEBUGGING.md`).

**Future Expansion:** Escalation quality becomes a Phase VIII metric (engineering effort saved).

**Completion Status:** **Planned.**

---

### Phase V — Chief of Staff Awareness

**Purpose:** Expose Operations **Truth** to the Chief of Staff — **not** Operations *intelligence*.

**Goals:** Let the person ask the CoS about the platform ("How is WLJ doing?", "Anything need my
attention?") and have the CoS answer from a composed Operations briefing, exactly as it answers a
health question from a health briefing.

**Capabilities (example CoS-surfaced truth):**
- "Three incidents recovered automatically."
- "One engineering issue remains."
- "Everything is healthy."

**The boundary is strict:** Operations **publishes** truth. The Chief of Staff **decides if and when**
to interrupt Danny. **Operations never interrupts directly.** This is a truth-domain integration
(a composed Operations briefing consumed through the existing envelope), **not** a new CoS capability
and **not** a change to CoS reasoning.

**The division of responsibility (explicit):**

*Operations publishes deterministic operational truth, including an expression of deterministic urgency:*
- `operational_status` — the current health posture (e.g. HEALTHY / DEGRADED / INCIDENT).
- `priority` — deterministic ranking of what matters most right now.
- `urgency` — how time-sensitive the condition is, derived from evidence (duration, customer impact, trend).
- `attention_required` — a deterministic boolean: does this cross the threshold where a human *could* be needed?
- `recommended_action` — the single deterministic next action (or "none — monitoring").

*The Chief of Staff — and only the Chief of Staff — determines:*
- **whether** interruption is appropriate (given everything else in the person's life and context),
- **when** the interruption should occur (now, at a daypart boundary, never),
- **how** it should be communicated (tone, framing, channel).

This keeps **all reasoning inside the Chief of Staff** while letting Operations express **deterministic
urgency**. Operations saying `attention_required = true, urgency = high` is a *fact about the platform*,
not a command to interrupt — the CoS still owns the decision. Operations never pushes a notification and
never reaches the user except through the CoS's judgment.

**Deliverables:** *(planned)* an Operations truth briefing + a page-summary/tool the CoS can consume;
zero CoS reasoning code.

**Success Criteria:** *(planned)* The CoS can answer "how is the platform doing?" from deterministic
Operations truth, and chooses surfacing on its own — with Operations never pushing a notification.

**Dependencies:** Phase I truth; the truth/action contract; the Current Context page-summary pattern.

**Future Expansion:** Richer Operations briefings as later phases add recovery history and forecasts.

**Completion Status:** **Planned.**

---

### Phase VI — Autonomous Operations

**Purpose:** Self-healing as the normal state, with escalation only when necessary.

**Goals:** Close the loop: recovery attempts + verification + recovery history, with human escalation
as the exception — and measure how well it's working.

**Capabilities — dashboard metrics:**
- Incidents today
- Recovered automatically
- Manual recoveries
- Failed recoveries
- Average recovery time
- Recovery success rate

**Deliverables:** *(planned)* recovery-history storage + the autonomy metrics panel.

**Success Criteria:** *(planned)* Most incidents recover and verify without a human; the metrics prove it.

**Dependencies:** Phases II–IV.

**Future Expansion:** Feeds Phase VIII operational-excellence measurement.

**Completion Status:** **Planned.**

---

### Phase VII — Predictive Operations

**Purpose:** Prevent incidents before they happen.

**Goals:** Move from reactive recovery to proactive prevention via deterministic trend analysis.

**Capabilities:** Trend analysis · Capacity forecasting · Operational drift · Storage forecasts ·
Queue forecasts · Performance-degradation forecasts · OpenAI upstream trend monitoring.

**Deliverables:** *(planned)* forecasting over the historical snapshots already accumulating in Phase I
(`StorageSnapshot`, integrity/KPI history, upstream buckets).

**Success Criteria:** *(planned)* Operations flags "you will run out of X in N days" before the incident.

**Dependencies:** Phase I historical snapshots (already accumulating).

**Future Expansion:** Predictive signals become CoS-surfaceable truth (Phase V).

**Completion Status:** **Planned.**

---

### Phase VIII — Operational Excellence

**Purpose:** Measure the Operations subsystem **itself**.

**Goals:** Hold Operations to the same evidence standard it holds everything else — prove it is
effective.

**Capabilities:** Recovery effectiveness · MTTR · Engineering effort saved · Customer impact avoided ·
Operational maturity.

**Deliverables:** *(planned)* a self-measurement panel over recovery/escalation history.

**Success Criteria:** *(planned)* Operations can show, deterministically, that it is reducing human
toil and customer impact over time.

**Dependencies:** Phases II, IV, VI.

**Future Expansion:** Maturity scoring parallels the existing system-maturity engine.

**Completion Status:** **Planned.**

---

### Phase IX — Mission Control

**Purpose:** The completed vision — a world-class autonomous operations platform.

**Goals:** Observe · Repair · Verify · Audit · Escalate · Inform the Chief of Staff — as one coherent
platform rather than a dashboard that shows failures.

**Capabilities:** The surface becomes **Mission Control** — Engineering Workspace · Executive Reporting ·
Operational History — not merely a failure list.

**Deliverables:** *(planned)* the unified Mission Control experience.

**Success Criteria:** *(planned)* An operator runs WLJ from Mission Control: sees health, watches
recovery happen, reviews history, and only rarely intervenes.

**Dependencies:** All prior phases.

**Future Expansion:** The living end-state; this document continues to track drift and refinement.

**Completion Status:** **Planned.**

---

## 9. Living Status Section (The Ledger)

> **This section is ALWAYS maintained.** Every completed item records **Completion Date · Git SHA ·
> Deployment Date · Docs Updated · Tests Added**. Checkbox legend: `[x]` Completed · `[~]` In Progress ·
> `[ ]` Planned · `[-]` Deferred · `[✗]` Cancelled.

### Phase I — Operations Visibility · **Mostly Complete**

| ✔ | Sub-feature | Completed | Git SHA | Deployed | Docs | Tests |
|---|---|---|---|---|---|---|
| [x] | Operations Command Center surface (`/admin-console/ops/`, 2s poll) | 2026-07-11 | `0fec5f77` | 2026-07-11 | Coverage audit §1 | `tests_ops_wall_v2.py` |
| [x] | Telemetry payload builder (`build_ops_stream_payload`, ~27 sections) | 2026-07-11 | `0fec5f77` | 2026-07-11 | Coverage audit §1 | `tests_payload_builder.py` |
| [x] | SAME anomaly engine (11 detectors, 60s) | 2026-07-11 | prior | 2026-07-11 | Coverage audit §1 | `tests_ops_wall_v2.py` |
| [x] | Executive Operations Summary / synthesis (`ops_executive.py`) | 2026-07-11 | `0fec5f77` | 2026-07-11 | Coverage audit §1 | `test_ops_executive.py` (9) |
| [x] | Explainable 0–100 System Integrity score + posture bands | 2026-07-11 | `0fec5f77` | 2026-07-11 | Coverage audit §1 | `test_ops_executive.py` |
| [x] | Incident detection + persistent history (`OpsAnomaly` lifecycle) | 2026-07-11 | prior | 2026-07-11 | Coverage audit §1 | `tests_ops_wall_v2.py` |
| [x] | Root-cause chains (dependency graph) | 2026-07-11 | `0fec5f77` | 2026-07-11 | Coverage audit §1 | `test_ops_executive.py` |
| [x] | Customer-impact roll-up (per-incident + worst-of) | 2026-07-11 | `0fec5f77` | 2026-07-11 | Coverage audit §1 | `test_ops_executive.py` |
| [x] | Per-KPI trends (persisted KPI history) | 2026-07-11 | `0fec5f77` | 2026-07-11 | Coverage audit §1 | `test_ops_executive.py` |
| [x] | **OPS-1** Scheduled Beat-task monitor (all non-engine Beat tasks) | 2026-07-11 | `bc8f49b4` | 2026-07-11 | Coverage audit §4 | `test_scheduled_task_monitor.py` (13) |
| [x] | **OPS-2** Storage/volume monitor (Postgres/Redis/disk + `StorageSnapshot`) | 2026-07-11 | `8d7dab87` | 2026-07-11 | Coverage audit §4 | `test_storage_monitor.py` |
| [x] | **OPS-3** Chat-queue monitor (depth/wait/throughput/stuck/starvation) | 2026-07-11 | `8d7dab87` | 2026-07-11 | Coverage audit §4 | `test_chat_queue_monitor.py` |
| [x] | **OPS-4** OpenAI upstream-health monitor (avail/latency/degradation) | 2026-07-11 | `8d7dab87` | 2026-07-11 | Coverage audit §4 | `test_upstream_health.py` |
| [ ] | **OPS-5** Postgres depth + DB administration | — | — | — | — | — |
| [ ] | **OPS-6** Per-component `owner` dimension (cross-cutting) | — | — | — | — | — |
| [ ] | **OPS-7** Dead-job / stuck-task / general Celery-retry aggregation | — | — | — | — | — |
| [ ] | **OPS-8** Confirmation queue, attachment persistence, dedup, audit-lag | — | — | — | — | — |
| [ ] | **OPS-9** Build-runner / deploy-pipeline observability | — | — | — | — | — |
| [ ] | **OPS-10** Celery Beat directly measured (not inferred) | — | — | — | — | — |

*OPS-1…4 detail and the ranked remediation backlog live in `WLJ_OPS_WALL_COVERAGE.md` §4 (the
authoritative coverage source). This ledger mirrors status; the coverage doc holds the as-built detail.*

### Phase II — Deterministic Recovery · **Planned**
- [ ] Per-monitor `diagnose()` · [ ] `recover()` · [ ] `verify()` · [ ] `escalate()`
- [ ] Verification gate blocking auto-close on unverified recovery

### Phase III — Recovery Framework · **Planned**
- [ ] Declarative recovery-policy schema (retry · cooldown · verification · escalation · audit)
- [ ] Policy executor · [ ] migration of Phase II recoveries onto the framework

### Phase IV — Engineering Escalation · **Planned**
- [ ] Escalation-context assembler · [ ] deterministic Claude prompt generator
- [ ] Prompt types: [ ] Investigation · [ ] Repair · [ ] Architecture Review · [ ] Regression

### Phase V — Chief of Staff Awareness · **Planned**
- [ ] Operations truth briefing · [ ] CoS-consumable page-summary/tool · [ ] no CoS reasoning added

### Phase VI — Autonomous Operations · **Planned**
- [ ] Recovery history · [ ] autonomy metrics panel (incidents/recovered/manual/failed/MTTR/success rate)

### Phase VII — Predictive Operations · **Planned**
- [ ] Trend analysis · [ ] capacity/storage/queue/performance forecasts · [ ] OpenAI trend monitoring

### Phase VIII — Operational Excellence · **Planned**
- [ ] Recovery effectiveness · [ ] MTTR · [ ] effort saved · [ ] impact avoided · [ ] operational maturity

### Phase IX — Mission Control · **Planned**
- [ ] Mission Control unification · [ ] Engineering Workspace · [ ] Executive Reporting · [ ] Operational History

### Deferred / Cancelled
- *(none yet)* — deferred items get a phase number + promotion trigger, never "maybe someday."

---

## 10. Architectural Decisions (ADR Log)

Every material Operations decision is recorded here with its rationale, so the *why* is never lost.

| # | Date | Decision | Rationale |
|---|---|---|---|
| ADR-1 | 2026-07-11 | **Operations is a Layer 1 Truth Domain, not a CoS feature.** | Preserves the constitutionally-protected CoS architecture; operational intelligence is consumed as truth, exactly like Health/Finance. No new reasoning engine, no new conversational AI. |
| ADR-2 | 2026-07-11 | **Strict bidirectional independence (Principles 13 & 14).** | Neither subsystem may be load-bearing for the other; Operations heals the platform, the CoS reasons over the person's life. Removing either must not break the other. |
| ADR-3 | 2026-07-11 | **All observation/scoring/recovery/verification run off the request path.** | Inherits `WLJ_REQUEST_PATH_SAFETY.md`. The telemetry payload is built on the 60s SAME cycle and only *read* by the Command Center — no live compute, ever (repeated 524 timeouts came from live fallbacks). |
| ADR-4 | 2026-07-11 | **Operations publishes truth; the CoS decides surfacing. Operations never interrupts directly.** | Keeps the interruption decision where the person's context lives (the CoS), not in the ops layer. Phase V is a truth integration, not a CoS capability. |
| ADR-5 | 2026-07-11 | **Prefer eliminating a failure *class* over adding a detector/recovery.** | Inherits the "eliminate the class" posture; recovery routines exist only for classes we cannot yet structurally remove, bounded by blast radius. |
| ADR-6 | 2026-07-11 | **OPS-1 monitor is a generic Beat-schedule-vs-actual reconciler**, not per-task registration. | Future Beat tasks are covered automatically; no registration drift. (As-built detail in coverage doc §4.) |
| ADR-7 | 2026-07-11 | **Recovery must verify before closing (Principle 9).** Established as a Phase II law up-front. | An unverified recovery is a guess; auto-close on an unverified recovery would manufacture false "healthy" truth — the exact class of trust-break this subsystem must never create. |
| ADR-8 | 2026-07-11 | **Five-level Recovery Safety Classification (R0–R4); only R1/R2 may auto-execute; R3 approval-gated; R4 engineering-only (§4).** | Puts the automate/approve/human-only decision in a declared property of the action, not a developer's in-the-moment judgment. "Classify higher when in doubt" makes the safe default structural. |
| ADR-9 | 2026-07-11 | **One mandatory Standard Recovery Lifecycle for every monitor (§5): Detect→Diagnose→Safe?→Recover→Verify→Healthy?→Audit/Retry→Escalate.** | Uniformity is the precondition for Phase III (recovery-as-config) and an identical audit trail; every path — including no-recovery escalation and every failed attempt — is audited. |
| ADR-10 | 2026-07-11 | **Operations expresses deterministic urgency (`operational_status`/`priority`/`urgency`/`attention_required`/`recommended_action`); the CoS owns whether/when/how to interrupt (§ Phase V).** | Lets Operations state a *fact* about platform urgency without ever owning the interruption decision — all reasoning stays in the CoS; Operations never reaches the user directly. Refines ADR-4. |
| ADR-11 | 2026-07-11 | **Operations Memory (§7) is deterministic history only — never a mind; O5 self-optimization depends on it but reasoning over it is out of scope until Phase VII/VIII.** | Preserves "WLJ owns truth, not reasoning" at the operations layer; the institutional record operationalizes "eliminate the class" with evidence, not intuition. |

*Append a new row for every material decision; never rewrite history — supersede it.*

---

## 11. Claude Responsibilities (Maintenance Contract)

**From this point forward, whenever ANY Operations work is completed, Claude MUST — automatically,
without being asked:**

1. **Update this document** (`docs/WLJ_OPERATIONS_VISION.md`).
2. **Mark completed work** in the Living Status ledger (§9) with Date · SHA · Deploy date · Docs · Tests.
3. **Adjust future phases** if the work changed the roadmap.
4. **Record architectural decisions** in the ADR log (§10).
5. **Record deferred work** (with a phase number + promotion trigger — never "someday").
6. **Update implementation status** so every checkbox reflects reality.
7. **Keep the roadmap accurate** — this document must never go stale; it always represents reality.

This is in addition to the standard On-Task-Completion protocol (changelog + user-facing docs +
commit + push main). Operations work updates *this* document as a required extra step.

---

## 12. Cross-References

- `docs/WLJ_OPERATIONS_PHASE2_PLAN.md` — the detailed Phase II (Deterministic Recovery) engineering implementation plan + risk register. Read before writing any recovery code.
- `docs/WLJ_OPS_WALL_COVERAGE.md` — the operational coverage matrix + the authoritative OPS-1…10 backlog (Phase I as-built detail).
- `docs/WLJ_REQUEST_PATH_SAFETY.md` — the never-compute-on-the-request-path law Operations inherits.
- `docs/WLJ_CONSTITUTION.md` / `WLJ_PRODUCT_VISION.md` — the apex documents this subsystem serves.
- `docs/WLJ_LLM_TRUTH_ACTION_CONTRACT.md` — the truth/action boundary the CoS↔Operations integration (Phase V) must honor.
- Code home: `apps/core/ai_observability/` (telemetry, SAME engine, executive synthesis, OPS-1…4 monitors, models).
- Surface: `/admin-console/ops/` (Operations Command Center).

---

*Last updated: 2026-07-11 — architecture refinement pass: added Recovery Safety Classification (§4),
Standard Recovery Lifecycle (§5), Operational Maturity Model (§6), Operations Memory (§7); expanded
Phase V urgency contract; ADR-8…11 recorded. Companion Phase II engineering plan authored
(`WLJ_OPERATIONS_PHASE2_PLAN.md`). Still documentation-only — no recovery code written.*
