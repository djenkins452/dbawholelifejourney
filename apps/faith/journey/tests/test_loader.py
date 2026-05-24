"""
Tests for the `load_journey_path` management command.

Exercises:
  - Idempotency (re-running upserts; doesn't duplicate)
  - Validation rules from spec §5 (translation, confusion_topics min, length caps,
    sequence/gap rule gated on is_active, required text fields)
  - Loading the real authored Day 15 content pack ingests cleanly
"""

import json
import tempfile
import shutil
from pathlib import Path
from unittest import mock

from django.apps import apps as django_apps
from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import TestCase

from apps.faith.journey.models import JourneyPath, JourneyArc, JourneyDay


VALID_DAY = {
    "day_number": 1,
    "scripture_refs": ["Genesis 1:1-2"],
    "scripture_content": {
        "translation": "WEB",
        "blocks": [
            {"ref": "Gen 1:1", "verse": 1, "text": "In the beginning God created the heavens and the earth.", "red_letter": False},
            {"ref": "Gen 1:2", "verse": 2, "text": "The earth was formless and empty.", "red_letter": False},
        ],
    },
    "context_before": "...",
    "plain_english_simple": "...",
    "plain_english_standard": "...",
    "plain_english_deeper": "...",
    "key_insight": "A short insight.",
    "reflection_prompt": "A question?",
    "application_action": "Do one small thing.",
    "confusion_topics": [
        {"topic": "Q1", "plain_english_answer": "A1"},
        {"topic": "Q2", "plain_english_answer": "A2"},
        {"topic": "Q3", "plain_english_answer": "A3"},
    ],
    "retention_anchor": "Connects to story arc.",
}


def _write_fixture_pack(tmpdir: Path, slug: str, path_data: dict, arcs: list[dict]):
    content_root = tmpdir / "content" / slug
    (content_root / "arcs").mkdir(parents=True)
    with (content_root / "path.json").open("w") as f:
        json.dump(path_data, f)
    for i, arc in enumerate(arcs):
        with (content_root / "arcs" / f"arc_{i:02d}.json").open("w") as f:
            json.dump(arc, f)
    return content_root


class LoaderTests(TestCase):
    def setUp(self):
        self.tmpdir = Path(tempfile.mkdtemp())

    def tearDown(self):
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    def _patch_content_root(self, slug: str, content_root: Path):
        """Patch the loader's content-root resolver to point at our temp dir."""
        # The loader resolves: Path(journey_app.path) / "content" / slug
        # We patch the journey app's path so its content/<slug> equals our temp dir.
        patcher = mock.patch.object(
            django_apps.get_app_config("journey"),
            "path",
            str(self.tmpdir),
        )
        patcher.start()
        self.addCleanup(patcher.stop)

    def _valid_path_data(self, slug="t"):
        return {
            "slug": slug,
            "name": "Test",
            "narrative_overview": "...",
            "cover_image_url": "",
            "estimated_weeks": 1,
            "difficulty_default": "standard",
            "is_active": False,
            "is_featured": False,
        }

    def _valid_arc(self, slug="arc_x", order=1, days=None, is_active=False):
        return {
            "journey_path": "t",
            "slug": slug,
            "name": "Arc X",
            "era_label": "Era",
            "order": order,
            "opening_note": "...",
            "closing_note": "...",
            "estimated_days": 1,
            "is_active": is_active,
            "days": days if days is not None else [dict(VALID_DAY)],
        }

    # --- happy path -------------------------------------------------------

    def test_loads_valid_pack(self):
        _write_fixture_pack(self.tmpdir, "t", self._valid_path_data(), [self._valid_arc()])
        self._patch_content_root("t", self.tmpdir / "content" / "t")
        call_command("load_journey_path", "t")
        self.assertEqual(JourneyPath.objects.filter(slug="t").count(), 1)
        self.assertEqual(JourneyArc.objects.count(), 1)
        self.assertEqual(JourneyDay.objects.count(), 1)

    def test_idempotent(self):
        _write_fixture_pack(self.tmpdir, "t", self._valid_path_data(), [self._valid_arc()])
        self._patch_content_root("t", self.tmpdir / "content" / "t")
        call_command("load_journey_path", "t")
        call_command("load_journey_path", "t")
        self.assertEqual(JourneyPath.objects.filter(slug="t").count(), 1)
        self.assertEqual(JourneyArc.objects.count(), 1)
        self.assertEqual(JourneyDay.objects.count(), 1)

    def test_dry_run_does_not_write(self):
        _write_fixture_pack(self.tmpdir, "t", self._valid_path_data(), [self._valid_arc()])
        self._patch_content_root("t", self.tmpdir / "content" / "t")
        call_command("load_journey_path", "t", "--dry-run")
        self.assertEqual(JourneyPath.objects.count(), 0)

    # --- validation -------------------------------------------------------

    def test_rejects_wrong_translation(self):
        bad_day = dict(VALID_DAY)
        bad_day["scripture_content"] = {"translation": "ESV", "blocks": [{"ref": "x", "verse": 1, "text": "x", "red_letter": False}]}
        _write_fixture_pack(self.tmpdir, "t", self._valid_path_data(), [self._valid_arc(days=[bad_day])])
        self._patch_content_root("t", self.tmpdir / "content" / "t")
        with self.assertRaises(CommandError):
            call_command("load_journey_path", "t")

    def test_rejects_too_few_confusion_topics(self):
        bad_day = dict(VALID_DAY)
        bad_day["confusion_topics"] = [
            {"topic": "Q1", "plain_english_answer": "A1"},
            {"topic": "Q2", "plain_english_answer": "A2"},
        ]
        _write_fixture_pack(self.tmpdir, "t", self._valid_path_data(), [self._valid_arc(days=[bad_day])])
        self._patch_content_root("t", self.tmpdir / "content" / "t")
        with self.assertRaises(CommandError):
            call_command("load_journey_path", "t")

    def test_rejects_oversized_key_insight(self):
        bad_day = dict(VALID_DAY)
        bad_day["key_insight"] = "x" * 201
        _write_fixture_pack(self.tmpdir, "t", self._valid_path_data(), [self._valid_arc(days=[bad_day])])
        self._patch_content_root("t", self.tmpdir / "content" / "t")
        with self.assertRaises(CommandError):
            call_command("load_journey_path", "t")

    def test_rejects_missing_retention_anchor(self):
        bad_day = dict(VALID_DAY)
        bad_day["retention_anchor"] = ""
        _write_fixture_pack(self.tmpdir, "t", self._valid_path_data(), [self._valid_arc(days=[bad_day])])
        self._patch_content_root("t", self.tmpdir / "content" / "t")
        with self.assertRaises(CommandError):
            call_command("load_journey_path", "t")

    def test_sequence_gap_check_skipped_when_arc_inactive(self):
        """Non-contiguous day_numbers OK when arc is_active=False (incremental authoring)."""
        gap_day = dict(VALID_DAY, day_number=15)
        _write_fixture_pack(self.tmpdir, "t", self._valid_path_data(), [self._valid_arc(days=[gap_day], is_active=False)])
        self._patch_content_root("t", self.tmpdir / "content" / "t")
        call_command("load_journey_path", "t")
        self.assertEqual(JourneyDay.objects.first().day_number, 15)

    def test_sequence_gap_check_enforced_when_arc_active(self):
        """Non-contiguous day_numbers REJECTED when arc is_active=True."""
        gap_day = dict(VALID_DAY, day_number=15)
        _write_fixture_pack(self.tmpdir, "t", self._valid_path_data(), [self._valid_arc(days=[gap_day], is_active=True)])
        self._patch_content_root("t", self.tmpdir / "content" / "t")
        with self.assertRaises(CommandError):
            call_command("load_journey_path", "t")

    def test_rejects_duplicate_day_numbers(self):
        bad_arc = self._valid_arc(days=[dict(VALID_DAY, day_number=1), dict(VALID_DAY, day_number=1)])
        _write_fixture_pack(self.tmpdir, "t", self._valid_path_data(), [bad_arc])
        self._patch_content_root("t", self.tmpdir / "content" / "t")
        with self.assertRaises(CommandError):
            call_command("load_journey_path", "t")


class RealContentPackTest(TestCase):
    """Smoke test: the actual Day 15 content pack on disk loads cleanly."""

    def test_walking_with_god_pack_loads(self):
        call_command("load_journey_path", "walking_with_god")
        path = JourneyPath.objects.get(slug="walking_with_god")
        self.assertEqual(path.name, "Walking With God Through Scripture")
        self.assertFalse(path.is_active)  # publish-gated

        arc = JourneyArc.objects.get(journey_path=path, slug="egypt_to_tabernacle")
        self.assertEqual(arc.order, 1)
        self.assertEqual(arc.era_label, "Exodus")
        self.assertFalse(arc.is_active)

        day = JourneyDay.objects.get(arc=arc, day_number=15)
        self.assertEqual(day.scripture_refs, ["Leviticus 1:1-17"])
        self.assertEqual(day.scripture_content["translation"], "WEB")
        self.assertEqual(len(day.scripture_content["blocks"]), 17)
        self.assertGreaterEqual(len(day.confusion_topics), 3)
        self.assertTrue(day.retention_anchor)
        self.assertLessEqual(len(day.key_insight), 200)
        self.assertLessEqual(len(day.application_action), 280)
