# ==============================================================================
# File: apps/finance/tests/test_debt_usability.py
# Project: Whole Life Journey - Django 5.x Personal Wellness/Journaling App
# Description: P8 — terms entry with provenance, saved scenarios, missing-debt guidance.
# Owner: Danny Jenkins (admin@wholelifejourney.com)
# ==============================================================================
"""The engine was already right. This is whether a person can drive it.

The truck loan is not in WLJ, and the page has to say how to add it WITHOUT implying
another bank connection is needed — because it is not, and believing otherwise is what
stops someone entering the one debt that would make their plan real.
"""
from datetime import date
from decimal import Decimal

from django.urls import reverse

from apps.finance.models import (FinancialAccount, LoanTerms, LoanTermsChange,
                                 PayoffScenario)
from apps.finance.tests.test_p1_economic_roles import RoleBase


class DebtBase(RoleBase):
    def setUp(self):
        super().setUp()
        self.truck = FinancialAccount.objects.create(
            user=self.user, name="Truck loan", account_type="loan",
            current_balance=Decimal("-24000"))
        self.url = reverse("finance:money_debt")


class MissingDebtGuidanceTests(DebtBase):
    def test_the_page_explains_how_to_add_a_debt_by_hand(self):
        response = self.client.get(self.url)
        self.assertContains(response, 'data-testid="add-debt-guidance"')
        self.assertContains(response, "add it by hand")

    def test_it_says_plainly_that_no_connection_is_needed(self):
        response = self.client.get(self.url)
        self.assertContains(response, "do <strong>not</strong> need to")
        self.assertContains(response, "same arithmetic as one that was imported")

    def test_it_links_to_account_creation(self):
        self.assertContains(self.client.get(self.url),
                            reverse("finance:account_create"))

    def test_the_guidance_appears_even_with_no_debts_at_all(self):
        FinancialAccount.objects.filter(
            user=self.user,
            account_type__in=FinancialAccount.LIABILITY_TYPES).delete()
        response = self.client.get(self.url)
        self.assertContains(response, 'data-testid="no-debts"')
        self.assertContains(response, 'data-testid="add-debt-guidance"')


class TermsEntryTests(DebtBase):
    def test_the_page_offers_a_form_for_each_missing_term(self):
        response = self.client.get(self.url)
        self.assertContains(response, 'data-testid="needs-terms-row"')
        self.assertContains(response, 'name="apr"')
        self.assertContains(response, 'name="minimum_payment"')

    def test_saving_terms_makes_the_debt_plannable(self):
        self.client.post(reverse("finance:money_save_terms", args=[self.truck.pk]), {
            "apr": "7.25", "minimum_payment": "450", "source": "user",
            "as_of": "2026-08-31"})
        terms = LoanTerms.objects.get(account=self.truck)
        self.assertEqual(terms.apr, Decimal("7.250"))
        self.assertEqual(terms.minimum_payment, Decimal("450"))

    def test_every_saved_term_records_where_it_came_from(self):
        self.client.post(reverse("finance:money_save_terms", args=[self.truck.pk]), {
            "apr": "7.25", "source": "statement", "as_of": "2026-03-01"})
        terms = LoanTerms.objects.get(account=self.truck)
        self.assertEqual(terms.source_of("apr"), "statement")
        self.assertEqual(terms.as_of("apr"), "2026-03-01")

    def test_each_field_keeps_its_own_freshness(self):
        self.client.post(reverse("finance:money_save_terms", args=[self.truck.pk]),
                         {"apr": "7.25", "source": "statement", "as_of": "2026-03-01"})
        self.client.post(reverse("finance:money_save_terms", args=[self.truck.pk]),
                         {"minimum_payment": "450", "source": "user",
                          "as_of": "2026-08-31"})
        terms = LoanTerms.objects.get(account=self.truck)
        self.assertEqual(terms.as_of("apr"), "2026-03-01")
        self.assertEqual(terms.as_of("minimum_payment"), "2026-08-31")

    def test_a_blank_field_stays_unknown_rather_than_becoming_zero(self):
        self.client.post(reverse("finance:money_save_terms", args=[self.truck.pk]),
                         {"apr": "", "minimum_payment": "450"})
        terms = LoanTerms.objects.get(account=self.truck)
        self.assertIsNone(terms.apr)
        self.assertIn("apr", terms.missing())

    def test_every_change_is_recorded_append_only(self):
        self.client.post(reverse("finance:money_save_terms", args=[self.truck.pk]),
                         {"apr": "7.25"})
        self.client.post(reverse("finance:money_save_terms", args=[self.truck.pk]),
                         {"apr": "6.90"})
        changes = LoanTermsChange.objects.filter(user=self.user, field="apr")
        self.assertEqual(changes.count(), 2)
        self.assertEqual(changes.order_by("created_at").last().new_value, "6.90")

    def test_an_unchanged_value_writes_no_history(self):
        self.client.post(reverse("finance:money_save_terms", args=[self.truck.pk]),
                         {"apr": "7.25"})
        self.client.post(reverse("finance:money_save_terms", args=[self.truck.pk]),
                         {"apr": "7.25"})
        self.assertEqual(LoanTermsChange.objects.filter(field="apr").count(), 1)

    def test_a_nonsense_value_is_dropped_not_stored(self):
        self.client.post(reverse("finance:money_save_terms", args=[self.truck.pk]),
                         {"apr": "seven-ish"})
        self.assertFalse(LoanTerms.objects.filter(
            account=self.truck, apr__isnull=False).exists())

    def test_one_user_cannot_set_terms_on_anothers_debt(self):
        from apps.finance.tests.test_p1_economic_roles import _usable
        from apps.users.models import User
        other = _usable(User.objects.create_user(email="d9@example.com", password="pw"))
        theirs = FinancialAccount.objects.create(
            user=other, name="Theirs", account_type="loan",
            current_balance=Decimal("-1000"))
        response = self.client.post(
            reverse("finance:money_save_terms", args=[theirs.pk]), {"apr": "1.0"})
        self.assertEqual(response.status_code, 404)
        self.assertFalse(LoanTerms.objects.filter(account=theirs).exists())

    def test_terms_immediately_change_the_comparison(self):
        LoanTerms.objects.create(user=self.user, account=self.card,
                                 apr=Decimal("19.99"),
                                 minimum_payment=Decimal("35"))
        before = self.client.get(self.url).context["comparison"]["comparable"]
        self.client.post(reverse("finance:money_save_terms", args=[self.truck.pk]),
                         {"apr": "7.25", "minimum_payment": "450"})
        after = self.client.get(self.url).context["comparison"]
        self.assertTrue(after["comparable"])
        self.assertIn("Truck loan", after["scenarios"]["avalanche"]["order"])


class ScenarioTests(DebtBase):
    def setUp(self):
        super().setUp()
        LoanTerms.objects.create(user=self.user, account=self.truck,
                                 apr=Decimal("7.25"),
                                 minimum_payment=Decimal("450"))
        LoanTerms.objects.create(user=self.user, account=self.card,
                                 apr=Decimal("19.99"),
                                 minimum_payment=Decimal("35"))

    def _save(self, name="Avalanche plus 300", **kw):
        payload = {"name": name, "strategy": "avalanche", "extra_monthly": "300"}
        payload.update(kw)
        return self.client.post(reverse("finance:money_save_scenario"), payload)

    def test_a_scenario_can_be_saved_as_a_draft(self):
        self._save()
        plan = PayoffScenario.objects.get(user=self.user)
        self.assertEqual(plan.plan_state, PayoffScenario.STATE_DRAFT)
        self.assertEqual(plan.extra_monthly, Decimal("300"))

    def test_it_snapshots_what_the_engine_said_at_the_time(self):
        self._save()
        plan = PayoffScenario.objects.get(user=self.user)
        self.assertIn("months", plan.projected)
        self.assertIn("order", plan.projected)
        self.assertEqual(plan.calculation_version, "1.0.0")

    def test_a_nameless_scenario_is_refused(self):
        self._save(name="")
        self.assertEqual(PayoffScenario.objects.count(), 0)

    def test_an_unknown_strategy_falls_back_rather_than_breaking(self):
        self._save(strategy="vibes")
        self.assertEqual(PayoffScenario.objects.get().strategy, "avalanche")

    def test_only_one_plan_can_be_the_one_being_followed(self):
        self._save(name="First")
        self._save(name="Second")
        plans = {p.name: p for p in PayoffScenario.objects.filter(user=self.user)}
        self.client.post(reverse("finance:money_scenario_state",
                                 args=[plans["First"].pk]), {"action": "active_plan"})
        self.client.post(reverse("finance:money_scenario_state",
                                 args=[plans["Second"].pk]), {"action": "active_plan"})
        live = PayoffScenario.objects.filter(
            user=self.user, status="active",
            plan_state=PayoffScenario.STATE_ACTIVE)
        self.assertEqual(live.count(), 1)
        self.assertEqual(live.first().name, "Second")

    def test_activating_records_when(self):
        self._save()
        plan = PayoffScenario.objects.get(user=self.user)
        self.client.post(reverse("finance:money_scenario_state", args=[plan.pk]),
                         {"action": "active_plan"})
        plan.refresh_from_db()
        self.assertIsNotNone(plan.activated_on)

    def test_a_plan_can_be_paused_and_archived(self):
        self._save()
        plan = PayoffScenario.objects.get(user=self.user)
        self.client.post(reverse("finance:money_scenario_state", args=[plan.pk]),
                         {"action": "paused"})
        plan.refresh_from_db()
        self.assertEqual(plan.plan_state, PayoffScenario.STATE_PAUSED)
        self.client.post(reverse("finance:money_scenario_state", args=[plan.pk]),
                         {"action": "delete"})
        plan.refresh_from_db()
        self.assertEqual(plan.status, "archived")

    def test_the_page_lists_saved_plans(self):
        self._save()
        response = self.client.get(self.url)
        self.assertContains(response, 'data-testid="saved-scenario"')
        self.assertContains(response, "Avalanche plus 300")

    def test_the_page_says_wlj_never_pays(self):
        response = self.client.get(self.url)
        self.assertContains(response, "never makes a payment")

    def test_one_user_cannot_change_anothers_plan(self):
        from apps.finance.tests.test_p1_economic_roles import _usable
        from apps.users.models import User
        other = _usable(User.objects.create_user(email="s9@example.com", password="pw"))
        plan = PayoffScenario.objects.create(user=other, name="Theirs")
        response = self.client.post(
            reverse("finance:money_scenario_state", args=[plan.pk]),
            {"action": "active_plan"})
        self.assertEqual(response.status_code, 404)

    def test_no_scenarios_says_what_to_do(self):
        response = self.client.get(self.url)
        self.assertContains(response, 'data-testid="no-scenarios"')
