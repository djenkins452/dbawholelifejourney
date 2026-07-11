# WLJ Operations — Phase II Engineering Implementation Plan (Deterministic Recovery)

> **Status:** PLAN · Not implemented. **Established:** 2026-07-11.
> **Authority:** Engineering plan (companion to the governing `WLJ_OPERATIONS_VISION.md`).
> **Governed by (authoritative, frozen 2026-07-11):** `WLJ_OPERATIONS_VISION.md` — §4 Recovery Safety
> Classification, §5 Standard Recovery Lifecycle, §8 Internal Architecture, §10 Package Layout, §11 Import
> Boundaries, §12 Operations Truth, §16 ADR Log, Principles 1–14. Also `WLJ_REQUEST_PATH_SAFETY.md`,
> `WLJ_CONSTITUTION.md`.
>
> This document is the deterministic blueprint for Phase II, **reconciled against the frozen architecture.**
> **No recovery code exists yet.** This plan must be reviewed (and its risks in §12 accepted) before
> implementation begins. Phase II turns the Observable subsystem (O1) into a Recoverable one (O2) for the
> R1/R2 classes — **first cut: R1 pilots only** (see §1). All new action code lives in the frozen
> **`apps/core/operations/`** package; observability/`apps/core/ai_observability/` is never modified to
> contain action logic.

---

## 1. Scope & Non-Goals

**In scope (Phase II) — all new code under `apps/core/operations/` (frozen §10):**
- A **Recovery Engine** that runs the Standard Recovery Lifecycle (vision §5) for R1/R2 actions.
- A **Recovery Policy** per recovery handler (classification, retry, cooldown, verification, escalation, recurrence).
- **Recovery Handlers** (`diagnose`/`recover`/`verify`) — action code in `operations/recovery/`, **registered by monitor key**, that *consume* Operations Truth from `ai_observability/`. Recover/verify logic is **never** added to the observability monitor classes (that would violate the frozen observation/action seam, §11).
- A **Verification framework** proving health was restored before an incident closes — reusing the *exact* observability detector predicate.
- An **Audit model** (`RecoveryAttempt`) recording every attempt on every path.
- A **Recovery execution pipeline** (background worker task, strictly downstream of the telemetry cycle, off the request path).
- An **Escalation** stub (full engineering-context assembly + prompt generation is Phase IV).
- Minimal **read-only UI** on the Command Center showing recovery attempts/outcomes.

**Terminology (frozen, vision §12):** *Operations Truth* = deterministic operational facts (owned by
`ai_observability/`). *Operations* = the action subsystem (`operations/`). *Recovery* = recovery execution.
*Verification* = deterministic proof health was restored. *Escalation* = deterministic hand-off when
recovery is unsafe or exhausted. Operations **never reasons, never converses, and never lets an
LLM/Claude execute an operational action** — Recovery actions are deterministic code; Escalation only
*prepares* context/prompts for a human to act on later (Phase IV).

**Explicit non-goals (deferred):**
- R3 (approval-gated) execution UI — **Phase III** once the policy framework exists.
- R4 destructive recovery — **never automated**; out of scope permanently.
- Declarative recovery-as-config framework — **Phase III** (Phase II may hard-code 2–3 pilots).
- Full engineering-escalation context assembly + Claude prompt generation — **Phase IV**.
- Autonomy metrics / recovery-history analytics — **Phase VI**.
- Operations Memory — **future** (§7 of the vision).
- Any CoS change — **out of scope in every Operations phase until Phase V truth integration.**

**Pilot set (first cut) — TWO R1 recoveries only.** After reconciling each candidate against the frozen
R0–R4 classification (§4) and the verification-reuses-detection invariant (vision §5), the first cut is
**two idempotent R1 actions**. The originally-proposed **chat-queue requeue was removed from the first
cut** (see below). Full per-pilot specifications are in **§1.1**.
1. **R1 — refresh a stale snapshot / recompute derived data** (a stale integrity/storage/maturity snapshot). Idempotent overwrite, zero external blast radius.
2. **R1 — re-enqueue a missed Beat task, restricted to an allowlist of provably-idempotent recompute/cleanup tasks** surfaced by OPS-1 MISSED_RUN. **User-facing send/notification/digest tasks are excluded** (a re-run could double-send).

**Removed from the first cut — chat-queue requeue (was R2):** it **cannot yet be proven safe.** A stuck
chat task may still be executing; re-enqueuing risks duplicate user-facing LLM output, double OpenAI
spend, and ownership ambiguity over the original request — with no proven idempotency/dedup key. Per the
"move it out rather than force it in" rule, it is deferred to a **later Phase II increment** with an
explicit **promotion trigger**: *a proven idempotency/dedup design (a request-scoped idempotency key +
proof the original task has terminated) exists and is tested.* Tracked, not forgotten (see §1.1).

Deliberately **no worker/scheduler restart in the first cut** either — those are R2 but higher blast
radius; add them only after the R1 pilot lifecycle is proven and audited.

### 1.1 Pilot Specifications

Each first-cut pilot, specified against the frozen classification (§4) and the verification invariant.
**Rule applied:** any action that cannot be proven safe *or* cannot reuse the exact detector predicate for
verification is moved out of the first cut rather than forced in.

**Pilot 1 — Snapshot refresh / derived-data recompute** *(KEPT)*
- **Provisional class:** R1 (Safe Idempotent Recovery).
- **Why justified:** recompute deterministically **overwrites** a derived snapshot; repeating it does no harm and has no external side effect; fully reversible-by-verification.
- **Exact action:** re-run the deterministic computation for the stale snapshot (e.g. `SystemIntegritySnapshot` / `StorageSnapshot` / `SystemMaturitySnapshot`) and write the fresh row/cache.
- **Detector predicate reused for verification:** the **same staleness check** that raised the incident (snapshot age > freshness threshold). After recompute, age resets → predicate reports healthy.
- **Blast radius:** zero external; writes one internal snapshot row + cache key.
- **Retry bound:** `max_attempts = 3`. **Cooldown:** `300s`. **Escalation:** snapshot still stale after 3 attempts → Engineering Escalation.
- **Per-handler flag:** `OPS_RECOVERY_SNAPSHOT_REFRESH`. **Rollback:** disable the flag; action is idempotent, nothing to undo.

**Pilot 2 — Missed Beat-task re-enqueue (allowlisted idempotent tasks only)** *(KEPT, constrained)*
- **Provisional class:** R1 **only for allowlisted idempotent recompute/cleanup tasks**; any task not on the allowlist stays **R0** (observe-only).
- **Why justified:** re-running a recompute/cleanup task is idempotent (it recomputes/cleans again). **User-facing send/notification/digest tasks are excluded** — a re-run could double-send; those remain R0.
- **Exact action:** `safe_enqueue(task_name)` **iff** `task_name ∈ IDEMPOTENT_RECOMPUTE_ALLOWLIST` (an explicit, reviewed allowlist; empty by default, grown one task at a time).
- **Detector predicate reused for verification:** the **same OPS-1 freshness predicate** (`scheduled_task_monitor`) — the task has recorded a run since the re-enqueue → MISSED_RUN clears.
- **Blast radius:** low, bounded to the allowlisted task's own idempotent effect.
- **Retry bound:** `max_attempts = 2`. **Cooldown:** ≥ the task's own cadence. **Escalation:** not fresh after 2 attempts → Engineering Escalation.
- **Per-handler flag:** `OPS_RECOVERY_BEAT_RETRY`. **Rollback:** disable the flag; nothing to undo (re-enqueue of an idempotent task).

**Removed from the first cut — Chat-queue requeue (was R2)** *(DEFERRED — cannot yet be proven safe)*
- **Why removed:** a "stuck" chat task (OPS-3) **may still be executing**. Re-enqueuing risks **duplicate user-facing LLM output**, **double OpenAI spend**, and **ownership ambiguity** over the original request. There is **no proven idempotency/dedup key** on chat generation, and **no clean detector predicate** for verification — "queue depth drained" does not prove the *specific* request completed exactly once.
- **What must exist to promote it (trigger):** a request-scoped **idempotency/dedup key**, deterministic proof the **original task has terminated** (not merely late), and dedup on the generated message — all **tested**. Until then it stays out.
- **Target:** a later Phase II increment (or Phase III), not the first cut.

---

## 2. Recovery Engine Architecture

**Home (frozen §10):** `apps/core/operations/recovery/` — the **action** package, physically separate
from `apps/core/ai_observability/` (observation). `operations/` is a sub-package of the `core` Django app
(like `ai_observability/`), so its models use `app_label="core"` and migrations live in
`apps/core/migrations/`. **The dependency arrow is one-way:** `operations/` imports Operations Truth from
`ai_observability/`; `ai_observability/` must **never** import `operations/` (§11; CI-enforced, §10 tests).

**Execution trigger (isolated & strictly downstream of the telemetry cycle):** recovery does **not** run
inline inside `build_ops_stream_payload()`. The telemetry cycle builds **and caches** Operations Truth
first; only then is a **separate** recovery task handed off. This guarantees a recovery fault can never
delay, lengthen, or prevent the Operations Truth payload from being built or cached.

```
run_same_cycle_task (Celery, 60s)                 # Phase I — UNCHANGED
  ├─ build_ops_stream_payload()  → detect + WRITE CACHE   (telemetry completes & caches first)
  └─ if OPS_RECOVERY_ENABLED:  safe_enqueue(run_recovery_cycle_task)   # non-blocking hand-off, last step

run_recovery_cycle_task (Celery, worker-only)     # Phase II — NEW, in apps/core/operations/
  ├─ read the ALREADY-CACHED Operations Truth payload  (consume, never re-detect)
  ├─ if payload missing/stale → NO-OP this cycle        (recovery is never load-bearing for detection)
  └─ for each active OpsAnomaly with a registered handler:
        RecoveryEngine.handle(anomaly)
          ├─ diagnose()  → RecoveryDiagnosis (evidence)
          ├─ gate: classification (R0–R4, §4) + policy (attempts/cooldown/recurrence)
          ├─ recover()   → RecoveryOutcome              (R1/R2 only)
          ├─ verify()    → VerificationResult           (reuses the observability detector predicate)
          ├─ audit (every path → RecoveryAttempt)
          └─ close | retry-next-cycle | escalate
```

**Key design decisions:**
- **Recovery consumes completed Operations Truth; it is never a detector.** It reads the cached payload + already-detected `OpsAnomaly` rows and never re-derives detection (single-producer discipline; keeps detection non-load-bearing on recovery).
- **Separate task, non-blocking hand-off.** The SAME task enqueues `run_recovery_cycle_task` via `apps/core/celery_utils.py :: safe_enqueue` as its **final** step, after the cache write. If the enqueue fails, or the recovery task is slow, dies, is disabled, or is removed entirely, **the telemetry path is unaffected** — Phase I keeps running exactly as today (Principles 13/14; the established telemetry safety limits are never lengthened).
- **`OPS_RECOVERY_ENABLED=False` is a true no-op.** The SAME task skips the enqueue entirely; no recovery task is created, no payload is read, nothing runs.
- **One engine, many registered handlers.** A `RecoveryRegistry` (in `operations/recovery/`) maps `anomaly_type → RecoveryHandler`. An anomaly with no registered handler is **R0 by default** (observe-only → escalate) — the safe default.
- **Runs entirely in the worker.** No recovery, verification, or diagnosis ever executes on the request path (ADR-3). The Command Center only *reads* recovery records.
- **Idempotent per cycle.** A recovery mid-flight or in cooldown makes the next cycle a no-op for that anomaly — safe to run every cycle.

---

## 3. Recovery Policy Model

A **declarative policy** per recovery handler (in `operations/recovery/` or `operations/policies/`),
consulted by the gate before any action. Phase II defines these as Python objects on the handler; Phase
III promotes them to configuration.

```python
@dataclass(frozen=True)
class RecoveryPolicy:
    classification: str        # "R0" | "R1" | "R2" | "R3" | "R4"
    max_attempts: int          # FINITE for EVERY class, including R1 (no unbounded loop in production)
    cooldown_seconds: int      # minimum interval between attempts (anti-thrash)
    verification_required: bool = True     # always True; present for explicitness
    verification_timeout_s: int = 120
    escalate_after_attempts: int = None    # → Engineering Escalation (defaults to max_attempts)
    requires_operator_approval: bool = False   # True for R3 (Phase III)
    # Recurrence / permanent-fix escalation (resolves the "R1 unlimited retries" wording):
    recurrence_window_hours: int = 24      # window over which recurrences are counted
    recurrence_limit: int = None           # repeated SUCCESSFUL recoveries of the same class within
                                           # the window beyond this → raise a permanent-fix escalation
    audit_every_path: bool = True          # always True
```

**On "R1 unlimited retries" (reconciling vision §4 with production code):** vision §4 states that for R1
*"unlimited retries are acceptable if verification succeeds"* — that is a statement of the **safety
property** (an idempotent, verified action does no harm when repeated). It is **not** a licence for an
unbounded loop in code. This plan is explicit: **every production policy — R1 included — has a finite
`max_attempts`, a `cooldown`, and an `escalate_after_attempts` threshold.** The two are complementary,
not contradictory: R1 *may* be repeated safely, but production still bounds it.

**Permanent-fix escalation (the "eliminate the class" guard, vision §3.2 posture):** repeated *successful*
recovery of the **same failure class** is itself a signal. When successful recoveries of a class exceed
`recurrence_limit` within `recurrence_window_hours`, the engine raises a **permanent-fix Escalation**
("this keeps happening — fix the condition, don't keep recovering it") instead of silently masking the
defect. This is the deterministic mechanism behind risk R-1.

**Gate rules (deterministic):**
- `classification in {"R0","R3","R4"}` → **do not auto-execute**; route to Escalation (R0) or approval-staging (R3, Phase III) or engineering (R4).
- `classification in {"R1","R2"}` → auto-execute only if `attempts_used < max_attempts` **and** `now - last_attempt ≥ cooldown_seconds`; otherwise wait or escalate. Exhausting `escalate_after_attempts` → Engineering Escalation.
- **Cooldown, attempt counts, and recurrence are all computed from the `RecoveryAttempt` audit records**, not in-memory state (survives worker restarts).

---

## 4. Recovery Handler Interfaces

Recovery is delivered by **Recovery Handlers that live in `apps/core/operations/recovery/`** — **not** by
adding methods to the observability monitor classes. This is the frozen observation/action seam (§11):
the handler *consumes* Operations Truth (the cached payload, the detector predicate) from
`ai_observability/`, but the recover/verify **action** code lives in `operations/`. Recovery is **opt-in
per monitor key**: a monitor with no registered handler stays observe-only (R0) — nothing regresses.

```python
# apps/core/operations/recovery/base.py
class RecoveryHandler(Protocol):
    monitor_key: str                # associates the handler with a monitor's incidents
    recovery_policy: RecoveryPolicy

    def diagnose(self, anomaly: OpsAnomaly) -> RecoveryDiagnosis: ...
    def recover(self, diagnosis: RecoveryDiagnosis) -> RecoveryOutcome: ...
    def verify(self, diagnosis: RecoveryDiagnosis) -> VerificationResult: ...
```

- **`diagnose`** reads evidence already in the cached Operations Truth payload / DB; returns a structured cause + the specific target (which task, which snapshot). No side effects.
- **`recover`** performs the single safest deterministic action for the diagnosed cause. Idempotent (R1) or bounded (R2). Returns what it did. **No LLM/Claude is ever in this path** — recovery is deterministic code (vision §12).
- **`verify`** re-checks health by **importing and calling the exact detector predicate the observability layer used to raise the incident** (allowed direction: `operations/` → `ai_observability/`). "Recovered" is provably the negation of "detected" — never a second, drifting definition of "healthy."
- **Where the handlers read from (not write to):** the OPS-1 freshness check (`scheduled_task_monitor`), the storage/integrity staleness check, etc. remain in `ai_observability/`; the pilot handlers in `operations/recovery/` call those predicates. **No observability file is edited to hold recover/verify logic.**

---

## 5. Verification Framework

**The most important safety component.** An incident may close **only** on a passing `verify()`.

- **Reuse detection, don't reinvent it.** `verify()` calls the same predicate the SAME detector uses, so "recovered" is provably the negation of "detected." This kills the drift class where recovery declares success against a looser bar than detection.
- **Bounded wait.** Some recoveries take effect asynchronously (a re-enqueued job runs next cycle). Verification either (a) checks synchronously when the effect is immediate, or (b) defers to the *next* recovery cycle and marks the incident `RECOVERING` until verified — never closing optimistically.
- **Verification is itself audited** (result + evidence snapshot).
- **Failed verification never closes.** It increments the attempt counter and routes to Retry?/Escalate per policy.

---

## 6. Audit Model

New model `RecoveryAttempt` in **`apps/core/operations/audit/models.py`** (the action package, frozen
§10; **not** in `ai_observability/models.py`). Because `operations/` is a sub-package of the `core` app,
the model keeps `app_label="core"` and its migration lands in `apps/core/migrations/` — additive only,
no changes to existing tables:

| Field | Purpose |
|---|---|
| `anomaly` (FK → OpsAnomaly) | which incident |
| `monitor_key` | which monitor owns the recovery |
| `classification` | R0–R4 at time of action |
| `phase` | DIAGNOSED / RECOVER_ATTEMPTED / VERIFIED / CLOSED / ESCALATED / SKIPPED_COOLDOWN / SKIPPED_UNSAFE |
| `action_taken` | human-readable deterministic description |
| `outcome` | SUCCESS / FAILED / PENDING_VERIFICATION |
| `evidence_before` / `evidence_after` | JSON snapshots of the detection signal |
| `attempt_number` | Nth attempt for this anomaly |
| `created_at` | timestamp (also drives cooldown) |
| `error` | captured exception text on failure (never swallowed) |

**Every lifecycle path writes a row** — including "Safe? = No" (`SKIPPED_UNSAFE`) and cooldown skips —
so the audit is a complete, queryable history (foundation for Phase VI metrics and Operations Memory).
Migration: additive only, no changes to existing tables.

---

## 7. Recovery Execution Pipeline

1. **Trigger:** a **separate** `run_recovery_cycle_task`, enqueued fire-and-forget (`safe_enqueue`) by the SAME task as its final step **after** Operations Truth is built and cached — never inline in the telemetry build.
2. **Consume, don't detect:** the recovery task reads the **already-cached** Operations Truth payload + active `OpsAnomaly` rows. If the payload is missing or stale, the cycle is a **no-op** (recovery never triggers detection itself).
3. **Select:** active `OpsAnomaly` rows that have a registered recovery handler.
4. **Per anomaly:** `diagnose` → gate (classification §4 + policy: attempts/cooldown/recurrence) → `recover` (R1/R2) → `verify` (reuse detector predicate) → audit → `close` | `retry-next-cycle` | `escalate`.
5. **Concurrency:** processed sequentially within the recovery task; a single anomaly can never be recovered twice at once (`RECOVERING` state + cooldown-from-audit guard).
6. **Failure isolation:** each anomaly's handling is wrapped so one failing recovery cannot abort the task or block others. Exceptions are logged at `error` with `exc_info=True` and audited — **never swallowed** (AI Engineering Rules).
7. **Kill switch:** settings flag `OPS_RECOVERY_ENABLED` (default **False**) — when off, the SAME task skips the enqueue, so recovery is a **true no-op** (no task, no payload read). Per-monitor enable flags allow staged rollout.

**Execution-isolation guarantees (required — reconciled against the frozen independence rules):**
- A recovery failure **cannot** prevent the fresh Operations Truth payload from being built or cached — telemetry builds + caches *before* the recovery task is even enqueued.
- The Phase I observability cycle remains **fully functional when recovery is disabled, absent, broken, or removed** — the only coupling is one optional, non-blocking `safe_enqueue` at the very end of the SAME task.
- Recovery **consumes a completed Operations Truth result** and is **never load-bearing for detection** — it re-reads the cache and no-ops if truth isn't ready.
- `OPS_RECOVERY_ENABLED=False` → the enqueue is skipped entirely → recovery is a genuine no-op.
- Because recovery runs in its **own** worker task (not inside `build_ops_stream_payload()`), it **cannot lengthen or destabilize the telemetry path** beyond its established safety limits — the 60s telemetry cadence is unaffected by recovery duration.

---

## 8. Escalation Pipeline (Phase II stub)

- **Escalation** (the deterministic hand-off when recovery is unsafe or exhausted) fires when the gate says
  unsafe (R0/R3/R4), when retries are exhausted, **or** when a class exceeds its `recurrence_limit`
  (permanent-fix escalation, §3). The engine marks the anomaly `ESCALATED` and writes a `RecoveryAttempt`
  audit row with the diagnosis + attempt history.
- **Phase II stub:** Escalation = the incident is flagged on the Command Center as *"needs engineering"*
  (or *"recurring — needs permanent fix"*) with its recovery history attached. **No Claude/LLM prompt
  generation yet, and no LLM call ever** — that deterministic-context + prompt assembly is Phase IV, and
  even then it only *prepares a string* for a human to run (vision §11 boundary).
- The escalation record is structured so Phase IV can later attach logs/metrics/commits without rework.

---

## 9. UI Changes (read-only, minimal)

- On the Command Center incident view, each incident gains a **recovery strip**: classification badge
  (R0–R4), attempts (n/max), last action, outcome, and *verified/ not verified*.
- A small **"Recovery activity"** panel: recent `RecoveryAttempt` rows (auto/verified/escalated).
- **No action buttons in Phase II** (R3 approval controls are Phase III). Everything is read-only —
  consistent with the request-path-safety posture (the page only reads pre-computed records).
- Follows CSP rules (nonce scripts, `addEventListener`, `data-*` context) and the Visual Truth Contract
  (only a *verified* recovery may render as "resolved"; a `RECOVERING`/`PENDING_VERIFICATION` state must
  never look done).

---

## 10. Testing Strategy

Scoped tests only (never the full suite). New tests under `apps/core/operations/tests/`:

**Behavioural tests:**
- **Classification gate:** R0/R3/R4 never auto-execute; R1/R2 do; "classify higher when in doubt" default (unregistered anomaly → R0).
- **Lifecycle completeness:** every path writes a `RecoveryAttempt` row (happy, unsafe-skip, cooldown-skip, failed-verify, retry-exhausted-escalate).
- **Verification reuses detection:** a recovery that doesn't actually fix the signal fails verification and does **not** close the incident (the core safety test).
- **Cooldown/retry/recurrence bounds:** attempts respect `max_attempts` + `cooldown_seconds`; **R1 is finite** (no unbounded loop); exceeding `recurrence_limit` raises a permanent-fix escalation; all computed from audit records and surviving a simulated worker restart.
- **Idempotency:** running two recovery cycles back-to-back on the same anomaly performs at most one action.
- **Execution isolation:** a handler that raises does not abort the recovery task or affect telemetry; with `OPS_RECOVERY_ENABLED=False` the SAME task performs **no enqueue** and the cycle is a complete no-op; a missing/stale cached payload → recovery no-ops (never detects).
- **End-to-end pilot:** an OPS-1 stale Beat task (allowlisted) → detected → re-enqueued → verified fresh via the OPS-1 predicate → incident auto-closed with a full audit trail.

**Import-boundary contract tests (CI-enforceable — the frozen §11 rules as executable assertions, extending `apps/core/tests/test_request_path_safety_contract.py` or a new `test_operations_import_boundaries.py`):**
- **No request-path import of action code:** no `views*.py` / `api*.py` / `urls*.py` / template tag / any request-path module imports `apps/core/operations/**` (the whole action tree is worker-only by construction).
- **Truth never imports action:** no module under `apps/core/ai_observability/**` imports `apps/core/operations/**`.
- **Action never imports reasoning:** no module under `apps/core/operations/**` imports Chief-of-Staff reasoning (`apps/ai` orchestration / personal assistant), conversation logic, Current Context reasoning, LLM orchestration, prompt composition, or model-interface code.
- **CoS never imports recovery internals:** no CoS module imports `operations/recovery`, `operations/policies`, `operations/verification`, `operations/escalation`, or `operations/audit` internals — any future CoS integration (Phase V) may consume **only** the composed Operations Truth surface.
- **No inline LLM in recovery:** the recovery/verification path issues no LLM call (extends the existing inline-LLM contract).

---

## 11. Deployment Strategy

1. **Ship dark.** Merge with `OPS_RECOVERY_ENABLED=False`; the `apps/core/operations/` package + additive `RecoveryAttempt` migration deploy with zero behavior change. Verify `manage.py check` + `makemigrations --check` clean.
2. **Enable Pilot 1** (snapshot refresh — zero external blast radius) via `OPS_RECOVERY_SNAPSHOT_REFRESH`; watch the audit trail + Command Center for a full cycle.
3. **Enable Pilot 2** (allowlisted Beat-task re-enqueue) via `OPS_RECOVERY_BEAT_RETRY`, once Pilot 1 is proven; grow `IDEMPOTENT_RECOMPUTE_ALLOWLIST` one task at a time.
4. **Only then** consider deferred/higher-blast-radius candidates (chat requeue *after its idempotency/dedup design ships and is tested*; worker/scheduler restart), each behind its own flag.
5. Every enablement updates the **vision doc ledger** (vision §15) + changelog (Claude maintenance contract).
6. Rollback = flip `OPS_RECOVERY_ENABLED` (or a per-handler flag) off — instant, no redeploy; recovery is additive and reversible by flag.

---

## 12. Architectural Risks (identify before implementing)

| # | Risk | Severity | Mitigation |
|---|---|---|---|
| R-1 | **Recovery masks a systemic defect** — auto-recovering the same class forever hides a bug that should be fixed (violates "eliminate the class"). | High | **Concrete mechanism:** `RecoveryPolicy.recurrence_limit` / `recurrence_window_hours` (§3) — repeated *successful* recoveries of the same class beyond the limit raise a **permanent-fix Escalation** ("recurring — needs permanent fix") instead of silently masking. All computed from the `RecoveryAttempt` audit trail; matures into Operations-Memory analytics (Phase VIII). |
| R-2 | **Verification drift** — `verify()` uses a looser "healthy" bar than detection, closing incidents that aren't fixed (manufactures false healthy truth). | High | **Mandate** `verify()` reuse the SAME detector predicate (§5); a test proves a non-fix fails verification. This is the core safety invariant. |
| R-3 | **Recovery thrash** — a flapping condition triggers restart→fail→restart loops that amplify the incident. | High | Cooldown + bounded `max_attempts` + escalate-on-exhaust; cooldown persisted in audit (survives restarts); worker/scheduler restarts deferred out of the first cut. |
| R-4 | **Blast-radius misclassification** — an action labeled R2 that is actually R3 runs automatically. | High | "Classify higher when in doubt"; classification recorded in ADR when first assigned; R2 restricted to provably reversible-by-verification actions; the first cut ships only zero/low-blast-radius R1s. |
| R-5 | **Request-path leakage** — recovery logic accidentally reachable from a view (blocks Gunicorn workers). | High | All action code lives in the worker-only `apps/core/operations/` package; CI contract test asserts no request-path import of `operations/**` (§10); kill switch. |
| R-6 | **Redis/Celery dependency for recovery** — recovery depends on the same broker that may be degraded during an incident. | Medium | `safe_enqueue` (non-blocking); recoveries that don't need the broker run inline in the recovery worker task; never block on Redis. |
| R-7 | **Independence erosion (Principles 13/14)** — recovery quietly takes a dependency on CoS internals, or `ai_observability/` on `operations/`. | Medium | `operations/` imports nothing from CoS reasoning; `ai_observability/` never imports `operations/`; both directions enforced by the §10 import-boundary contract tests. |
| R-8 | **Audit volume** — high-frequency anomalies (30s `cos_keepalive`) generate excessive `RecoveryAttempt` rows. | Low | Only *active anomalies with a registered recovery* are processed; cooldown bounds write rate; a retention/cleanup Beat task if needed. |
| R-9 | **Concurrent recovery** — overlapping SAME cycles double-execute a recovery. | Medium | `RECOVERING` state + cooldown-from-audit guard; sequential per-cycle processing; idempotency test. |
| R-10 | **Silent exception swallowing** in a recovery path hides functional loss. | Medium | Follow AI Engineering Rules: separate `ImportError` from `Exception`; log `error` with `exc_info=True`; audit the failure; never `except: pass`. |

**Top-3 to resolve before writing code:** R-2 (verification-reuses-detection invariant), R-4
(classification discipline + first-cut R1-only), and R-5 (request-path isolation + kill switch). These
three are the difference between a safe healer and a subsystem that manufactures false truth or takes
down the site.

---

## 13. Definition of Done (Phase II)

- `apps/core/operations/` package created (minimal subset — see below); Recovery Engine + registry + policy model + `RecoveryAttempt` audit model shipped (dark).
- The **two R1 pilots** (snapshot refresh, allowlisted Beat-task re-enqueue) implemented, tested, and each enabled behind its own flag. (Chat requeue explicitly deferred with a promotion trigger, §1.1.)
- Verification-reuses-detection invariant enforced by test; R1 finite-bound + recurrence/permanent-fix escalation enforced by test.
- Import-boundary + request-path-safety contract tests cover `operations/` (§10).
- Command Center shows read-only recovery activity (Visual-Truth-compliant).
- Vision-doc ledger (vision §15) marks the Phase II pilot items complete with Date/SHA/Deploy/Docs/Tests; ADRs recorded (vision §16) for each classification assignment.
- Subsystem maturity for the covered monitors advances O1 → **O2 (Recoverable)**.

**Minimal package subset for the first cut** (do not create empty packages the first milestone doesn't
use; the frozen §10 layout is the destination, not a day-one requirement):
```
apps/core/operations/
    __init__.py
    recovery/        # engine, registry, base handler, the 2 pilot handlers, RecoveryPolicy
    audit/           # RecoveryAttempt model
    tests/
```
`policies/`, `verification/`, and `escalation/` begin as **modules** (e.g. `recovery/policies.py`,
`recovery/verification.py`, `recovery/escalation.py`) and graduate to their own sub-packages as they grow
into the full frozen §10 layout — no premature empty directories.

---

*Last updated: 2026-07-11 — **reconciled against the frozen architecture** (`WLJ_OPERATIONS_VISION.md`,
frozen at SHA `d1a06636`): action code relocated to `apps/core/operations/` (frozen §10); recovery runs
as a separate downstream task (execution isolation); stale vision cross-refs corrected (ledger §15,
terminology §12); import-boundary contract tests specified (§10/§11); pilot set reduced to two R1 actions
with full specs (§1.1) and chat requeue deferred with a promotion trigger; R1 bounded with a
permanent-fix recurrence escalation. Plan only — not implemented; awaiting review before Phase II begins.*
