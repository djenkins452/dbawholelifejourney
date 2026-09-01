# ==============================================================================
# File: apps/finance/tests/test_recurring_workflow.py
# Project: Whole Life Journey - Django 5.x Personal Wellness/Journaling App
# Description: Detected recurring commitments — discovery, review, and correction.
# Owner: Danny Jenkins (admin@wholelifejourney.com)
# ==============================================================================
"""The dashboard told a man with a mortgage he had no recurring activity.

It read `RecurringTransaction` — the table a person fills in by hand — and said "No
upcoming recurring. Add subscriptions or bills." WLJ had two years of his transactions
and a detector that could see the mortgage; it simply never looked at what the detector
had found, because the detector had never been asked.

These tests hold three things: that detection can explain itself when it finds nothing,
that a guess is never dressed as a decision, and that a person can correct WLJ without
having to accept or destroy its answer whole.
"""
from datetime import date, timedelta
from decimal import Decimal

from django.test import TestCase
from django.urls import reverse

from apps.finance.models import (FinancialAccount, RecurringSeries,
                                 RecurringTransaction, Transaction)
from apps.finance.services.finance_calc import recurring as REC
from apps.finance.tests.test_p1_economic_roles import RoleBase


class RecurringBase(RoleBase):
    def _series(self, **kw):
        defaults = dict(
            user=self.user, name="Streamflix", payee="streamflix",
            kind=RecurringSeries.KIND_SUBSCRIPTION,
            frequency=RecurringSeries.FREQ_MONTHLY,
            amount_expected=Decimal("15.99"), confidence="high",
            review_state=RecurringSeries.REVIEW_CANDIDATE,
            source=RecurringSeries.SOURCE_DETECTED,
            occurrence_count=6, first_seen_date=date(2026, 1, 5),
            last_seen_date=date(2026, 6, 5),
            next_due_date=date(2026, 7, 5), account=self.checking)
        defaults.update(kw)
        return RecurringSeries.objects.create(**defaults)

    def _repeating(self, payee, amount, *, months=6, primary="GENERAL_SERVICES",
                   detailed="", account=None, start=date(2026, 1, 5)):
        made = []
        for i in range(months):
            month = start.month + i
            year = start.year + (month - 1) // 12
            when = date(year, ((month - 1) % 12) + 1, start.day)
            made.append(self._txn(amount, account=account or self.checking, on=when,
                                  primary=primary, detailed=detailed,
                                  description=payee))
        return made


class DetectionExplainsItselfTests(RecurringBase):
    """"No recurring activity" is a claim, and WLJ must be able to substantiate it."""

    def test_an_empty_result_says_why(self):
        report = REC.rehearse(self.user)
        self.assertEqual(report["would_propose"], 0)
        self.assertIn("transactions", report["diagnostics"])
        self.assertTrue(report["read_only"])

    def test_a_single_charge_is_reported_as_too_few_occurrences(self):
        self._txn(-15.99, primary="GENERAL_SERVICES", description="streamflix")
        report = REC.rehearse(self.user)
        self.assertEqual(report["would_propose"], 0)
        self.assertGreaterEqual(report["diagnostics"]["too_few_occurrences"], 1)

    def test_a_real_monthly_charge_is_proposed(self):
        self._repeating("streamflix", -15.99)
        report = REC.rehearse(self.user)
        self.assertGreaterEqual(report["would_propose"], 1)
        self.assertIn(RecurringSeries.FREQ_MONTHLY, report["by_frequency"])

    def test_the_rehearsal_writes_nothing(self):
        self._repeating("streamflix", -15.99)
        REC.rehearse(self.user)
        self.assertEqual(RecurringSeries.objects.filter(user=self.user).count(), 0)


class KindIsTheMostDefensibleOneTests(RecurringBase):
    """"Do not call every repeated charge a subscription."""

    def _kind_of(self, payee):
        for proposal in REC.detect(self.user):
            if proposal["series"].payee == payee:
                return proposal["series"].kind
        return None

    def test_a_utility_is_a_bill_not_a_subscription(self):
        self._repeating("city power", -140.00, primary="RENT_AND_UTILITIES")
        self.assertEqual(self._kind_of("city power"), RecurringSeries.KIND_BILL)

    def test_a_variable_utility_stays_a_bill(self):
        for i, amount in enumerate([-80, -95, -210, -130, -175, -99]):
            when = date(2026, i + 1, 12)
            self._txn(amount, on=when, primary="RENT_AND_UTILITIES",
                      description="city power")
        self.assertEqual(self._kind_of("city power"), RecurringSeries.KIND_BILL)

    def test_the_provider_saying_subscription_is_believed(self):
        self._repeating("streamflix", -15.99, primary="ENTERTAINMENT",
                        detailed="ENTERTAINMENT_STREAMING_SUBSCRIPTION")
        self.assertEqual(self._kind_of("streamflix"),
                         RecurringSeries.KIND_SUBSCRIPTION)

    def test_a_steady_entertainment_charge_is_a_subscription(self):
        self._repeating("streamflix", -15.99, primary="ENTERTAINMENT")
        self.assertEqual(self._kind_of("streamflix"),
                         RecurringSeries.KIND_SUBSCRIPTION)

    def test_income_is_income_not_a_bill(self):
        self._repeating("acme payroll", 3200.00, primary="INCOME")
        self.assertEqual(self._kind_of("acme payroll"), RecurringSeries.KIND_INCOME)

    def test_a_loan_payment_is_a_debt_payment(self):
        self._repeating("ally auto", -849.84, primary="LOAN_PAYMENTS",
                        detailed="LOAN_PAYMENTS_CAR_PAYMENT")
        self.assertEqual(self._kind_of("ally auto"),
                         RecurringSeries.KIND_DEBT_PAYMENT)


class TheDashboardTellsTheTruthTests(RecurringBase):
    """The sentence that started this."""

    def test_a_confirmed_series_appears(self):
        self._series(review_state=RecurringSeries.REVIEW_CONFIRMED)
        body = self.client.get(reverse("finance:dashboard")).content.decode()
        self.assertIn('data-testid="upcoming-recurring"', body)
        self.assertIn("Streamflix", body)

    def test_a_likely_candidate_appears_and_is_labelled_as_a_guess(self):
        self._series()
        body = self.client.get(reverse("finance:dashboard")).content.decode()
        self.assertIn('data-testid="likely-flag"', body)
        self.assertIn("Likely", body)

    def test_it_says_how_many_are_waiting(self):
        self._series()
        self._series(name="Gym", payee="gym", next_due_date=date(2026, 7, 9))
        body = self.client.get(reverse("finance:dashboard")).content.decode()
        self.assertIn('data-testid="awaiting-review"', body)
        self.assertIn("WLJ found 2 likely recurring items for review", body)

    def test_it_never_claims_there_is_no_recurring_activity(self):
        """The original defect, asserted directly."""
        body = self.client.get(reverse("finance:dashboard")).content.decode()
        self.assertNotIn("No upcoming recurring", body)
        self.assertIn('data-testid="empty-not-detected"', body)
        self.assertIn("hasn't found any recurring patterns", body)

    def test_a_low_confidence_candidate_does_not_lead_the_dashboard(self):
        self._series(confidence="low")
        body = self.client.get(reverse("finance:dashboard")).content.decode()
        self.assertNotIn("Streamflix", body)

    def test_a_low_confidence_candidate_is_still_reviewable(self):
        self._series(confidence="low")
        body = self.client.get(reverse("finance:series_list")).content.decode()
        self.assertIn("Streamflix", body)

    def test_a_declared_template_is_not_shown_twice(self):
        template = RecurringTransaction.objects.create(
            user=self.user, name="Streamflix", amount=Decimal("15.99"),
            account=self.checking, frequency="monthly",
            start_date=date(2026, 1, 5), next_due_date=date(2026, 7, 5),
            transaction_type="expense")
        self._series(review_state=RecurringSeries.REVIEW_CONFIRMED,
                     declared_template=template)
        result = REC.upcoming(self.user)
        self.assertEqual(len([i for i in result["items"]
                              if i["name"] == "Streamflix"]), 1)


class ForecastCountsOnlyConfirmedTests(RecurringBase):
    """A guess must never enter a committed total."""

    def test_a_candidate_is_not_counted(self):
        self._series()
        total, unknown = REC.monthly_obligation_total(self.user)
        self.assertEqual(total, Decimal("0.00"))
        self.assertEqual(unknown, [])

    def test_confirming_it_makes_it_count(self):
        series = self._series()
        series.review_state = RecurringSeries.REVIEW_CONFIRMED
        series.save(update_fields=["review_state"])
        total, _unknown = REC.monthly_obligation_total(self.user)
        self.assertEqual(total, Decimal("15.99"))

    def test_is_counted_requires_confirmed_active_and_unmerged(self):
        series = self._series(review_state=RecurringSeries.REVIEW_CONFIRMED)
        self.assertTrue(series.is_counted)
        series.merged_into = self._series(name="Other", payee="other")
        self.assertFalse(series.is_counted)


class OrdinaryUserCrudTests(RecurringBase):
    """Every verb a person needs, without Django admin."""

    def test_confirm(self):
        series = self._series()
        self.client.post(reverse("finance:money_series_decide", args=[series.pk]),
                         {"decision": "confirmed", "kind": series.kind})
        series.refresh_from_db()
        self.assertEqual(series.review_state, RecurringSeries.REVIEW_CONFIRMED)

    def test_reject(self):
        series = self._series()
        self.client.post(reverse("finance:money_series_decide", args=[series.pk]),
                         {"decision": "ignored"})
        series.refresh_from_db()
        self.assertEqual(series.review_state, RecurringSeries.REVIEW_IGNORED)

    def test_view_detail_shows_the_evidence(self):
        series = self._series(evidence={"occurrences": 6, "first": "2026-01-05",
                                        "last": "2026-06-05", "median_gap_days": 30,
                                        "gap_standard_deviation_days": 0.4,
                                        "amount_min": "15.99", "amount_max": "15.99",
                                        "detector_version": "1.0.0"})
        body = self.client.get(
            reverse("finance:series_detail", args=[series.pk])).content.decode()
        self.assertIn("Why WLJ believes this", body)
        self.assertIn("6 occurrences", body)

    def test_edit_every_correctable_field(self):
        series = self._series()
        response = self.client.post(
            reverse("finance:series_update", args=[series.pk]),
            {"name": "Streamflix Premium", "payee": "streamflix prem",
             "kind": RecurringSeries.KIND_BILL,
             "frequency": RecurringSeries.FREQ_ANNUAL,
             "amount_expected": "199.00", "amount_min": "199.00",
             "amount_max": "199.00", "category": "", "account": self.savings.pk,
             "next_due_date": "2027-01-05", "note": "moved to annual"})
        self.assertEqual(response.status_code, 302)
        series.refresh_from_db()
        self.assertEqual(series.name, "Streamflix Premium")
        self.assertEqual(series.kind, RecurringSeries.KIND_BILL)
        self.assertEqual(series.frequency, RecurringSeries.FREQ_ANNUAL)
        self.assertEqual(series.amount_expected, Decimal("199.00"))
        self.assertEqual(series.account_id, self.savings.pk)
        self.assertEqual(series.next_due_date, date(2027, 1, 5))

    def test_an_edit_marks_it_as_the_users(self):
        """`source = user` is what stops the next run arguing with them."""
        series = self._series()
        self.client.post(reverse("finance:series_update", args=[series.pk]),
                         {"name": "Mine", "payee": "streamflix",
                          "kind": series.kind, "frequency": series.frequency,
                          "amount_expected": "15.99", "account": self.checking.pk,
                          "category": "", "next_due_date": "2026-07-05", "note": ""})
        series.refresh_from_db()
        self.assertEqual(series.source, RecurringSeries.SOURCE_USER)

    def test_create_by_hand_is_confirmed_immediately(self):
        response = self.client.post(
            reverse("finance:series_create"),
            {"name": "New gym", "payee": "new gym",
             "kind": RecurringSeries.KIND_SUBSCRIPTION,
             "frequency": RecurringSeries.FREQ_MONTHLY,
             "amount_expected": "40.00", "account": self.checking.pk,
             "category": "", "next_due_date": "2026-07-01", "note": ""})
        self.assertEqual(response.status_code, 302)
        created = RecurringSeries.objects.get(user=self.user, payee="new gym")
        self.assertEqual(created.review_state, RecurringSeries.REVIEW_CONFIRMED)
        self.assertEqual(created.source, RecurringSeries.SOURCE_USER)

    def test_archive_then_restore(self):
        series = self._series()
        self.client.post(reverse("finance:series_archive", args=[series.pk]))
        series.refresh_from_db()
        self.assertEqual(series.status, "archived")

        self.client.post(reverse("finance:series_restore", args=[series.pk]))
        series.refresh_from_db()
        self.assertEqual(series.status, "active")

    def test_archived_are_listed_separately(self):
        series = self._series()
        self.client.post(reverse("finance:series_archive", args=[series.pk]))

        # Assert on the ROWS, not the page text: the redirect carries a flash message
        # naming the series ("Streamflix archived"), which is correct and would make a
        # naive text assertion pass or fail for the wrong reason.
        active = self.client.get(reverse("finance:series_list"))
        self.assertNotIn('data-testid="candidate-row"',
                         active.content.decode())
        self.assertContains(active, 'data-testid="show-archived"')

        archived = self.client.get(reverse("finance:series_list") + "?show=archived")
        self.assertContains(archived, 'data-testid="group-archived"')
        self.assertContains(archived, "Streamflix")

    def test_delete_removes_the_series_but_never_the_transactions(self):
        series = self._series()
        txn = self._txn(-15.99, description="streamflix")
        Transaction.objects.filter(pk=txn.pk).update(recurring_series=series)

        self.client.post(reverse("finance:series_delete", args=[series.pk]))
        self.assertFalse(RecurringSeries.objects.filter(pk=series.pk).exists())
        txn.refresh_from_db()
        self.assertIsNone(txn.recurring_series_id)
        self.assertEqual(txn.amount, Decimal("-15.99"))

    def test_mark_ended_is_not_the_same_as_never_recurring(self):
        series = self._series(review_state=RecurringSeries.REVIEW_CONFIRMED)
        self.client.post(reverse("finance:series_end", args=[series.pk]))
        series.refresh_from_db()
        self.assertIsNone(series.next_due_date)
        self.assertIn("Marked ended by you", series.note)
        self.assertFalse(series.is_counted)

    def test_merge_moves_the_observations_and_leaves_a_pointer(self):
        keep = self._series(name="Streamflix", payee="streamflix")
        dupe = self._series(name="Streamflix Inc", payee="streamflix inc")
        txn = self._txn(-15.99, description="streamflix inc")
        Transaction.objects.filter(pk=txn.pk).update(recurring_series=dupe)

        self.client.post(reverse("finance:series_merge", args=[dupe.pk]),
                         {"into": keep.pk})
        dupe.refresh_from_db()
        txn.refresh_from_db()
        self.assertEqual(dupe.merged_into_id, keep.pk)
        self.assertEqual(txn.recurring_series_id, keep.pk)
        self.assertFalse(dupe.is_counted)

    def test_a_series_cannot_be_merged_into_itself(self):
        series = self._series()
        self.client.post(reverse("finance:series_merge", args=[series.pk]),
                         {"into": series.pk})
        series.refresh_from_db()
        self.assertIsNone(series.merged_into_id)

    def test_split_releases_the_observations(self):
        series = self._series()
        txn = self._txn(-15.99, description="streamflix")
        Transaction.objects.filter(pk=txn.pk).update(recurring_series=series)

        self.client.post(reverse("finance:series_split", args=[series.pk]))
        txn.refresh_from_db()
        series.refresh_from_db()
        self.assertIsNone(txn.recurring_series_id)
        self.assertEqual(series.review_state, RecurringSeries.REVIEW_IGNORED)

    def test_a_fixed_series_must_have_an_amount(self):
        series = self._series()
        response = self.client.post(
            reverse("finance:series_update", args=[series.pk]),
            {"name": "Streamflix", "payee": "streamflix", "kind": series.kind,
             "frequency": series.frequency, "amount_expected": "",
             "account": self.checking.pk, "category": "",
             "next_due_date": "2026-07-05", "note": ""})
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "needs an expected amount")


class UserDecisionsSurviveDetectionTests(RecurringBase):
    """Running detection again must not argue with a decision already made."""

    def test_an_ignored_series_is_not_reproposed(self):
        self._repeating("streamflix", -15.99, primary="ENTERTAINMENT")
        REC.persist(self.user, REC.detect(self.user), commit=True)
        series = RecurringSeries.objects.get(user=self.user, payee="streamflix")
        series.review_state = RecurringSeries.REVIEW_IGNORED
        series.save(update_fields=["review_state"])

        REC.persist(self.user, REC.detect(self.user), commit=True)
        series.refresh_from_db()
        self.assertEqual(series.review_state, RecurringSeries.REVIEW_IGNORED)
        self.assertEqual(
            RecurringSeries.objects.filter(user=self.user, payee="streamflix").count(),
            1, "a decision must not become a duplicate")

    def test_a_confirmed_series_is_not_reopened(self):
        self._repeating("streamflix", -15.99, primary="ENTERTAINMENT")
        REC.persist(self.user, REC.detect(self.user), commit=True)
        series = RecurringSeries.objects.get(user=self.user, payee="streamflix")
        series.review_state = RecurringSeries.REVIEW_CONFIRMED
        series.save(update_fields=["review_state"])

        REC.persist(self.user, REC.detect(self.user), commit=True)
        series.refresh_from_db()
        self.assertEqual(series.review_state, RecurringSeries.REVIEW_CONFIRMED)

    def test_observations_still_refresh(self):
        """Decisions are preserved; the EVIDENCE behind them keeps updating."""
        self._repeating("streamflix", -15.99, primary="ENTERTAINMENT", months=4)
        REC.persist(self.user, REC.detect(self.user), commit=True)
        series = RecurringSeries.objects.get(user=self.user, payee="streamflix")
        series.review_state = RecurringSeries.REVIEW_CONFIRMED
        series.save(update_fields=["review_state"])
        before = series.occurrence_count

        self._txn(-15.99, on=date(2026, 5, 5), primary="ENTERTAINMENT",
                  description="streamflix")
        REC.persist(self.user, REC.detect(self.user), commit=True)
        series.refresh_from_db()
        self.assertGreater(series.occurrence_count, before)

    def test_detection_is_idempotent(self):
        self._repeating("streamflix", -15.99, primary="ENTERTAINMENT")
        REC.persist(self.user, REC.detect(self.user), commit=True)
        count = RecurringSeries.objects.filter(user=self.user).count()
        second = REC.persist(self.user, REC.detect(self.user), commit=True)
        self.assertEqual(second["created"], 0)
        self.assertEqual(RecurringSeries.objects.filter(user=self.user).count(), count)


class OwnerIsolationTests(RecurringBase):
    def setUp(self):
        super().setUp()
        from apps.finance.tests.test_p1_economic_roles import _usable
        from django.contrib.auth import get_user_model
        self.other = _usable(get_user_model().objects.create_user(
            email="other-recurring@example.com", password="pw"))
        self.their_series = RecurringSeries.objects.create(
            user=self.other, name="Theirs", payee="theirs",
            kind=RecurringSeries.KIND_BILL,
            frequency=RecurringSeries.FREQ_MONTHLY,
            amount_expected=Decimal("10.00"))

    def test_another_users_series_is_not_visible(self):
        response = self.client.get(
            reverse("finance:series_detail", args=[self.their_series.pk]))
        self.assertEqual(response.status_code, 404)

    def test_another_users_series_cannot_be_edited(self):
        response = self.client.post(
            reverse("finance:series_update", args=[self.their_series.pk]),
            {"name": "Hijacked", "payee": "x", "kind": "bill",
             "frequency": "monthly", "amount_expected": "1.00"})
        self.assertEqual(response.status_code, 404)
        self.their_series.refresh_from_db()
        self.assertEqual(self.their_series.name, "Theirs")

    def test_another_users_series_cannot_be_deleted(self):
        response = self.client.post(
            reverse("finance:series_delete", args=[self.their_series.pk]))
        self.assertEqual(response.status_code, 404)
        self.assertTrue(
            RecurringSeries.objects.filter(pk=self.their_series.pk).exists())

    def test_a_series_cannot_be_merged_across_users(self):
        mine = self._series()
        self.client.post(reverse("finance:series_merge", args=[mine.pk]),
                         {"into": self.their_series.pk})
        mine.refresh_from_db()
        self.assertIsNone(mine.merged_into_id)


class RenderingTests(RecurringBase):
    def test_the_list_renders(self):
        self._series()
        response = self.client.get(reverse("finance:series_list"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'data-testid="finance-series"')

    def test_no_inline_handlers_anywhere(self):
        series = self._series()
        for url in (reverse("finance:series_list"),
                    reverse("finance:series_detail", args=[series.pk]),
                    reverse("finance:series_update", args=[series.pk]),
                    reverse("finance:series_create")):
            body = self.client.get(url).content.decode()
            for handler in ("onclick=", "onchange=", "onsubmit=", "onload="):
                self.assertNotIn(handler, body, url)

    def test_the_pages_work_at_375px(self):
        """No fixed width wider than an iPhone SE; touch targets clear 44px."""
        import re
        from pathlib import Path

        root = Path(__file__).resolve().parents[3] / "templates" / "finance"
        for name in ("series_list.html", "series_detail.html", "series_form.html"):
            css = "\n".join(re.findall(r"<style[^>]*>(.*?)</style>",
                                       (root / name).read_text(), re.S))
            offenders = [m for m in re.findall(r"(?<![a-z-])width:\s*(\d+)px", css)
                         if int(m) > 375]
            self.assertEqual(offenders, [], f"{name}: {offenders}")
            self.assertIn("44px", css, f"{name} must respect touch targets")
            self.assertIn("max-width: 480px", css, f"{name} needs a mobile breakpoint")


class CurrentContextTests(RecurringBase):
    def test_the_page_declares_a_summary(self):
        self._series()
        body = self.client.get(reverse("finance:series_list")).content.decode()
        self.assertIn('name="wlj-context"', body)
        self.assertIn("summary:finance.recurring", body)

    def test_the_provider_reports_facts_not_verdicts(self):
        from apps.core.current_context import _resolve_page_summary

        self._series()
        self._series(name="Gym", payee="gym",
                     review_state=RecurringSeries.REVIEW_CONFIRMED)
        from apps.finance.page_summaries_money import recurring_summary

        self.assertIsNotNone(
            _resolve_page_summary(self.user, "summary:finance.recurring"),
            "the provider must survive the call the resolver actually makes")
        facts = recurring_summary(self.user, None)["facts"]
        self.assertEqual(facts["confirmed"], 1)
        self.assertEqual(facts["awaiting_review"], 1)
        for value in facts.values():
            self.assertNotIn(str(value).lower(),
                             ("on track", "behind", "good", "bad"))


class PageSummaryProviderSignatureTests(TestCase):
    """Every registered provider must survive the call the resolver actually makes.

    `_resolve_page_summary` calls `provider(user, params)` inside a try/except. A
    one-argument provider therefore raises TypeError, is swallowed, and the page ends up
    with NO Current Context — the assistant does not know what the person is looking at,
    and nothing anywhere says so. All seven Finance providers were written that way and
    had been failing silently.
    """

    def test_every_provider_accepts_user_and_params(self):
        import inspect

        from apps.core.current_context import _PAGE_SUMMARY_PROVIDERS

        offenders = []
        for key, fn in sorted(_PAGE_SUMMARY_PROVIDERS.items()):
            parameters = inspect.signature(fn).parameters.values()
            takes_varargs = any(p.kind == p.VAR_POSITIONAL for p in parameters)
            if len(parameters) < 2 and not takes_varargs:
                offenders.append(key)
        self.assertEqual(
            offenders, [],
            "these providers cannot be called as provider(user, params), so their "
            f"pages have no Current Context: {offenders}")

    def test_the_finance_providers_actually_resolve(self):
        """Signature is necessary, not sufficient — call them for real."""
        from apps.core.current_context import (_PAGE_SUMMARY_PROVIDERS,
                                               _resolve_page_summary)
        from apps.finance.tests.test_p1_economic_roles import _usable
        from django.contrib.auth import get_user_model

        user = _usable(get_user_model().objects.create_user(
            email="summaries@example.com", password="pw"))
        failed = []
        for key in sorted(_PAGE_SUMMARY_PROVIDERS):
            if not key.startswith("finance."):
                continue
            if _resolve_page_summary(user, f"summary:{key}") is None:
                failed.append(key)
        self.assertEqual(failed, [],
                         f"these finance summaries resolve to nothing: {failed}")


class DetectionRunsWithoutBeingAskedTests(RecurringBase):
    """Nothing was ever detected because nothing ever ran detection."""

    def test_a_sync_that_added_rows_asks_for_detection(self):
        from unittest.mock import patch

        from apps.finance.services.sync_service import TransactionSyncService

        service = TransactionSyncService.__new__(TransactionSyncService)
        service.bank_connection = type("C", (), {"pk": 1, "user_id": self.user.pk})()
        with patch("apps.core.celery_utils.safe_enqueue") as enqueue:
            service._look_for_recurring_patterns({"added": 3, "modified": 0})
        self.assertTrue(enqueue.called)

    def test_a_sync_that_changed_nothing_does_not(self):
        from unittest.mock import patch

        from apps.finance.services.sync_service import TransactionSyncService

        service = TransactionSyncService.__new__(TransactionSyncService)
        service.bank_connection = type("C", (), {"pk": 1, "user_id": self.user.pk})()
        with patch("apps.core.celery_utils.safe_enqueue") as enqueue:
            service._look_for_recurring_patterns({"added": 0, "modified": 0})
        self.assertFalse(enqueue.called, "an empty poll has nothing new to find")

    def test_a_failed_sync_does_not(self):
        from unittest.mock import patch

        from apps.finance.services.sync_service import TransactionSyncService

        service = TransactionSyncService.__new__(TransactionSyncService)
        service.bank_connection = type("C", (), {"pk": 1, "user_id": self.user.pk})()
        with patch("apps.core.celery_utils.safe_enqueue") as enqueue:
            service._look_for_recurring_patterns(
                {"added": 5, "error": "sync_incomplete"})
        self.assertFalse(enqueue.called)

    def test_a_broken_enqueue_never_fails_the_sync(self):
        from unittest.mock import patch

        from apps.finance.services.sync_service import TransactionSyncService

        service = TransactionSyncService.__new__(TransactionSyncService)
        service.bank_connection = type("C", (), {"pk": 1, "user_id": self.user.pk})()
        with patch("apps.core.celery_utils.safe_enqueue",
                   side_effect=RuntimeError("redis down")):
            service._look_for_recurring_patterns({"added": 3})  # must not raise

    def test_the_nightly_sweep_is_scheduled(self):
        from django.conf import settings

        tasks = {entry["task"] for entry in
                 settings.CELERY_BEAT_SCHEDULE.values()}
        self.assertIn(
            "apps.finance.tasks_intelligence.sweep_recurring_detection", tasks)

    def test_the_sweep_is_a_crontab_not_an_interval(self):
        """Railway's filesystem resets PersistentScheduler, starving interval jobs."""
        from celery.schedules import crontab
        from django.conf import settings

        for entry in settings.CELERY_BEAT_SCHEDULE.values():
            if entry["task"].endswith("sweep_recurring_detection"):
                self.assertIsInstance(entry["schedule"], crontab)
