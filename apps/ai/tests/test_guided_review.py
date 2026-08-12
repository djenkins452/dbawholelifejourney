# Blocker #15: a GUIDED, one-at-a-time execution review must PRESERVE the question it asked,
# so the user's next short reply ("yes") binds to that item instead of being lost to the
# generic confirmation path. These tests prove the deterministic state loop (persist current
# item → survive the turn → advance → reconcile → clear) and that the salient lead surfaces it.
from datetime import timedelta

from django.contrib.auth import get_user_model
from django.test import TestCase

from apps.ai.model_interface import conversation_state as CS
from apps.ai.cos_services.guided_review import next_review_item
from apps.ai.cos_services.execution_completion import complete_execution_item
from apps.ai.models import AssistantConversation

User = get_user_model()


class GuidedReviewStateTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(email="gr@test.com", password="x")
        from apps.core.utils import get_user_today
        self.day = get_user_today(self.user) - timedelta(days=1)
        from apps.life.models import Task
        # Two incomplete, non-routine tasks due yesterday → two review items.
        self.t1 = Task.objects.create(user=self.user, title="Call the pharmacy",
                                      due_date=self.day, is_routine=False,
                                      completion_status="pending")
        self.t2 = Task.objects.create(user=self.user, title="Submit the expense report",
                                      due_date=self.day, is_routine=False,
                                      completion_status="pending")
        self.conv = AssistantConversation.objects.create(
            user=self.user, is_active=False, title="[gr-test]")

    def _lead(self):
        from apps.ai.model_interface.service import ModelInterfaceService
        svc = ModelInterfaceService(self.user)
        return svc._conversation_state_lead(svc.build_standing_context(conversation=self.conv))

    def test_no_guided_review_no_lead(self):
        # Nothing active → the salient lead must be empty (no false "awaiting answer").
        self.assertNotIn("AWAITING THE USER'S ANSWER", self._lead())

    def test_question_persists_and_survives_the_turn(self):
        r = next_review_item(self.user, self.conv, day="yesterday")
        self.assertEqual(r["status"], "question")
        title = r["item"]["title"]
        # persisted as the pending question...
        cur = (CS.read(self.conv) or {}).get("guided_review", {}).get("current", {})
        self.assertEqual(cur.get("title"), title)
        # ...and the salient lead raises it for the NEXT turn.
        self.assertIn("AWAITING THE USER'S ANSWER", self._lead())
        self.assertIn(title, self._lead())
        # end-of-turn rebuild must NOT wipe it (the exact Blocker #15 loss).
        CS.record_turn(self.conv)
        cur2 = (CS.read(self.conv) or {}).get("guided_review", {}).get("current", {})
        self.assertEqual(cur2.get("title"), title)

    def test_yes_advances_and_review_reconciles_then_clears(self):
        seen = []
        r = next_review_item(self.user, self.conv, day="yesterday")
        for _ in range(6):
            if r["status"] == "reconciled":
                break
            cur = r["item"]
            seen.append(cur["title"])
            # user answered "yes" → record that item, then advance
            comp = complete_execution_item(self.user, cur["kind"], cur["title"], day="yesterday")
            self.assertIn(comp["status"], ("recorded", "already_complete"))
            CS.record_turn(self.conv)
            r = next_review_item(self.user, self.conv, day="yesterday")
        self.assertEqual(r["status"], "reconciled")
        self.assertEqual(sorted(seen), ["Call the pharmacy", "Submit the expense report"])
        # session cleared on reconciliation — no stale pending question lingers.
        self.assertIsNone((CS.read(self.conv) or {}).get("guided_review"))

    def test_skip_does_not_re_present_the_same_item(self):
        # Answer "no" to the first (advance without completing) → the next call must present
        # the OTHER item, never loop on the skipped one.
        r1 = next_review_item(self.user, self.conv, day="yesterday")
        first = r1["item"]["title"]
        CS.record_turn(self.conv)
        r2 = next_review_item(self.user, self.conv, day="yesterday")  # no completion between
        self.assertEqual(r2["status"], "question")
        self.assertNotEqual(r2["item"]["title"], first)

    def test_stop_ends_the_review(self):
        next_review_item(self.user, self.conv, day="yesterday")
        r = next_review_item(self.user, self.conv, day="yesterday", stop=True)
        self.assertEqual(r["status"], "stopped")
        self.assertIsNone((CS.read(self.conv) or {}).get("guided_review"))
        self.assertNotIn("AWAITING THE USER'S ANSWER", self._lead())

    def test_next_review_item_is_write_gated(self):
        from apps.ai.model_interface.constitution import all_tools
        write_names = [t["function"]["name"] for t in all_tools(writes_enabled=True)]
        read_names = [t["function"]["name"] for t in all_tools(writes_enabled=False)]
        self.assertIn("next_review_item", write_names)
        self.assertNotIn("next_review_item", read_names)
