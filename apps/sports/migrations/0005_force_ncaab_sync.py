"""
Force NCAAB game sync on deploy.

The ESPN team-linking fix (limit=500) was deployed but Celery may not
have run the sync yet. This migration ensures production gets NCAAB
games (including March Madness Sweet 16) on the next deploy.

Runs sync_sports_data(leagues=["ncaab"]) which:
1. Links NCAAB teams to ESPN external_ids
2. Fetches today's + yesterday's games from ESPN scoreboard
3. Populates game_type='tournament' and game_note='NCAA Tournament - Sweet 16'
"""
from django.db import migrations


def force_ncaab_sync(apps, schema_editor):
    """Run NCAAB sync to populate tournament games."""
    try:
        from apps.sports.services.sync_service import sync_sports_data
        result = sync_sports_data(leagues=["ncaab"], days_ahead=2, days_back=2)
        print(f"  NCAAB sync: {result.get('games_upserted', 0)} upserted, "
              f"{result.get('games_updated', 0)} updated, "
              f"errors: {result.get('errors', [])}")
    except Exception as e:
        # Non-fatal: sync will happen on next Celery tick anyway
        print(f"  NCAAB sync failed (non-fatal): {e}")


def noop(apps, schema_editor):
    pass


class Migration(migrations.Migration):
    dependencies = [
        ("sports", "0004_gameevent_game_note_gameevent_game_type"),
    ]

    operations = [
        migrations.RunPython(force_ncaab_sync, noop),
    ]
