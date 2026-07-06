"""Repair internally-inconsistent milestone MAJOR-WIN GuidanceItems.

Origin (2026-07-06): the Significant Event Pipeline's win composer produced a
record whose parts came from DIFFERENT missions — a milestone completed on
"Relationship with God" was persisted with the generic title "Milestone reached"
and a next milestone of "Goal Weight 279.9 lb" (borrowed from the user's WEIGHT
goal via ``goal_pace(user)``). Two composer bugs, now fixed in
``apps/ai/significant_events.py``:

  1. title fell back to the literal "Milestone reached" (real milestone_id title
     never read), and
  2. the next milestone came from a user-global weight trajectory instead of the
     completing goal's own next rung.

Existing rows won't self-heal (a one-time achievement never re-fires), so this
migration re-composes each ``cos_event:win:milestone:*`` GuidanceItem through the
NOW-FIXED composer (``recompose_milestone_win``) — same code path a live win
takes, no string patching. Idempotent, fail-soft, and a no-op on fresh DBs.
"""
from django.db import migrations


def repair_wins(apps, schema_editor):
    # Use the REAL model/logic (not the historical apps registry) — we need the
    # live composer + related-model traversal. Import inside the function so the
    # migration module stays importable even if app code shifts.
    try:
        from apps.core.ai_guidance.models import GuidanceItem
        from apps.ai.significant_events import recompose_milestone_win
    except Exception:
        return

    qs = GuidanceItem.objects.filter(
        is_active=True, dedupe_key__startswith="cos_event:win:milestone:")
    for item in qs.iterator():
        try:
            recompose_milestone_win(item)
        except Exception:
            # Fail-soft per row — one bad row must never abort the deploy.
            continue


def noop_reverse(apps, schema_editor):
    # Re-composition is not reversible (the old inconsistent text is exactly what
    # we're removing); nothing to undo.
    pass


class Migration(migrations.Migration):

    dependencies = [
        ("core", "0126_behavior_directive"),
    ]

    operations = [
        migrations.RunPython(repair_wins, noop_reverse),
    ]
