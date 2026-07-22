# ==============================================================================
# File: apps/ai/tests/test_metric_date_authority.py
# Project: Whole Life Journey - Django 5.x Personal Wellness/Journaling App
# Description: Certification gates for the single date-scoped metric authority
# Owner: Danny Jenkins (admin@wholelifejourney.com)
# Created: 2026-07-22
# ==============================================================================
"""
Single-authority certification — "metric X on calendar date D".

Origin: `docs/WLJ_WEIGHT_YESTERDAY_INVESTIGATION.md` (2026-07-22). Four surfaces
answered "my weight yesterday" under different contracts; with no observation on the
requested date one silently carried a 105-day-old value forward and labelled it
yesterday's, while the history authority correctly returned empty.

These gates are GENERIC (they enumerate the registered date-scoped keys) so a future
curated key cannot reintroduce the class for a different metric.
"""
from datetime import datetime, time, timedelta

from django.test import TestCase
from django.utils import timezone

from apps.ai.cos_services import metric_date as md
from apps.ai.cos_services.domain_history import get_domain_history
from apps.ai.cos_services.health_facts import (
    _DATE_SCOPED_FACTS,
    _LATEST_OBSERVATION_FACTS,
    get_foundational_health_facts,
)
from apps.core.utils import get_user_today
from apps.health.models import GlucoseEntry, StepsEntry, WeightEntry
from apps.users.models import User


def _weight(user, on_date, value):
    return WeightEntry.objects.create(
        user=user, value=value, unit="lb",
        recorded_at=timezone.make_aware(datetime.combine(on_date, time(6, 30))))


class DateScopedAuthorityContractTests(TestCase):
    """The canonical authority's own contract: exact-date never carries forward."""

    @classmethod
    def setUpTestData(cls):
        cls.user = User.objects.create_user(email="metricdate@test.com", password="x")
        cls.today = get_user_today(cls.user)
        cls.yest = cls.today - timedelta(days=1)

    def test_exact_date_returns_the_value_recorded_on_that_date(self):
        _weight(self.user, self.today, 280.4)
        _weight(self.user, self.yest, 281.5)
        fact = md.metric_on_date(self.user, "health", "weight", self.yest)
        self.assertEqual(fact["status"], "ok")
        self.assertEqual(fact["value"], 281.5)
        self.assertEqual(fact["semantics"], md.EXACT_DATE)
        self.assertEqual(fact["observed_on"], self.yest.isoformat())
        self.assertTrue(fact["exact"])
        self.assertEqual(fact["age_days"], 0)

    def test_exact_date_never_carries_forward_an_older_observation(self):
        """The defect itself: nothing on the requested day must NOT become an answer."""
        _weight(self.user, self.today - timedelta(days=30), 298.3)
        fact = md.metric_on_date(self.user, "health", "weight", self.yest)
        self.assertEqual(fact["status"], "not_recorded")
        self.assertNotIn("value", fact)
        self.assertIsNone(fact["observed_on"])
        self.assertFalse(fact["exact"])

    def test_carry_forward_is_available_only_under_its_own_name(self):
        _weight(self.user, self.today - timedelta(days=30), 298.3)
        fact = md.latest_observation_on_or_before(self.user, "health", "weight", self.yest)
        self.assertEqual(fact["status"], "ok")
        self.assertEqual(fact["value"], 298.3)
        self.assertEqual(fact["semantics"], md.LATEST_ON_OR_BEFORE)
        # It discloses the REAL observation date and how old it is — never "yesterday".
        self.assertEqual(fact["observed_on"],
                         (self.today - timedelta(days=30)).isoformat())
        self.assertEqual(fact["age_days"], 29)
        self.assertFalse(fact["exact"])
        self.assertEqual(fact["freshness"], "stale")

    def test_envelope_is_complete_for_every_answer(self):
        _weight(self.user, self.yest, 281.5)
        required = {"status", "semantics", "domain", "metric", "requested_date",
                    "user_local_date", "observed_on", "freshness", "confidence",
                    "source", "authority", "exact"}
        for fact in (md.metric_on_date(self.user, "health", "weight", self.yest),
                     md.metric_on_date(self.user, "health", "weight",
                                       self.today - timedelta(days=9)),
                     md.latest_observation_on_or_before(self.user, "health", "weight",
                                                        self.today)):
            self.assertTrue(required.issubset(fact), msg=sorted(required - set(fact)))

    def test_unsupported_metric_is_honest_not_a_guess(self):
        fact = md.metric_on_date(self.user, "health", "not_a_metric", self.yest)
        self.assertEqual(fact["status"], "unsupported")
        self.assertNotIn("value", fact)


class CuratedSurfaceDelegationTests(TestCase):
    """No curated convenience key may independently answer a deterministic question."""

    @classmethod
    def setUpTestData(cls):
        cls.user = User.objects.create_user(email="delegation@test.com", password="x")
        cls.today = get_user_today(cls.user)
        cls.yest = cls.today - timedelta(days=1)

    def test_every_date_scoped_key_agrees_with_the_history_authority(self):
        """Generic: identical inputs → identical value from both surfaces."""
        _weight(self.user, self.yest, 281.5)
        _weight(self.user, self.today, 280.4)
        StepsEntry.objects.create(user=self.user, count=8123, logged_date=self.yest)
        StepsEntry.objects.create(user=self.user, count=4200, logged_date=self.today)
        GlucoseEntry.objects.create(
            user=self.user, value=118, unit="mg/dL",
            recorded_at=timezone.make_aware(datetime.combine(self.yest, time(9, 0))))

        facts = get_foundational_health_facts(self.user, keys=list(_DATE_SCOPED_FACTS))
        for key, (domain, metric, days_back) in _DATE_SCOPED_FACTS.items():
            on_date = self.today - timedelta(days=days_back)
            hist = get_domain_history(self.user, domain, metric, period="custom",
                                      start=on_date, end=on_date)
            fact = facts[key]
            # `calories_*` keeps a deliberate, pre-existing contract: "no food logged"
            # is a real 0 kcal, not an absence. It declares `semantics: derived_zero`,
            # so it is honest about being derived rather than observed.
            if fact.get("semantics") == "derived_zero":
                continue
            if hist.get("status") == "ready":
                point = (hist.get("points") or [])[-1]
                self.assertEqual(fact.get("value"), point["value"], msg=key)
                self.assertEqual(fact.get("status"), "ok", msg=key)
            else:
                # Honest absence on BOTH surfaces — never a value on one and empty
                # on the other (the proven contradiction).
                self.assertNotEqual(fact.get("status"), "ok", msg=key)
                self.assertNotIn("value", fact, msg=key)

    def test_every_date_scoped_key_declares_exact_date_semantics(self):
        facts = get_foundational_health_facts(self.user, keys=list(_DATE_SCOPED_FACTS))
        for key in _DATE_SCOPED_FACTS:
            fact = facts[key]
            # calories carries a deliberate derived-zero contract; it declares that.
            self.assertIn(fact.get("semantics"), (md.EXACT_DATE, "derived_zero"),
                          msg=f"{key}: {fact}")

    def test_weight_yesterday_reports_missing_rather_than_yesterdays_neighbour(self):
        _weight(self.user, self.today, 280.4)          # today only — nothing yesterday
        fact = get_foundational_health_facts(
            self.user, keys=["weight_yesterday"])["weight_yesterday"]
        self.assertEqual(fact["status"], "not_recorded")
        self.assertNotIn("value", fact)

    def test_current_weight_delegates_and_discloses_staleness(self):
        """A stale value may still be returned — it may NOT pretend to be today's."""
        _weight(self.user, self.today - timedelta(days=105), 298.3)
        fact = get_foundational_health_facts(
            self.user, keys=["current_weight"])["current_weight"]
        self.assertEqual(fact["value"], 298.3)
        self.assertEqual(fact["semantics"], md.LATEST_ON_OR_BEFORE)
        self.assertEqual(fact["freshness"], "stale")
        self.assertEqual(fact["age_days"], 105)
        self.assertEqual(fact["observed_on"],
                         (self.today - timedelta(days=105)).isoformat())
        self.assertFalse(fact["exact"])

    def test_current_weight_is_not_read_from_the_sae_snapshot(self):
        """The stale-snapshot shadow is gone: the answer names the history authority."""
        _weight(self.user, self.today, 280.4)
        fact = get_foundational_health_facts(
            self.user, keys=["current_weight"])["current_weight"]
        self.assertNotIn("SAE", str(fact.get("source", "")))
        self.assertEqual(fact["authority"], "get_domain_history:health.weight")

    def test_no_curated_key_answers_a_date_question_from_a_second_producer(self):
        """Registry gate: every date-scoped/latest key must resolve through metric_date."""
        for key in set(_DATE_SCOPED_FACTS) | set(_LATEST_OBSERVATION_FACTS):
            facts = get_foundational_health_facts(self.user, keys=[key])
            fact = facts[key]
            if fact.get("semantics") == "derived_zero":
                continue
            self.assertTrue(
                str(fact.get("authority", "")).startswith("get_domain_history:"),
                msg=f"{key} did not delegate to the canonical authority: {fact}")


class DailyHealthQueriesExactDateTests(TestCase):
    """The lowest-level accessor must not silently carry forward either."""

    @classmethod
    def setUpTestData(cls):
        cls.user = User.objects.create_user(email="dhqexact@test.com", password="x")
        cls.today = get_user_today(cls.user)

    def test_weight_on_is_exact_date_only(self):
        from apps.health.services.daily_health_queries import DailyHealthQueries as Q
        _weight(self.user, self.today - timedelta(days=3), 285.0)
        self.assertEqual(Q.weight_on(self.user, self.today)["status"], "no_data")

    def test_named_carry_forward_still_available(self):
        from apps.health.services.daily_health_queries import DailyHealthQueries as Q
        _weight(self.user, self.today - timedelta(days=3), 285.0)
        res = Q.weight_latest_on_or_before(self.user, self.today)
        self.assertEqual(res["value"], 285.0)
        self.assertFalse(res["exact"])
        self.assertEqual(res["as_of"], (self.today - timedelta(days=3)).isoformat())

    def test_domain_truth_current_agrees_with_history(self):
        """`get_domain_truth(...).current('weight_yesterday')` was the last shadow."""
        from apps.core.truth.domain import get_domain_truth
        yest = self.today - timedelta(days=1)
        _weight(self.user, self.today - timedelta(days=30), 298.3)
        current = get_domain_truth(self.user, "health").current(
            "weight_yesterday").to_fact_dict()
        hist = get_domain_history(self.user, "health", "weight", period="custom",
                                  start=yest, end=yest)
        self.assertEqual(hist["status"], "empty")
        self.assertIsNone(current.get("value"))
