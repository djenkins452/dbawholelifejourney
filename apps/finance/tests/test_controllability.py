# ==============================================================================
# File: apps/finance/tests/test_controllability.py
# Project: Whole Life Journey - Django 5.x Personal Wellness/Journaling App
# Description: P2 — the controllability taxonomy, its precedence, and coverage.
# Owner: Danny Jenkins (admin@wholelifejourney.com)
# ==============================================================================
"""What a person can change, and what WLJ refuses to guess about it.

The tests that matter most here are the ones about ABSENCE: an unclassified cost must
not drift into "controllable" (which would invent savings) or into "uncontrollable"
(which would hide them). Silence has to stay silence.
"""
from decimal import Decimal

from apps.finance.models import (SpendingClassification, Transaction,
                                 TransactionCategory)
from apps.finance.services.finance_calc import controllability as C
from apps.finance.services.finance_calc import measures as M
from apps.finance.tests.test_p1_economic_roles import RoleBase


class TaxonomyShapeTests(RoleBase):
    def test_levers_co_occur_rather_than_exclude_each_other(self):
        c = SpendingClassification.objects.create(
            user=self.user, scope=SpendingClassification.SCOPE_PAYEE, payee="Telco",
            levers=[SpendingClassification.LEVER_NEGOTIABLE,
                    SpendingClassification.LEVER_REDUCIBLE])
        self.assertEqual(c.clean_levers(), ["negotiable", "reducible"])

    def test_an_unrecognised_lever_is_dropped_not_stored(self):
        c = SpendingClassification.objects.create(
            user=self.user, scope=SpendingClassification.SCOPE_PAYEE, payee="Telco",
            levers=["negotiable", "teleported"])
        c.refresh_from_db()
        self.assertEqual(c.levers, ["negotiable"])

    def test_everything_starts_unknown(self):
        c = SpendingClassification.objects.create(
            user=self.user, scope=SpendingClassification.SCOPE_PAYEE, payee="Shop")
        self.assertEqual(c.necessity, "unknown")
        self.assertEqual(c.variability, "unknown")
        self.assertFalse(c.is_controllable)

    def test_essential_can_still_be_controllable(self):
        """Insurance is essential AND negotiable. Conflating the two hides savings."""
        c = SpendingClassification.objects.create(
            user=self.user, scope=SpendingClassification.SCOPE_PAYEE, payee="Insurer",
            necessity=SpendingClassification.NECESSITY_ESSENTIAL,
            levers=[SpendingClassification.LEVER_NEGOTIABLE])
        self.assertTrue(c.is_controllable)


class PrecedenceTests(RoleBase):
    def setUp(self):
        super().setUp()
        self.category = TransactionCategory.objects.create(
            user=self.user, name="Streaming", category_type="expense")
        self.txn = self._txn(-15, primary="ENTERTAINMENT", description="Filmflix")
        self.txn.category = self.category
        self.txn.save()

    def _classify(self, scope, **kw):
        return SpendingClassification.objects.create(
            user=self.user, scope=scope, **kw)

    def test_the_more_specific_scope_wins(self):
        self._classify(SpendingClassification.SCOPE_CATEGORY, category=self.category,
                       necessity=SpendingClassification.NECESSITY_ESSENTIAL)
        self._classify(SpendingClassification.SCOPE_PAYEE, payee="filmflix",
                       necessity=SpendingClassification.NECESSITY_DISCRETIONARY)
        verdict = C.resolve(self.txn, C.active_classifications(self.user))
        self.assertEqual(verdict.scope, SpendingClassification.SCOPE_PAYEE)
        self.assertEqual(verdict.necessity, "discretionary")

    def test_a_transaction_decision_beats_everything(self):
        self._classify(SpendingClassification.SCOPE_PAYEE, payee="filmflix",
                       necessity=SpendingClassification.NECESSITY_DISCRETIONARY)
        self._classify(SpendingClassification.SCOPE_TRANSACTION, transaction=self.txn,
                       necessity=SpendingClassification.NECESSITY_ESSENTIAL)
        verdict = C.resolve(self.txn, C.active_classifications(self.user))
        self.assertEqual(verdict.scope, SpendingClassification.SCOPE_TRANSACTION)

    def test_the_user_outranks_an_inference_at_the_same_scope(self):
        self._classify(SpendingClassification.SCOPE_RULE, match_contains="film",
                       source=SpendingClassification.SOURCE_INFERRED,
                       necessity=SpendingClassification.NECESSITY_ESSENTIAL)
        self._classify(SpendingClassification.SCOPE_RULE, match_contains="flix",
                       source=SpendingClassification.SOURCE_USER,
                       necessity=SpendingClassification.NECESSITY_DISCRETIONARY)
        verdict = C.resolve(self.txn, C.active_classifications(self.user))
        self.assertEqual(verdict.source, SpendingClassification.SOURCE_USER)

    def test_the_verdict_shows_what_it_outranked(self):
        self._classify(SpendingClassification.SCOPE_CATEGORY, category=self.category)
        self._classify(SpendingClassification.SCOPE_PAYEE, payee="filmflix")
        verdict = C.resolve(self.txn, C.active_classifications(self.user))
        self.assertEqual(len(verdict.beat), 1)
        self.assertTrue(verdict.beat[0].startswith("category:"))

    def test_an_archived_classification_stops_applying(self):
        c = self._classify(SpendingClassification.SCOPE_PAYEE, payee="filmflix",
                           levers=[SpendingClassification.LEVER_CANCELLABLE])
        c.status = "archived"
        c.save()
        verdict = C.resolve(self.txn, C.active_classifications(self.user))
        self.assertFalse(verdict.is_known)

    def test_one_users_classification_never_reaches_another(self):
        from apps.finance.tests.test_p1_economic_roles import _usable
        from apps.users.models import User
        other = _usable(User.objects.create_user(email="c2@example.com", password="pw"))
        SpendingClassification.objects.create(
            user=other, scope=SpendingClassification.SCOPE_PAYEE, payee="filmflix",
            levers=[SpendingClassification.LEVER_CANCELLABLE])
        verdict = C.resolve(self.txn, C.active_classifications(self.user))
        self.assertFalse(verdict.is_known)


class ControllableMeasureTests(RoleBase):
    def setUp(self):
        super().setUp()
        self._txn(-100, primary="ENTERTAINMENT", description="Filmflix")
        self._txn(-400, primary="RENT_AND_UTILITIES", description="Landlord")

    def test_silence_is_not_controllable(self):
        m = M.all_measures(self.user)["controllable_spending"]
        self.assertEqual(m.value, Decimal("0.00"))
        self.assertEqual(m.confidence, "low")
        self.assertIn("controllability_classification", m.inputs_missing)

    def test_silence_is_not_uncontrollable_either(self):
        m = M.all_measures(self.user)["controllable_spending"]
        self.assertEqual(m.exclusions["unclassified_spend"], Decimal("500.00"))
        self.assertIn("NEITHER", " ".join(m.assumptions))

    def test_a_lever_makes_a_cost_controllable(self):
        SpendingClassification.objects.create(
            user=self.user, scope=SpendingClassification.SCOPE_PAYEE,
            payee="filmflix", levers=[SpendingClassification.LEVER_CANCELLABLE])
        m = M.all_measures(self.user)["controllable_spending"]
        self.assertEqual(m.value, Decimal("100.00"))
        self.assertEqual(m.components["cancellable"], Decimal("100.00"))

    def test_a_classification_without_a_lever_is_not_controllable(self):
        SpendingClassification.objects.create(
            user=self.user, scope=SpendingClassification.SCOPE_PAYEE,
            payee="landlord",
            necessity=SpendingClassification.NECESSITY_ESSENTIAL)
        m = M.all_measures(self.user)["controllable_spending"]
        self.assertEqual(m.value, Decimal("0.00"))

    def test_confidence_follows_coverage(self):
        for payee in ("filmflix", "landlord"):
            SpendingClassification.objects.create(
                user=self.user, scope=SpendingClassification.SCOPE_PAYEE, payee=payee,
                levers=[SpendingClassification.LEVER_REDUCIBLE])
        m = M.all_measures(self.user)["controllable_spending"]
        self.assertEqual(m.confidence, "high")
        self.assertEqual(m.value, Decimal("500.00"))

    def test_only_purchases_can_be_controllable(self):
        """A transfer is not a cost, so it cannot be a saving."""
        SpendingClassification.objects.create(
            user=self.user, scope=SpendingClassification.SCOPE_RULE,
            match_contains="row", levers=[SpendingClassification.LEVER_CANCELLABLE])
        self._txn(-2000, state=Transaction.TRANSFER_STATE_CONFIRMED,
                  kind=Transaction.TRANSFER_KIND_INTERNAL,
                  by=Transaction.TRANSFER_BY_PROVIDER)
        m = M.all_measures(self.user)["controllable_spending"]
        self.assertNotIn("2000", str(m.value))
