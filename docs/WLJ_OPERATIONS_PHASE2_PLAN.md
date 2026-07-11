# WLJ Operations — Phase II Engineering Implementation Plan (Deterministic Recovery)

> **Status:** PLAN · Not implemented. **Established:** 2026-07-11.
> **Authority:** Engineering plan (companion to the governing `WLJ_OPERATIONS_VISION.md`).
> **Governed by:** `WLJ_OPERATIONS_VISION.md` (§4 Recovery Safety Classification, §5 Standard Recovery
> Lifecycle, Principles 1–14), `WLJ_REQUEST_PATH_SAFETY.md`, `WLJ_CONSTITUTION.md`.
>
> This document is the deterministic blueprint for Phase II. **No recovery code exists yet.** This plan
> must be reviewed (and its risks §11 accepted) before implementation begins. Phase II turns the
> Observable subsystem (O1) into a Recoverable one (O2) for the R1/R2 classes only.

---

## 1. Scope & Non-Goals

**In scope (Phase II):**
- A **Recovery Engine** that runs the Standard Recovery Lifecycle (§5 of the vision) for R1/R2 actions.
- A **recovery policy** attached to each monitor (retry, cooldown, verification, escalation, audit).
- **Monitor interfaces** (`diagnose`/`recover`/`verify`) added to existing monitors, opt-in per monitor.
- A **verification framework** proving health was restored before an incident closes.
- An **audit model** recording every attempt on every path.
- A **recovery execution pipeline** (background, off the request path).
- An **escalation pipeline** stub (full engineering-context assembly is Phase IV).
- Minimal **read-only UI** on the Command Center showing recovery attempts/outcomes.

**Explicit non-goals (deferred):**
- R3 (approval-gated) execution UI — **Phase III** once the policy framework exists.
- R4 destructive recovery — **never automated**; out of scope permanently.
- Declarative recovery-as-config framework — **Phase III** (Phase II may hard-code 2–3 pilots).
- Full engineering-escalation context assembly + Claude prompt generation — **Phase IV**.
- Autonomy metrics / recovery-history analytics — **Phase VI**.
- Operations Memory — **future** (§7 of the vision).
- Any CoS change — **out of scope in every Operations phase until Phase V truth integration.**

**Pilot set (recommended first recoveries):** start with **two R1** and **one R2** action to prove the
lifecycle end-to-end before generalizing:
1. **R1 — refresh a stale snapshot / recompute derived data** (e.g. a stale integrity or storage snapshot). Idempotent, verifiable, zero blast radius.
2. **R1 — retry a failed scheduled Beat task** surfaced by OPS-1 MISSED_RUN. Idempotent re-enqueue.
3. **R2 — requeue stuck chat-queue work** surfaced by OPS-3 (bounded retry, verify depth drains).

Deliberately **no worker/scheduler restart in the first cut** — those are R2 but higher blast radius;
add them only after the pilot lifecycle is proven and audited.

---

## 2. Recovery Engine Architecture

**Home:** `apps/core/ai_observability/recovery/` (new package), invoked from the **SAME 60s cycle**
after `build_ops_stream_payload()` — never from a request path.

```
run_same_cycle_task (Celery, 60s)
  └─ build_ops_stream_payload()      # Phase I: detect (unchanged)
  └─ run_recovery_cycle(payload)     # Phase II: NEW
       for each active OpsAnomaly with a registered recovery:
         RecoveryEngine.handle(anomaly)
           ├─ diagnose()   → RecoveryDiagnosis (evidence)
           ├─ gate: classify (R0–R4) + policy (attempts/cooldown)
           ├─ recover()    → RecoveryOutcome        (R1/R2 only)
           ├─ verify()     → VerificationResult
           ├─ audit (every path)
           └─ close | retry | escalate
```

**Key design decisions:**
- **The Recovery Engine is a consumer of Phase I truth, not a new detector.** It acts on already-detected `OpsAnomaly` rows; it never re-derives detection. (Preserves single-producer discipline.)
- **One engine, many registered recoveries.** A `RecoveryRegistry` maps `anomaly_type → RecoveryHandler`. Anomalies with no registered handler are **R0 by default** (observe-only, escalate) — the safe default.
- **Runs entirely in the worker.** No recovery, verification, or diagnosis ever executes on the request path (ADR-3). The Command Center only *reads* recovery records.
- **Idempotent per cycle.** If a recovery is mid-flight or in cooldown, the next 60s cycle is a no-op for that anomaly — the engine is safe to run every cycle.
- **Fire-and-forget enqueues** use `apps/core/celery_utils.py :: safe_enqueue` (never block on Redis).

---

## 3. Recovery Policy Model

A **declarative policy** per recovery, consulted by the gate before any action. Phase II may define
these as Python objects on the handler; Phase III promotes them to configuration.

```python
@dataclass(frozen=True)
class RecoveryPolicy:
    classification: str        # "R0" | "R1" | "R2" | "R3" | "R4"
    max_attempts: int          # bounded for R2; R1 may be high but never truly unlimited in code
    cooldown_seconds: int      # minimum interval between attempts (anti-thrash)
    verification_required: bool = True     # always True; present for explicitness
    verification_timeout_s: int = 120
    escalate_after_attempts: int = None    # → Engineering Escalation (defaults to max_attempts)
    requires_operator_approval: bool = False   # True for R3 (Phase III)
    audit_every_path: bool = True          # always True
```

**Gate rules (deterministic):**
- `classification in {"R0","R3","R4"}` → **do not auto-execute**; route to escalation (R0) or approval-staging (R3, Phase III) or engineering (R4).
- `classification in {"R1","R2"}` → check `attempts_used < max_attempts` **and** `now - last_attempt ≥ cooldown_seconds`; if either fails → wait or escalate.
- **Cooldown is enforced from the audit record**, not from in-memory state (survives worker restarts).

---

## 4. Monitor Interfaces

Recovery is **opt-in per monitor** via a small mixin/protocol. Monitors that don't implement it stay
observe-only (R0) — nothing regresses.

```python
class SupportsRecovery(Protocol):
    def diagnose(self, anomaly: OpsAnomaly) -> RecoveryDiagnosis: ...
    def recover(self, diagnosis: RecoveryDiagnosis) -> RecoveryOutcome: ...
    def verify(self, diagnosis: RecoveryDiagnosis) -> VerificationResult: ...
    recovery_policy: RecoveryPolicy
```

- **`diagnose`** reads evidence already in the payload/DB; returns a structured cause + the specific target (which task, which snapshot, which queue). No side effects.
- **`recover`** performs the single safest action for the diagnosed cause. Must be idempotent (R1) or bounded (R2). Returns what it did.
- **`verify`** re-checks the *same deterministic signal that detected the incident* and returns healthy/not. **Verification reuses the Phase I detection logic** — never a second, drifting definition of "healthy."
- Existing monitors to retrofit for the pilot: `scheduled_task_monitor.py` (retry Beat task), `chat_queue_monitor.py` (requeue), and a snapshot refresher for storage/integrity.

---

## 5. Verification Framework

**The most important safety component.** An incident may close **only** on a passing `verify()`.

- **Reuse detection, don't reinvent it.** `verify()` calls the same predicate the SAME detector uses, so "recovered" is provably the negation of "detected." This kills the drift class where recovery declares success against a looser bar than detection.
- **Bounded wait.** Some recoveries take effect asynchronously (a re-enqueued job runs next cycle). Verification either (a) checks synchronously when the effect is immediate, or (b) defers to the *next* recovery cycle and marks the incident `RECOVERING` until verified — never closing optimistically.
- **Verification is itself audited** (result + evidence snapshot).
- **Failed verification never closes.** It increments the attempt counter and routes to Retry?/Escalate per policy.

---

## 6. Audit Model

New model `RecoveryAttempt` (app_label `core`, alongside the other observability models in
`apps/core/ai_observability/models.py`):

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

1. **Trigger:** `run_recovery_cycle()` invoked at the end of the SAME 60s task, passed the fresh payload.
2. **Select:** active `OpsAnomaly` rows that have a registered recovery handler.
3. **Per anomaly:** `diagnose` → gate (classification + policy + cooldown) → `recover` (R1/R2) → `verify` → audit → `close` | `retry-next-cycle` | `escalate`.
4. **Concurrency:** processed sequentially within the cycle; a single anomaly can never be recovered by two cycles at once (a `RECOVERING` state + cooldown guards this).
5. **Failure isolation:** each anomaly's handling is wrapped so one failing recovery cannot abort the cycle or block others (per-section isolation, matching the Phase I telemetry pattern). Exceptions are logged at `error` with `exc_info=True` and audited — **never swallowed** (AI Engineering Rules).
6. **Kill switch:** a settings flag `OPS_RECOVERY_ENABLED` (default **False** at first deploy) so recovery ships dark and is enabled deliberately. Per-monitor enable flags allow staged rollout.

---

## 8. Escalation Pipeline (Phase II stub)

- When the gate says unsafe (R0/R3/R4) or retries are exhausted, the engine marks the anomaly
  `ESCALATED` and writes an audit row with the diagnosis + attempt history.
- **Phase II stub:** escalation = the incident is flagged on the Command Center as *"needs engineering"*
  with its recovery history attached. **No Claude prompt generation yet** — that is Phase IV.
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

Scoped tests only (never the full suite). New file `apps/core/ai_observability/tests_recovery.py`:

- **Classification gate:** R0/R3/R4 never auto-execute; R1/R2 do; "classify higher when in doubt" default (unregistered anomaly → R0).
- **Lifecycle completeness:** every path writes an audit row (happy, unsafe-skip, cooldown-skip, failed-verify, retry-exhausted-escalate).
- **Verification reuses detection:** a recovery that doesn't actually fix the signal fails verification and does **not** close the incident (the core safety test).
- **Cooldown/retry bounds:** attempts respect `max_attempts` and `cooldown_seconds`; cooldown read from audit records survives a simulated worker restart.
- **Idempotency:** running two recovery cycles back-to-back on the same anomaly performs at most one action.
- **Request-path safety:** add a test (or extend `test_request_path_safety_contract.py`) asserting no view/api imports the recovery engine.
- **End-to-end pilot:** an OPS-1 stale Beat task → detected → retried → verified fresh → incident auto-closed with a full audit trail (mirrors the existing OPS-1 end-to-end proof).
- **Kill switch:** with `OPS_RECOVERY_ENABLED=False`, the cycle is a complete no-op.

---

## 11. Deployment Strategy

1. **Ship dark.** Merge with `OPS_RECOVERY_ENABLED=False`; the migration (additive `RecoveryAttempt`) and code deploy with zero behavior change. Verify `manage.py check` + `makemigrations --check` clean.
2. **Enable one R1 pilot** (snapshot refresh — zero blast radius) via the per-monitor flag; watch the audit trail and Command Center for a full cycle.
3. **Enable the second R1** (Beat-task retry), then the **R2** (chat requeue) once R1 is proven.
4. **Only then** consider higher-blast-radius R2 (worker/scheduler restart), each behind its own flag.
5. Every enablement updates the **vision doc ledger** (§9) + changelog (Claude maintenance contract).
6. Rollback = flip `OPS_RECOVERY_ENABLED` off (instant, no redeploy) — recovery is additive and reversible by flag.

---

## 12. Architectural Risks (identify before implementing)

| # | Risk | Severity | Mitigation |
|---|---|---|---|
| R-1 | **Recovery masks a systemic defect** — auto-recovering the same class forever hides a bug that should be fixed (violates "eliminate the class"). | High | Every recovery is audited with an attempt count; a rising recurrence is the Phase VI/Operations-Memory signal to escalate for a permanent fix. Consider a "recurring — needs permanent fix" flag when attempts-per-day crosses a threshold. |
| R-2 | **Verification drift** — `verify()` uses a looser "healthy" bar than detection, closing incidents that aren't fixed (manufactures false healthy truth). | High | **Mandate** `verify()` reuse the SAME detector predicate (§5); a test proves a non-fix fails verification. This is the core safety invariant. |
| R-3 | **Recovery thrash** — a flapping condition triggers restart→fail→restart loops that amplify the incident. | High | Cooldown + bounded `max_attempts` + escalate-on-exhaust; cooldown persisted in audit (survives restarts); worker/scheduler restarts deferred out of the first cut. |
| R-4 | **Blast-radius misclassification** — an action labeled R2 that is actually R3 runs automatically. | High | "Classify higher when in doubt"; classification recorded in ADR when first assigned; R2 restricted to provably reversible-by-verification actions; the first cut ships only zero/low-blast-radius R1s. |
| R-5 | **Request-path leakage** — recovery logic accidentally reachable from a view (blocks Gunicorn workers). | High | Engine lives in the worker-only package; CI contract test asserts no view/api import; kill switch. |
| R-6 | **Redis/Celery dependency for recovery** — recovery depends on the same broker that may be degraded during an incident. | Medium | `safe_enqueue` (non-blocking); storage/upstream recoveries that don't need the broker run inline in the SAME worker; never block on Redis. |
| R-7 | **Independence erosion (Principle 13/14)** — recovery quietly takes a dependency on CoS internals. | Medium | Recovery package imports nothing from `apps/ai` CoS reasoning; add an import-boundary test. |
| R-8 | **Audit volume** — high-frequency anomalies (30s `cos_keepalive`) generate excessive `RecoveryAttempt` rows. | Low | Only *active anomalies with a registered recovery* are processed; cooldown bounds write rate; a retention/cleanup Beat task if needed. |
| R-9 | **Concurrent recovery** — overlapping SAME cycles double-execute a recovery. | Medium | `RECOVERING` state + cooldown-from-audit guard; sequential per-cycle processing; idempotency test. |
| R-10 | **Silent exception swallowing** in a recovery path hides functional loss. | Medium | Follow AI Engineering Rules: separate `ImportError` from `Exception`; log `error` with `exc_info=True`; audit the failure; never `except: pass`. |

**Top-3 to resolve before writing code:** R-2 (verification-reuses-detection invariant), R-4
(classification discipline + first-cut R1-only), and R-5 (request-path isolation + kill switch). These
three are the difference between a safe healer and a subsystem that manufactures false truth or takes
down the site.

---

## 13. Definition of Done (Phase II)

- Recovery Engine + registry + policy model + `RecoveryAttempt` audit model shipped (dark).
- The three pilot recoveries (2×R1, 1×R2) implemented, tested, and each enabled behind a flag.
- Verification-reuses-detection invariant enforced by test.
- Request-path-safety contract extended to cover the recovery package.
- Command Center shows read-only recovery activity (Visual-Truth-compliant).
- Vision-doc ledger (§9) marks the Phase II pilot items complete with Date/SHA/Deploy/Docs/Tests; ADRs recorded for each classification assignment.
- Subsystem maturity for the covered monitors advances O1 → **O2 (Recoverable)**.

---

*Last updated: 2026-07-11 — plan authored; not implemented. Awaiting review + risk acceptance before Phase II begins.*
