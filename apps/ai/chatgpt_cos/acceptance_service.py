# ==============================================================================
# File: apps/ai/chatgpt_cos/acceptance_service.py
# Project: Whole Life Journey - Django 5.x Personal Wellness/Journaling App
# Description: Shared Beth acceptance RUNNER. Executes the validation questions
#   through the REAL chat path (ChatGPTCoSService.generate), evaluates each
#   response with the shared rules, persists an AcceptanceRun + AcceptanceResults,
#   and generates the ChatGPT-review and Claude-fix prompts. Called by BOTH the
#   `beth_acceptance` management command and the Admin Console (via a Celery task).
#
#   Read-only validation: generate() does not persist chat messages, send
#   notifications, fire proactive behavior, or mutate user data. The throwaway
#   conversation is deleted after the run.
# ==============================================================================
import logging
import os
import re
import time
from contextlib import contextmanager

from django.utils import timezone

from apps.ai.chatgpt_cos.acceptance_rules import (
    QUESTIONS, evaluate, questions_for, GOAL_INTENTS, categorize_rule,
    is_critical_rule, grade as grade_run, compute_grade, RELEASE_THRESHOLD,
    layer_of, row_layer, INFRA_LAYERS, ARCHITECTURAL_INVARIANTS,
)

SLOW_MS = 9000      # a response slower than this earns a warning


# ---- architectural failure analysis ----------------------------------------
def analyze(rows):
    """Classify failures by architectural LAYER, split infrastructure vs content,
    detect entire-suite failures + release blockers, assess run trustworthiness,
    and emit ranked root-cause hypotheses. Pure — operates on row dicts."""
    layers, categories = {}, {}
    infra_fails = content_fails = empty_count = 0
    blockers = []
    suite_tot, suite_fail = {}, {}

    for r in rows:
        s = r.get("suite", "?")
        suite_tot[s] = suite_tot.get(s, 0) + 1
        if not r["passed"]:
            suite_fail[s] = suite_fail.get(s, 0) + 1
        for f in r["fails"]:
            categories[categorize_rule(f)] = categories.get(categorize_rule(f), 0) + 1
        if not r["passed"]:
            lyr = row_layer(r["fails"]) or "content_quality"
            layers[lyr] = layers.get(lyr, 0) + 1
            if lyr in INFRA_LAYERS:
                infra_fails += 1
            else:
                content_fails += 1
            if any(f == "empty" or f.startswith("empty") for f in r["fails"]):
                empty_count += 1
            # release blockers: empty, orchestration, infra, wrong-domain
            if lyr in INFRA_LAYERS:
                blockers.append({"key": r["key"], "layer": lyr,
                                 "reason": ", ".join(r["fails"])[:160]})

    entire_suites_failed = sorted(
        s for s, tot in suite_tot.items()
        if tot >= 2 and suite_fail.get(s, 0) == tot)

    trustworthy = (infra_fails == 0 and not entire_suites_failed)
    if trustworthy:
        trust_reason = ("Infrastructure healthy — quality conclusions can be "
                        "trusted.")
    else:
        bits = []
        if infra_fails:
            bits.append(f"{infra_fails} infrastructure/orchestration failure(s)")
        if entire_suites_failed:
            bits.append("entire suite(s) unavailable: " + ", ".join(entire_suites_failed))
        trust_reason = ("Quality assessment is PARTIALLY INVALID because "
                        "infrastructure is unhealthy (" + "; ".join(bits) + "). "
                        "Content conclusions for affected paths cannot be trusted; "
                        "a GREEN here would be FALSELY green and a content-RED may "
                        "just be downstream of the outage.")

    return {
        "layers": layers, "categories": categories,
        "infra_fails": infra_fails, "content_fails": content_fails,
        "empty_count": empty_count, "blockers": blockers,
        "entire_suites_failed": entire_suites_failed,
        "trustworthy": trustworthy, "trust_reason": trust_reason,
        "hypotheses": _hypotheses(layers, empty_count, entire_suites_failed, rows),
    }


# ---------------------------------------------------------------------------
# Telemetry-driven SUBSYSTEM inference. Hypotheses are derived from a row's OWN
# telemetry (suite / intent / lane / openai / fallback / failure category) — never
# from historical bias toward Goals. A HEALTH-suite banned phrase is attributed to
# HEALTH narration, not Goals. Output is ADVISORY: it MUST be validated against
# repository evidence (see EVIDENCE_SUPREMACY).
# ---------------------------------------------------------------------------
_CONF_RANK = {"LOW": 1, "MEDIUM": 2, "HIGH": 3}
_SUITE_NARRATION = {"goals": "goal narration", "health": "health narration",
                    "checkin": "check-in narration", "rhythm": "rhythm narration"}
_PRIMARY_LAYER = {
    "tool loop": "conversation_orchestration",
    "conversation orchestration": "conversation_orchestration",
    "OpenAI integration": "infrastructure", "general outage fallback": "infrastructure",
    "routing": "routing", "lane selection": "routing", "planner": "routing",
    "deterministic fallback": "deterministic_truth",
    "goal narration": "narration", "health narration": "narration",
    "check-in narration": "narration", "rhythm narration": "narration",
    "narration": "narration", "acceptance guard": "content_quality",
    "deterministic capability gap": "deterministic_truth",
}
_HYP_TITLE = {
    "tool loop": "Possible silent orchestration termination",
    "OpenAI integration": "Possible OpenAI / general-knowledge dependency outage",
    "routing": "Possible routing / lane mis-classification",
    "deterministic fallback": "Possible defect in a DETERMINISTIC fallback (no LLM involved)",
    "goal narration": "Possible narration leak in GOAL narration",
    "health narration": "Possible narration leak in HEALTH narration",
    "planner": "Possible planner / answer-duplication issue",
    "acceptance guard": ("Possible missing required content OR an over-narrow "
                         "acceptance contract (check BOTH — the evaluator may be wrong)"),
    "deterministic capability gap": ("Possible DETERMINISTIC CAPABILITY GAP — WLJ owns "
                                     "this truth but no deterministic path reached it "
                                     "(NOT an OpenAI/infrastructure failure)"),
}


def _suite_narration(suite):
    return _SUITE_NARRATION.get(suite, f"{suite} narration")


def _infer_subsystems(row):
    """Probable subsystem(s) for ONE failed row, inferred from its OWN telemetry —
    never from history. Returns (subsystems:list, confidence, telemetry_reason)."""
    suite = row.get("suite", "?")
    cats = {categorize_rule(f) for f in row.get("fails", [])}
    openai = row.get("openai_called")
    fallback = row.get("fallback_used")
    telem = (f"suite={suite}, intent={row.get('intent') or '-'}, "
             f"lane={row.get('lane') or '-'}, openai={openai}, fallback={fallback}")
    if "empty_response" in cats:
        return (["tool loop", "conversation orchestration"], "HIGH", telem)
    if "general_failure" in cats or (suite == "general" and openai is False):
        if suite == "general":
            # external knowledge genuinely depends on OpenAI -> infrastructure.
            return (["OpenAI integration", "general outage fallback"], "HIGH", telem)
        # P27: an outage message in a domain WLJ OWNS the truth for (goals/health)
        # is a DETERMINISTIC CAPABILITY GAP — deterministic truth exists but no
        # deterministic reasoning path reached it. This is NOT infrastructure
        # (OpenAI availability is not the root cause); Beth should answer it offline.
        return (["deterministic capability gap", _suite_narration(suite)], "HIGH", telem)
    if "wrong_domain" in cats:
        return (["routing", "lane selection"], "MEDIUM", telem)
    if "duplicate_answer" in cats:
        return (["planner", "narration"], "MEDIUM", telem)
    if openai is False and fallback is True:
        # the answer came from the DETERMINISTIC fallback, not the LLM
        return (["deterministic fallback", _suite_narration(suite)], "MEDIUM", telem)
    if "banned_phrase" in cats:
        src = "LLM narration" if openai else "deterministic fallback"
        return ([_suite_narration(suite), src], "MEDIUM", telem)
    # Content-completeness failure (missing required concept / gate / too short). This
    # is NOT a "narration leak" — it is EITHER a narration omission OR an over-narrow
    # acceptance contract. Lead with "acceptance guard" so the reviewer checks the
    # EVALUATOR too (a goal_failure_modes missing_required was an evaluator-breadth
    # defect — the contract, not Beth, was wrong; commit 70413109).
    src = "LLM narration" if openai else "deterministic fallback"
    return (["acceptance guard", _suite_narration(suite), src, "content quality"],
            "LOW", telem)


def probable_subsystems(row):
    """Public one-line subsystem attribution for a failed row (used per-question)."""
    subs, conf, _ = _infer_subsystems(row)
    return subs, conf


def _hypotheses(layers, empty_count, entire_suites_failed, rows):
    """ADVISORY hypotheses, grouped by telemetry-inferred subsystem. Each is a guess
    that MUST be validated against repository evidence — never a conclusion."""
    failed = [r for r in rows if not r.get("passed")]
    buckets = {}
    for r in failed:
        subs, conf, telem = _infer_subsystems(r)
        primary = subs[0]
        b = buckets.setdefault(primary, {"subs": subs, "conf": conf, "keys": [],
                                         "suites": set(), "telem": telem})
        b["keys"].append(r["key"])
        b["suites"].add(r.get("suite", "?"))
        if _CONF_RANK[conf] > _CONF_RANK[b["conf"]]:
            b["conf"], b["telem"] = conf, telem
    h = []
    for primary, b in buckets.items():
        suites = ", ".join(sorted(b["suites"]))
        systemic = any(s in entire_suites_failed for s in b["suites"])
        ev = (f"{len(b['keys'])} failing question(s) [{', '.join(b['keys'][:6])}] in "
              f"suite(s): {suites}. Representative telemetry: {b['telem']}."
              + (" Entire suite failed — presumed systemic." if systemic else ""))
        h.append({"title": _HYP_TITLE.get(primary, f"Possible defect in {primary}"),
                  "subsystems": b["subs"],
                  "layer": _PRIMARY_LAYER.get(primary, "content_quality"),
                  "confidence": b["conf"], "evidence": ev})
    h.sort(key=lambda x: (-_LAYER_PRECEDENCE_RANK.get(x["layer"], 0),
                          -_CONF_RANK[x["confidence"]]))
    return h


_LAYER_PRECEDENCE_RANK = {"conversation_orchestration": 6, "infrastructure": 5,
                          "routing": 4, "deterministic_truth": 3, "narration": 2,
                          "content_quality": 1, "unknown": 0}

# Permanent architectural law injected into BOTH generated prompts. The automated
# analysis GUIDES — it must never ANCHOR. Repository evidence always wins.
EVIDENCE_SUPREMACY = (
    "EVIDENCE SUPREMACY (permanent law):\n"
    "  Repository evidence takes precedence over automated hypotheses, telemetry "
    "heuristics, and Acceptance analysis.\n"
    "  If evidence contradicts automated analysis, fix the EVIDENCE-BASED defect and "
    "DOCUMENT the discrepancy.\n"
    "  The automated analysis below is generated from telemetry + heuristics and CAN "
    "BE WRONG — it may, for example, attribute a HEALTH-suite failure to Goals. "
    "Hypothesize, do not conclude; suggest, do not dictate; guide, do not anchor.")

ADVISORY_HEADER = "AUTOMATED HYPOTHESES (may be wrong):"
ADVISORY_NOTE = ("These hypotheses were generated from telemetry + heuristics. You "
                 "MUST validate each against repository evidence. If repository "
                 "evidence contradicts a hypothesis: (1) document the discrepancy, "
                 "(2) explain why the hypothesis was wrong, (3) fix the evidence-based "
                 "root cause.")

logger = logging.getLogger(__name__)


# ---- telemetry capture (intent / lane / fallback / openai-called) ----------
class _Capture(logging.Handler):
    def __init__(self):
        super().__init__()
        self.lines = []

    def emit(self, record):
        try:
            self.lines.append(record.getMessage())
        except Exception:
            pass


_INTENT_RE = re.compile(r"intent=([a-z_]+)")
_LANE_RE = re.compile(r"\blane=([a-z_]+)")


def parse_telemetry(lines):
    intent = lane = None
    fallback_used = None
    openai_called = False
    for ln in lines:
        if "BETH_GOAL_ROUTE_RESULT" in ln or "COS_REASONING_GOAL_PREROUTE" in ln:
            m = _INTENT_RE.search(ln)
            if m:
                intent = m.group(1)
        if "COS_REASONING_RESPONSE" in ln:
            m = _INTENT_RE.search(ln)
            if m:
                intent = m.group(1)
            if "fallback=True" in ln:
                fallback_used = True
            elif "fallback=False" in ln:
                fallback_used = False
                openai_called = True
        if "BETH_GENERAL_CALL" in ln:
            lane = "general_conversation"
            if "call_outcome=content" in ln:
                openai_called = True
            if "fallback_used=True" in ln:
                fallback_used = True
            elif "fallback_used=False" in ln:
                fallback_used = False
        if "COS_LANE_TRACE" in ln and lane is None:
            m = _LANE_RE.search(ln)
            if m:
                lane = m.group(1)
        if "LLM RESPONSE" in ln or "call_outcome=content" in ln:
            openai_called = True
    return intent, lane, fallback_used, openai_called


@contextmanager
def _telemetry():
    cap = _Capture()
    cap.setLevel(logging.DEBUG)
    loggers = [logging.getLogger("apps.ai.chatgpt_cos"),
               logging.getLogger("apps.ai"),
               logging.getLogger("apps.ai.services")]
    for lg in loggers:
        lg.addHandler(cap)
    try:
        yield cap
    finally:
        for lg in loggers:
            lg.removeHandler(cap)


def environment_label():
    env = os.environ.get("RAILWAY_ENVIRONMENT") or os.environ.get("DJANGO_ENV")
    return env or ("production" if not os.environ.get("DEBUG") else "development")


def git_commit():
    return (os.environ.get("RAILWAY_GIT_COMMIT_SHA", "") or "development")[:12]


# ---- run a single question through the real chat path ----------------------
def run_one(svc, conversation, spec, evening=False):
    text = spec["text"]
    patches = []
    if spec.get("evening") and evening:
        from unittest.mock import patch
        patches.append(patch(
            "apps.core.cos_briefing.daily_agenda._user_hour", return_value=21))
    for p in patches:
        p.start()
    t0 = time.monotonic()
    answer, intent, lane, fb, openai = "", None, None, None, False
    try:
        with _telemetry() as cap:
            res = svc.generate(conversation, text) or {}
        answer = (res.get("answer") or "").strip()
        lane = res.get("lane")
        intent, plane, fb, openai = parse_telemetry(cap.lines)
        lane = lane or plane
    except Exception as exc:
        logger.warning("beth_acceptance run_one failed key=%s", spec.get("key"),
                       exc_info=True)
        answer = f"<EXCEPTION: {type(exc).__name__}: {exc}>"
    finally:
        for p in patches:
            p.stop()
    elapsed = round((time.monotonic() - t0) * 1000)
    fails = evaluate(spec, answer, intent=intent, lane=lane)
    if answer.startswith("<EXCEPTION"):
        fails = ["exception"] + fails
    return {
        "key": spec["key"], "suite": _suite_of(spec), "question": text,
        "answer": answer, "expected_intent": spec.get("expect_intent", ""),
        "expected_lane": spec.get("expect_lane", ""), "intent": intent, "lane": lane,
        "fallback_used": fb, "openai_called": openai, "ms": elapsed,
        "required": spec.get("required", []) + spec.get("required_any", []),
        "forbidden": spec.get("forbidden", []),
        "distinct_group": spec.get("distinct_group", ""),
        "criticality": spec.get("criticality", "normal"),
        "spec": spec, "fails": fails, "passed": not fails,
    }


def _suite_of(spec):
    from apps.ai.chatgpt_cos.acceptance_rules import suite_of
    return suite_of(spec)


# ---- the orchestrator: fill an AcceptanceRun in place ----------------------
def execute_run(run, evening=True):
    """Run `run.suite_name` against the live stack, persist results onto `run`,
    compute score + prompts, and mark the run completed/failed. Returns `run`."""
    from django.contrib.auth import get_user_model
    from apps.ai.models import AssistantConversation
    from apps.ai.chatgpt_cos.service import ChatGPTCoSService
    from apps.admin_console.models import AcceptanceResult

    run.status = "running"
    run.started_at = timezone.now()
    run.environment = run.environment or environment_label()
    run.git_commit = run.git_commit or git_commit()
    run.save(update_fields=["status", "started_at", "environment", "git_commit"])

    User = get_user_model()
    user = run.target_user or User.objects.filter(is_superuser=True).first()
    if user is None:
        run.status = "failed"
        run.error_message = "No target user available."
        run.completed_at = timezone.now()
        run.save()
        return run

    conv = AssistantConversation.objects.create(
        user=user, title="[acceptance] Beth validation", session_type="general",
        is_active=False)
    svc = ChatGPTCoSService(user)
    specs = questions_for(run.suite_name, run.depth or "full")
    rows = []
    t0 = time.monotonic()
    try:
        for i, spec in enumerate(specs):
            r = run_one(svc, conv, spec, evening=evening)
            rows.append(r)
            AcceptanceResult.objects.create(
                run=run, question_key=r["key"], suite=r["suite"],
                question_text=r["question"], expected_intent=r["expected_intent"] or "",
                expected_lane=r["expected_lane"] or "", actual_intent=r["intent"] or "",
                actual_lane=r["lane"] or "", response_text=r["answer"],
                response_time_ms=r["ms"], passed=r["passed"], failed_rules=r["fails"],
                required_concepts=r["required"], forbidden_concepts=r["forbidden"],
                openai_called=r["openai_called"],
                fallback_used=r["fallback_used"], raw_result_json=r, sort_order=i)
    finally:
        try:
            conv.delete()      # never pollute chat history
        except Exception:
            pass

    _detect_duplicates(rows)
    _finalize(run, rows, round((time.monotonic() - t0) * 1000))
    return run


def _detect_duplicates(rows):
    """Within each distinct_group, answers from DIFFERENT intents that are
    substantially identical (same normalized text OR same first 20 words) are
    duplicates. Paraphrases of the SAME intent are allowed to match."""
    def norm(a):
        return " ".join((a or "").strip().lower().split())

    def first20(a):
        return " ".join(norm(a).split()[:20])

    groups = {}
    for r in rows:
        g = r.get("distinct_group")
        if g:
            groups.setdefault(g, []).append(r)
    for members in groups.values():
        seen_full, seen_head = {}, {}
        for r in members:
            if not r["answer"] or r["answer"].startswith("<EXCEPTION"):
                continue
            nf, nh = norm(r["answer"]), first20(r["answer"])
            for store, key in ((seen_full, nf), (seen_head, nh)):
                prev = store.get(key)
                if prev and prev["intent"] != r["intent"]:
                    r["fails"].append("duplicate_answer")
                    r["passed"] = False
                store.setdefault(key, r)


def _finalize(run, rows, duration_ms):
    total = len(rows)
    passed = sum(1 for r in rows if r["passed"])
    # per-row criticality + slow + category, persisted to the result objects
    category = {}
    critical = warnings = 0
    objs = list(run.results.order_by("sort_order"))
    for r, obj in zip(rows, objs):
        r_critical = any(is_critical_rule(f, r.get("spec")) for f in r["fails"]) \
            or (not r["passed"] and r.get("criticality") == "critical")
        r_slow = r["ms"] >= SLOW_MS
        if r_critical:
            critical += 1
        if r_slow:
            warnings += 1
        for f in r["fails"]:
            cat = categorize_rule(f)
            category[cat] = category.get(cat, 0) + 1
        obj.passed = r["passed"]
        obj.failed_rules = r["fails"]
        obj.is_critical = r_critical
        obj.is_slow = r_slow
        obj.save(update_fields=["passed", "failed_rules", "is_critical", "is_slow"])

    analysis = analyze(rows)
    run.total_count = total
    run.pass_count = passed
    run.fail_count = total - passed
    run.score_percent = round(passed / total * 100) if total else 0
    run.duration_ms = duration_ms
    run.avg_response_ms = round(sum(r["ms"] for r in rows) / total) if total else 0
    run.critical_count = critical
    run.warning_count = warnings
    run.category_summary = category
    run.analysis = analysis
    run.trustworthy = analysis["trustworthy"]
    run.grade = compute_grade(
        run.score_percent, critical, infra_fails=analysis["infra_fails"],
        empty_present=analysis["empty_count"] > 0,
        entire_suite_failed=bool(analysis["entire_suites_failed"]))
    run.status = "completed"
    run.completed_at = timezone.now()
    run.raw_report_json = {"rows": [{k: v for k, v in r.items() if k != "spec"}
                                    for r in rows],
                           "suite": run.suite_name, "depth": run.depth}
    run.chatgpt_review_prompt = build_chatgpt_review_prompt(run, rows)
    run.claude_fix_prompt = build_claude_fix_prompt(run, rows)
    run.save()


def create_and_execute(suite="full", depth="full", target_user=None,
                       created_by=None, evening=True):
    """Convenience for the CLI: create the AcceptanceRun then execute it."""
    from apps.admin_console.models import AcceptanceRun
    run = AcceptanceRun.objects.create(
        suite_name=suite, depth=depth, target_user=target_user, created_by=created_by,
        environment=environment_label(), git_commit=git_commit())
    return execute_run(run, evening=evening)


# ---- failure analytics + prompt generators ---------------------------------
def _category_summary(rows):
    cats = {}
    for r in rows:
        for f in r["fails"]:
            c = categorize_rule(f)
            cats[c] = cats.get(c, 0) + 1
    return cats


_CATEGORY_ORDER = ["banned_phrase", "missing_required", "wrong_domain",
                   "empty_response", "duplicate_answer", "general_failure",
                   "checkin_time_awareness", "forbidden_concept", "response_quality",
                   "slow_response"]


def _root_cause_groups(failed):
    """Group failures into likely systemic root-cause buckets (Claude prompt)."""
    groups = []
    has = lambda pred: [r for r in failed if any(pred(f) for f in r["fails"])]
    coaching = [r for r in failed if any(
        f.startswith("banned_phrase:") and f.split(":", 1)[1] in COACHING_HINT for f in r["fails"])]
    if coaching:
        # Attribute to the ACTUAL suite(s) + source — never assume Goals. A health
        # banned phrase is HEALTH narration; openai=True means the LLM produced it.
        where = ", ".join(sorted({_suite_narration(r["suite"]) for r in coaching}))
        src = ("LLM narration" if any(r.get("openai_called") for r in coaching)
               else "a deterministic fallback")
        groups.append((f"Generic coaching language leaking into {where} (probable "
                       f"source: {src}). VALIDATE the source against repository "
                       "evidence — do NOT assume Goals.", coaching))
    system = has(lambda f: f.startswith("banned_phrase:") and any(
        s in f for s in ("source of truth", "state builder", "momentum score",
                         "confidence score", "signal", "canonical")))
    if system:
        groups.append(("Internal/system language leaking to the user.", system))
    deflect = has(lambda f: f.startswith("banned_phrase:") and any(
        s in f for s in ("dashboard", "goals page", "open the app", "navigate")))
    if deflect:
        groups.append(("Deflection — pointing the user elsewhere instead of answering.",
                       deflect))
    slipping = [r for r in failed if r["key"].startswith("goal_concern")
                or r.get("expected_intent") == "goal_concerns"]
    if slipping:
        groups.append(("Goal 'slipping' filter — the concerns answer lists healthy "
                       "goals or misses the slipping/none requirement.", slipping))
    routing = has(lambda f: f.startswith("wrong_domain"))
    if routing:
        groups.append(("Routing — questions reaching the wrong domain/intent.", routing))
    general = [r for r in failed if r["suite"] == "general"]
    if general:
        groups.append(("General-knowledge lane reliability (empty/failure/rate-limit).",
                       general))
    quality = has(lambda f: f.startswith(("gate_", "too_short")))
    if quality:
        groups.append(("Response quality — missing evidence/synthesis/actionable step.",
                       quality))
    return groups


# coaching phrases (for grouping) — kept as a module set to avoid re-import cost
from apps.ai.chatgpt_cos.acceptance_rules import COACHING_BANNED as COACHING_HINT  # noqa: E402


def _summary_block(run, rows):
    failed = [r for r in rows if not r["passed"]]
    cats = run.category_summary or _category_summary(rows)
    passed_suites = {}
    for r in rows:
        passed_suites.setdefault(r["suite"], [0, 0])
        passed_suites[r["suite"]][0 if r["passed"] else 1] += 1
    dupes = [r["key"] for r in rows if "duplicate_answer" in r["fails"]]
    slow = [(r["key"], r["ms"]) for r in rows if r["ms"] >= SLOW_MS]
    openai_fail = sum(1 for r in rows if "openai_failure_message" in r["fails"]
                      or (not r["openai_called"] and r["suite"] == "general"))
    status = "PASS" if (run.grade == "GREEN") else "FAIL"
    lines = [
        "OVERALL RESULT:",
        f"  Pass rate: {run.score_percent}% ({run.pass_count}/{run.total_count})",
        f"  Release threshold: {RELEASE_THRESHOLD}% and zero critical failures",
        f"  Grade: {run.grade}   Current status: {status}",
        f"  Critical failures: {run.critical_count}   Warnings(slow): {run.warning_count}"
        f"   Avg response: {run.avg_response_ms} ms",
        "",
        "FAILURE SUMMARY BY CATEGORY:",
    ]
    for c in _CATEGORY_ORDER:
        lines.append(f"  - {c}: {cats.get(c, 0)}")
    lines.append("")
    lines.append("SUITE RESULTS (pass/fail):")
    for s, (p, f) in sorted(passed_suites.items()):
        lines.append(f"  - {s}: {p} passed, {f} failed")
    lines.append("")
    lines.append(f"OpenAI/fallback failure count: {openai_fail}")
    lines.append(f"Duplicate-answer warnings: {', '.join(dupes) or 'none'}")
    lines.append("Slow responses (>9s): "
                 + (", ".join(f"{k}={ms}ms" for k, ms in slow) or "none"))
    return "\n".join(lines), failed


def _arch_block(run, rows):
    a = run.analysis or analyze(rows)
    lines = ["ARCHITECTURAL LAYER AGGREGATION:"]
    if a["layers"]:
        for lyr, n in sorted(a["layers"].items(), key=lambda x: -x[1]):
            lines.append(f"  - {lyr}: {n}")
    else:
        lines.append("  - (no failures)")
    lines += [
        "",
        f"INFRASTRUCTURE vs CONTENT:  infrastructure={a['infra_fails']}  "
        f"content={a['content_fails']}  (empty responses={a['empty_count']})",
        "  NOTE: infrastructure failures take precedence — fix them FIRST; content "
        "conclusions downstream of an outage are unreliable.",
        "",
        "RELEASE BLOCKERS:",
    ]
    if a["blockers"]:
        for b in a["blockers"]:
            lines.append(f"  - [{b['key']}] {b['layer']} :: {b['reason']}")
    else:
        lines.append("  - none")
    if a["entire_suites_failed"]:
        lines.append("  - ENTIRE SUITE(S) FAILED (presumed systemic): "
                     + ", ".join(a["entire_suites_failed"]))
    lines += [
        "",
        "RUN TRUSTWORTHINESS:",
        f"  trustworthy: {'YES' if a['trustworthy'] else 'NO'}",
        f"  {a['trust_reason']}",
        "  Consider: could this run be FALSELY GREEN (infra masking content) or "
        "FALSELY RED (content failing only because infra is down)?",
        "",
        ADVISORY_HEADER,
        "  " + ADVISORY_NOTE,
    ]
    for i, hyp in enumerate(a["hypotheses"], 1):
        subs = ", ".join(hyp.get("subsystems", [])) or "unknown"
        lines.append(f"  {i}. {hyp['title']}  [layer={hyp['layer']}, "
                     f"confidence={hyp['confidence']}]\n"
                     f"     probable subsystem(s): {subs}\n"
                     f"     evidence/telemetry: {hyp['evidence']}")
    if not a["hypotheses"]:
        lines.append("  (none — run is clean)")
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# REVIEW OUTPUT CONTRACT — the controlled vocabularies + rigid output schema that
# force a generated prompt to elicit an EXPERT architectural review with no human
# augmentation. Reviewers must classify every systemic defect against these exact
# enums and fill every section; shallow commentary is structurally disallowed.
# ---------------------------------------------------------------------------
REVIEW_LAYER_VOCAB = ("conversation_orchestration", "infrastructure", "routing",
                      "deterministic_truth", "narration", "content_quality", "unknown")
REVIEW_SUBSYSTEMS = ("planner", "tool loop", "routing", "lane selection",
                     "deterministic fallback", "goal narration", "health narration",
                     "acceptance guard", "OpenAI integration",
                     "deterministic capability gap", "unknown")
# P27/P29: the architectural CLASS of a failure — forces reviewers to separate a
# CAPABILITY GAP (WLJ has the truth, no deterministic path reaches it) from a true
# Infrastructure outage (OpenAI genuinely unavailable), and — when a REAL USER report
# contradicts a GREEN Acceptance run — a PRODUCTION-PATH DIVERGENCE (live UI path
# differs from the harness path) or an ACCEPTANCE COVERAGE GAP (the harness never
# tested this exact path).
FAILURE_CLASSIFICATION = ("infrastructure", "deterministic capability gap",
                          "semantic routing", "production-path divergence",
                          "acceptance coverage gap", "prompt quality",
                          "acceptance contract")
REVIEW_SEVERITIES = ("BLOCKER", "HIGH", "MEDIUM", "LOW")
INFRA_DEFECT_EXAMPLES = ("empty responses", "OpenAI unavailable", "routing failure",
                         "orchestration abort", "timeout", "fallback bypass")
CONTENT_DEFECT_EXAMPLES = ("banned phrases", "generic coaching", "wrong recommendation",
                           "missing evidence", "duplicate answers")
STABLE_TAG_CONDITIONS = ("two consecutive GREEN Full runs", "zero banned-phrase leakage",
                         "Deep suite GREEN", "manual spot-check complete")


def _review_output_contract(run, rows):
    """The rigid OUTPUT schema a reviewer MUST fill — every section, controlled
    vocabularies, one regression test per defect class. Includes the live infra/
    content counts so the reviewer reasons from numbers, not impressions."""
    a = run.analysis or analyze(rows)
    layers = " | ".join(REVIEW_LAYER_VOCAB)
    subs = " | ".join(REVIEW_SUBSYSTEMS)
    sev = " | ".join(REVIEW_SEVERITIES)
    return "\n".join([
        "═══ REQUIRED OUTPUT — fill EVERY section. Use ONLY the controlled "
        "vocabularies. No commentary outside this schema; no shallow summaries. ═══",
        "",
        "A. SYSTEMIC DEFECT CLASSES  (defect CLASSES, never individual questions)",
        "   For EACH class, provide ALL of:",
        f"     - name:",
        f"     - primary classification: one of {{{' | '.join(FAILURE_CLASSIFICATION)}}}",
        "         (CAPABILITY GAP = WLJ HAS the deterministic truth but no deterministic "
        "path reaches it — distinct from INFRASTRUCTURE, where OpenAI is genuinely the "
        "unavailable dependency. If a REAL USER report contradicts a GREEN run, ask "
        "whether it is a PRODUCTION-PATH DIVERGENCE (the live UI path differs from this "
        "harness path / a feature flag diverges) or an ACCEPTANCE COVERAGE GAP (the "
        "harness never tested this exact phrasing/path). Ask: Infrastructure? Capability "
        "Gap? Semantic Routing? Production-path divergence? Acceptance coverage gap? "
        "Prompt Quality? Acceptance Contract?)",
        f"     - architectural layer:  one of {{{layers}}}",
        f"     - probable subsystem(s): one or more of {{{subs}}}",
        f"     - severity:             one of {{{sev}}}",
        "     - confidence:           HIGH | MEDIUM | LOW",
        "     - evidence:             cite the exact failed question keys + telemetry "
        "(intent/lane/openai/fallback) that prove it",
        "     - permanent regression test: ONE concrete test (file + assertion) that "
        "would catch this defect CLASS forever — 'every production defect becomes a "
        "permanent test'.",
        "",
        "B. INFRASTRUCTURE vs CONTENT  (infrastructure ALWAYS takes precedence)",
        f"   Infrastructure defects: <count>  — choose from: {', '.join(INFRA_DEFECT_EXAMPLES)}",
        f"   Content defects:        <count>  — choose from: {', '.join(CONTENT_DEFECT_EXAMPLES)}",
        f"   (automated tally for cross-check: infrastructure={a['infra_fails']}  "
        f"content={a['content_fails']}  empty={a['empty_count']} — reconcile any "
        "discrepancy and explain it.)",
        "",
        "C. RANKED ROOT CAUSES  (most-probable first)",
        "   1. <root cause> — subsystem / layer / confidence / evidence",
        "   2. ...",
        "",
        "D. RUN TRUSTWORTHINESS  (answer yes/no AND justify each)",
        "   - Is this run trustworthy?",
        "   - Could this run be FALSELY GREEN (infra masking real content defects)?",
        "   - Could this run be FALSELY RED (content failing only because infra is down)?",
        "   - Does infrastructure instability invalidate the quality conclusions?",
        f"   (automated verdict for cross-check: trustworthy={'YES' if a['trustworthy'] else 'NO'}.)",
        "",
        "E. RELEASE READINESS — beth-stable-v3",
        "   - Stable-tag eligible? yes/no — justify.",
        "   - If NOT eligible: list the EXACT conditions that must ALL be satisfied "
        "first, e.g.: " + "; ".join(STABLE_TAG_CONDITIONS) + ".",
        "",
        "F. AGREEMENT WITH AUTOMATED HYPOTHESES  (anti-anchoring — answer explicitly)",
        "   - Do you AGREE with the automated hypotheses above? yes/no",
        "   - If NO: provide the CORRECTED hypotheses, cite the repository evidence that "
        "contradicts the automated ones, and explain why each heuristic was wrong "
        "(repository evidence takes precedence over the automated analysis).",
    ])


def build_chatgpt_review_prompt(run, rows):
    summary, failed = _summary_block(run, rows)
    lines = [
        "You are reviewing an automated acceptance run for 'Beth', a personal "
        "Chief-of-Staff AI. Assess RELEASE READINESS. Reason at the ARCHITECTURAL "
        "level: classify failures by layer, separate INFRASTRUCTURE from CONTENT "
        "defects, and identify SYSTEMIC defect classes — not individual questions. "
        "Do NOT ask follow-up questions — everything you need is below.\n",
        f"Environment: {run.environment}   Commit: {run.git_commit}   "
        f"Suite: {run.suite_name}/{run.depth}   Time: {run.completed_at or run.created_at}\n",
        ARCHITECTURAL_INVARIANTS,
        "",
        EVIDENCE_SUPREMACY,
        "",
        summary,
        "",
        _arch_block(run, rows),
    ]
    if failed:
        lines.append(f"\nFAILED QUESTIONS ({len(failed)}):")
        for r in failed:
            crit = " [CRITICAL]" if any(
                is_critical_rule(f, r.get("spec")) for f in r["fails"]) else ""
            subs, conf = probable_subsystems(r)
            lines.append(
                f"\n- [{r['key']}] suite={r['suite']} depth={r.get('spec',{}).get('depth','')}{crit}\n"
                f"  Q: {r['question']}\n"
                f"  expected_intent={r['expected_intent'] or '-'} "
                f"actual_intent={r['intent'] or '-'} lane={r['lane'] or '-'} "
                f"openai={r['openai_called']} fallback={r['fallback_used']} time={r['ms']}ms\n"
                f"  failed_rules: {', '.join(r['fails'])}\n"
                f"  probable subsystem(s) [telemetry-derived, confidence={conf}, "
                f"VALIDATE vs evidence]: {', '.join(subs)}\n"
                f"  actual_response: {r['answer'][:500]}")
    else:
        lines.append("\nNo failed questions — every response passed its rules.")
    lines.append("\n\n" + _review_output_contract(run, rows))
    return "\n".join(lines)


def build_claude_fix_prompt(run, rows):
    failed = [r for r in rows if not r["passed"]]
    lines = [
        "This is an implementation task for Claude Code in the WLJ Django repo. Fix "
        "the failing Beth acceptance behaviors below.\n",
        f"Environment: {run.environment}   Commit: {run.git_commit}   "
        f"Suite: {run.suite_name}/{run.depth}   Grade: {run.grade}   "
        f"Score: {run.score_percent}% ({run.pass_count}/{run.total_count})   "
        f"Critical: {run.critical_count}\n",
    ]
    if not failed:
        lines.append("The run is GREEN — no fixes required. Optionally add new "
                     "acceptance questions to harden coverage.")
        return "\n".join(lines)

    lines.append("")
    lines.append(ARCHITECTURAL_INVARIANTS)
    lines.append("")
    lines.append(EVIDENCE_SUPREMACY)
    lines.append("")
    lines.append(_arch_block(run, rows))
    lines.append("\nFIX INFRASTRUCTURE DEFECTS FIRST — they take precedence and a "
                 "content failure downstream of an outage may not be real.\n")
    groups = _root_cause_groups(failed)
    lines.append("LIKELY ROOT-CAUSE GROUPS (treat each as a SYSTEMIC defect — fix the "
                 "defect class, not only the individual question):")
    for i, (label, members) in enumerate(groups, 1):
        lines.append(f"  {i}. {label}  [{', '.join(m['key'] for m in members)}]")
    if not groups:
        lines.append("  (no obvious grouping — treat each failure individually)")

    lines.append(f"\nFAILING QUESTIONS ({len(failed)}):")
    for r in failed:
        sub_list, sub_conf = probable_subsystems(r)
        lines.append(
            f"\n- [{r['key']}] suite={r['suite']}\n"
            f"  Question: {r['question']}\n"
            f"  Expected: routes to '{r['expected_intent'] or '(correct domain)'}' and "
            f"passes its rules.\n"
            f"  Actual: intent={r['intent'] or '-'} lane={r['lane'] or '-'} "
            f"openai={r['openai_called']} fallback={r['fallback_used']}.\n"
            f"  Failed rules: {', '.join(r['fails'])}\n"
            f"  Probable subsystem(s) [telemetry-derived, confidence={sub_conf}, "
            f"VALIDATE vs repository evidence]: {', '.join(sub_list)}\n"
            f"  Actual response: {r['answer'][:500]}")
    layers = " | ".join(REVIEW_LAYER_VOCAB)
    subs = " | ".join(REVIEW_SUBSYSTEMS)
    sev = " | ".join(REVIEW_SEVERITIES)
    lines.append(
        "\n\nFOR EACH defect class above, state BEFORE you change code (controlled "
        "vocabularies — fill every field):\n"
        f"  - architectural layer:  one of {{{layers}}}\n"
        f"  - probable subsystem(s): one or more of {{{subs}}}\n"
        f"  - severity:             one of {{{sev}}}\n"
        "  - root cause:           the exact mechanism (with file:line evidence)\n"
        "  - permanent regression test: ONE test (file + assertion) that catches this "
        "CLASS forever — every production defect becomes a permanent test.\n")
    lines.append(
        "VALIDATE THE AUTOMATED HYPOTHESES against repository evidence FIRST — they are "
        "telemetry heuristics and can mis-attribute a subsystem (e.g. a HEALTH failure "
        "labelled as Goals). Repository evidence takes precedence.\n"
        "IF AN AUTOMATED HYPOTHESIS IS WRONG, document the discrepancy with ALL of:\n"
        "  1. the original (automated) hypothesis\n"
        "  2. the repository evidence that contradicts it\n"
        "  3. the corrected, evidence-based root cause\n"
        "  4. why the heuristic failed\n"
        "  5. whether prompt generation should improve to prevent this misattribution\n")
    lines.append(
        "Instructions:\n"
        "- INFRASTRUCTURE defects FIRST (they take precedence; a content failure "
        "downstream of an outage may not be real).\n"
        "- Treat the grouped failures as SYSTEMIC defects: fix the defect class, not "
        "only the individual question.\n"
        "- Fix the ROOT CAUSE (routing, reasoning, fallback, profile, or evaluator).\n"
        "- Add the per-class regression tests you named above; validate ACTUAL "
        "rendered responses, not template strings.\n"
        "- PRESERVE all currently-passing behaviors (Health byte-identical; goal "
        "intent differentiation intact; routing/orchestration unchanged unless they "
        "are the proven root cause).\n"
        "- Re-run the acceptance suite (Admin Console Beth Acceptance Center, or "
        "`python manage.py beth_acceptance`) until green.\n"
        "- STABLE-TAG (beth-stable-v3) requires ALL of: " + "; ".join(STABLE_TAG_CONDITIONS)
        + ". State whether this fix gets us there and what remains.\n"
        "- Deploy to main when green.\n"
        "- Do not stop for approval unless there is a migration, security issue, or "
        "architectural conflict.")
    return "\n".join(lines)
