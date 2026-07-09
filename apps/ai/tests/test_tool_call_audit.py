# ==============================================================================
# File: apps/ai/tests/test_tool_call_audit.py
# Project: Whole Life Journey - Django 5.x Personal Wellness/Journaling App
# Description: Tool-call audit ledger (Audit pillar of the model interface).
# ==============================================================================
"""
Tests for the append-only tool-call audit (docs/WLJ_MODEL_INTERFACE_DESIGN.md §8).

Locks in: the four record kinds answer the four audit questions; the recorder is
request-path-safe (never raises); payloads are JSON-safe and bounded.
"""

from unittest import mock

from django.contrib.auth import get_user_model
from django.test import TestCase

from apps.ai.cos_services.audit import record_tool_call
from apps.ai.models import ToolCallLog

User = get_user_model()


class ToolCallAuditTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.user = User.objects.create_user(email="audit@example.com", password="x")

    def test_records_the_four_kinds_for_one_turn(self):
        turn = "turn-abc"
        record_tool_call(self.user, kind="truth", tool_name="get_sleep",
                         turn_id=turn, args={"metric": "last_night"},
                         result_status="ok", result_digest={"value": "6h12m"})
        record_tool_call(self.user, kind="action", tool_name="mutate_task",
                         turn_id=turn, args={"id": 5, "time": "21:00"},
                         result_status="confirmation_required")
        record_tool_call(self.user, kind="action", tool_name="mutate_task",
                         turn_id=turn, result_status="ok",
                         result_digest={"message": "moved to 9:00 PM"})
        record_tool_call(self.user, kind="response", turn_id=turn,
                         result_digest={"text": "Done — moved it."})

        rows = ToolCallLog.objects.filter(user=self.user, turn_id=turn)
        self.assertEqual(rows.count(), 4)
        kinds = set(rows.values_list("kind", flat=True))
        self.assertEqual(kinds, {"truth", "action", "response"})
        # Q3 "what actually occurred" is answerable: the executed action row.
        occurred = rows.filter(kind="action", result_status="ok").first()
        self.assertEqual(occurred.result_digest["message"], "moved to 9:00 PM")

    def test_recorder_never_raises_on_db_failure(self):
        # A failed audit write must not break the turn — it returns None, not raises.
        with mock.patch(
            "apps.ai.models.ToolCallLog.objects.create",
            side_effect=RuntimeError("db down"),
        ):
            result = record_tool_call(self.user, kind="truth", tool_name="x")
        self.assertIsNone(result)

    def test_payload_is_json_safe_and_bounded(self):
        # Non-JSON-native values (datetime) are coerced; huge payloads are truncated.
        from django.utils import timezone
        big = {"blob": "z" * 9000, "when": timezone.now()}
        row = record_tool_call(self.user, kind="truth", tool_name="big",
                               args=big, result_digest=big)
        row.refresh_from_db()
        import json
        json.dumps(row.args)          # must serialize
        json.dumps(row.result_digest)
        self.assertTrue(row.args.get("_truncated"))

    def test_append_only_creates_distinct_rows(self):
        record_tool_call(self.user, kind="truth", tool_name="a", turn_id="t1")
        record_tool_call(self.user, kind="truth", tool_name="a", turn_id="t1")
        self.assertEqual(
            ToolCallLog.objects.filter(user=self.user, tool_name="a").count(), 2
        )
