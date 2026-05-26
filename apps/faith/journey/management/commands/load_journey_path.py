"""
Management command: load_journey_path <slug>

Loads a JourneyPath (and its arcs/days) from JSON content packs into the
database. Idempotent: re-running upserts, never duplicates.

Expected file layout under apps/faith/journey/content/<slug>/:
    path.json                       — JourneyPath fields
    arcs/<arc_slug>.json            — JourneyArc + its days

Schema validation rules (see docs/CLAUDE_WALKING_WITH_GOD.md §5):
    - All required fields populated on every day
    - day_number values unique within an arc and ≥ 1
    - Sequence/gap check (1..N contiguous) runs ONLY when the arc is
      `is_active=true`, permitting incremental authoring while inactive
    - confusion_topics has ≥ 3 entries per day
    - All three plain_english_* tiers populated
    - scripture_refs non-empty
    - scripture_content.translation == "WEB" (Phase 1)
    - key_insight ≤ 200 chars, application_action ≤ 280 chars
    - retention_anchor populated (required for chronological arcs)

Usage:
    python manage.py load_journey_path walking_with_god
    python manage.py load_journey_path walking_with_god --dry-run
    python manage.py load_journey_path walking_with_god --arc-slug creation_to_egypt

When ``--arc-slug`` is provided the loader will validate and upsert ONLY the
matching arc file. Resolution prefers a filename match (stem ends with the
slug) but falls back to reading the JSON ``slug`` field if filename narrowing
finds nothing — the JSON ``slug`` is canonical. This single-arc mode is what
historical data migrations use to remain deterministic; new arc files added
to disk later cannot change which file an existing ``arc_slug=...`` resolves
to, because slug uniqueness is a content-authoring contract.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from django.apps import apps
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction


CONFUSION_TOPICS_MIN = 3
KEY_INSIGHT_MAX_CHARS = 200
APPLICATION_ACTION_MAX_CHARS = 280
SUPPORTED_TRANSLATIONS = {"WEB"}
ALLOWED_DIFFICULTY = {"simple", "standard", "deeper"}


class ContentPackError(CommandError):
    """Raised when a content pack fails schema validation."""


class Command(BaseCommand):
    help = "Load a Journey content pack (path + arcs + days) from JSON into the database."

    def add_arguments(self, parser):
        parser.add_argument(
            "slug",
            help="Journey path slug. Loader will look in apps/faith/journey/content/<slug>/.",
        )
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Validate the content pack without writing to the database.",
        )
        parser.add_argument(
            "--arc-slug",
            dest="arc_slug",
            default=None,
            help=(
                "When provided, load ONLY the arc whose JSON filename stem ends "
                "with this slug (e.g. 'creation_to_egypt' matches "
                "'arc_01_creation_to_egypt.json'). Used by historical data "
                "migrations to remain deterministic regardless of which other "
                "arc files are present on disk."
            ),
        )

    def handle(self, *args, **options):
        slug = options["slug"]
        dry_run = options["dry_run"]
        arc_slug = options.get("arc_slug")

        content_root = self._resolve_content_root(slug)
        path_file = content_root / "path.json"
        arcs_dir = content_root / "arcs"

        if not path_file.exists():
            raise ContentPackError(f"path.json not found at {path_file}")
        if not arcs_dir.exists():
            raise ContentPackError(f"arcs/ directory not found at {arcs_dir}")

        path_data = self._read_json(path_file)
        arc_files = self._select_arc_files(arcs_dir, arc_slug)

        self._validate_path_data(path_data, slug)
        arc_payloads = [self._read_json(p) for p in arc_files]
        for arc_payload, arc_file in zip(arc_payloads, arc_files):
            self._validate_arc_payload(arc_payload, arc_file)

        self.stdout.write(
            f"Validated {len(arc_payloads)} arc file(s) for journey '{slug}'."
        )

        if dry_run:
            self.stdout.write(self.style.WARNING("--dry-run: not writing to database."))
            return

        with transaction.atomic():
            path = self._upsert_path(path_data)
            self.stdout.write(f"  Path: {path.name} ({path.slug})")
            for arc_payload in arc_payloads:
                arc, day_count = self._upsert_arc_and_days(path, arc_payload)
                self.stdout.write(
                    f"    Arc: {arc.name} (order={arc.order}, days={day_count}, "
                    f"is_active={arc.is_active})"
                )

        self.stdout.write(self.style.SUCCESS(f"Loaded journey '{slug}' successfully."))

    # ------------------------------------------------------------------ helpers

    def _resolve_content_root(self, slug: str) -> Path:
        """Locate apps/faith/journey/content/<slug>/."""
        journey_app = apps.get_app_config("journey")
        return Path(journey_app.path) / "content" / slug

    def _select_arc_files(self, arcs_dir: Path, arc_slug: str | None) -> list[Path]:
        """Return arc JSON files to load.

        Architecture contract: the JSON ``slug`` field is the canonical
        identifier for an arc. Filenames are a convenience and may drift over
        time — content authors should not be forced to rename a file just
        because they rename a slug.

        Resolution order when ``arc_slug`` is provided:
          1. **Filename fast path.** Match stems equal to ``arc_slug`` or
             ending with ``_<arc_slug>``. No JSON parsing required.
          2. **Slug fallback.** If filename narrowing finds zero matches,
             read every ``.json`` file's ``slug`` field and match against
             ``arc_slug``. A single fallback hit logs a warning and proceeds;
             multiple slug hits or zero hits raise.

        Determinism is preserved because the content-authoring contract
        guarantees slug uniqueness within a journey path. Future arc files
        added to disk cannot retroactively change which file an existing
        ``arc_slug=...`` call resolves to.
        """
        all_json = sorted(p for p in arcs_dir.iterdir() if p.is_file() and p.suffix == ".json")

        if arc_slug is None:
            if not all_json:
                raise ContentPackError(f"No arc files found in {arcs_dir}")
            return all_json

        # 1) Filename fast path — cheap, no JSON parsing.
        filename_matches = [
            p for p in all_json
            if p.stem == arc_slug or p.stem.endswith(f"_{arc_slug}")
        ]
        if len(filename_matches) == 1:
            return filename_matches
        if len(filename_matches) > 1:
            raise ContentPackError(
                f"Multiple files in {arcs_dir} match arc_slug '{arc_slug}' by "
                f"filename: {[p.name for p in filename_matches]}. Filenames "
                f"must be unambiguous when more than one would match."
            )

        # 2) Slug fallback — JSON `slug` field is canonical.
        slug_matches: list[Path] = []
        for p in all_json:
            try:
                with p.open("r", encoding="utf-8") as f:
                    payload = json.load(f)
            except (json.JSONDecodeError, OSError):
                # Tolerate other malformed files while searching for a specific
                # arc. If the malformed file IS the target, the "no match"
                # error below is clearer than a JSON parse error blamed on an
                # unrelated file.
                continue
            if isinstance(payload, dict) and payload.get("slug") == arc_slug:
                slug_matches.append(p)

        if len(slug_matches) == 1:
            match = slug_matches[0]
            self.stdout.write(self.style.WARNING(
                f"Arc '{arc_slug}' resolved by JSON `slug` field (filename "
                f"'{match.name}' does not end with '_{arc_slug}'). The JSON "
                f"slug is canonical; the filename is advisory."
            ))
            return slug_matches
        if len(slug_matches) > 1:
            raise ContentPackError(
                f"Multiple arc files in {arcs_dir} declare slug '{arc_slug}': "
                f"{[p.name for p in slug_matches]}. Slugs must be unique "
                f"within a journey path."
            )

        # 3) No match by either route.
        raise ContentPackError(
            f"No arc file in {arcs_dir} matches arc_slug '{arc_slug}'. "
            f"Searched {len(all_json)} .json file(s) by filename (stem == "
            f"'{arc_slug}' or stem ends with '_{arc_slug}') and by JSON "
            f"`slug` field. Neither approach found a match."
        )

    def _read_json(self, path: Path) -> dict[str, Any]:
        try:
            with path.open("r", encoding="utf-8") as f:
                return json.load(f)
        except json.JSONDecodeError as e:
            raise ContentPackError(f"JSON parse error in {path}: {e}") from e

    # ----------------------------------------------------------------- validate

    def _validate_path_data(self, data: dict, expected_slug: str) -> None:
        required = ["slug", "name", "narrative_overview", "difficulty_default"]
        for field in required:
            if not data.get(field):
                raise ContentPackError(f"path.json missing required field: '{field}'")
        if data["slug"] != expected_slug:
            raise ContentPackError(
                f"path.json slug '{data['slug']}' does not match directory slug '{expected_slug}'."
            )
        if data["difficulty_default"] not in ALLOWED_DIFFICULTY:
            raise ContentPackError(
                f"path.json difficulty_default must be one of {sorted(ALLOWED_DIFFICULTY)}, "
                f"got '{data['difficulty_default']}'."
            )

    def _validate_arc_payload(self, arc: dict, source_file: Path) -> None:
        required = ["journey_path", "slug", "name", "order", "opening_note", "closing_note", "days"]
        for field in required:
            if field not in arc or arc.get(field) in (None, ""):
                if field == "days" and isinstance(arc.get(field), list):
                    pass  # empty days list is checked below
                else:
                    raise ContentPackError(
                        f"{source_file.name} missing required arc field: '{field}'"
                    )

        days = arc.get("days") or []
        if not isinstance(days, list) or len(days) == 0:
            raise ContentPackError(f"{source_file.name} has no days authored.")

        seen_day_numbers = set()
        for day in days:
            self._validate_day(day, arc.get("slug"), source_file)
            day_num = day["day_number"]
            if day_num in seen_day_numbers:
                raise ContentPackError(
                    f"{source_file.name}: duplicate day_number {day_num} within arc '{arc.get('slug')}'."
                )
            seen_day_numbers.add(day_num)

        # Sequence/gap check ONLY when the arc is being activated.
        is_active = bool(arc.get("is_active", False))
        if is_active:
            sorted_days = sorted(seen_day_numbers)
            expected = list(range(1, len(sorted_days) + 1))
            if sorted_days != expected:
                raise ContentPackError(
                    f"{source_file.name}: arc is is_active=true but day_numbers "
                    f"{sorted_days} are not a contiguous sequence starting at 1. "
                    f"Either set is_active=false (incremental authoring) or fill the gaps."
                )

    def _validate_day(self, day: dict, arc_slug: str | None, source_file: Path) -> None:
        required_text_fields = [
            "context_before",
            "plain_english_simple",
            "plain_english_standard",
            "plain_english_deeper",
            "key_insight",
            "reflection_prompt",
            "application_action",
            "retention_anchor",
        ]
        for field in required_text_fields:
            if not (day.get(field) and str(day.get(field)).strip()):
                raise ContentPackError(
                    f"{source_file.name} arc='{arc_slug}' day={day.get('day_number')}: "
                    f"missing or empty required field '{field}'."
                )

        day_number = day.get("day_number")
        if not isinstance(day_number, int) or day_number < 1:
            raise ContentPackError(
                f"{source_file.name} arc='{arc_slug}': day_number must be int ≥ 1, got {day_number!r}."
            )

        scripture_refs = day.get("scripture_refs") or []
        if not isinstance(scripture_refs, list) or not scripture_refs:
            raise ContentPackError(
                f"{source_file.name} day {day_number}: scripture_refs must be a non-empty list."
            )

        scripture_content = day.get("scripture_content") or {}
        if not isinstance(scripture_content, dict):
            raise ContentPackError(
                f"{source_file.name} day {day_number}: scripture_content must be an object."
            )
        translation = scripture_content.get("translation")
        if translation not in SUPPORTED_TRANSLATIONS:
            raise ContentPackError(
                f"{source_file.name} day {day_number}: translation must be one of "
                f"{sorted(SUPPORTED_TRANSLATIONS)}, got '{translation}'."
            )
        blocks = scripture_content.get("blocks") or []
        if not isinstance(blocks, list) or not blocks:
            raise ContentPackError(
                f"{source_file.name} day {day_number}: scripture_content.blocks must be a non-empty list."
            )

        if len(day["key_insight"]) > KEY_INSIGHT_MAX_CHARS:
            raise ContentPackError(
                f"{source_file.name} day {day_number}: key_insight is "
                f"{len(day['key_insight'])} chars (max {KEY_INSIGHT_MAX_CHARS})."
            )
        if len(day["application_action"]) > APPLICATION_ACTION_MAX_CHARS:
            raise ContentPackError(
                f"{source_file.name} day {day_number}: application_action is "
                f"{len(day['application_action'])} chars (max {APPLICATION_ACTION_MAX_CHARS})."
            )

        confusion_topics = day.get("confusion_topics") or []
        if not isinstance(confusion_topics, list) or len(confusion_topics) < CONFUSION_TOPICS_MIN:
            raise ContentPackError(
                f"{source_file.name} day {day_number}: confusion_topics must have "
                f"≥ {CONFUSION_TOPICS_MIN} entries (found {len(confusion_topics)})."
            )
        for i, topic in enumerate(confusion_topics):
            if not isinstance(topic, dict):
                raise ContentPackError(
                    f"{source_file.name} day {day_number}: confusion_topics[{i}] must be an object."
                )
            if not (topic.get("topic") and topic.get("plain_english_answer")):
                raise ContentPackError(
                    f"{source_file.name} day {day_number}: confusion_topics[{i}] missing "
                    f"'topic' or 'plain_english_answer'."
                )

    # ------------------------------------------------------------------- upsert

    def _upsert_path(self, data: dict):
        from apps.faith.journey.models import JourneyPath

        path, _ = JourneyPath.objects.update_or_create(
            slug=data["slug"],
            defaults={
                "name": data["name"],
                "narrative_overview": data["narrative_overview"],
                "cover_image_url": data.get("cover_image_url", ""),
                "estimated_weeks": int(data.get("estimated_weeks", 0)),
                "difficulty_default": data["difficulty_default"],
                "is_active": bool(data.get("is_active", False)),
                "is_featured": bool(data.get("is_featured", False)),
            },
        )
        return path

    def _upsert_arc_and_days(self, path, arc_payload: dict):
        from apps.faith.journey.models import JourneyArc, JourneyDay

        if arc_payload.get("journey_path") and arc_payload["journey_path"] != path.slug:
            raise ContentPackError(
                f"Arc payload journey_path='{arc_payload['journey_path']}' does not "
                f"match path slug '{path.slug}'."
            )

        arc, _ = JourneyArc.objects.update_or_create(
            journey_path=path,
            slug=arc_payload["slug"],
            defaults={
                "name": arc_payload["name"],
                "era_label": arc_payload.get("era_label", ""),
                "order": int(arc_payload["order"]),
                "opening_note": arc_payload["opening_note"],
                "closing_note": arc_payload["closing_note"],
                "estimated_days": int(arc_payload.get("estimated_days", 0)),
                "is_active": bool(arc_payload.get("is_active", False)),
            },
        )

        day_count = 0
        for day_data in arc_payload["days"]:
            JourneyDay.objects.update_or_create(
                arc=arc,
                day_number=int(day_data["day_number"]),
                defaults={
                    "scripture_refs": day_data["scripture_refs"],
                    "scripture_content": day_data["scripture_content"],
                    "context_before": day_data["context_before"],
                    "plain_english_simple": day_data["plain_english_simple"],
                    "plain_english_standard": day_data["plain_english_standard"],
                    "plain_english_deeper": day_data["plain_english_deeper"],
                    "key_insight": day_data["key_insight"],
                    "reflection_prompt": day_data["reflection_prompt"],
                    "application_action": day_data["application_action"],
                    "confusion_topics": day_data["confusion_topics"],
                    "retention_anchor": day_data["retention_anchor"],
                },
            )
            day_count += 1

        return arc, day_count
