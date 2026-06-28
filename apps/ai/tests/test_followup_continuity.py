# ==============================================================================
# File: apps/ai/tests/test_followup_continuity.py
# Description: Defect Class 3 (Conversation Continuity). A follow-up like "Why do you
#   say that?" references Beth's PRIOR answer, not the world — it must NOT be claimed
#   by the SANDBOXED general lane (which gets no history). It must fall through to the
#   history-aware tool loop so continuity survives. Origin: real Beth conversation.
# ==============================================================================
from django.test import SimpleTestCase

from apps.ai.chatgpt_cos.lanes import _looks_general, general_answer


class FollowUpContinuityTests(SimpleTestCase):
    def test_meta_followups_are_not_sandboxed_general(self):
        for q in ("Why do you say that?", "What do you mean?", "How do you know?",
                  "What makes you say that?", "Based on what?", "Says who?"):
            self.assertFalse(_looks_general(q), q)         # not stolen by the sandbox
            self.assertIsNone(general_answer(None, q), q)  # general lane declines

    def test_genuine_general_knowledge_still_routes_general(self):
        # The fix must not over-reach: real general-knowledge questions stay general.
        for q in ("What is the capital of France?", "Who was Abraham Lincoln?",
                  "Explain photosynthesis."):
            self.assertTrue(_looks_general(q), q)
