"""
Request-Path Safety Contract — architectural enforcement.

> Interactive user requests never depend on asynchronous infrastructure or
> heavy intelligence.

This test is the ENFORCEMENT for that guarantee. It is the analogue of
`test_visual_truth_contract.py` and the metric-access purity tests: it
statically (AST) scans every request-path module and FAILS CI if a new
regression is introduced — so the guarantee cannot silently rot back the way
the 2026-07-05 15–20s dashboard/task-completion regression did.

WHAT IT ENFORCES
    1. No request-path module (views*.py / signals.py / api*.py) may CALL a
       canonical-state rebuild or heavy-intelligence function
       (`BANNED_REQUEST_PATH_CALLEES`). Defer via `fire_intelligence` /
       `safe_enqueue` instead — never inline `update_user_state`,
       `run_intelligence_chain`, `build_health_state`, etc.
    2. No request-path module may construct an OpenAI client or issue an LLM
       completion INLINE, unless the module is on `INLINE_LLM_ALLOWLIST` (a
       user-invoked AI-generation endpoint the user knowingly waits for). A new
       inline LLM call forces the developer to either defer it OR add a
       reviewed, greppable allowlist entry in the same change.

WHAT IT INTENTIONALLY DOES NOT CATCH (documented residual risk)
    - LLM/heavy work reached THROUGH a service layer (e.g. a view calling
      `some_service.analyze()` that internally calls OpenAI). Static call-graph
      analysis is out of scope; those endpoints are governed by the reviewed
      `INLINE_LLM_ALLOWLIST` of intentional AI endpoints + code review.
    - The `.delay()` result-backend block is already ENFORCED at the
      configuration layer (`CELERY_TASK_IGNORE_RESULT=True` + 0.5s
      broker/result socket timeouts in config/settings.py) and cannot recur.

TO INTRODUCE A NEW INLINE AI ENDPOINT: add its module path to
`INLINE_LLM_ALLOWLIST` below (with a one-line justification) IN THE SAME CHANGE.
That entry is the audit trail — reviewers see the deliberate opt-out.
"""
from __future__ import annotations

import ast
from pathlib import Path

from django.test import SimpleTestCase

REPO_ROOT = Path(__file__).resolve().parents[3]
APPS_DIR = REPO_ROOT / "apps"

# Request-path modules: HTTP is served from these. A filename match is the
# cheap, robust proxy for "runs on the gunicorn request thread".
REQUEST_MODULE_MATCHERS = (
    lambda n: n == "views.py",
    lambda n: n.startswith("views_") and n.endswith(".py"),
    lambda n: n == "signals.py",
    lambda n: n == "api.py",
    lambda n: n == "api_views.py",
)

# Canonical-state rebuild / heavy-intelligence functions. These run hundreds of
# queries and/or the PIE insight sweep. They belong in Celery workers / the SAME
# cycle — NEVER on a request thread. (The 2026-07-05 regression was exactly
# these firing synchronously from form_valid()/signals.)
BANNED_REQUEST_PATH_CALLEES = frozenset({
    "rebuild_user_state",        # full ~600q SAE rebuild
    "update_user_state",         # single-module SAE rebuild (~69q for health)
    "run_intelligence_chain",    # SAE + run_insights synchronous core
    "run_insights",              # PIE insight sweep over all rules
    "build_health_state",        # the ~69q health SAE builder
    "compute_system_life_impact",  # ~600q cross-user analytics
    "compute_signal_health",     # ~24q signal-health analytics
})

# OpenAI LLM call surface (attribute names that terminate an LLM/embedding call).
LLM_TERMINAL_ATTRS = frozenset({"create"})
LLM_CLIENT_CTORS = frozenset({"OpenAI"})  # OpenAI(...) / openai.OpenAI(...)

# Modules ALLOWED to construct an OpenAI client / issue an LLM call inline on the
# request thread — user-invoked AI generation the user is knowingly waiting for.
# Keep this list SHORT and justified. Adding an entry is a deliberate, reviewed
# opt-out of "no hidden LLM on the request path".
INLINE_LLM_ALLOWLIST = frozenset({
    # Provider AI lookup — user clicks "AI lookup" and waits for the result.
    # Bounded by timeout=20, max_retries=1 (health/views.py:6319).
    "apps/health/views.py",
})


def _iter_request_modules():
    for path in APPS_DIR.rglob("*.py"):
        if "/tests/" in path.as_posix() or path.name.startswith("test_"):
            continue
        name = path.name
        if any(match(name) for match in REQUEST_MODULE_MATCHERS):
            yield path


def _rel(path: Path) -> str:
    return path.relative_to(REPO_ROOT).as_posix()


def _called_name(node: ast.Call) -> str | None:
    """Return the terminal callable name for a Call node (Name or Attribute)."""
    func = node.func
    if isinstance(func, ast.Name):
        return func.id
    if isinstance(func, ast.Attribute):
        return func.attr
    return None


class RequestPathSafetyContractTests(SimpleTestCase):
    """Static enforcement of the request-path safety guarantee."""

    def test_scanner_actually_scans_request_modules(self):
        """Guard against a vacuously-passing scanner (bad glob / moved tree)."""
        modules = list(_iter_request_modules())
        self.assertGreater(
            len(modules), 25,
            "Request-path scanner found too few modules — the glob is likely "
            "broken; the purity tests below would pass vacuously.",
        )

    def test_no_heavy_intelligence_on_request_path(self):
        """No view/signal/api module may CALL a canonical-state rebuild or
        heavy-intelligence function. Defer via fire_intelligence/safe_enqueue."""
        violations = []
        for path in _iter_request_modules():
            try:
                tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
            except (SyntaxError, UnicodeDecodeError):
                continue
            for node in ast.walk(tree):
                if not isinstance(node, ast.Call):
                    continue
                name = _called_name(node)
                if name in BANNED_REQUEST_PATH_CALLEES:
                    violations.append(f"{_rel(path)}:{node.lineno} → {name}()")

        self.assertEqual(
            violations, [],
            "Heavy-intelligence / canonical-state rebuild called on a request "
            "thread. Defer it (fire_intelligence / safe_enqueue), never inline:\n"
            + "\n".join(violations),
        )

    def test_no_inline_llm_on_request_path(self):
        """No view/signal module may construct an OpenAI client or issue an LLM
        completion inline, unless the module is an allowlisted, user-invoked AI
        endpoint. New inline LLM ⇒ defer it OR add a reviewed allowlist entry."""
        violations = []
        for path in _iter_request_modules():
            rel = _rel(path)
            if rel in INLINE_LLM_ALLOWLIST:
                continue
            try:
                tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
            except (SyntaxError, UnicodeDecodeError):
                continue
            for node in ast.walk(tree):
                if not isinstance(node, ast.Call):
                    continue
                func = node.func
                # OpenAI(...) or openai.OpenAI(...)
                if isinstance(func, ast.Name) and func.id in LLM_CLIENT_CTORS:
                    violations.append(f"{rel}:{node.lineno} → {func.id}() client ctor")
                elif isinstance(func, ast.Attribute) and func.attr in LLM_CLIENT_CTORS:
                    violations.append(f"{rel}:{node.lineno} → .{func.attr}() client ctor")
                # <...>.chat.completions.create / .embeddings.create /
                # .audio.speech.create / .responses.create
                elif isinstance(func, ast.Attribute) and func.attr in LLM_TERMINAL_ATTRS:
                    chain = _attr_chain(func)
                    if any(seg in chain for seg in (
                        "completions", "embeddings", "speech", "responses",
                    )):
                        violations.append(
                            f"{rel}:{node.lineno} → {'.'.join(chain)}()")

        self.assertEqual(
            violations, [],
            "Inline LLM inference on a request thread (not an allowlisted "
            "AI-generation endpoint). Defer via safe_enqueue, OR add the module "
            "to INLINE_LLM_ALLOWLIST with a justification if the user explicitly "
            "invokes AI and waits:\n" + "\n".join(violations),
        )


def _attr_chain(attr: ast.Attribute) -> list[str]:
    """Flatten an attribute access chain into its segment names."""
    segs: list[str] = []
    node: ast.expr = attr
    while isinstance(node, ast.Attribute):
        segs.append(node.attr)
        node = node.value
    if isinstance(node, ast.Name):
        segs.append(node.id)
    return list(reversed(segs))
