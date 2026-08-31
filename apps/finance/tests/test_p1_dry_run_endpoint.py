# ==============================================================================
# File: apps/finance/tests/test_p1_dry_run_endpoint.py
# Project: Whole Life Journey - Django 5.x Personal Wellness/Journaling App
# Description: TEMPORARY — guards the one-shot P1 dry-run operator endpoint.
# Owner: Danny Jenkins (admin@wholelifejourney.com)
# ==============================================================================
"""Delete this file in the SAME commit that deletes the endpoint.

It proves the two things that make a production rehearsal safe to run: the endpoint
cannot be reached without the operator key, and invoking it leaves every shadow column
exactly as it found it.
"""

from django.urls import reverse

from apps.finance.models import Transaction
from apps.finance.tests.test_p1_economic_roles import RoleBase


class DryRunEndpointTests(RoleBase):
    def setUp(self):
        super().setUp()
        self.url = reverse('admin_console:api_claude_finance_p1_dry_run')

    def test_no_key_no_report(self):
        with self.settings(CLAUDE_API_KEY='test-operator-key'):
            resp = self.client.get(self.url, {'email': self.user.email})
        self.assertEqual(resp.status_code, 401)

    def test_wrong_key_no_report(self):
        with self.settings(CLAUDE_API_KEY='test-operator-key'):
            resp = self.client.get(self.url, {'email': self.user.email},
                                   HTTP_X_CLAUDE_API_KEY='not-the-key')
        self.assertEqual(resp.status_code, 401)

    def test_an_unconfigured_server_refuses_rather_than_reporting(self):
        """No operator key on the server is a refusal, not an open door."""
        with self.settings(CLAUDE_API_KEY=''):
            resp = self.client.get(self.url, {'email': self.user.email},
                                   HTTP_X_CLAUDE_API_KEY='anything')
        self.assertEqual(resp.status_code, 500)
        self.assertNotIn('measures', resp.json())

    def test_the_rehearsal_writes_nothing(self):
        self._txn(-40, primary="FOOD_AND_DRINK")
        self._txn(2500, primary="INCOME")
        with self.settings(CLAUDE_API_KEY='test-operator-key'):
            resp = self.client.get(self.url, {'email': self.user.email},
                                   HTTP_X_CLAUDE_API_KEY='test-operator-key')
        self.assertEqual(resp.status_code, 200)
        body = resp.json()
        self.assertTrue(body['read_only_proof']['shadow_population_untouched'])
        self.assertEqual(
            Transaction.objects.filter(economic_role__isnull=False).count(), 0)
        self.assertIn('measures', body)
        self.assertIn('reconciliation', body)

    def test_report_carries_no_descriptions_or_merchants(self):
        self._txn(-40, primary="FOOD_AND_DRINK", description="ACME CORP STORE 41")
        with self.settings(CLAUDE_API_KEY='test-operator-key'):
            resp = self.client.get(self.url, {'email': self.user.email},
                                   HTTP_X_CLAUDE_API_KEY='test-operator-key')
        self.assertNotIn('ACME', resp.content.decode())
