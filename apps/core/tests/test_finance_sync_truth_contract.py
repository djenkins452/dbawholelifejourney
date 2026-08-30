# ==============================================================================
# File: apps/core/tests/test_finance_sync_truth_contract.py
# Project: Whole Life Journey - Django 5.x Personal Wellness/Journaling App
# Description: WLJ's actual Plaid synchronization behaviour is exposed as truth
# Owner: Danny Jenkins (admin@wholelifejourney.com)
# Created: 2026-08-20
# ==============================================================================
""""How do my finance accounts update through Plaid?"

The Chief of Staff answered that from generic provider knowledge and suggested a manual
refresh might fix stale data. WLJ does not work that way — and the state needed to answer
correctly (last sync, connection health, whether action is genuinely required) was sitting
on `BankConnection` the whole time, simply never exposed as truth. A Layer-1 ACCESSIBILITY
gap, not a missing capability.

Two things must hold, and this file certifies both:

  1. the per-connection state is retrievable;
  2. the MECHANICS travel with it, so the model never has to fall back on what it happens
     to know about Plaid in general.

The single most important negative: **Sync Now does not force the bank to refresh.** No
answer may imply otherwise, and no answer may tell the user routine manual action is needed.
No provider calls.
"""

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.utils import timezone

from apps.core.truth.domain import get_domain_truth
from apps.core.truth.semantics import domain_semantics
from apps.finance.models import BankConnection

User = get_user_model()


def _entity_dict(e):
    return e.to_dict() if hasattr(e, "to_dict") else dict(e.__dict__)


class ConnectionTruthTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(email="sync@contract.test", password="x")
        self.healthy = BankConnection.objects.create(
            user=self.user, institution_name="Test Credit Union", item_id="itm-ok",
            connection_status=BankConnection.STATUS_ACTIVE,
            last_sync_at=timezone.now(), transactions_synced=412,
            initial_update_complete=True, historical_update_complete=True)
        self.truth = get_domain_truth(self.user, "finance")

    def _connections(self):
        return [_entity_dict(e) for e in self.truth.describe("connection")]

    def test_connection_is_an_advertised_entity_type(self):
        self.assertIn("connection", self.truth.entity_types)

    def test_wlj_last_successful_sync_is_exposed(self):
        standing = self._connections()[0]["standing"]
        self.assertIsNotNone(standing["wlj_last_sync_at"])
        self.assertEqual(standing["transactions_synced_total"], 412)

    def test_connection_health_is_exposed(self):
        conn = self._connections()[0]
        self.assertEqual(conn["status"], BankConnection.STATUS_ACTIVE)
        self.assertFalse(conn["standing"]["user_action_required"])

    def test_backfill_completion_is_exposed(self):
        standing = self._connections()[0]["standing"]
        self.assertTrue(standing["initial_window_complete"])
        self.assertTrue(standing["historical_backfill_complete"])

    def test_no_credential_or_cursor_VALUE_ever_leaves_the_surface(self):
        """The surface must not become a way to read secrets.

        Asserts on the VALUES, not the word: the mechanics legitimately say Sync Now is
        "cursor-based", so banning the substring would fail on correct copy while missing
        an actual leak.
        """
        self.healthy.last_sync_cursor = "CURSOR-VALUE-MUST-NOT-LEAK"
        # Write the stored field directly — this asserts the SURFACE does not
        # expose it; it is not a test of the encryption helper.
        self.healthy.access_token_encrypted = "TOKEN-VALUE-MUST-NOT-LEAK"
        self.healthy.save()
        blob = repr(self._connections())
        self.assertNotIn("CURSOR-VALUE-MUST-NOT-LEAK", blob)
        self.assertNotIn("TOKEN-VALUE-MUST-NOT-LEAK", blob)
        for banned in ("access_token", "access_token_encrypted", "client_id"):
            self.assertNotIn(banned, blob.lower())


class SyncMechanicsTests(TestCase):
    """The mechanics must be stated, and stated correctly."""

    def setUp(self):
        self.user = User.objects.create_user(email="mech@contract.test", password="x")
        BankConnection.objects.create(
            user=self.user, institution_name="Test Bank", item_id="itm-mech",
            connection_status=BankConnection.STATUS_ACTIVE)
        self.truth = get_domain_truth(self.user, "finance")
        self.mechanics = _entity_dict(
            self.truth.describe("connection")[0])["definition"]["how_it_updates"]

    def test_mechanics_travel_with_the_connection_state(self):
        """If mechanics lived elsewhere they could drift from the state they describe."""
        for key in ("institution_checks", "primary_trigger", "safety_net",
                    "manual_sync_now", "refresh_endpoint", "expectation",
                    "when_action_is_needed"):
            self.assertIn(key, self.mechanics)

    def test_updates_are_described_as_automatic(self):
        text = " ".join(self.mechanics.values()).lower()
        self.assertIn("automatic", text)

    def test_webhooks_are_named_as_the_primary_trigger(self):
        self.assertIn("webhook", self.mechanics["primary_trigger"].lower())

    def test_scheduled_reconciliation_is_described_as_a_safety_net(self):
        text = self.mechanics["safety_net"].lower()
        self.assertIn("safety net", text)
        self.assertIn("not the main path", text)

    def test_sync_now_is_described_as_cursor_based_retrieval(self):
        text = self.mechanics["manual_sync_now"].lower()
        self.assertIn("/transactions/sync", text)
        self.assertIn("already has", text)

    def test_sync_now_explicitly_does_NOT_force_a_bank_refresh(self):
        """The correction that prompted all of this."""
        text = self.mechanics["manual_sync_now"].lower()
        self.assertIn("does not", text)
        self.assertIn("contact the bank", text)

    def test_wlj_states_it_does_not_use_the_refresh_endpoint(self):
        text = self.mechanics["refresh_endpoint"].lower()
        self.assertIn("/transactions/refresh", text)
        self.assertIn("does not use", text)

    def test_data_is_not_promised_to_be_real_time(self):
        self.assertIn("not guaranteed to be real-time",
                      self.mechanics["expectation"].lower())

    def test_reauth_is_tied_to_an_actionable_state_not_to_missing_data(self):
        text = self.mechanics["when_action_is_needed"].lower()
        self.assertIn("login required", text)
        self.assertIn("never merely because", text)

    def test_the_mechanics_never_tell_the_user_to_refresh_to_fix_staleness(self):
        """The exact wrong answer: 'try refreshing and it'll catch up'."""
        text = " ".join(self.mechanics.values()).lower()
        for wrong in ("force plaid", "force a refresh", "forces plaid",
                      "refresh to get the latest", "you must refresh"):
            self.assertNotIn(wrong, text)


class ActionRequiredTests(TestCase):
    """`user_action_required` must mean an actionable state — never 'data looks old'."""

    def setUp(self):
        self.user = User.objects.create_user(email="act@contract.test", password="x")
        self.truth = get_domain_truth(self.user, "finance")

    def _one(self, **kw):
        BankConnection.objects.all().delete()
        BankConnection.objects.create(
            user=self.user, institution_name="Bank", item_id="itm-act", **kw)
        return _entity_dict(self.truth.describe("connection")[0])["standing"]

    def test_reauth_required_sets_action_required(self):
        standing = self._one(connection_status=BankConnection.STATUS_REAUTH_REQUIRED,
                             error_code="ITEM_LOGIN_REQUIRED")
        self.assertTrue(standing["user_action_required"])
        self.assertEqual(standing["error_code"], "ITEM_LOGIN_REQUIRED")

    def test_error_state_sets_action_required(self):
        self.assertTrue(self._one(
            connection_status=BankConnection.STATUS_ERROR)["user_action_required"])

    def test_a_healthy_connection_with_no_recent_sync_does_NOT_require_action(self):
        """The precise mistake to avoid: quiet != broken. A bank that simply has not
        published anything yet must never be reported as needing the user to reconnect."""
        standing = self._one(connection_status=BankConnection.STATUS_ACTIVE,
                             last_sync_at=None)
        self.assertFalse(standing["user_action_required"],
                         "a quiet-but-healthy connection was reported as needing action")

    def test_a_rejected_webhook_is_visible_as_a_wlj_side_fault(self):
        standing = self._one(connection_status=BankConnection.STATUS_ACTIVE,
                             last_webhook_rejected_at=timezone.now(),
                             last_webhook_rejection_reason="bad_signature")
        self.assertIsNotNone(standing["last_webhook_rejected_at"])


class RoutingTests(TestCase):
    """Truth the model cannot find is truth it will not use."""

    def test_the_connection_entity_is_described_by_meaning(self):
        entities = domain_semantics("finance")["entities"]
        self.assertIn("connection", entities)
        desc = entities["connection"].lower()
        self.assertIn("how and when money data actually arrives", desc)
        self.assertIn("never answer those from general knowledge", desc)

    def test_sync_questions_have_routing_cues(self):
        cues = " | ".join(domain_semantics("finance")["cues"]).lower()
        for question in ("how do my accounts update", "does it sync automatically",
                         "do I have to refresh", "why is this transaction missing"):
            self.assertIn(question.lower(), cues,
                          f"no routing cue for {question!r} — the model will answer from "
                          f"generic knowledge again")

    def test_finance_purpose_mentions_the_connections(self):
        self.assertIn("connection", domain_semantics("finance")["purpose"].lower())


class IsolationTests(TestCase):
    def test_connections_are_scoped_to_the_owner(self):
        a = User.objects.create_user(email="own-a@contract.test", password="x")
        b = User.objects.create_user(email="own-b@contract.test", password="x")
        BankConnection.objects.create(user=a, institution_name="A Bank", item_id="itm-a",
                                      connection_status=BankConnection.STATUS_ACTIVE)
        BankConnection.objects.create(user=b, institution_name="B Bank", item_id="itm-b",
                                      connection_status=BankConnection.STATUS_ACTIVE)
        names = [_entity_dict(e)["identity"]
                 for e in get_domain_truth(a, "finance").describe("connection")]
        self.assertEqual(names, ["A Bank"])

    def test_a_user_with_no_connections_gets_an_empty_list_not_an_error(self):
        u = User.objects.create_user(email="none@contract.test", password="x")
        self.assertEqual(get_domain_truth(u, "finance").describe("connection"), [])
