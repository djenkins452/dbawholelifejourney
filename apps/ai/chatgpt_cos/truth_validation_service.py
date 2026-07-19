# ==============================================================================
# File: apps/ai/chatgpt_cos/truth_validation_service.py
# Project: Whole Life Journey - Django 5.x Personal Wellness/Journaling App
# Description: Truth Validation Center runner. Reuses the Acceptance engine's plumbing
#   (production gateway asker, evidence capture, heartbeat, cooperative cancel, stale
#   reaping) but sources its work-list from the Truth Discovery Suite and grades each
#   object with the DETERMINISTIC comparison engine (expected WLJ truth vs structured
#   values in the response). One engine, typed by validation_type. WLJ is the authority.
# Owner: Danny Jenkins (admin@wholelifejourney.com)
# ==============================================================================
"""execute_truth_run(run) — fill a `validation_type="truth"` AcceptanceRun in place.

For each discovery prompt in scope: send it through the PRODUCTION Chief of Staff exactly
as a customer would (the shared `_gateway_asker`), resolve the deterministic WLJ object the
prompt is about, compare the structured expected values against the response, persist one
AcceptanceResult per object, and finalize with truth-health rollups. No AI grades AI.
"""
import logging
import time

from django.utils import timezone

# REUSE the acceptance engine's production plumbing — never a second harness.
from apps.ai.chatgpt_cos.acceptance_service import (
    _cancel_requested,
    _extract_evidence,
    _first_failing_layer,
    _gateway_asker,
    _write_heartbeat,
    environment_label,
    git_commit,
)

logger = logging.getLogger(__name__)

# Bump when the discovery suite's OBJECT set changes structurally (new object, changed
# surface) so history rows record which suite version produced them.
SUITE_VERSION = "1.0"


def provider_version():
    """A cheap pin on the truth-provider surface (count of registered domains). The exact
    provider CODE is pinned by git_commit; this flags provider-registry changes at a glance."""
    try:
        from apps.core.truth.domain import registered_domains
        return f"domains={len(registered_domains())}"
    except Exception:
        return ""


# ---- work-list -------------------------------------------------------------
def prompts_for_scope(scope_kind, scope_key):
    """The discovery prompts a run covers. full -> all; domain -> one domain; object ->
    one prompt id. Returns [] for an unknown object/domain (the run finalizes as empty)."""
    from apps.core.truth.discovery_suite import DISCOVERY_PROMPTS
    if scope_kind == "object" and scope_key:
        return [p for p in DISCOVERY_PROMPTS if p.get("id") == scope_key]
    if scope_kind == "domain" and scope_key:
        return [p for p in DISCOVERY_PROMPTS if p.get("domain") == scope_key]
    return list(DISCOVERY_PROMPTS)


# ---- one object ------------------------------------------------------------
def validate_one(ask, prompt, resolver, *, today=None, prompt_mode="resolved"):
    """Resolve the object FIRST (using the app's own selection rule), then send the prompt
    through the gateway and grade the answer deterministically. `resolver(prompt) ->
    ExpectedObject` is the user-bound deterministic truth resolver (passed in, never a module
    global — so concurrent runs never cross). In "resolved" mode, when the object resolves we
    send a prompt that NAMES the resolved object (removing ambiguity); "natural" mode always
    sends the raw NL discovery prompt. Returns a dict ready to persist. Never raises."""
    from apps.core.truth.validation import (
        compare_object, flatten_entity, grade_checks,
    )
    # 1) Resolve the deterministic object BEFORE asking — object resolution must never be a
    #    side effect of the answer, and the operator must see exactly what is being validated.
    expected = resolver(prompt) if resolver else None
    resolution = expected.resolution() if expected is not None else {}

    # 2) Choose the prompt. Resolved mode binds to the resolved identity when available.
    nl_prompt = prompt.get("prompt", "")
    text = nl_prompt
    bound = False
    if (prompt_mode == "resolved" and expected is not None and expected.present
            and expected.resolved_identity):
        tmpl = prompt.get("bind_template") or 'Tell me everything you know about "{identity}".'
        try:
            text = tmpl.format(identity=expected.resolved_identity)
            bound = True
        except (KeyError, IndexError):
            text = nl_prompt

    t0 = time.monotonic()
    answer, evidence = "", {}
    try:
        answer, evidence = ask(text)
    except Exception as exc:
        logger.warning("truth_validation validate_one failed id=%s",
                       prompt.get("id"), exc_info=True)
        answer = f"<EXCEPTION: {type(exc).__name__}: {exc}>"
    evidence = evidence or {}
    answer = answer or ""
    elapsed = round((time.monotonic() - t0) * 1000)

    forbidden = prompt.get("must_not_surface") or []
    checks = []
    expected_entity = {}
    if expected is not None and expected.present:
        expected_entity = expected.entity
        evs = flatten_entity(expected.entity)
        checks = compare_object(evs, answer, today=today, forbidden=forbidden)
    else:
        # Nothing to surface (absent record) or an unresolvable surface: no positive
        # checks, but STILL run contamination guards against the answer.
        checks = compare_object([], answer, today=today, forbidden=forbidden)

    grade = grade_checks(checks)
    passed = grade.passed
    is_na = grade.is_na and (expected is None or not expected.present)

    fails = [c.label for c in checks
             if (not c.is_forbidden and c.status in ("missing", "mismatch"))
             or (c.is_forbidden and c.status == "mismatch")]
    if answer.startswith("<EXCEPTION"):
        fails = ["exception"] + fails
    layer = _first_failing_layer(passed and not is_na, fails, evidence)

    return {
        "object_key": prompt.get("id", ""),
        "domain": prompt.get("domain", ""),
        "question": text,                 # the prompt actually SENT to the CoS
        "nl_prompt": nl_prompt,           # the original natural-language discovery prompt
        "bound": bound,
        "prompt_mode": prompt_mode,
        "resolution": resolution,         # Resolved Object / From / Rule / Provider
        "answer": answer,
        "ms": elapsed,
        "passed": passed,
        "is_na": is_na,
        "reason": "" if (expected and expected.present) else (
            expected.reason if expected else "Expected truth could not be resolved."),
        "selector": expected.selector if expected else "",
        "expected_truth": expected_entity,
        "extracted_truth": {
            "present": grade.present, "missing": grade.missing,
            "mismatch": grade.mismatch, "na": grade.na,
            "forbidden_hits": grade.forbidden_hits},
        "checks": [c.to_dict() for c in checks],
        "check_pass_count": grade.present,
        "check_total": grade.total,
        "fails": fails,
        "first_failing_layer": layer,
        # evidence columns (same provenance as the behavior suite)
        "runtime_used": evidence.get("runtime_used", ""),
        "selected_tool": evidence.get("selected_tool", ""),
        "tool_arguments": evidence.get("tool_arguments", {}),
        "canonical_provider": evidence.get("canonical_provider", ""),
        "retrieved_records": evidence.get("retrieved_records", {}),
        "retrieval_evidence": evidence.get("retrieval_evidence", []),
        "intent": evidence.get("intent"),
        "openai_called": bool(evidence.get("openai_called")),
    }


# ---- orchestrator ----------------------------------------------------------
def execute_truth_run(run, ask=None):
    """Run the Truth Validation suite for `run`'s scope against the PRODUCTION runtime,
    persist one AcceptanceResult per object, and finalize with truth-health rollups.
    `ask` is injectable for deterministic tests. Returns `run`."""
    from django.contrib.auth import get_user_model
    from apps.admin_console.models import AcceptanceResult
    from apps.core.truth.validation import resolve_expected_object

    run.status = "running"
    run.validation_type = "truth"
    run.started_at = timezone.now()
    run.environment = run.environment or environment_label()
    run.git_commit = run.git_commit or git_commit()
    run.suite_version = run.suite_version or SUITE_VERSION
    run.provider_version = run.provider_version or provider_version()
    run.save(update_fields=["status", "validation_type", "started_at", "environment",
                            "git_commit", "suite_version", "provider_version"])

    User = get_user_model()
    user = run.target_user or User.objects.filter(is_superuser=True).first()
    if user is None:
        run.status = "failed"
        run.error_message = "No target user available."
        run.completed_at = timezone.now()
        run.save()
        return run

    if ask is None:
        ask = _gateway_asker(user)
    # The deterministic resolver is bound to THIS run's user and passed explicitly.
    resolver = lambda prompt: resolve_expected_object(user, prompt)

    today = timezone.localdate()
    prompts = prompts_for_scope(run.scope_kind, run.scope_key)
    total = len(prompts)
    run.total_count = total
    run.save(update_fields=["total_count"])
    _write_heartbeat(run, "(starting)", 0, total)

    rows = []
    cancelled = False
    t0 = time.monotonic()
    for i, prompt in enumerate(prompts):
        if _cancel_requested(run.id):
            cancelled = True
            logger.info("truth_validation: cancel detected run=%s at %s/%s",
                        run.id, i, total)
            break
        _write_heartbeat(run, prompt.get("id", ""), i, total)
        r = validate_one(ask, prompt, resolver, today=today,
                         prompt_mode=(run.prompt_mode or "resolved"))
        rows.append(r)
        _write_heartbeat(run, prompt.get("id", ""), i + 1, total)
        AcceptanceResult.objects.create(
                run=run, question_key=r["object_key"], object_key=r["object_key"],
                suite=r["domain"], question_text=r["question"],
                response_text=r["answer"], response_time_ms=r["ms"],
                passed=r["passed"], is_na=r["is_na"],
                failed_rules=r["fails"],
                expected_truth=r["expected_truth"] or {},
                extracted_truth=r["extracted_truth"] or {},
                checks=r["checks"] or [],
                check_pass_count=r["check_pass_count"], check_total=r["check_total"],
                openai_called=r["openai_called"], sort_order=i,
                raw_result_json={"reason": r["reason"], "selector": r["selector"],
                                 "resolution": r.get("resolution") or {},
                                 "sent_prompt": r.get("question", ""),
                                 "nl_prompt": r.get("nl_prompt", ""),
                                 "bound": r.get("bound", False),
                                 "prompt_mode": r.get("prompt_mode", "")},
                runtime_used=r.get("runtime_used", ""),
                selected_tool=r.get("selected_tool", ""),
                tool_arguments=r.get("tool_arguments") or {},
                canonical_provider=r.get("canonical_provider", ""),
                retrieved_records=r.get("retrieved_records") or {},
                retrieval_evidence=r.get("retrieval_evidence") or [],
                first_failing_layer=r.get("first_failing_layer", ""))

    if cancelled:
        _finalize_cancelled(run, rows, total)
    else:
        _finalize_truth(run, rows, round((time.monotonic() - t0) * 1000))
    return run


def _finalize_cancelled(run, rows, full_total):
    completed = len(rows)
    passed = sum(1 for r in rows if r.get("passed"))
    run.status = "cancelled"
    run.completed_at = timezone.now()
    run.total_count = full_total
    run.pass_count = passed
    run.fail_count = completed - passed
    run.score_percent = 0
    run.grade = ""
    run.trustworthy = False
    run.error_message = (
        f"Cancelled by administrator after {completed}/{full_total} objects. "
        "Results are partial — no truth-health grade is computed for a cancelled run.")
    run.save()


def _finalize_truth(run, rows, duration_ms):
    total = len(rows)
    na = sum(1 for r in rows if r.get("is_na"))
    scorable = [r for r in rows if not r.get("is_na")]
    passed = sum(1 for r in scorable if r.get("passed"))
    fail = len(scorable) - passed
    checks_total = sum(r.get("check_total", 0) for r in rows)
    checks_passed = sum(r.get("check_pass_count", 0) for r in rows)
    has_contradiction = any(
        (r["extracted_truth"].get("mismatch", 0) or
         r["extracted_truth"].get("forbidden_hits", 0)) for r in rows)

    run.total_count = total
    run.pass_count = passed
    run.fail_count = fail
    run.na_count = na
    run.checks_total = checks_total
    run.checks_passed = checks_passed
    run.score_percent = round(100 * checks_passed / checks_total) if checks_total else 0
    run.duration_ms = duration_ms
    run.avg_response_ms = round(sum(r["ms"] for r in rows) / total) if total else 0
    run.critical_count = sum(
        r["extracted_truth"].get("mismatch", 0) +
        r["extracted_truth"].get("forbidden_hits", 0) for r in rows)
    # GREEN only when nothing failed AND no contradiction/contamination.
    if fail == 0 and not has_contradiction:
        run.grade = "GREEN"
    elif run.score_percent >= 70 and not has_contradiction:
        run.grade = "YELLOW"
    else:
        run.grade = "RED"
    run.trustworthy = True
    run.status = "completed"
    run.completed_at = timezone.now()
    run.category_summary = truth_category_breakdown(run)   # executive-summary breakdown
    run.raw_report_json = {
        "bugs": _truth_bugs(run, rows),
        "scope_kind": run.scope_kind, "scope_key": run.scope_key,
        "na_objects": [r["object_key"] for r in rows if r.get("is_na")]}
    run.save()


# ---- executive summary: failure breakdown by category ----------------------
# Maps the first-failing-layer taxonomy to the operator-facing categories so the summary
# shows WHERE engineering effort belongs. Each failed object lands in exactly one category.
CATEGORY_ORDER = ["object_resolution", "provider_failure", "routing", "tool_selection",
                  "answer_grounding", "contamination", "unknown"]
CATEGORY_LABELS = {
    "object_resolution": "Object Resolution", "provider_failure": "Provider Failures",
    "routing": "Routing", "tool_selection": "Tool Selection",
    "answer_grounding": "Answer Grounding", "contamination": "Contamination",
    "unknown": "Unknown"}
# Categories owned by the Truth Layer (sum = "Truth Layer Bugs").
TRUTH_LAYER_CATEGORIES = ("object_resolution", "provider_failure", "routing", "tool_selection")
_LAYER_CATEGORY = {
    "fixture": "provider_failure", "provider": "provider_failure", "evidence": "provider_failure",
    "registration": "tool_selection", "routing": "routing", "answer": "answer_grounding",
    "transport": "unknown", "": "unknown"}


def _object_category(result):
    """The single primary failure category for one AcceptanceResult (None if it passed or
    is a legitimately-absent record)."""
    if result.passed:
        return None
    checks = result.checks or []
    forbidden_hit = any(c.get("is_forbidden") and c.get("status") == "mismatch" for c in checks)
    resolution = (result.raw_result_json or {}).get("resolution") or {}
    unresolvable = resolution.get("resolvable") is False
    if result.is_na:
        # unresolvable object = a resolution bug; a legitimately-absent record is not a bug
        return "object_resolution" if unresolvable else None
    if unresolvable:
        return "object_resolution"
    if forbidden_hit:
        return "contamination"
    return _LAYER_CATEGORY.get(result.first_failing_layer or "", "unknown")


def truth_category_breakdown(run):
    """{category: count} + truth_layer_bugs total, over the run's persisted results."""
    cats = {c: 0 for c in CATEGORY_ORDER}
    for r in run.results.all():
        cat = _object_category(r)
        if cat:
            cats[cat] += 1
    cats["truth_layer_bugs"] = sum(cats[c] for c in TRUTH_LAYER_CATEGORIES)
    return cats


# ---- truth bug report ------------------------------------------------------
_LAYER_OWNER = {
    "fixture": "Truth Layer (fixtures/data)", "provider": "Truth Layer (domain provider)",
    "registration": "Tool wiring (registry)", "routing": "Tool wiring (intent routing)",
    "evidence": "Truth Layer (provider returned nothing)",
    "answer": "Model / prompt (evidence present, answer not grounded)",
    "transport": "Infrastructure (transport error)", "": "Review",
}


def _truth_bugs(run, rows):
    """Structured, copyable truth-bug list for every failed OBJECT."""
    bugs = []
    for r in rows:
        if r.get("is_na") or r.get("passed"):
            continue
        failed_checks = [c for c in r["checks"]
                         if (not c.get("is_forbidden") and c.get("status") in ("missing", "mismatch"))
                         or (c.get("is_forbidden") and c.get("status") == "mismatch")]
        for c in failed_checks:
            bugs.append({
                "object": r["object_key"],
                "prompt": r["question"],
                "expected_truth": c.get("expected"),
                "field": c.get("label"),
                "difference": ("contradicted (%s)" % c.get("extracted")
                               if c.get("status") == "mismatch"
                               else ("contamination" if c.get("is_forbidden") else "omitted")),
                "actual_response": (r["answer"] or "")[:600],
                "underlying_record": r.get("selector") or r["object_key"],
                "first_failing_layer": r.get("first_failing_layer", ""),
                "suggested_owner": _LAYER_OWNER.get(r.get("first_failing_layer", ""), "Review"),
            })
    return bugs


# ---- convenience -----------------------------------------------------------
def create_and_execute_truth(scope_kind="full", scope_key="", target_user=None,
                             created_by=None):
    from apps.admin_console.models import AcceptanceRun
    run = AcceptanceRun.objects.create(
        validation_type="truth", suite_name="truth", depth="truth",
        scope_kind=scope_kind, scope_key=scope_key,
        target_user=target_user, created_by=created_by,
        environment=environment_label(), git_commit=git_commit(),
        suite_version=SUITE_VERSION, provider_version=provider_version())
    return execute_truth_run(run)
