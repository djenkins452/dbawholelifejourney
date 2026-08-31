# ==============================================================================
# File: apps/finance/tests/test_review_queue.py
# Project: Whole Life Journey - Django 5.x Personal Wellness/Journaling App
# Description: Grouped review, previewed bulk decisions, and undo.
# Owner: Danny Jenkins (admin@wholelifejourney.com)
# ==============================================================================
"""Confirming forty rows at once is a large act, and a mistake is now forty mistakes.

The tests that matter are the refusals and the reversals: a set that changed since the
preview, a decision the user already made, a row edited after the batch, another
household's transactions.
"""
from datetime import date, timedelta
from decimal import Decimal

from apps.finance.models import ReviewBatch, SpendingClassification, Transaction
from apps.finance.services.finance_calc import review_queue as RQ
from apps.finance.tests.test_p1_economic_roles import RoleBase

JAN = date(2026, 1, 15)


class ReviewBase(RoleBase):
    def _held(self, amount, *, reason="ambiguous_credit", description="Filmflix",
              on=JAN, account=None):
        txn = self._txn(amount, on=on, description=description,
                        account=account, primary="GENERAL_MERCHANDISE")
        txn.economic_role = Transaction.ROLE_UNCERTAIN
        txn.role_reason = reason
        txn.role_source = Transaction.ROLE_SOURCE_DERIVED
        txn.role_confidence = Transaction.ROLE_CONFIDENCE_LOW
        txn.save()
        return txn


class GroupingTests(ReviewBase):
    def test_rows_that_look_alike_become_one_decision(self):
        for i in range(5):
            self._held(120, on=JAN + timedelta(days=30 * i))
        groups = RQ.build_groups(self.user)
        self.assertEqual(len(groups), 1)
        self.assertEqual(groups[0]["count"], 5)

    def test_different_reasons_stay_separate_questions(self):
        self._held(120, reason="ambiguous_credit")
        self._held(-120, reason="unmatched_transfer_candidate")
        self.assertEqual(len(RQ.build_groups(self.user)), 2)

    def test_a_credit_and_a_debit_are_different_questions(self):
        self._held(120)
        self._held(-120)
        self.assertEqual(len(RQ.build_groups(self.user)), 2)

    def test_each_group_explains_why_it_was_held(self):
        self._held(120, reason="unmatched_liability_credit")
        group = RQ.build_groups(self.user)[0]
        self.assertIn("payment, or borrowing", group["reason_label"])
        self.assertIn("landed on a credit card", group["explain"])

    def test_each_group_names_the_measures_it_would_move(self):
        self._held(-500, reason="unmatched_transfer_candidate")
        group = RQ.build_groups(self.user)[0]
        self.assertIn("net_spending", group["affects"])

    def test_a_group_of_one_is_never_high_confidence(self):
        self._held(120)
        self.assertEqual(RQ.build_groups(self.user)[0]["confidence"], "low")

    def test_a_consistent_group_earns_high_confidence(self):
        for i in range(4):
            self._held(120, on=JAN + timedelta(days=30 * i))
        self.assertEqual(RQ.build_groups(self.user)[0]["confidence"], "high")

    def test_mixed_accounts_lower_the_confidence(self):
        self._held(120)
        self._held(120, account=self.savings)
        self.assertEqual(RQ.build_groups(self.user)[0]["confidence"], "low")

    def test_groups_are_ranked_by_what_they_move(self):
        self._held(50, description="Small")
        self._held(-5000, description="Large", reason="unmatched_transfer_candidate")
        self.assertEqual(RQ.build_groups(self.user)[0]["payee"], "large")

    def test_a_decision_the_user_already_made_is_never_regrouped(self):
        txn = self._held(120)
        txn.role_source = Transaction.ROLE_SOURCE_USER
        txn.save()
        self.assertEqual(RQ.build_groups(self.user), [])

    def test_the_short_list_gives_value_without_reviewing_everything(self):
        for i in range(3):
            self._held(500, description=f"Payee{i}")
        for i in range(20):
            self._held(5, description=f"Tiny{i}")
        short = RQ.highest_impact(self.user, limit=3)
        self.assertEqual(len(short["groups"]), 3)
        self.assertEqual(short["covers"], 3)
        self.assertGreater(short["remaining_groups"], 0)

    def test_a_group_carries_its_evidence(self):
        self._held(120, on=JAN)
        self._held(120, on=JAN + timedelta(days=60))
        evidence = RQ.build_groups(self.user)[0]["evidence"]
        self.assertEqual(evidence["first_seen"], str(JAN))
        self.assertEqual(evidence["distinct_accounts"], 1)


class PreviewTests(ReviewBase):
    def test_preview_counts_and_totals_before_anything_happens(self):
        rows = [self._held(120), self._held(80)]
        result = RQ.preview(self.user, [t.pk for t in rows], "reimbursement")
        self.assertEqual(result["eligible_count"], 2)
        self.assertEqual(result["total_amount"], Decimal("200.00"))
        self.assertEqual(Transaction.objects.filter(
            role_source=Transaction.ROLE_SOURCE_USER).count(), 0)

    def test_preview_separates_inflow_from_outflow(self):
        self._held(120)
        self._held(-80, reason="unmatched_transfer_candidate")
        ids = list(Transaction.objects.values_list("pk", flat=True))
        result = RQ.preview(self.user, ids, "internal_transfer")
        self.assertEqual(result["inflow"], Decimal("120.00"))
        self.assertEqual(result["outflow"], Decimal("80.00"))

    def test_preview_refuses_rows_that_are_not_eligible(self):
        held = self._held(120)
        decided = self._held(80)
        decided.role_source = Transaction.ROLE_SOURCE_USER
        decided.save()
        result = RQ.preview(self.user, [held.pk, decided.pk], "reimbursement")
        self.assertEqual(result["eligible_count"], 1)
        self.assertEqual(result["refused_count"], 1)

    def test_preview_never_reaches_another_household(self):
        from apps.finance.tests.test_p1_economic_roles import _usable
        from apps.users.models import User
        other = _usable(User.objects.create_user(email="rq@example.com", password="pw"))
        theirs = Transaction.objects.create(
            user=other, account=self.checking, date=JAN, amount=Decimal("500"),
            description="theirs", economic_role=Transaction.ROLE_UNCERTAIN)
        mine = self._held(120)
        result = RQ.preview(self.user, [mine.pk, theirs.pk], "reimbursement")
        self.assertEqual(result["eligible_ids"], [mine.pk])


class ApplyTests(ReviewBase):
    def _apply(self, ids, decision, **kw):
        preview = RQ.preview(self.user, ids, decision)
        return RQ.apply_bulk(self.user, ids, decision,
                             token=preview["token"], **kw)

    def test_a_previewed_batch_applies(self):
        rows = [self._held(120), self._held(80)]
        result = self._apply([t.pk for t in rows], "reimbursement")
        self.assertEqual(result["applied"], 2)
        for txn in rows:
            txn.refresh_from_db()
            self.assertEqual(txn.economic_role, Transaction.ROLE_REIMBURSEMENT)
            self.assertEqual(txn.role_source, Transaction.ROLE_SOURCE_USER)

    def test_a_stale_token_is_refused_outright(self):
        rows = [self._held(120), self._held(80)]
        ids = [t.pk for t in rows]
        stale = RQ.preview(self.user, ids, "reimbursement")["token"]
        extra = self._held(60)
        result = RQ.apply_bulk(self.user, ids + [extra.pk], "reimbursement",
                               token=stale)
        self.assertTrue(result["refused"])
        self.assertIn("changed since you previewed", result["reason"])
        extra.refresh_from_db()
        self.assertEqual(extra.economic_role, Transaction.ROLE_UNCERTAIN)

    def test_an_unknown_decision_is_rejected(self):
        row = self._held(120)
        with self.assertRaises(ValueError):
            RQ.apply_bulk(self.user, [row.pk], "vibes", token="x")

    def test_leaving_it_uncertain_is_a_recorded_decision(self):
        row = self._held(120)
        self._apply([row.pk], RQ.DECISION_LEAVE)
        row.refresh_from_db()
        self.assertEqual(row.economic_role, Transaction.ROLE_UNCERTAIN)
        self.assertTrue(row.role_reason.endswith(":reviewed"))

    def test_the_batch_records_what_each_row_used_to_say(self):
        rows = [self._held(120), self._held(80)]
        self._apply([t.pk for t in rows], "reimbursement")
        batch = ReviewBatch.objects.get()
        self.assertEqual(batch.row_count, 2)
        self.assertEqual(batch.previous_state[0]["role"], Transaction.ROLE_UNCERTAIN)

    def test_a_rule_can_be_created_from_one_payee(self):
        rows = [self._held(120), self._held(80)]
        result = self._apply([t.pk for t in rows], "reimbursement", create_rule=True)
        self.assertIsNotNone(result["rule_created"])
        self.assertEqual(SpendingClassification.objects.get().payee, "filmflix")

    def test_no_rule_is_invented_across_different_payees(self):
        rows = [self._held(120, description="Alpha"),
                self._held(80, description="Beta")]
        result = self._apply([t.pk for t in rows], "reimbursement", create_rule=True)
        self.assertIsNone(result["rule_created"])
        self.assertEqual(SpendingClassification.objects.count(), 0)

    def test_a_bulk_action_cannot_touch_another_household(self):
        from apps.finance.tests.test_p1_economic_roles import _usable
        from apps.users.models import User
        other = _usable(User.objects.create_user(email="rq2@example.com", password="pw"))
        theirs = Transaction.objects.create(
            user=other, account=self.checking, date=JAN, amount=Decimal("500"),
            description="theirs", economic_role=Transaction.ROLE_UNCERTAIN)
        mine = self._held(120)
        self._apply([mine.pk, theirs.pk], "reimbursement")
        theirs.refresh_from_db()
        self.assertEqual(theirs.economic_role, Transaction.ROLE_UNCERTAIN)


class UndoTests(ReviewBase):
    def setUp(self):
        super().setUp()
        self.rows = [self._held(120), self._held(80)]
        ids = [t.pk for t in self.rows]
        preview = RQ.preview(self.user, ids, "reimbursement")
        RQ.apply_bulk(self.user, ids, "reimbursement", token=preview["token"])
        self.batch = ReviewBatch.objects.get()

    def test_undo_puts_the_rows_back(self):
        result = RQ.undo(self.user, self.batch.pk)
        self.assertEqual(result["restored"], 2)
        for txn in self.rows:
            txn.refresh_from_db()
            self.assertEqual(txn.economic_role, Transaction.ROLE_UNCERTAIN)
            self.assertEqual(txn.role_source, Transaction.ROLE_SOURCE_DERIVED)

    def test_undoing_twice_is_refused(self):
        RQ.undo(self.user, self.batch.pk)
        self.assertTrue(RQ.undo(self.user, self.batch.pk)["refused"])

    def test_a_row_edited_since_the_batch_is_left_alone(self):
        """Their later decision outranks the undo log."""
        edited = self.rows[0]
        edited.economic_role = Transaction.ROLE_REFUND
        edited.role_reason = "user_confirmed_role"
        edited.save()
        result = RQ.undo(self.user, self.batch.pk)
        self.assertEqual(result["restored"], 1)
        self.assertEqual(result["skipped_edited_since"], 1)
        edited.refresh_from_db()
        self.assertEqual(edited.economic_role, Transaction.ROLE_REFUND)

    def test_one_user_cannot_undo_anothers_batch(self):
        from apps.finance.tests.test_p1_economic_roles import _usable
        from apps.users.models import User
        other = _usable(User.objects.create_user(email="rq3@example.com", password="pw"))
        self.assertTrue(RQ.undo(other, self.batch.pk)["refused"])
        self.rows[0].refresh_from_db()
        self.assertEqual(self.rows[0].economic_role, Transaction.ROLE_REIMBURSEMENT)

    def test_a_batch_marks_itself_undone(self):
        RQ.undo(self.user, self.batch.pk)
        self.batch.refresh_from_db()
        self.assertEqual(self.batch.batch_status, ReviewBatch.STATUS_UNDONE)
        self.assertFalse(self.batch.can_undo)


class ReviewPageTests(ReviewBase):
    """The service is only useful if the page actually offers the decisions."""

    def setUp(self):
        super().setUp()
        from django.urls import reverse
        for i in range(4):
            self._held(120, on=JAN + timedelta(days=30 * i))
        self.url = reverse("finance:money_review")

    def test_the_page_renders_groups_not_a_flat_list(self):
        response = self.client.get(self.url)
        self.assertContains(response, 'data-testid="review-group"')
        self.assertContains(response, "Apply to all 4")

    def test_it_offers_a_starting_point(self):
        response = self.client.get(self.url)
        self.assertContains(response, 'data-testid="shortlist"')
        self.assertContains(response, "do not have to work through everything")

    def test_each_group_shows_the_evidence_behind_it(self):
        response = self.client.get(self.url)
        self.assertContains(response, "Confidence these belong together")
        self.assertContains(response, "Deciding changes")

    def test_the_group_carries_a_token_binding_its_rows(self):
        group = self.client.get(self.url).context["groups"][0]
        self.assertEqual(group["token"], RQ.selection_token(group["ids"]))

    def test_preview_reports_impact_without_applying(self):
        from django.urls import reverse
        ids = list(Transaction.objects.values_list("pk", flat=True))
        response = self.client.post(reverse("finance:money_preview_bulk"),
                                    {"ids": [str(i) for i in ids],
                                     "decision": "reimbursement"})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["eligible_count"], 4)
        self.assertEqual(Transaction.objects.filter(
            role_source=Transaction.ROLE_SOURCE_USER).count(), 0)

    def test_applying_from_the_page_works_end_to_end(self):
        from django.urls import reverse
        group = self.client.get(self.url).context["groups"][0]
        self.client.post(reverse("finance:money_apply_bulk"), {
            "ids": ",".join(str(i) for i in group["ids"]),
            "token": group["token"], "decision": "reimbursement"})
        self.assertEqual(Transaction.objects.filter(
            economic_role=Transaction.ROLE_REIMBURSEMENT).count(), 4)

    def test_a_tampered_token_changes_nothing(self):
        from django.urls import reverse
        group = self.client.get(self.url).context["groups"][0]
        response = self.client.post(reverse("finance:money_apply_bulk"), {
            "ids": ",".join(str(i) for i in group["ids"]),
            "token": "0" * 32, "decision": "reimbursement"}, follow=True)
        self.assertContains(response, "Nothing was changed")
        self.assertEqual(Transaction.objects.filter(
            role_source=Transaction.ROLE_SOURCE_USER).count(), 0)

    def test_the_page_offers_undo_after_a_batch(self):
        from django.urls import reverse
        group = self.client.get(self.url).context["groups"][0]
        self.client.post(reverse("finance:money_apply_bulk"), {
            "ids": ",".join(str(i) for i in group["ids"]),
            "token": group["token"], "decision": "reimbursement"})
        response = self.client.get(self.url)
        self.assertContains(response, 'data-testid="batch-row"')
        self.assertContains(response, "Undo")

    def test_undo_from_the_page_restores_the_rows(self):
        from django.urls import reverse
        group = self.client.get(self.url).context["groups"][0]
        self.client.post(reverse("finance:money_apply_bulk"), {
            "ids": ",".join(str(i) for i in group["ids"]),
            "token": group["token"], "decision": "reimbursement"})
        batch = ReviewBatch.objects.get()
        self.client.post(reverse("finance:money_undo_bulk", args=[batch.pk]))
        self.assertEqual(Transaction.objects.filter(
            economic_role=Transaction.ROLE_UNCERTAIN).count(), 4)

    def test_a_malformed_id_is_dropped_not_guessed(self):
        from django.urls import reverse
        response = self.client.post(reverse("finance:money_preview_bulk"),
                                    {"ids": ["not-a-number"],
                                     "decision": "reimbursement"})
        self.assertEqual(response.status_code, 400)

    def test_an_empty_queue_says_so_plainly(self):
        Transaction.objects.all().delete()
        response = self.client.get(self.url)
        self.assertContains(response, 'data-testid="no-groups"')

    def test_the_page_uses_no_inline_handlers(self):
        body = self.client.get(self.url).content.decode()
        for handler in ("onclick=", "onchange=", "onsubmit="):
            self.assertNotIn(handler, body)
