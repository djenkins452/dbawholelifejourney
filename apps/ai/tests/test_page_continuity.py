"""Page-awareness continuity — keeps follow-ups grounded in the active content
page instead of being hijacked by a stale health thread. Cache-based, bounded."""

from django.test import SimpleTestCase

from apps.ai import page_context_state as pcs


class _Conv:
    def __init__(self, cid):
        self.id = cid


class PageContinuityTests(SimpleTestCase):
    def setUp(self):
        from django.core.cache import cache
        cache.clear()

    def test_absent_by_default(self):
        self.assertFalse(pcs.active_page_present(_Conv(1)))

    def test_remember_then_present(self):
        conv = _Conv(2)
        pcs.remember_active_page(conv)
        self.assertTrue(pcs.active_page_present(conv))

    def test_scoped_per_conversation(self):
        pcs.remember_active_page(_Conv(3))
        self.assertFalse(pcs.active_page_present(_Conv(4)))

    def test_no_conversation_is_safe(self):
        # No id → no key → never raises, never present.
        pcs.remember_active_page(object())
        self.assertFalse(pcs.active_page_present(object()))

    def test_disabled_flag_is_noop(self):
        conv = _Conv(5)
        with self.settings(WLJ_BETH_PAGE_CONTINUITY=False):
            pcs.remember_active_page(conv)
            self.assertFalse(pcs.active_page_present(conv))

    def test_router_defers_health_followup_when_page_active(self):
        # Integration-ish: the router's health-continuity branch must NOT hijack a
        # follow-up when a content page is active (it checks active_page_present).
        import inspect
        from apps.ai import deterministic_router as dr
        src = inspect.getsource(dr.classify_and_route)
        self.assertIn("active_page_present", src)
        self.assertIn("not _on_content_page", src)
