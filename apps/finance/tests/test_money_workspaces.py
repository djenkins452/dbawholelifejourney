# ==============================================================================
# File: apps/finance/tests/test_money_workspaces.py
# Project: Whole Life Journey - Django 5.x Personal Wellness/Journaling App
# Description: P10 — the Finance 2.0 pages, their CRUD, and their honesty.
# Owner: Danny Jenkins (admin@wholelifejourney.com)
# ==============================================================================
"""The pages where the engines become usable, and the guarantees they carry.

The rule under every assertion: the page and the Chief of Staff read the SAME
deterministic service. Two surfaces deriving one figure separately will eventually
disagree, and the user has no way to know which to believe.
"""
from datetime import date, timedelta
from decimal import Decimal

from django.urls import reverse

from apps.finance.models import (FinancialAccount, LoanTerms, RecurringSeries,
                                 SavingsOpportunity, SpendingClassification,
                                 Transaction)
from apps.finance.tests.test_p1_economic_roles import RoleBase

START = date(2026, 1, 5)


class OverviewTests(RoleBase):
    def setUp(self):
        super().setUp()
        self._txn(-50, primary="FOOD_AND_DRINK")
        self._txn(3000, primary="INCOME")
        self.url = reverse("finance:money_overview")

    def test_the_page_renders_every_measure(self):
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 200)
        for key in ("cash_inflow", "net_spending", "debt_service",
                    "controllable_spending", "recurring_obligations"):
            self.assertContains(response, f'data-measure="{key}"')

    def test_it_states_whether_the_totals_reconcile(self):
        response = self.client.get(self.url)
        self.assertContains(response, 'data-testid="recon-ok"')

    def test_a_measure_shows_what_it_is_missing_rather_than_a_bare_zero(self):
        response = self.client.get(self.url)
        self.assertContains(response, "WLJ still needs")

    def test_the_page_and_the_assistant_read_the_same_service(self):
        from apps.finance.services.finance_calc import measures as M
        response = self.client.get(self.url)
        rendered = response.context["measures"]
        direct = M.all_measures(self.user)
        for entry in rendered:
            self.assertEqual(entry["result"].value, direct[entry["key"]].value)

    def test_the_current_context_summary_matches_the_page(self):
        from apps.finance.page_summaries_money import money_overview_summary
        from apps.finance.services.finance_calc import measures as M
        summary = money_overview_summary(self.user)
        direct = M.all_measures(self.user)
        self.assertEqual(summary["facts"]["net_spending"]["value"],
                         str(direct["net_spending"].value))

    def test_it_requires_a_signed_in_owner(self):
        self.client.logout()
        response = self.client.get(self.url)
        self.assertIn(response.status_code, (301, 302, 403))


class ReviewQueueTests(RoleBase):
    def setUp(self):
        super().setUp()
        self.held = self._txn(220, primary="GENERAL_MERCHANDISE")
        self.held.economic_role = Transaction.ROLE_UNCERTAIN
        self.held.role_reason = "ambiguous_credit"
        self.held.save()
        self.series = RecurringSeries.objects.create(
            user=self.user, name="Filmflix", payee="filmflix",
            amount_expected=Decimal("15"), occurrence_count=6,
            review_state=RecurringSeries.REVIEW_CANDIDATE)
        self.url = reverse("finance:money_review")

    def test_held_transactions_are_listed_with_a_readable_reason(self):
        response = self.client.get(self.url)
        self.assertContains(response, 'data-testid="held-row"')
        self.assertContains(response, "cannot say why")

    def test_candidates_are_listed_and_labelled_as_not_yet_counted(self):
        response = self.client.get(self.url)
        self.assertContains(response, 'data-testid="candidate-row"')
        self.assertContains(response, "until you confirm it")

    def test_resolving_a_held_row_makes_the_user_the_authority(self):
        response = self.client.post(
            reverse("finance:money_set_role", args=[self.held.pk]),
            {"economic_role": Transaction.ROLE_REIMBURSEMENT})
        self.assertEqual(response.status_code, 200)
        self.held.refresh_from_db()
        self.assertEqual(self.held.economic_role, Transaction.ROLE_REIMBURSEMENT)
        self.assertEqual(self.held.role_source, Transaction.ROLE_SOURCE_USER)

    def test_a_user_resolution_survives_reclassification(self):
        self.client.post(reverse("finance:money_set_role", args=[self.held.pk]),
                         {"economic_role": Transaction.ROLE_REIMBURSEMENT})
        from apps.finance.services.finance_calc import backfill
        backfill.run(self.user, commit=True)
        self.held.refresh_from_db()
        self.assertEqual(self.held.economic_role, Transaction.ROLE_REIMBURSEMENT)

    def test_an_unknown_role_is_refused(self):
        response = self.client.post(
            reverse("finance:money_set_role", args=[self.held.pk]),
            {"economic_role": "vibes"})
        self.assertEqual(response.status_code, 400)

    def test_confirming_a_series_makes_it_count(self):
        from apps.finance.services.finance_calc import measures as M
        self.client.post(reverse("finance:money_series_decide", args=[self.series.pk]),
                         {"decision": "confirmed", "kind": "subscription"})
        self.series.refresh_from_db()
        self.assertEqual(self.series.review_state, RecurringSeries.REVIEW_CONFIRMED)
        self.assertEqual(M.all_measures(self.user)["recurring_obligations"].value,
                         Decimal("15.00"))

    def test_ignoring_a_series_keeps_it_out(self):
        from apps.finance.services.finance_calc import measures as M
        self.client.post(reverse("finance:money_series_decide", args=[self.series.pk]),
                         {"decision": "ignored"})
        self.assertEqual(M.all_measures(self.user)["recurring_obligations"].value,
                         Decimal("0.00"))

    def test_one_user_cannot_resolve_anothers_transaction(self):
        from apps.finance.tests.test_p1_economic_roles import _usable
        from apps.users.models import User
        other = _usable(User.objects.create_user(email="w2@example.com", password="pw"))
        self.client.force_login(other)
        response = self.client.post(
            reverse("finance:money_set_role", args=[self.held.pk]),
            {"economic_role": Transaction.ROLE_REFUND})
        self.assertEqual(response.status_code, 404)
        self.held.refresh_from_db()
        self.assertEqual(self.held.economic_role, Transaction.ROLE_UNCERTAIN)


class ControlPageTests(RoleBase):
    def setUp(self):
        super().setUp()
        self.url = reverse("finance:money_control")

    def test_with_nothing_recorded_it_says_what_it_needs(self):
        response = self.client.get(self.url)
        self.assertContains(response, 'data-testid="largest-missing"')
        self.assertContains(response, "will not guess")

    def test_levers_are_offered_as_multiple_choices_not_alternatives(self):
        response = self.client.get(self.url)
        self.assertContains(response, 'name="levers" value="negotiable"')
        self.assertContains(response, 'name="levers" value="reducible"')
        self.assertContains(response, "not alternatives")

    def test_recording_a_classification_creates_it(self):
        self.client.post(reverse("finance:money_set_controllability"), {
            "payee": "Filmflix", "necessity": "discretionary",
            "variability": "fixed", "levers": ["cancellable"]})
        classification = SpendingClassification.objects.get(user=self.user)
        self.assertEqual(classification.payee, "filmflix")
        self.assertEqual(classification.levers, ["cancellable"])
        self.assertEqual(classification.source, SpendingClassification.SOURCE_USER)

    def test_recording_without_a_payee_is_refused(self):
        self.client.post(reverse("finance:money_set_controllability"),
                         {"payee": "", "levers": ["cancellable"]})
        self.assertEqual(SpendingClassification.objects.count(), 0)

    def test_a_bogus_lever_is_discarded(self):
        self.client.post(reverse("finance:money_set_controllability"),
                         {"payee": "Filmflix", "levers": ["cancellable", "teleport"]})
        self.assertEqual(SpendingClassification.objects.get(user=self.user).levers,
                         ["cancellable"])

    def test_archiving_stops_it_applying(self):
        self.client.post(reverse("finance:money_set_controllability"),
                         {"payee": "Filmflix", "levers": ["cancellable"]})
        classification = SpendingClassification.objects.get(user=self.user)
        self.client.post(reverse("finance:money_archive_controllability",
                                 args=[classification.pk]))
        classification.refresh_from_db()
        self.assertEqual(classification.status, "archived")

    def test_deciding_an_opportunity_records_the_decision(self):
        opportunity = SavingsOpportunity.objects.create(
            user=self.user, kind=SavingsOpportunity.KIND_CANCEL, title="Cancel it",
            projected_monthly_savings=Decimal("15"))
        self.client.post(
            reverse("finance:money_decide_opportunity", args=[opportunity.pk]),
            {"decision": "rejected", "reason": "I use it daily"})
        opportunity.refresh_from_db()
        self.assertEqual(opportunity.decision, SavingsOpportunity.STATUS_REJECTED)
        self.assertEqual(opportunity.decision_reason, "I use it daily")

    def test_one_user_cannot_decide_anothers_opportunity(self):
        from apps.finance.tests.test_p1_economic_roles import _usable
        from apps.users.models import User
        other = _usable(User.objects.create_user(email="w3@example.com", password="pw"))
        opportunity = SavingsOpportunity.objects.create(
            user=other, kind=SavingsOpportunity.KIND_CANCEL, title="Theirs",
            projected_monthly_savings=Decimal("15"))
        response = self.client.post(
            reverse("finance:money_decide_opportunity", args=[opportunity.pk]),
            {"decision": "rejected"})
        self.assertEqual(response.status_code, 404)


class DebtPageTests(RoleBase):
    def setUp(self):
        super().setUp()
        self.truck = FinancialAccount.objects.create(
            user=self.user, name="Truck loan", account_type="loan",
            current_balance=Decimal("-24000"))
        self.url = reverse("finance:money_debt")

    def test_missing_terms_are_shown_as_a_guided_request(self):
        response = self.client.get(self.url)
        self.assertContains(response, 'data-testid="needs-terms"')
        self.assertContains(response, "Truck loan")
        self.assertContains(response, "do not")   # "you do not need the institution"

    def test_an_unknown_apr_renders_as_unknown_never_as_zero(self):
        response = self.client.get(self.url)
        self.assertContains(response, "unknown")

    def test_with_terms_the_comparison_appears(self):
        LoanTerms.objects.create(user=self.user, account=self.truck,
                                 apr=Decimal("7.25"),
                                 minimum_payment=Decimal("450"))
        LoanTerms.objects.create(user=self.user, account=self.card,
                                 apr=Decimal("19.99"),
                                 minimum_payment=Decimal("35"))
        response = self.client.get(self.url)
        self.assertContains(response, 'data-testid="trade-off"')
        self.assertContains(response, "does not declare a winner")

    def test_an_extra_payment_changes_the_answer(self):
        LoanTerms.objects.create(user=self.user, account=self.truck,
                                 apr=Decimal("7.25"),
                                 minimum_payment=Decimal("450"))
        LoanTerms.objects.create(user=self.user, account=self.card,
                                 apr=Decimal("19.99"),
                                 minimum_payment=Decimal("35"))
        base = self.client.get(self.url).context["scenarios"]["avalanche"]["months"]
        faster = self.client.get(self.url, {"extra": "300"}) \
            .context["scenarios"]["avalanche"]["months"]
        self.assertLess(faster, base)

    def test_a_nonsense_extra_does_not_break_the_page(self):
        response = self.client.get(self.url, {"extra": "lots"})
        self.assertEqual(response.status_code, 200)

    def test_it_never_shows_another_households_debt(self):
        from apps.finance.tests.test_p1_economic_roles import _usable
        from apps.users.models import User
        other = _usable(User.objects.create_user(email="w4@example.com", password="pw"))
        FinancialAccount.objects.create(
            user=other, name="Their yacht", account_type="loan",
            current_balance=Decimal("-999999"))
        self.assertNotContains(self.client.get(self.url), "Their yacht")


class ResponsiveAndAccessibilityTests(RoleBase):
    """375px, keyboard, and labels — checked on every new page, not retrofitted."""

    PAGES = ("finance:money_overview", "finance:money_review",
             "finance:money_control", "finance:money_debt")

    def test_no_page_uses_an_inline_event_handler(self):
        """CSP with a nonce silently drops these — the control would just not work."""
        for name in self.PAGES:
            with self.subTest(page=name):
                body = self.client.get(reverse(name)).content.decode()
                for handler in ("onclick=", "onchange=", "onsubmit=", "onload="):
                    self.assertNotIn(handler, body)

    def test_inputs_are_at_least_16px_so_ios_does_not_zoom(self):
        for name in self.PAGES:
            with self.subTest(page=name):
                body = self.client.get(reverse(name)).content.decode()
                if "<input" in body or "<select" in body:
                    self.assertIn("font-size: 16px", body)

    def test_no_page_sets_a_fixed_width_that_breaks_at_375px(self):
        for name in self.PAGES:
            with self.subTest(page=name):
                body = self.client.get(reverse(name)).content.decode()
                self.assertNotIn("width: 800px", body)
                self.assertNotIn("min-width: 600px", body)

    def test_every_form_control_has_a_label(self):
        for name in self.PAGES:
            with self.subTest(page=name):
                body = self.client.get(reverse(name)).content.decode()
                selects = body.count("<select")
                labelled = body.count("<label") + body.count("aria-label")
                self.assertGreaterEqual(labelled, selects)

    def test_touch_targets_are_declared(self):
        for name in self.PAGES:
            with self.subTest(page=name):
                body = self.client.get(reverse(name)).content.decode()
                self.assertIn("min-height: 44px", body)


class DetectionTriggerTests(RoleBase):
    """Detection reads every transaction. It must never do that on a request path."""

    def test_the_page_offers_a_way_to_run_detection(self):
        response = self.client.get(reverse("finance:money_review"))
        self.assertContains(response, reverse("finance:money_detect"))
        self.assertContains(response, "does not run while you wait")

    def test_the_trigger_enqueues_and_never_computes_inline(self):
        from unittest.mock import patch
        with patch("apps.core.celery_utils.safe_enqueue", return_value=True) as enqueue:
            response = self.client.post(reverse("finance:money_detect"))
        self.assertEqual(response.status_code, 302)
        self.assertEqual(enqueue.call_count, 1)

    def test_a_degraded_queue_is_reported_not_swallowed(self):
        from unittest.mock import patch
        with patch("apps.core.celery_utils.safe_enqueue", return_value=False):
            response = self.client.post(reverse("finance:money_detect"), follow=True)
        self.assertContains(response, "could not start the search")

    def test_the_task_detects_and_proposes_without_confirming(self):
        from apps.finance.tasks import detect_recurring_and_opportunities
        for i in range(6):
            self._txn(-15, on=START + timedelta(days=30 * i), description="Filmflix",
                      primary="ENTERTAINMENT")
        detect_recurring_and_opportunities(self.user.pk)
        series = RecurringSeries.objects.get(user=self.user)
        self.assertEqual(series.review_state, RecurringSeries.REVIEW_CANDIDATE)
        self.assertEqual(SavingsOpportunity.objects.count(), 0,
                         "no lever recorded, so no opportunity may be claimed")

    def test_the_task_is_idempotent(self):
        from apps.finance.tasks import detect_recurring_and_opportunities
        for i in range(6):
            self._txn(-15, on=START + timedelta(days=30 * i), description="Filmflix",
                      primary="ENTERTAINMENT")
        detect_recurring_and_opportunities(self.user.pk)
        detect_recurring_and_opportunities(self.user.pk)
        self.assertEqual(RecurringSeries.objects.filter(user=self.user).count(), 1)

    def test_one_failing_user_does_not_stop_the_sweep(self):
        from apps.finance.tasks import detect_recurring_and_opportunities
        result = detect_recurring_and_opportunities()
        self.assertIn("users", result)
