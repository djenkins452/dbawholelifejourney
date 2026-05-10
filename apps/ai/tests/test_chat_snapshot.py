"""Tests for the chat snapshot artifact (B1)."""

import json
import tempfile
from pathlib import Path

from django.test import SimpleTestCase, override_settings

from apps.ai.observability.chat_snapshot import (
    build_snapshot_payload,
    dump_chat_snapshot,
    extract_tier_blob,
    new_request_id,
    parse_prompt_sections,
)


class PromptSectionParsingTests(SimpleTestCase):

    def test_parses_tier_headers(self):
        prompt = (
            "[TIER:canonical_item_truth] DECISIONS\n"
            "  next: X\n"
            "[TIER:rollup_summary] DAILY EXECUTION STATUS\n"
            "  prayer: DONE\n"
            "[TIER:advisory] PLAN\n"
            "  do X\n"
        )
        sections = parse_prompt_sections(prompt)
        tiers = [s["tier"] for s in sections]
        self.assertEqual(
            tiers,
            ["canonical_item_truth", "rollup_summary", "advisory"],
        )

    def test_extract_tier_blob_returns_concatenated_sections(self):
        prompt = (
            "[TIER:canonical_item_truth] A\n  one\n"
            "[TIER:rollup_summary] B\n  two\n"
            "[TIER:canonical_item_truth] C\n  three\n"
        )
        canonical = extract_tier_blob(prompt, "canonical_item_truth")
        self.assertIn("A", canonical)
        self.assertIn("C", canonical)
        self.assertNotIn("B", canonical)

    def test_empty_prompt_returns_empty_list(self):
        self.assertEqual(parse_prompt_sections(""), [])
        self.assertEqual(extract_tier_blob("", "canonical_item_truth"), "")


class SnapshotPayloadTests(SimpleTestCase):

    def test_build_payload_has_all_required_keys(self):
        payload = build_snapshot_payload(
            request_id="r1", user_id=20,
            user_message="status?",
            rendered_prompt="[TIER:canonical_item_truth] DECISIONS\n",
            execution_state={"now": "13:00"},
            selector_outputs={"execution": {"message": "Next: X."}},
            rollup_summaries={"domains": {"prayer": True}},
            contradictions=[],
            narration_validations={"summary": {"passed": 1}},
            llm_response_text="Hello",
            llm_model="gpt-4o", llm_duration_ms=1234,
        )
        for k in (
            "request_id", "user_id", "timestamp", "user_message",
            "prompt_sections", "execution_snapshot", "selector_outputs",
            "rollup_summaries", "contradictions",
            "narration_validations", "llm_response",
        ):
            self.assertIn(k, payload)

    def test_dump_snapshot_no_op_when_flag_disabled(self):
        # Default settings: WLJ_CHAT_SNAPSHOTS_ENABLED is False.
        path = dump_chat_snapshot({"request_id": "rx", "user_id": 1})
        self.assertEqual(path, "")

    @override_settings(WLJ_CHAT_SNAPSHOTS_ENABLED=True)
    def test_dump_snapshot_writes_file_when_flag_enabled(self):
        with tempfile.TemporaryDirectory() as tmp:
            with override_settings(LOG_DIR=Path(tmp)):
                rid = new_request_id()
                payload = build_snapshot_payload(
                    request_id=rid, user_id=20,
                    user_message="m", rendered_prompt="",
                    execution_state={}, selector_outputs={},
                    rollup_summaries={}, contradictions=[],
                    narration_validations={},
                    llm_response_text="ok", llm_model="x",
                    llm_duration_ms=1,
                )
                path = dump_chat_snapshot(payload)
                self.assertTrue(path)
                with open(path) as fh:
                    loaded = json.load(fh)
                self.assertEqual(loaded["request_id"], rid)
                self.assertEqual(loaded["user_id"], 20)
