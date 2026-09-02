# ==============================================================================
# File: apps/ai/llm_admission.py
# Project: Whole Life Journey - Django 5.x Personal Wellness/Journaling App
# Description: THE admission authority for every real provider request
# Owner: Danny Jenkins (admin@wholelifejourney.com)
# Created: 2026-08-20
# ==============================================================================
"""Real-LLM Cost Governor — the single admission seam.

    NO EXPLICIT AUTHORIZATION  ->  NO REAL PROVIDER CALL.
    AUTHORIZATION              ->  HARD FINITE BUDGET  ->  FAIL CLOSED AT ZERO.

**Why this exists.** A development session made 63 paid provider calls against Danny's
account without anyone deciding that it should. Nothing in the codebase could have stopped
it: the only precondition for a real request was a non-empty API key, there was no budget
anywhere, and local calls recorded $0.00 so no dashboard ever showed them. The overspend was
discovered from a credit-card recharge. This module makes that class impossible.

**Where the guard sits.** Not on the API key — a key is *configuration*, and emptying it at
runtime would be a process-local mutation that two workers would disagree about. The guard
sits on the CLIENT: `build_guarded_client()` returns a proxy that admits (or refuses) each
request immediately before the network call. Because every provider request in WLJ goes
through a client object, wrapping the client governs every call site — including ones not
yet written — without touching 34 individual `.create(...)` calls.

**Production is not affected.** Real customer traffic is admitted unconditionally and
accounted exactly as before. The governor applies to non-production environments, which is
where uncontrolled development spend actually happens.

**Claude Code may never self-authorize.** Minting or extending an authorization requires an
interactive terminal and a typed confirmation (see `authorize_real_llm`). Claude may CONSUME
a budget Danny already approved, for the purpose he approved, and must STOP when it is
exhausted — never reset it, never mint another, never switch environments or keys.
"""

import contextlib
import contextvars
import logging
import os

logger = logging.getLogger(__name__)

# Set at admission, read by the accounting seam, so a paid development call is traceable to
# the authorization that permitted it. A contextvar (not a global) so concurrent turns in one
# worker cannot attribute each other's spend.
_admitted_run_id: contextvars.ContextVar = contextvars.ContextVar(
    "wlj_llm_admitted_run_id", default=None)


def current_admitted_run_id():
    return _admitted_run_id.get()


# WORKLOAD ORIGIN — independent of environment, and the reason this axis exists:
#
#     ENVIRONMENT decides whether real product traffic may use the provider.
#     WORKLOAD ORIGIN decides whether AUTONOMOUS provider spend is authorized.
#
# Being in production is NOT permission for a background job to spend money. Without
# this split, any future scheduled feature would start consuming credits merely by
# shipping to production — which is exactly how proactive AI reached ~$1.09/day
# firing whether or not anyone opened the app.
_autonomous: contextvars.ContextVar = contextvars.ContextVar(
    "wlj_llm_autonomous_workload", default=None)


@contextlib.contextmanager
def autonomous_workload(reason="scheduled"):
    """Mark everything inside as AUTONOMOUS provider work — no human asked for it.

    Every scheduled/background provider-backed path must run inside this (or carry a
    proactive/background traffic class, which is treated the same way). Autonomous spend
    is refused unless `WLJ_PROACTIVE_AI_ENABLED` is explicitly on.
    """
    token = _autonomous.set(reason)
    try:
        yield
    finally:
        _autonomous.reset(token)


def current_workload_is_autonomous():
    """True when this call has no human behind it.

    Two signals, either sufficient: the explicit marker above, or an ambient
    proactive/background traffic class — which every existing scheduled provider path
    already sets, so the gate covers them without touching their call sites.
    """
    if _autonomous.get():
        return True
    try:
        from apps.ai.llm_accounting import current_traffic_class
        return current_traffic_class() in ("proactive", "background")
    except Exception:  # pragma: no cover - defensive
        return False


#     DIAGNOSTIC WORKLOAD — an operator looking, not a customer using.
#
# Production is unconditionally admitted below, and that is right: real customers must
# never be refused. But an operator endpoint that RUNS IN production inherits that
# permission, and on 2026-09-02 a verification call to `cos-run` spent Danny's credits
# with nobody having authorized it. Being in production is not evidence that a human
# asked for this particular call.
#
# So diagnostics declare themselves and default to REFUSED. Authorizing one is explicit,
# bounded to a call count, and audited — the same shape as the development governor,
# applied to the one environment that had no gate at all.
_diagnostic: contextvars.ContextVar = contextvars.ContextVar(
    "wlj_llm_diagnostic_workload", default=None)


class DiagnosticBudget:
    """An operator's explicit permission to spend, for N calls and no more."""

    __slots__ = ("reason", "authorized", "spent", "operator")

    def __init__(self, reason, authorized, operator=""):
        self.reason = reason
        self.authorized = max(0, int(authorized or 0))
        self.spent = 0
        self.operator = operator or ""

    @property
    def remaining(self):
        return max(0, self.authorized - self.spent)

    def consume(self):
        if self.remaining <= 0:
            return False
        self.spent += 1
        return True

    def as_audit(self):
        return {"reason": self.reason, "authorized": self.authorized,
                "spent": self.spent, "operator": self.operator}


@contextlib.contextmanager
def diagnostic_workload(reason, *, authorized_calls=0, operator=""):
    """Mark everything inside as OPERATOR DIAGNOSTIC work.

    `authorized_calls` defaults to 0, which means every provider call inside is refused
    — a diagnostic that quietly costs money is the failure this exists to prevent. A
    caller that genuinely needs a real call passes the number a human authorized, and
    gets exactly that many.

    The budget object is yielded so the caller can report what was actually spent.
    """
    budget = DiagnosticBudget(reason, authorized_calls, operator)
    token = _diagnostic.set(budget)
    try:
        yield budget
    finally:
        _diagnostic.reset(token)


def current_diagnostic_budget():
    """The budget for this diagnostic, or None when this is not diagnostic work."""
    return _diagnostic.get()


def proactive_ai_enabled():
    """Is provider-backed autonomous work authorized in THIS environment?

    Default False. Re-enabling is a deliberate product/environment decision
    (`WLJ_PROACTIVE_AI_ENABLED=true`), never something automated tooling turns on.
    """
    try:
        from django.conf import settings
        return bool(getattr(settings, "WLJ_PROACTIVE_AI_ENABLED", False))
    except Exception:  # pragma: no cover - fail closed
        return False

# Requests that actually cost money. Anything reached through a guarded client whose
# attribute path matches one of these is admitted (or refused) before it leaves the process.
BILLABLE_OPERATIONS = (
    ("chat", "completions", "create"),
    ("embeddings", "create"),
    ("audio", "transcriptions", "create"),
    ("audio", "translations", "create"),
    ("audio", "speech", "create"),
    ("responses", "create"),
    ("images", "generate"),
    ("moderations", "create"),
)

ENV_PRODUCTION = "production"
ENV_DEVELOPMENT = "development"

FLAG_ALLOW = "WLJ_ALLOW_REAL_LLM"
# The finite call budget is NOT an environment integer. It lives on the authorization row
# that WLJ_LLM_RUN_ID names, because web and worker are separate processes: an env-var count
# would let each of them believe it owned the whole budget. The run id IS the budget handle.
FLAG_RUN_ID = "WLJ_LLM_RUN_ID"


class RealLLMCallDenied(RuntimeError):
    """A real provider request was refused by the cost governor.

    Deliberately a hard error, not a silent None: a denied call must be impossible to
    mistake for a provider outage, and must never be quietly retried into a bill.
    """


# ──────────────────────────────────────────────────────────────────────────────
# Environment
# ──────────────────────────────────────────────────────────────────────────────

def current_environment():
    """Deterministic environment classification.

    PRODUCTION is asserted only by a positive signal that genuinely exists on Railway
    (`RAILWAY_GIT_COMMIT_SHA`, already used for the build stamp) or by an explicit
    `WLJ_ENV=production`. Everything else — local shells, CI, a developer's machine — is
    development and therefore governed.

    Deliberately NOT keyed on DEBUG alone: DEBUG is a rendering/security setting and has
    been wrong in both directions before.
    """
    explicit = (os.environ.get("WLJ_ENV") or "").strip().lower()
    if explicit in (ENV_PRODUCTION, ENV_DEVELOPMENT):
        return explicit
    sha = (os.environ.get("RAILWAY_GIT_COMMIT_SHA") or "").strip()
    if sha and sha != ENV_DEVELOPMENT:
        return ENV_PRODUCTION
    return ENV_DEVELOPMENT


def is_production():
    return current_environment() == ENV_PRODUCTION


# ──────────────────────────────────────────────────────────────────────────────
# Admission
# ──────────────────────────────────────────────────────────────────────────────

class AdmissionDecision:
    """Why a request was admitted or refused — carried into accounting so every real
    development call is attributable to the authorization that permitted it."""

    __slots__ = ("allowed", "reason", "environment", "run_id", "remaining")

    def __init__(self, allowed, reason, environment, run_id=None, remaining=None):
        self.allowed = allowed
        self.reason = reason
        self.environment = environment
        self.run_id = run_id
        self.remaining = remaining

    def __repr__(self):  # pragma: no cover - diagnostics
        return (f"<AdmissionDecision {'ALLOW' if self.allowed else 'DENY'} "
                f"{self.reason} env={self.environment} run={self.run_id}>")


def _denied(reason, env):
    return AdmissionDecision(False, reason, env)


def may_real_llm_call(*, source=None, traffic_class=None, environment=None):
    """THE admission decision. Deterministic, side-effect-free EXCEPT for the atomic
    budget decrement, which is the whole point (an admission consumes a call).

    Returns an :class:`AdmissionDecision`. Never raises — the caller decides whether a
    refusal is fatal.
    """
    env = environment or current_environment()

    # ── AUTONOMOUS WORK IS GATED IN EVERY ENVIRONMENT, PRODUCTION INCLUDED. ──
    # Checked BEFORE the production allow on purpose: running in production must never
    # imply permission to spend money with no human present.
    if current_workload_is_autonomous() and not proactive_ai_enabled():
        return _denied("proactive_ai_disabled", env)

    # ── Operator diagnostics are gated in EVERY environment, production included. ──
    # Checked BEFORE the production allow for the same reason as autonomous work: being
    # in production means real customers are served there, not that a diagnostic may
    # spend on their behalf.
    budget = current_diagnostic_budget()
    if budget is not None:
        if not budget.consume():
            return _denied("diagnostic_not_authorized", env)
        return AdmissionDecision(True, "authorized_diagnostic", env,
                                 remaining=budget.remaining)

    # ── Production: real customers. Unconditionally admitted, accounted as before. ──
    if env == ENV_PRODUCTION:
        return AdmissionDecision(True, "production_runtime", env)

    # ── Everything else is governed. Both conditions are required. ──
    if (os.environ.get(FLAG_ALLOW) or "").strip() not in ("1", "true", "TRUE", "yes"):
        return _denied("no_authorization_flag", env)

    run_id = (os.environ.get(FLAG_RUN_ID) or "").strip()
    if not run_id:
        return _denied("no_run_id", env)

    consumed = _consume_budget(run_id)
    if consumed is None:
        return _denied("no_valid_authorization", env)
    if consumed is False:
        return _denied("budget_exhausted", env)
    return AdmissionDecision(True, "authorized_development", env,
                             run_id=run_id, remaining=consumed)


def _consume_budget(run_id):
    """Atomically consume ONE call from the authorization.

    Returns the remaining count on success, ``False`` when the budget is exhausted or
    expired, ``None`` when no such authorization exists.

    The decrement is a single conditional UPDATE, so two workers can never each believe
    they own the last call — the database, not a process-local integer, is the authority.
    """
    try:
        from django.db.models import F
        from django.utils import timezone
        from apps.ai.models import RealLLMAuthorization

        now = timezone.now()
        updated = (RealLLMAuthorization.objects
                   .filter(run_id=run_id, calls_remaining__gt=0, expires_at__gt=now)
                   .update(calls_remaining=F("calls_remaining") - 1))
        if updated:
            row = (RealLLMAuthorization.objects
                   .filter(run_id=run_id).values_list("calls_remaining", flat=True).first())
            return row if row is not None else 0
        # Distinguish "spent/expired" from "never existed" so the log is actionable.
        exists = RealLLMAuthorization.objects.filter(run_id=run_id).exists()
        return False if exists else None
    except Exception:
        # FAIL CLOSED. If the budget store cannot be consulted we do not spend money.
        logger.error("REAL-LLM GOVERNOR: budget store unavailable — denying the call",
                     exc_info=True)
        return None


def admit_or_raise(*, source=None, traffic_class=None, operation=""):
    """Admit one billable request or raise :class:`RealLLMCallDenied`."""
    decision = may_real_llm_call(source=source, traffic_class=traffic_class)
    if decision.allowed:
        _admitted_run_id.set(decision.run_id)
        if decision.run_id:
            logger.warning(
                "REAL-LLM GOVERNOR: ADMITTED paid %s under authorization run=%s "
                "(%s call(s) remaining after this one)",
                operation or "request", decision.run_id, decision.remaining,
            )
        return decision
    raise RealLLMCallDenied(_explain(decision, operation))


def _explain(decision, operation):
    base = (f"Real provider call refused by the WLJ cost governor "
            f"(operation={operation or 'unknown'}, environment={decision.environment}, "
            f"reason={decision.reason}). ")
    guidance = {
        "no_authorization_flag": (
            f"Development defaults to DENY. A configured OPENAI_API_KEY is NOT "
            f"authorization. Danny must mint an authorization "
            f"(`manage.py authorize_real_llm`) and export {FLAG_ALLOW}=1 and "
            f"{FLAG_RUN_ID}. Claude Code must never do this itself."),
        "no_run_id": f"{FLAG_ALLOW} is set but {FLAG_RUN_ID} is missing.",
        "no_valid_authorization": (
            f"{FLAG_RUN_ID} does not match a live authorization (unknown id, or the "
            f"budget store is unreachable — which fails closed by design)."),
        "proactive_ai_disabled": (
            "Provider-backed PROACTIVE/BACKGROUND AI is paused for pre-production "
            "(WLJ_PROACTIVE_AI_ENABLED is off). No human requested this work, so it does "
            "not spend. User-initiated Chief of Staff conversation is unaffected. "
            "Re-enabling is Danny's explicit product decision — Claude Code must not set "
            "this flag."),
        "budget_exhausted": (
            "The authorized call budget is spent or expired. STOP. Do not reset it, mint "
            "another, switch environments, or use a different key — ask Danny."),
        "diagnostic_not_authorized": (
            "This is an OPERATOR DIAGNOSTIC and diagnostics do not spend money by "
            "default — not even in production, where the surrounding runtime serves real "
            "customers. Verify with deterministic fixtures, the truth probe, or "
            "read-only evidence instead. If a real call is genuinely the only way to "
            "answer the question, ask Danny for a number and pass it explicitly; the "
            "endpoint will allow exactly that many and record who authorized it."),
    }
    return base + guidance.get(decision.reason, "")


# ──────────────────────────────────────────────────────────────────────────────
# The guarded client
# ──────────────────────────────────────────────────────────────────────────────

class _GuardedEndpoint:
    """Proxies one attribute path on the real client, admitting billable operations.

    Attribute access is forwarded verbatim, so a guarded client is a drop-in replacement:
    call sites keep using `client.chat.completions.create(...)` unchanged.
    """

    __slots__ = ("_target", "_path", "_ctx")

    def __init__(self, target, path, ctx):
        self._target = target
        self._path = path
        self._ctx = ctx

    def __getattr__(self, name):
        attr = getattr(self._target, name)
        path = self._path + (name,)
        if path in BILLABLE_OPERATIONS and callable(attr):
            return _guarded_call(attr, path, self._ctx)
        if callable(attr) and not hasattr(attr, "__dict__"):
            return attr
        return _GuardedEndpoint(attr, path, self._ctx)


def _guarded_call(fn, path, ctx):
    op = ".".join(path)

    def _call(*args, **kwargs):
        admit_or_raise(source=ctx.get("source"), traffic_class=ctx.get("traffic_class"),
                       operation=op)
        return fn(*args, **kwargs)

    return _call


class GuardedOpenAIClient:
    """A real OpenAI client that cannot make an unauthorized paid request.

    Everything except the billable operations is passed straight through, so this stays a
    transparent stand-in for the SDK client.
    """

    __slots__ = ("_client", "_ctx")

    def __init__(self, client, ctx=None):
        self._client = client
        self._ctx = ctx or {}

    def __getattr__(self, name):
        attr = getattr(self._client, name)
        path = (name,)
        if path in BILLABLE_OPERATIONS and callable(attr):
            return _guarded_call(attr, path, self._ctx)
        if isinstance(attr, (str, int, float, bool, type(None))):
            return attr
        return _GuardedEndpoint(attr, path, self._ctx)

    @property
    def unguarded(self):  # pragma: no cover - escape hatch for introspection only
        """The raw SDK client. NEVER use this to make a request — it bypasses the governor.
        Present so diagnostics can read client configuration."""
        return self._client


def build_guarded_client(api_key=None, *, source=None, traffic_class=None, **kwargs):
    """THE approved way to construct an OpenAI client anywhere in WLJ.

    Returns ``None`` when no API key is configured — the long-established
    graceful-degradation contract every call site already handles.

    Constructing `OpenAI(...)` directly is a CI failure (see
    `apps/core/tests/test_llm_admission_contract.py`): a direct client would be ungoverned,
    which is precisely how the overspend happened.
    """
    from django.conf import settings

    key = api_key or getattr(settings, "OPENAI_API_KEY", None)
    if not key:
        # NEVER SILENT — a missing key disables every AI feature in this process.
        logger.warning(
            "OpenAI client NOT created — no API key in THIS process (proc=%s pid=%s).",
            os.path.basename(__import__("sys").argv[0]) if __import__("sys").argv else "?",
            os.getpid(),
        )
        return None

    try:
        from openai import OpenAI  # noqa: WLJ-APPROVED-OPENAI-CONSTRUCTION
    except ImportError:
        logger.error("openai package unavailable — cannot build a client", exc_info=True)
        return None

    try:
        raw = OpenAI(api_key=key, **kwargs)  # noqa: WLJ-APPROVED-OPENAI-CONSTRUCTION
    except Exception:
        logger.error("OpenAI client construction failed", exc_info=True)
        return None

    if not is_production():
        logger.info("REAL-LLM GOVERNOR active (environment=%s): provider calls require "
                    "%s=1 and a live %s.", current_environment(), FLAG_ALLOW, FLAG_RUN_ID)
    return GuardedOpenAIClient(raw, {"source": source, "traffic_class": traffic_class})
