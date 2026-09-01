# ==============================================================================
# File: apps/finance/tests/test_finance_claim_integrity.py
# Description: Contract — FINANCE TRUST INCIDENT (2026-08-31).
#
#   Two independent defects, both proven from production ToolCallLog:
#
#   1. PERIOD. On Aug 31 "this past month" resolved to `last_month` = all of JULY, so
#      an August question was answered with July data and every August transaction the
#      user then named looked like an omission.
#   2. CLAIM INTEGRITY. The user asked "didn't July have a $2,300 house payment?" — no
#      such transaction exists — and the assistant asserted "$2,300.00" as fact in a
#      turn that called NO tool (`tools_called: []`).
#
#   Spend semantics are owned by Finance 2.0 (`measures.spend_magnitude` /
#   `could_be_consumption_q`); these tests assert the CoS consumes that authority
#   rather than re-deciding what "spend" means.
#
#   Fixtures only. ZERO provider calls.
# ==============================================================================
import inspect
from datetime import date, timedelta
from decimal import Decimal

from django.contrib.auth import get_user_model
from unittest import expectedFailure

from django.test import SimpleTestCase, TestCase
from django.utils import timezone

from apps.core.truth.periods import resolve_date_expression, resolve_period


class PeriodVocabularyTests(SimpleTestCase):
    """Decision 2 — frozen centrally so no domain can drift."""

    TODAY = date(2026, 8, 31)          # the production date of the incident

    def test_this_month_is_the_current_calendar_month(self):
        p = resolve_period("this_month", self.TODAY)
        self.assertEqual((p.start, p.end), (date(2026, 8, 1), date(2026, 8, 31)))

    def test_last_month_remains_the_previous_calendar_month(self):
        p = resolve_period("last_month", self.TODAY)
        self.assertEqual((p.start, p.end), (date(2026, 7, 1), date(2026, 7, 31)))

    def test_past_month_is_the_trailing_30_days(self):
        """The incident: this resolved to all of July."""
        p = resolve_date_expression("past month", self.TODAY)
        self.assertEqual((p.start, p.end), (date(2026, 8, 2), date(2026, 8, 31)))

    def test_this_past_month_matches_past_month(self):
        a = resolve_date_expression("this past month", self.TODAY)
        b = resolve_date_expression("past month", self.TODAY)
        self.assertEqual((a.start, a.end), (b.start, b.end))

    def test_past_30_days_is_the_trailing_30_days(self):
        p = resolve_date_expression("past 30 days", self.TODAY)
        self.assertEqual((p.start, p.end), (date(2026, 8, 2), date(2026, 8, 31)))

    def test_past_month_and_last_month_are_different_questions(self):
        a = resolve_date_expression("past month", self.TODAY)
        b = resolve_date_expression("last month", self.TODAY)
        self.assertNotEqual((a.start, a.end), (b.start, b.end),
                            "'past month' collapsed back onto 'last month'")

    def test_the_ranked_tool_tells_the_model_not_to_translate_the_phrase(self):
        from apps.ai.cos_services import domain_ranked_entity as dre
        src = inspect.getsource(dre.get_domain_ranked_entity)
        self.assertIn("do not translate them", src)


class ClaimIntegrityAnchorTests(SimpleTestCase):
    """Decision 3 — a user-supplied value is a hypothesis, never adopted truth.

    Asserted at the ANCHOR (the opening internal question), because that placement is
    what has been proven to change tool-selection behaviour (`03 §10b`); the same rule
    stated only mid-prompt did not fire.
    """

    def setUp(self):
        from apps.ai.model_interface.constitution import CONSTITUTION
        self.c = CONSTITUTION
        self.low = CONSTITUTION.lower()

    def test_the_rule_exists_and_is_unambiguous(self):
        self.assertIn("a number the user says is not a fact wlj holds", self.low)
        self.assertIn("hypothesis to check", self.low)
        self.assertIn("agreeing is not verifying", self.low)

    def test_it_forbids_agreeing_first(self):
        self.assertIn("do not open with 'you're right'", self.low)
        self.assertIn("say you will check", self.low)

    def test_repeating_the_users_number_is_named_as_fabrication(self):
        self.assertIn("is a fabrication even though they said it", self.low)

    def test_a_challenge_triggers_verification_not_substitution(self):
        self.assertIn("a challenge is a reason to look again, never a reason to switch",
                      self.low)

    def test_it_sits_inside_the_opening_internal_question_block(self):
        start = self.c.find("HOW A CHIEF OF STAFF BEGINS")
        end = self.c.find("You are the user's personal assistant")
        anchor = self.c.find("A NUMBER THE USER SAYS IS NOT A FACT")
        self.assertTrue(start < anchor < end,
                        "the rule must be read BEFORE the model decides it needs no tool")

    def test_it_precedes_the_mid_prompt_conflict_clause(self):
        self.assertLess(self.c.find("A NUMBER THE USER SAYS IS NOT A FACT"),
                        self.c.find("CONFLICT — WHEN THE USER CHALLENGES A VALUE"))

    def test_no_incident_specific_rule(self):
        """The reproducer may be cited as prose; it may never be the mechanism."""
        for banned in ("2300", "2,300", "house payment", "849.84"):
            self.assertNotIn(banned, self.low.replace("$2,300 house payment", ""))


class SpendSemanticsAreDelegatedTests(TestCase):
    """Decision 1 — the CoS consumes the Finance authority; it holds no rival
    definition of "spend"."""

    @classmethod
    def setUpTestData(cls):
        from apps.finance.models import FinancialAccount
        cls.user = get_user_model().objects.create_user(
            email="claimintegrity@test.com", password="x")
        cls.acct = FinancialAccount.objects.create(
            user=cls.user, name="Checking", account_type="checking")

    def _tx(self, amount, *, days_ago=3, payee="M", **kw):
        from apps.finance.models import Transaction
        return Transaction.objects.create(
            user=self.user, account=self.acct, amount=Decimal(str(amount)),
            date=timezone.localdate() - timedelta(days=days_ago),
            description=payee, payee=payee, **kw)

    def test_the_truth_surface_asks_the_measure_authority(self):
        from apps.finance.services import finance_domain_truth as fdt
        src = inspect.getsource(fdt.FinanceDomainTruth._transaction_entity)
        self.assertIn("spend_magnitude", src)
        self.assertNotIn("abs(float(t.amount)) if t.amount < 0", src,
                         "the CoS is still reading 'spend' off the sign")

    def test_the_ranked_bound_uses_the_consumption_population(self):
        from apps.finance.services import finance_domain_truth as fdt
        src = inspect.getsource(fdt.FinanceDomainTruth.describe)
        self.assertIn("could_be_consumption_q", src)

    # NOTE: `spend_magnitude` classifies LIVE via the role authority — it does not read
    # a persisted `economic_role` — so these drive it with the provider category the
    # classifier actually consumes. That live behaviour is also why the ranking does not
    # depend on a backfill having run.
    def test_a_loan_payment_is_not_consumption(self):
        """The production row: an auto-loan payment that outranked every purchase."""
        from apps.finance.services.finance_calc import measures as M
        t = self._tx(-900.00, payee="Loan Servicer",
                     provider_category_primary="LOAN_PAYMENTS")
        self.assertIsNone(M.spend_magnitude(t), "debt service ranked as a purchase")

    def test_a_transfer_marked_card_payment_never_reaches_the_spend_population(self):
        """How production is actually protected today: the $5,000 CRDEPAY was excluded
        by `financial_activity` as a TRANSFER, before roles were consulted at all."""
        from apps.finance.models import Transaction
        from apps.finance.services.attribution_population import financial_activity
        self._tx(-5000.00, payee="Card Payment",
                 transfer_state=Transaction.TRANSFER_STATE_CONFIRMED)
        self.assertEqual(
            financial_activity(self.user).filter(payee="Card Payment").count(), 0)

    @expectedFailure
    def test_KNOWN_GAP_unpaired_card_payment_from_cash_ranks_as_a_purchase(self):
        """DOCUMENTED GAP — reported to the Finance owner, deliberately NOT patched here.

        A credit-card payment made FROM a cash account, carrying the provider's own
        `LOAN_PAYMENTS_CREDIT_CARD_PAYMENT` detail but NOT transfer-paired, classifies
        as `purchase` and returns a spend magnitude — so it would rank as spending and
        double-count purchases already counted on the card.

        Production is currently protected only because Danny's card payments ARE
        transfer-paired (see the test above). This is a gap in the role authority
        (`finance_calc/roles.py`), which another session owns; the sequencing rule for
        this incident forbids editing their module to unblock myself. Marked
        `expectedFailure` so it is visible in CI and flips to a failure the moment the
        owner closes it — at which point this decorator comes off.
        """
        from apps.finance.services.finance_calc import measures as M
        t = self._tx(-5000.00, payee="Card Payment From Checking",
                     provider_category_primary="LOAN_PAYMENTS",
                     provider_category_detailed="LOAN_PAYMENTS_CREDIT_CARD_PAYMENT")
        self.assertIsNone(M.spend_magnitude(t))

    def test_a_purchase_has_a_spend_magnitude(self):
        from apps.finance.services.finance_calc import measures as M
        t = self._tx(-120.00, payee="Store",
                     provider_category_primary="GENERAL_MERCHANDISE")
        self.assertEqual(M.spend_magnitude(t), Decimal("120.00"))

    def test_income_is_not_consumption(self):
        from apps.finance.services.finance_calc import measures as M
        t = self._tx(5400.00, payee="Payroll", provider_category_primary="INCOME")
        self.assertIsNone(M.spend_magnitude(t))
