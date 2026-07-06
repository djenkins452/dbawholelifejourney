# ==============================================================================
# File: apps/ai/tests/test_executive_read.py
# Description: ONE executive narrative, not domain sections. The standing context used to
#   hand the LLM a flat catalog of per-domain fields (health/momentum/risks/signals/…),
#   so a broad "what would you tell me this morning?" came back as a dashboard. Beth must
#   LEAD with one composed conclusion from the one brain (interpret); everything else is
#   supporting evidence.
# ==============================================================================
from unittest import mock

from django.contrib.auth import get_user_model
from django.test import TestCase

from apps.ai.cos_intelligence import compose_executive_read

User = get_user_model()
_INTERPRET = "apps.ai.chatgpt_cos.executive_interpretation.interpret"


def _sig(**kw):
    class S:
        pass
    s = S()
    s.executive_picture = kw.get("executive_picture", "")
    s.priority_action = kw.get("priority_action", {})
    s.strategic_focus = kw.get("strategic_focus", "")
    return s


class ExecutiveReadTests(TestCase):
    def setUp(self):
        self.u = User.objects.create_user(email="er@x.com", password="x")

    def test_one_narrative_conclusion_move_arc_not_sections(self):
        sig = _sig(
            executive_picture="Recovery is today's limiting factor, so protecting energy is the highest-leverage move.",
            priority_action={"text": "finish your remaining medication", "why": "it's due tonight"},
            strategic_focus="France 2027")
        with mock.patch(_INTERPRET, return_value=sig):
            read = compose_executive_read(self.u)
        self.assertIn("Recovery is today's limiting factor", read)   # conclusion
        self.assertIn("finish your remaining medication", read)      # the move
        self.assertIn("France 2027", read)                           # the arc
        self.assertIn("north star", read.lower())
        # It is ONE narrative, not a dashboard of sections.
        for banned in ("Sleep:", "Protein:", "Calories:", "Medication:", "Relationships:",
                       "Recommendation:", "\n- ", "\n-"):
            self.assertNotIn(banned, read)

    def test_no_picture_defaults_to_disciplined_execution(self):
        sig = _sig(executive_picture="", priority_action={"text": "advance France 2027"})
        with mock.patch(_INTERPRET, return_value=sig):
            read = compose_executive_read(self.u)
        self.assertIn("executing well", read.lower())
        self.assertIn("advance France 2027", read)

    def test_degrades_to_none_on_interpret_failure(self):
        with mock.patch(_INTERPRET, side_effect=RuntimeError("boom")):
            self.assertIsNone(compose_executive_read(self.u))


class StandingPackageLeadsWithReadTests(TestCase):
    def setUp(self):
        self.u = User.objects.create_user(email="sp@x.com", password="x")

    def test_package_leads_with_executive_read_and_subordinates_domains(self):
        from apps.ai.cos_services.standing_context import _project_standing
        ctx = {"executive_read": "Today is about executing well. The one move is X.",
               "cos_intelligence": {}}
        pkg = _project_standing(self.u, ctx, source="test", build_ms=0, page_context=None)
        self.assertEqual(pkg["executive_read"], "Today is about executing well. The one move is X.")
        # trust_framing tells the narrator to LEAD with the read and treat the rest as evidence
        tf = pkg["trust_framing"].lower()
        self.assertIn("lead with `executive_read`", tf)
        self.assertIn("supporting evidence", tf)
        self.assertIn("never present the fields as separate sections", tf)
        # executive_read precedes the per-domain fields in the package order
        keys = list(pkg.keys())
        self.assertLess(keys.index("executive_read"), keys.index("health_summary"))
