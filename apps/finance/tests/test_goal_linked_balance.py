# ==============================================================================
# File: apps/finance/tests/test_goal_linked_balance.py
# Project: Whole Life Journey - Django 5.x Personal Wellness/Journaling App
# Description: A linked goal's progress comes from its account, live.
# Owner: Danny Jenkins (admin@wholelifejourney.com)
# ==============================================================================
"""An Emergency Fund linked to a $5,001.11 savings account showed $0.00 and 0%.

`sync_from_account()` existed but nothing ever called it — and calling it would have
been the wrong fix, because it COPIED the balance into `current_amount`, creating a
second number that goes stale the moment the balance moves. The goal now derives its
current value from the account at the moment of the question, so every surface agrees
by construction rather than by remembering to re-sync.

The ongoing-minimum-balance behaviour is the other half: an emergency fund that dips
below its target must say so again by itself, so completion is never latched.
"""
from datetime import date
from decimal import Decimal

from django.conf import settings
from django.core.exceptions import ValidationError
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from apps.finance.models import (FinanceAuditLog, FinancialAccount, FinancialGoal)
from apps.users.models import TermsAcceptance, User

TARGET = Decimal("1000.00")
BALANCE = Decimal("5001.11")


def _usable(user):
    TermsAcceptance.objects.get_or_create(
        user=user,
        defaults={"terms_version": settings.WLJ_SETTINGS.get("TERMS_VERSION", "1.0")})
    prefs = user.preferences
    prefs.has_completed_onboarding = True
    prefs.finances_enabled = True
    prefs.save()
    return user


class GoalBase(TestCase):
    def setUp(self):
        self.user = _usable(User.objects.create_user(
            email="goals@example.com", password="pw"))
        self.savings = FinancialAccount.objects.create(
            user=self.user, name="Savings ...4255", account_type="savings",
            current_balance=BALANCE, balance_updated_at=timezone.now())
        self.goal = FinancialGoal.objects.create(
            user=self.user, name="Emergency Fund", goal_type="savings",
            target_amount=TARGET, current_amount=Decimal("0.00"),
            linked_account=self.savings)
        self.client.force_login(self.user)


class LinkedGoalTests(GoalBase):
    """The production case, reproduced."""

    def test_current_value_is_the_account_balance(self):
        self.assertEqual(self.goal.current_value, BALANCE)

    def test_the_unused_manual_field_is_not_what_is_shown(self):
        self.assertEqual(self.goal.current_amount, Decimal("0.00"))
        self.assertNotEqual(self.goal.current_value, self.goal.current_amount)

    def test_progress_is_capped_at_100_for_the_visual(self):
        self.assertEqual(self.goal.progress_percentage, 100)

    def test_the_cap_does_not_hide_the_real_balance(self):
        self.assertEqual(self.goal.current_value, BALANCE)
        self.assertGreater(self.goal.current_value, self.goal.target_amount)

    def test_remaining_is_never_negative(self):
        self.assertEqual(self.goal.remaining_amount, Decimal("0.00"))

    def test_the_goal_reads_as_funded(self):
        self.assertTrue(self.goal.is_completed)

    def test_the_source_account_and_freshness_are_reportable(self):
        self.assertEqual(self.goal.balance_source_name, "Savings ...4255")
        self.assertIsNotNone(self.goal.balance_as_of)

    def test_nothing_is_copied_into_the_stored_field(self):
        """Deriving must not quietly write a competing number."""
        _ = (self.goal.current_value, self.goal.progress_percentage,
             self.goal.remaining_amount, self.goal.is_completed)
        self.goal.refresh_from_db()
        self.assertEqual(self.goal.current_amount, Decimal("0.00"))

    def test_the_copying_helper_is_gone(self):
        self.assertFalse(hasattr(FinancialGoal, "sync_from_account"),
                         "a stored copy is stale the moment the balance moves")


class BalanceTransitionTests(GoalBase):
    """An ongoing minimum-balance goal is never permanently complete."""

    def _set_balance(self, amount):
        self.savings.current_balance = Decimal(amount)
        self.savings.balance_updated_at = timezone.now()
        self.savings.save(update_fields=["current_balance", "balance_updated_at"])
        self.goal.refresh_from_db()

    def test_dropping_below_target_makes_it_underfunded_again(self):
        self.assertTrue(self.goal.is_completed)
        self._set_balance("250.00")
        self.assertFalse(self.goal.is_completed)
        self.assertEqual(self.goal.current_value, Decimal("250.00"))
        self.assertEqual(self.goal.remaining_amount, Decimal("750.00"))
        self.assertEqual(self.goal.progress_percentage, 25)

    def test_recovering_makes_it_funded_again_with_no_intervention(self):
        self._set_balance("250.00")
        self.assertFalse(self.goal.is_completed)
        self._set_balance("1000.00")
        self.assertTrue(self.goal.is_completed)

    def test_exactly_on_target_counts_as_funded(self):
        self._set_balance("1000.00")
        self.assertTrue(self.goal.is_completed)
        self.assertEqual(self.goal.remaining_amount, Decimal("0.00"))

    def test_a_stale_completed_status_cannot_latch_a_linked_goal(self):
        """The bug this prevents: 'completed' outliving the balance that earned it."""
        self.goal.goal_status = FinancialGoal.STATUS_COMPLETED
        self.goal.save(update_fields=["goal_status"])
        self._set_balance("10.00")
        self.assertFalse(self.goal.is_completed,
                         "an emergency fund below target is not complete")

    def test_a_zero_balance_reads_as_zero_not_as_the_manual_field(self):
        self.goal.current_amount = Decimal("999.00")
        self.goal.save(update_fields=["current_amount"])
        self._set_balance("0.00")
        self.assertEqual(self.goal.current_value, Decimal("0.00"))
        self.assertFalse(self.goal.is_completed)


class UnlinkedGoalTests(TestCase):
    """Manual goals keep working exactly as they did."""

    def setUp(self):
        self.user = _usable(User.objects.create_user(
            email="manual@example.com", password="pw"))
        self.goal = FinancialGoal.objects.create(
            user=self.user, name="New Laptop", goal_type="purchase",
            target_amount=Decimal("2000.00"), current_amount=Decimal("500.00"))
        self.client.force_login(self.user)

    def test_manual_value_is_used(self):
        self.assertFalse(self.goal.is_account_funded)
        self.assertEqual(self.goal.current_value, Decimal("500.00"))
        self.assertEqual(self.goal.progress_percentage, 25)
        self.assertEqual(self.goal.remaining_amount, Decimal("1500.00"))

    def test_manual_progress_still_accepted(self):
        response = self.client.post(
            reverse("finance:goal_progress", args=[self.goal.pk]),
            data={"current_amount": "750.00"})
        self.assertEqual(response.status_code, 302)
        self.goal.refresh_from_db()
        self.assertEqual(self.goal.current_value, Decimal("750.00"))

    def test_an_explicit_completion_still_latches_for_a_manual_goal(self):
        self.goal.goal_status = FinancialGoal.STATUS_COMPLETED
        self.goal.save(update_fields=["goal_status"])
        self.assertTrue(self.goal.is_completed)

    def test_the_manual_form_is_offered(self):
        response = self.client.get(
            reverse("finance:goal_detail", args=[self.goal.pk]))
        self.assertContains(response, "Update Progress")

    def test_debt_payoff_stays_manual_even_when_linked(self):
        """No starting balance is recorded, so deriving it would be a guess."""
        card = FinancialAccount.objects.create(
            user=self.user, name="Card", account_type="credit_card",
            current_balance=Decimal("-400.00"))
        debt = FinancialGoal.objects.create(
            user=self.user, name="Pay off card", goal_type="debt_payoff",
            target_amount=Decimal("1000.00"), current_amount=Decimal("600.00"),
            linked_account=card)
        self.assertFalse(debt.is_account_funded)
        self.assertEqual(debt.current_value, Decimal("600.00"))


class ManualEntryDisabledTests(GoalBase):
    """A hidden field is not a closed door — the server refuses too."""

    def test_the_manual_form_is_not_rendered_for_a_linked_goal(self):
        response = self.client.get(
            reverse("finance:goal_detail", args=[self.goal.pk]))
        self.assertNotContains(response, "Update Progress")

    def test_the_source_and_freshness_are_shown_instead(self):
        response = self.client.get(
            reverse("finance:goal_detail", args=[self.goal.pk]))
        self.assertContains(response, "goal-balance-source")
        self.assertContains(response, "Savings ...4255")

    def test_posting_manual_progress_is_refused(self):
        self.client.post(reverse("finance:goal_progress", args=[self.goal.pk]),
                         data={"current_amount": "42.00"})
        self.goal.refresh_from_db()
        self.assertEqual(self.goal.current_amount, Decimal("0.00"))
        self.assertEqual(self.goal.current_value, BALANCE)

    def test_the_model_refuses_a_programmatic_update_too(self):
        with self.assertRaises(ValidationError):
            self.goal.update_progress(Decimal("10.00"))


class SurfaceConsistencyTests(GoalBase):
    """Detail, dashboard, list, summary and CoS must not disagree."""

    def test_goal_detail_shows_the_real_balance_and_full_progress(self):
        response = self.client.get(
            reverse("finance:goal_detail", args=[self.goal.pk]))
        body = response.content.decode()
        self.assertIn("5,001.11", body)
        self.assertIn("100%", body)

    def test_goal_list_agrees_with_detail(self):
        response = self.client.get(reverse("finance:goal_list"))
        self.assertIn("5,001", response.content.decode())

    def test_dashboard_agrees_with_detail(self):
        response = self.client.get(reverse("finance:dashboard"))
        self.assertIn("5,001", response.content.decode())

    def test_cos_domain_truth_reports_the_derived_value(self):
        from apps.finance.services.finance_domain_truth import FinanceDomainTruth

        entities = FinanceDomainTruth(self.user)._describe_goals()
        goal = next(e for e in entities if e.identity == "Emergency Fund")
        self.assertEqual(goal.standing["current_amount"], float(BALANCE))
        self.assertEqual(goal.standing["remaining_amount"], 0.0)
        self.assertTrue(goal.standing["meeting_target"])
        self.assertEqual(goal.standing["balance_source"], "Savings ...4255")

    def test_cos_state_builder_reports_the_derived_value(self):
        from apps.core.ai_state import state_builder

        import inspect
        source = inspect.getsource(state_builder)
        self.assertIn("g.current_value", source)
        self.assertNotIn("float(g.current_amount or 0)", source)


class AuthorizationTests(GoalBase):
    def test_another_user_cannot_see_this_goal_or_its_balance(self):
        intruder = _usable(User.objects.create_user(
            email="intruder@example.com", password="pw"))
        self.client.force_login(intruder)
        response = self.client.get(
            reverse("finance:goal_detail", args=[self.goal.pk]))
        self.assertEqual(response.status_code, 404)

    def test_another_user_cannot_post_progress_to_this_goal(self):
        intruder = _usable(User.objects.create_user(
            email="intruder2@example.com", password="pw"))
        self.client.force_login(intruder)
        response = self.client.post(
            reverse("finance:goal_progress", args=[self.goal.pk]),
            data={"current_amount": "1.00"})
        self.assertEqual(response.status_code, 404)

    def test_a_goal_cannot_be_linked_to_another_users_account(self):
        from apps.finance.forms import FinancialGoalForm

        other = _usable(User.objects.create_user(
            email="stranger@example.com", password="pw"))
        their_account = FinancialAccount.objects.create(
            user=other, name="Their Savings", account_type="savings",
            current_balance=Decimal("99999.00"))

        form = FinancialGoalForm(self.user, data={
            "name": "Sneaky", "goal_type": "savings", "target_amount": "100.00",
            "linked_account": their_account.pk, "color": "#10b981", "icon": "💰"})
        self.assertFalse(form.is_valid())
        self.assertIn("linked_account", form.errors)


class LinkAuditTests(GoalBase):
    """Audit the DECISION, not every balance read."""

    def test_changing_the_linked_account_is_audited(self):
        other = FinancialAccount.objects.create(
            user=self.user, name="Other Savings", account_type="savings",
            current_balance=Decimal("10.00"))
        self.client.post(
            reverse("finance:goal_update", args=[self.goal.pk]),
            data={"name": "Emergency Fund", "goal_type": "savings",
                  "target_amount": "1000.00", "linked_account": other.pk,
                  "color": "#10b981", "icon": "💰"})
        entry = (FinanceAuditLog.objects
                 .filter(user=self.user, entity_type="goal", action="update")
                 .order_by("-id").first())
        self.assertIsNotNone(entry)
        self.assertEqual(entry.details["field"], "linked_account")
        self.assertEqual(entry.details["to_account_id"], other.pk)

    def test_reading_the_balance_creates_no_audit_noise(self):
        before = FinanceAuditLog.objects.count()
        for _ in range(5):
            self.client.get(reverse("finance:goal_detail", args=[self.goal.pk]))
            _ = self.goal.current_value
        self.assertEqual(FinanceAuditLog.objects.count(), before,
                         "a refresh is not a decision worth recording")


@override_settings(TIME_ZONE="UTC")
class TimezoneRenderingTests(TestCase):
    """"Started August 30" on a screenshot taken on August 29."""

    def setUp(self):
        self.user = _usable(User.objects.create_user(
            email="tz@example.com", password="pw"))
        prefs = self.user.preferences
        prefs.timezone = "America/New_York"
        prefs.save(update_fields=["timezone"])
        self.client.force_login(self.user)

    def test_started_at_uses_the_users_date_not_utc(self):
        from apps.core.utils import get_user_today
        from unittest.mock import patch

        # 01:45 UTC on the 30th is 21:45 on the 29th in New York.
        moment = timezone.datetime(2026, 8, 30, 1, 45, tzinfo=timezone.utc)
        with patch("django.utils.timezone.now", return_value=moment):
            self.client.post(reverse("finance:goal_create"), data={
                "name": "Emergency Fund", "goal_type": "savings",
                "target_amount": "1000.00", "color": "#10b981", "icon": "💰"})

        goal = FinancialGoal.objects.get(user=self.user, name="Emergency Fund")
        self.assertEqual(goal.started_at, date(2026, 8, 29),
                         "the user's local date, not the server's")
        self.assertEqual(goal.started_at, get_user_today(self.user)
                         if get_user_today(self.user) == date(2026, 8, 29)
                         else goal.started_at)

    def test_the_model_default_is_no_longer_a_utc_datetime(self):
        field = FinancialGoal._meta.get_field("started_at")
        self.assertIs(field.default, timezone.localdate,
                      "timezone.now is a UTC datetime; coerced to a date it is "
                      "tomorrow for anyone west of Greenwich after 8pm")
