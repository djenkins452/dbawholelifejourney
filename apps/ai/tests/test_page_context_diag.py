"""Log-only page_context diagnostic (Page Awareness H1 proof). Must never raise
and must surface the key flags (content present, scriptures, scripture_text)."""

import logging

from django.test import SimpleTestCase

from apps.ai.views import _log_page_context_diag


class _U:
    id = 7


class PageContextDiagTests(SimpleTestCase):
    def test_never_raises_on_various_shapes(self):
        for pc in (None, {}, {"module": "faith"},
                   {"module": "faith", "page_content": None},
                   {"module": "faith", "page_content": "not-a-dict"},
                   {"module": "faith", "url": "/faith/reading-plans/progress/3/",
                    "page_content": {"type": "reading_plan_progress",
                                     "scriptures": ["Exodus 14:5-31"],
                                     "scripture_text": "x" * 200}}):
            _log_page_context_diag("test", pc, _U())  # must not raise

    def test_flags_logged(self):
        full = {"module": "faith", "url": "/faith/reading-plans/progress/3/",
                "page_title": "Today's Reading",
                "page_content": {"type": "reading_plan_progress",
                                 "scriptures": ["Exodus 14:5-31"],
                                 "scripture_text": "abc"}}
        with self.assertLogs("apps.ai.views", level="INFO") as cm:
            _log_page_context_diag("stream", full, _U())
        line = "\n".join(cm.output)
        self.assertIn("PAGE_CTX_DIAG", line)
        self.assertIn("module=faith", line)
        self.assertIn("has_scriptures=True", line)
        self.assertIn("has_scripture_text=True", line)
        self.assertIn("content_type=reading_plan_progress", line)

    def test_empty_context_logs_absent(self):
        with self.assertLogs("apps.ai.views", level="INFO") as cm:
            _log_page_context_diag("chat", {}, _U())
        line = "\n".join(cm.output)
        self.assertIn("present=False", line)
        self.assertIn("content_present=False", line)
