"""
Invalidate cached sports state for all users.

The previous deploy added game_type/game_note to the _contract builder,
but existing UserState records still have the old _contract without
those fields. This causes the importance engine to score all games as
regular (10 pts) instead of tournament (100 pts).

By clearing the sports module from UserState, the next access triggers
a rebuild with the corrected contract builder that includes game_type
and game_note.
"""
from django.db import migrations


def invalidate_sports_state(apps, schema_editor):
    """Clear sports state from all UserState records to force rebuild."""
    try:
        # Also re-sync all leagues to ensure game_type/game_note populated
        from apps.sports.services.sync_service import sync_sports_data
        result = sync_sports_data(days_ahead=2, days_back=2)
        print(f"  Full sports sync: {result.get('games_upserted', 0)} upserted, "
              f"{result.get('games_updated', 0)} updated, "
              f"leagues: {result.get('leagues_synced', [])}")
    except Exception as e:
        print(f"  Sports sync (non-fatal): {e}")

    try:
        UserState = apps.get_model('core', 'UserState')
        count = 0
        for us in UserState.objects.all():
            if us.state_data and 'sports' in us.state_data:
                us.state_data.pop('sports', None)
                us.save(update_fields=['state_data'])
                count += 1
        print(f"  Invalidated sports state for {count} users")
    except Exception as e:
        print(f"  State invalidation (non-fatal): {e}")


def noop(apps, schema_editor):
    pass


class Migration(migrations.Migration):
    dependencies = [
        ("sports", "0005_force_ncaab_sync"),
        ("core", "0001_initial"),
    ]

    operations = [
        migrations.RunPython(invalidate_sports_state, noop),
    ]
