"""Regression guard: the CoS context builders must never be parallelised
while the calling connection holds an open transaction.

Why this file exists
--------------------
`build_cos_context` fans its builders out over a `ThreadPoolExecutor` for
latency. Each thread runs on its OWN database connection. If the CALLING
connection is inside a transaction, that is a deadlock:

* the caller holds uncommitted rows,
* a builder thread's independent connection blocks on those row locks,
* and `ThreadPoolExecutor.__exit__` joins that thread with **no timeout**.

Neither side can move. On 2026-08-20 this hung `manage.py test apps.ai`
against Postgres indefinitely (main thread in `concurrent.futures.thread.
shutdown`; three builder backends in `Lock/transactionid` behind the test
transaction's uncommitted `core_personaloperatingblueprint` INSERT). The
existing `as_completed(timeout=10)` / `future.result(timeout=5)` guards did
NOT help — they bound only the wait for *results*, never the join at pool exit.

These tests fail loudly rather than hanging: the end-to-end check replaces
`ThreadPoolExecutor` with a mock that refuses to run, so a regression is a
FAILED assertion, never a frozen suite.

Project: Whole Life Journey
Path: apps/core/tests/test_cos_context_transaction_safety.py
"""

from unittest import mock

from django.conf import settings
from django.contrib.auth import get_user_model
from django.db import connection, transaction
from django.test import TestCase

from apps.core.ai_orchestrator import cos_context
from apps.core.ai_orchestrator.cos_context import _parallel_builders_allowed

User = get_user_model()

POSTGRES = 'django.db.backends.postgresql'
SQLITE = 'django.db.backends.sqlite3'


class ParallelBuilderDecisionTests(TestCase):
    """The pure decision — every combination of the two forbidding conditions."""

    def test_allowed_outside_transaction_on_a_threadsafe_backend(self):
        self.assertTrue(_parallel_builders_allowed(POSTGRES, False))

    def test_refused_inside_open_transaction(self):
        """The deadlock condition. This is the assertion that matters."""
        self.assertFalse(
            _parallel_builders_allowed(POSTGRES, True),
            "Builders must run sequentially inside a transaction: threads use "
            "separate connections and will block on the caller's uncommitted "
            "rows while the caller joins them unbounded.",
        )

    def test_refused_on_sqlite_regardless_of_transaction_state(self):
        """Each SQLite thread gets its own (empty) database."""
        self.assertFalse(_parallel_builders_allowed(SQLITE, False))
        self.assertFalse(_parallel_builders_allowed(SQLITE, True))

    def test_missing_engine_string_is_tolerated(self):
        self.assertTrue(_parallel_builders_allowed('', False))
        self.assertTrue(_parallel_builders_allowed(None, False))


class BuildCosContextTransactionSafetyTests(TestCase):
    """End-to-end: `build_cos_context` must not construct a thread pool while
    a transaction is open — including the implicit one wrapping every TestCase.
    """

    @classmethod
    def setUpTestData(cls):
        cls.user = User.objects.create_user(
            email='cos_txn_safety@test.com', password='x',
        )

    def test_testcase_body_really_is_inside_a_transaction(self):
        """Anchors the premise of the test below — if Django ever stopped
        wrapping TestCase in atomic, the guard below would pass vacuously."""
        self.assertTrue(connection.in_atomic_block)

    def _assert_no_thread_pool(self):
        """Run a context build with ThreadPoolExecutor booby-trapped.

        The mock raises if constructed. `build_cos_context` catches builder
        errors and falls back to sequential, so a regression cannot hang the
        suite — it just trips the `called` assertion below.
        """
        boom = mock.MagicMock(
            side_effect=RuntimeError('ThreadPoolExecutor must not be used here')
        )
        with mock.patch.object(cos_context, 'ThreadPoolExecutor', boom):
            context = cos_context.build_cos_context(self.user)

        self.assertIsInstance(context, dict)
        self.assertFalse(
            boom.called,
            "build_cos_context parallelised its builders while a transaction "
            "was open — this is the unbounded-join deadlock. Builders must run "
            "sequentially on the caller's connection.",
        )

    def test_no_thread_pool_inside_implicit_testcase_transaction(self):
        # Force the non-SQLite branch so the transaction guard is the ONLY
        # thing standing between us and the thread pool. Read-only patch of the
        # settings dict — the live connection is untouched.
        with mock.patch.dict(
            settings.DATABASES['default'], {'ENGINE': POSTGRES}
        ):
            self._assert_no_thread_pool()

    def test_no_thread_pool_inside_explicit_atomic_block(self):
        with mock.patch.dict(
            settings.DATABASES['default'], {'ENGINE': POSTGRES}
        ), transaction.atomic():
            self._assert_no_thread_pool()
