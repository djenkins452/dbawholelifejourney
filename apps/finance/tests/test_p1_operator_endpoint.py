# ==============================================================================
# File: apps/finance/tests/test_p1_operator_endpoint.py
# Project: Whole Life Journey - Django 5.x Personal Wellness/Journaling App
# Description: TEMPORARY — guards the P1 rehearsal/backfill operator endpoint.
# Owner: Danny Jenkins (admin@wholelifejourney.com)
# ==============================================================================
"""Delete this file in the SAME commit that deletes the endpoint.

An endpoint that can rewrite four thousand financial rows earns its tests: it must be
unreachable without the operator key, it must refuse to write without an explicit
acknowledgement, and its read-only action must actually be read-only.
"""
from django.urls import reverse

from apps.finance.models import Transaction
from apps.finance.tests.test_p1_economic_roles import RoleBase

KEY = 'test-operator-key'


class OperatorEndpointTests(RoleBase):
    def setUp(self):
        super().setUp()
        # The endpoint is rate limited to 5/minute — correct for production, and a
        # shared counter across tests in one process. Each test starts clean.
        from django.core.cache import cache
        cache.clear()
        self.url = reverse('admin_console:api_claude_finance_p1')
        self._txn(-50, primary="FOOD_AND_DRINK")
        self._txn(3000, primary="INCOME")

    def _get(self, **params):
        params.setdefault('email', self.user.email)
        with self.settings(CLAUDE_API_KEY=KEY):
            return self.client.get(self.url, params, HTTP_X_CLAUDE_API_KEY=KEY)

    def test_no_key_no_access(self):
        with self.settings(CLAUDE_API_KEY=KEY):
            resp = self.client.get(self.url, {'email': self.user.email})
        self.assertEqual(resp.status_code, 401)

    def test_an_unconfigured_server_refuses(self):
        with self.settings(CLAUDE_API_KEY=''):
            resp = self.client.get(self.url, {'email': self.user.email},
                                   HTTP_X_CLAUDE_API_KEY='anything')
        self.assertEqual(resp.status_code, 500)

    def test_an_unknown_action_is_refused(self):
        self.assertEqual(self._get(action='destroy').status_code, 400)

    def test_rehearsal_is_read_only(self):
        resp = self._get(action='rehearse')
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.json()['read_only_proof']['classified_after'], 0)
        self.assertEqual(
            Transaction.objects.filter(economic_role__isnull=False).count(), 0)

    def test_the_backfill_refuses_without_an_explicit_acknowledgement(self):
        resp = self._get(action='backfill')
        self.assertEqual(resp.status_code, 400)
        self.assertEqual(
            Transaction.objects.filter(economic_role__isnull=False).count(), 0)

    def test_the_backfill_writes_when_acknowledged(self):
        resp = self._get(action='backfill', reviewed='yes')
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.json()['written'], 2)
        self.assertEqual(
            Transaction.objects.filter(economic_role__isnull=False).count(), 2)

    def test_clear_refuses_without_an_explicit_acknowledgement(self):
        self._get(action='backfill', reviewed='yes')
        self.assertEqual(self._get(action='clear').status_code, 400)
        self.assertEqual(
            Transaction.objects.filter(economic_role__isnull=False).count(), 2)

    def test_verify_reports_coverage_and_reconciliation(self):
        self._get(action='backfill', reviewed='yes')
        body = self._get(action='verify').json()
        self.assertEqual(body['coverage']['unclassified'], 0)
        self.assertTrue(body['reconciliation']['all_hold'])

    def test_the_report_carries_no_descriptions(self):
        self._txn(-40, primary="FOOD_AND_DRINK", description="ACME CORP STORE 41")
        self.assertNotIn('ACME', self._get(action='rehearse').content.decode())

    def test_one_user_cannot_reach_another(self):
        from apps.finance.tests.test_p1_economic_roles import _usable
        from apps.users.models import User
        other = _usable(User.objects.create_user(email="nope@example.com",
                                                 password="pw"))
        body = self._get(action='rehearse', email=other.email).json()
        self.assertEqual(body['population']['transactions'], 0)
