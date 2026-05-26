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


def _write_fixture_pack(tmpdir: Path, slug: str, path_data: dict, arcs: list[dict],
                        filenames=None):
    """Write a content pack to disk.

    ``filenames`` lets callers control each arc file's exact filename — used
    by arc_slug tests to exercise filename-match vs slug-fallback paths.
    """
    content_root = tmpdir / "content" / slug
    (content_root / "arcs").mkdir(parents=True)
    with (content_root / "path.json").open("w") as f:
        json.dump(path_data, f)
    for i, arc in enumerate(arcs):
        name = filenames[i] if filenames else f"arc_{i:02d}.json"
        with (content_root / "arcs" / name).open("w") as f:
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
        t_path = JourneyPath.objects.get(slug="t")
        self.assertEqual(JourneyArc.objects.filter(journey_path=t_path).count(), 1)
        self.assertEqual(JourneyDay.objects.filter(arc__journey_path=t_path).count(), 1)

    def test_idempotent(self):
        _write_fixture_pack(self.tmpdir, "t", self._valid_path_data(), [self._valid_arc()])
        self._patch_content_root("t", self.tmpdir / "content" / "t")
        call_command("load_journey_path", "t")
        call_command("load_journey_path", "t")
        t_path = JourneyPath.objects.get(slug="t")
        self.assertEqual(JourneyArc.objects.filter(journey_path=t_path).count(), 1)
        self.assertEqual(JourneyDay.objects.filter(arc__journey_path=t_path).count(), 1)

    def test_dry_run_does_not_write(self):
        _write_fixture_pack(self.tmpdir, "t", self._valid_path_data(), [self._valid_arc()])
        self._patch_content_root("t", self.tmpdir / "content" / "t")
        call_command("load_journey_path", "t", "--dry-run")
        # Assert this specific fixture path was NOT written.
        # (Data migration 0003 pre-loads walking_with_god, which is unrelated.)
        self.assertFalse(JourneyPath.objects.filter(slug="t").exists())

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
        t_path = JourneyPath.objects.get(slug="t")
        loaded_day = JourneyDay.objects.get(arc__journey_path=t_path)
        self.assertEqual(loaded_day.day_number, 15)

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

    # --- arc_slug resolution (fast path + slug fallback) ------------------

    def test_arc_slug_filename_fast_path_loads_only_named_arc(self):
        """When the filename ends with _<arc_slug>, only that arc is loaded."""
        arc_a = self._valid_arc(slug="alpha", order=1)
        arc_b = self._valid_arc(slug="beta", order=2)
        _write_fixture_pack(
            self.tmpdir, "t", self._valid_path_data(), [arc_a, arc_b],
            filenames=["arc_01_alpha.json", "arc_02_beta.json"],
        )
        self._patch_content_root("t", self.tmpdir / "content" / "t")
        call_command("load_journey_path", "t", arc_slug="alpha")
        t_path = JourneyPath.objects.get(slug="t")
        arc_slugs = set(JourneyArc.objects.filter(journey_path=t_path).values_list("slug", flat=True))
        self.assertEqual(arc_slugs, {"alpha"})

    def test_arc_slug_falls_back_to_json_slug_when_filename_unrelated(self):
        """JSON `slug` is canonical: filename need not encode it."""
        arc = self._valid_arc(slug="canonical_slug", order=1)
        _write_fixture_pack(
            self.tmpdir, "t", self._valid_path_data(), [arc],
            filenames=["unrelated_filename.json"],
        )
        self._patch_content_root("t", self.tmpdir / "content" / "t")
        call_command("load_journey_path", "t", arc_slug="canonical_slug")
        t_path = JourneyPath.objects.get(slug="t")
        self.assertTrue(
            JourneyArc.objects.filter(journey_path=t_path, slug="canonical_slug").exists()
        )

    def test_arc_slug_unknown_slug_raises(self):
        """A slug that matches neither filename nor JSON content raises clearly."""
        arc = self._valid_arc(slug="known_slug", order=1)
        _write_fixture_pack(self.tmpdir, "t", self._valid_path_data(), [arc])
        self._patch_content_root("t", self.tmpdir / "content" / "t")
        with self.assertRaises(CommandError):
            call_command("load_journey_path", "t", arc_slug="missing_slug")

    def test_arc_slug_filename_match_skips_other_arcs(self):
        """Other on-disk arc files are not validated when arc_slug narrows the set."""
        good_arc = self._valid_arc(slug="alpha", order=1)
        bad_arc = self._valid_arc(slug="beta", order=2)
        # Inject an invalid day into `beta` — would fail full validation.
        bad_arc["days"][0] = dict(VALID_DAY, key_insight="x" * 250)
        _write_fixture_pack(
            self.tmpdir, "t", self._valid_path_data(), [good_arc, bad_arc],
            filenames=["arc_01_alpha.json", "arc_02_beta.json"],
        )
        self._patch_content_root("t", self.tmpdir / "content" / "t")
        # arc_slug=alpha must succeed even though beta is invalid on disk.
        call_command("load_journey_path", "t", arc_slug="alpha")
        t_path = JourneyPath.objects.get(slug="t")
        self.assertEqual(
            set(JourneyArc.objects.filter(journey_path=t_path).values_list("slug", flat=True)),
            {"alpha"},
        )


class RealContentPackTest(TestCase):
    """Smoke test: the actual Day 15 content pack on disk loads cleanly."""

    def test_walking_with_god_pack_loads(self):
        call_command("load_journey_path", "walking_with_god")
        path = JourneyPath.objects.get(slug="walking_with_god")
        self.assertEqual(path.name, "Walking With God Through Scripture")
        self.assertTrue(path.is_active)  # Arc 1 launch: path is published

        arc = JourneyArc.objects.get(journey_path=path, slug="creation_to_egypt")
        self.assertEqual(arc.order, 1)
        self.assertEqual(arc.era_label, "Genesis")
        self.assertTrue(arc.is_active)  # Arc 1 is published for users

        # Spot-check Day 1 (Creation, Genesis 1-2)
        day1 = JourneyDay.objects.get(arc=arc, day_number=1)
        self.assertIn("Genesis 1:1-31", day1.scripture_refs)
        self.assertEqual(day1.scripture_content["translation"], "WEB")
        self.assertGreaterEqual(len(day1.scripture_content["blocks"]), 31)
        self.assertGreaterEqual(len(day1.confusion_topics), 3)
        self.assertTrue(day1.retention_anchor)
        self.assertLessEqual(len(day1.key_insight), 200)
        self.assertLessEqual(len(day1.application_action), 280)

        # All 7 days authored, sequential, every day passes schema
        all_days = JourneyDay.objects.filter(arc=arc).order_by("day_number")
        self.assertEqual(all_days.count(), 7)
        self.assertEqual([d.day_number for d in all_days], [1, 2, 3, 4, 5, 6, 7])
        for d in all_days:
            self.assertGreaterEqual(len(d.confusion_topics), 3, f"Day {d.day_number} confusion_topics")
            self.assertLessEqual(len(d.key_insight), 200, f"Day {d.day_number} key_insight")
            self.assertLessEqual(len(d.application_action), 280, f"Day {d.day_number} application_action")
            self.assertTrue(d.retention_anchor, f"Day {d.day_number} retention_anchor")
            self.assertTrue(d.plain_english_simple, f"Day {d.day_number} simple tier")
            self.assertTrue(d.plain_english_standard, f"Day {d.day_number} standard tier")
            self.assertTrue(d.plain_english_deeper, f"Day {d.day_number} deeper tier")
