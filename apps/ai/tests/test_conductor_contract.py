# ==============================================================================
# File: apps/ai/tests/test_conductor_contract.py
# Description: ENFORCES THE CONDUCTOR'S CONTRACT (sibling to test_request_path_safety_contract).
#   The Conductor owns orchestration ONLY — it must never grow into a reasoning engine. This
#   test fails CI if apps/ai/chatgpt_cos/conductor.py imports an intelligence / domain / truth
#   module (G1: no domain knowledge) or composes user-facing text (G2: no content generation).
#   The OWNS surface stays bounded and finite (G5). Keeping this machine-checked is what lets
#   The Conductor be the least-frequently-modified component while capabilities evolve around it.
# ==============================================================================
import ast
import os

from django.test import SimpleTestCase

_COS = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))),
                    "ai", "chatgpt_cos")
_CONDUCTOR = os.path.join(_COS, "conductor.py")
_CLASSIFIER = os.path.join(_COS, "classifier.py")
# Every file that IS The Conductor must stay orchestration-only.
_CONDUCTOR_FILES = (_CONDUCTOR, _CLASSIFIER)

# Intelligence / capability / truth / voice modules the orchestration layer may NOT import.
# If The Conductor needs any of these to make a decision, that decision belongs in a
# capability's advertisement — not in orchestration.
_FORBIDDEN = (
    "executive_interpretation", "executive_brief", "executive_evidence", "cos_briefing",
    "reasoning", "foundational_facts", "day_continuity", "naturalize", "response_coherence",
    "decision_support", "correction", "reconciliation", "accomplishment", "conversation_planner",
    "personal_assistant", "assistant_intelligence", "action_handlers", "intent_service",
    "proactive_checkins", "ai_state", "ai_insights", "ai_orchestrator", "blueprint",
    "apps.health", "apps.journal", "apps.faith", "apps.goals", "apps.finance", "apps.medical",
    "openai", "ai_service",
)


def _imports(path):
    with open(path, encoding="utf-8") as fh:
        tree = ast.parse(fh.read(), filename=path)
    names = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            names += [a.name for a in node.names]
        elif isinstance(node, ast.ImportFrom):
            names.append(node.module or "")
    return names


class ConductorPurityTests(SimpleTestCase):
    def test_conductor_imports_no_intelligence_or_domain_module(self):
        for path in _CONDUCTOR_FILES:
            imports = " ".join(_imports(path))
            for banned in _FORBIDDEN:
                self.assertNotIn(
                    banned, imports,
                    msg=(f"The Conductor ({os.path.basename(path)}) must not import "
                         f"'{banned}'. Orchestration owns WHO answers, never WHAT is "
                         "thought — move this into a capability."))

    def test_conductor_composes_no_user_facing_text(self):
        # G2: the Conductor selects and commits; it never authors an answer. No Conductor
        # file may build a user-facing 'answer'. (Cheap structural check.)
        for path in _CONDUCTOR_FILES:
            with open(path, encoding="utf-8") as fh:
                src = fh.read()
            self.assertNotIn('"answer"', src, msg=os.path.basename(path))
            self.assertNotIn("'answer'", src, msg=os.path.basename(path))

    def test_conductor_only_imports_from_safe_surface(self):
        # G5: bounded & finite — the Conductor's dependency surface stays tiny. Only the
        # standard library and low-level, domain-free helpers are allowed.
        allowed_prefixes = ("logging", "datetime", "dataclasses", "re", "apps.core.utils")
        for path in _CONDUCTOR_FILES:
            for mod in _imports(path):
                if not mod:
                    continue
                self.assertTrue(
                    any(mod == p or mod.startswith(p) for p in allowed_prefixes),
                    msg=f"Unexpected Conductor import '{mod}' in {os.path.basename(path)} "
                        "— keep the surface bounded (G5).")
