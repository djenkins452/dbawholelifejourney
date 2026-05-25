"""
Journey roadmap — the canonical table of contents for "Walking With God
Through Scripture."

A static list of all planned arcs (Old Testament + New Testament), with
status computed at render time from the JourneyArc database state. Arcs
that exist in the DB and are is_active=True render as "Available." All
others render as "Coming Soon."

The roadmap is intentionally curated, evocative, and chronological. The
purpose (per the product brief): optimize for momentum, context, and
curiosity while preserving the quiet/reverent visual style.

To add a new authored arc:
  1. Author the JSON content pack in apps/faith/journey/content/...
  2. Add a data migration that runs load_journey_path
  3. Update the slug field below to match the authored slug, if changed
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from apps.faith.journey.models import JourneyArc


@dataclass(frozen=True)
class RoadmapEntry:
    """A single arc entry in the journey roadmap."""

    order: int
    slug: str
    name: str
    covers: str         # e.g., "Genesis 1-50" or "Joshua, Judges, Ruth"
    teaser: str         # one short evocative sentence
    testament: str      # "OT" or "NT"


# The canonical roadmap. Twelve arcs covering the whole Bible.
# Order matches the chronological / canonical sweep.
ROADMAP: tuple[RoadmapEntry, ...] = (
    RoadmapEntry(
        order=1, testament="OT",
        slug="creation_to_egypt",
        name="Creation to Egypt",
        covers="Genesis 1–50",
        teaser="From the first words of the Bible to a coffin in Egypt. Creation, fall, flood, Abraham, Joseph.",
    ),
    RoadmapEntry(
        order=2, testament="OT",
        slug="slavery_to_deliverance",
        name="Slavery to Deliverance",
        covers="Exodus 1–20",
        teaser="A baby in a basket, a burning bush, ten plagues, a sea split, the law thundered at Sinai.",
    ),
    RoadmapEntry(
        order=3, testament="OT",
        slug="covenant_and_wilderness",
        name="Covenant and Wilderness",
        covers="Exodus 21 → Deuteronomy",
        teaser="Living with God in your midst. The tabernacle, the law unfolded, forty years of forming.",
    ),
    RoadmapEntry(
        order=4, testament="OT",
        slug="into_the_promised_land",
        name="Into the Promised Land",
        covers="Joshua, Judges, Ruth",
        teaser="Crossing the Jordan. Walls falling. Heroes rising. A foreign widow who changes everything.",
    ),
    RoadmapEntry(
        order=5, testament="OT",
        slug="kings_and_kingdom",
        name="Kings and Kingdom",
        covers="1–2 Samuel, 1–2 Kings",
        teaser="A boy with a sling. A shepherd-king. A wise son. A divided nation. A slow forgetting.",
    ),
    RoadmapEntry(
        order=6, testament="OT",
        slug="prophets_and_exile",
        name="Prophets and Exile",
        covers="Isaiah, Jeremiah, Daniel, the prophets",
        teaser="God's voice when the kingdom is failing. Warning, hope, ruin, exile, lions, fire.",
    ),
    RoadmapEntry(
        order=7, testament="OT",
        slug="return_and_waiting",
        name="Return and Waiting",
        covers="Ezra, Nehemiah, Esther, Malachi",
        teaser="Coming home. Rebuilding rubble. A queen who saves her people. Four hundred years of silence.",
    ),
    RoadmapEntry(
        order=8, testament="NT",
        slug="the_coming_of_jesus",
        name="The Coming of Jesus",
        covers="Matthew, Mark, Luke, John (birth & ministry)",
        teaser="The waiting ends. A baby in a manger. A man teaching on hillsides. A kingdom unlike any expected.",
    ),
    RoadmapEntry(
        order=9, testament="NT",
        slug="cross_and_empty_tomb",
        name="The Cross and the Empty Tomb",
        covers="The Passion narratives",
        teaser="The week that changed everything. A meal, a garden, a trial, a cross, a stone rolled away.",
    ),
    RoadmapEntry(
        order=10, testament="NT",
        slug="the_church_begins",
        name="The Church Begins",
        covers="Acts",
        teaser="A rushing wind. Bold fishermen. A persecutor becomes an apostle. The gospel goes to the world.",
    ),
    RoadmapEntry(
        order=11, testament="NT",
        slug="letters_to_the_churches",
        name="Letters to the Churches",
        covers="The Epistles",
        teaser="Real letters to real people. How to live, love, suffer, hope, and stay anchored when it's hard.",
    ),
    RoadmapEntry(
        order=12, testament="NT",
        slug="end_and_new_beginning",
        name="The End and the New Beginning",
        covers="Revelation",
        teaser="Visions, judgment, hope, and a new heaven and new earth where God dwells with his people forever.",
    ),
)


def get_roadmap_rows(current_user_arc_slug: Optional[str] = None) -> list[dict]:
    """Return roadmap rows with DB-computed status for the template.

    Each row dict has:
      order, name, covers, teaser, testament, status,
      day_count (when available), is_current (when current_user_arc_slug matches).

    Status values:
      "available"   — arc exists in DB with is_active=True
      "in_progress" — same as available, but matches the user's current arc
      "coming_soon" — otherwise
    """
    # Build a lookup of active arcs by slug, with day counts.
    active_arcs = {
        a.slug: a
        for a in JourneyArc.objects
        .filter(is_active=True, journey_path__slug="walking_with_god")
        .prefetch_related("days")
    }

    rows: list[dict] = []
    for entry in ROADMAP:
        arc = active_arcs.get(entry.slug)
        if arc is None:
            status = "coming_soon"
            day_count = None
        elif current_user_arc_slug and entry.slug == current_user_arc_slug:
            status = "in_progress"
            day_count = arc.days.count()
        else:
            status = "available"
            day_count = arc.days.count()

        rows.append({
            "order": entry.order,
            "name": entry.name,
            "covers": entry.covers,
            "teaser": entry.teaser,
            "testament": entry.testament,
            "status": status,
            "day_count": day_count,
            "is_current": status == "in_progress",
        })
    return rows
