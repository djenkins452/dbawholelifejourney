"""
Sports Domain — Sync Service

Single source of truth for sports data synchronization.
Fetches from provider adapter → upserts Teams and GameEvents.

Responsibilities:
- Sync team standings (wins/losses) from provider
- Sync game events (schedule, scores, pitchers) from provider
- Idempotent: safe to run repeatedly, no duplicates
- Raw sync ONLY: no streak computation, no urgency, no signals

Usage:
    from apps.sports.services.sync_service import sync_sports_data
    result = sync_sports_data()  # Full sync
    result = sync_sports_data(leagues=["mlb", "nba"])  # Targeted
"""
import logging
import time
from datetime import timedelta

from django.utils import timezone

from apps.sports.models import GameEvent, League, Team, UserTeamFollow
from apps.sports.services.cache_manager import (
    invalidate_user_caches_for_game,
    set_sync_health,
)
from apps.sports.services.provider_adapter import get_provider

logger = logging.getLogger(__name__)


def sync_sports_data(leagues=None, days_ahead=1, days_back=1):
    """
    Sync sports data from the configured provider.

    Fetches standings and games for leagues that have active followers.
    Upserts all data — safe to run on every schedule tick.

    Args:
        leagues: Optional list of league slugs to sync. If None, syncs
                 all leagues with active followers.
        days_ahead: Number of days ahead to fetch games (default 7).
        days_back: Number of days back to fetch completed games (default 2).

    Returns:
        dict with sync results:
        {
            "standings_updated": int,
            "games_upserted": int,
            "games_updated": int,
            "leagues_synced": list[str],
            "duration_seconds": float,
            "provider": str,
            "skipped_reason": str or None,
        }
    """
    start = time.monotonic()
    provider = get_provider()
    now = timezone.now()

    result = {
        "standings_updated": 0,
        "games_upserted": 0,
        "games_updated": 0,
        "leagues_synced": [],
        "duration_seconds": 0,
        "provider": provider.provider_name(),
        "skipped_reason": None,
        "errors": [],
    }

    # Fixture provider has no real data — skip sync
    if provider.provider_name() == "fixture":
        result["skipped_reason"] = "fixture_provider"
        result["duration_seconds"] = round(time.monotonic() - start, 3)
        logger.debug("Sports sync skipped: fixture provider")
        return result

    # Determine which leagues to sync
    if leagues:
        league_slugs = leagues
    else:
        # Only sync leagues that have active followers (deduplicated)
        league_slugs = list(set(
            UserTeamFollow.objects.filter(is_active=True)
            .values_list("team__league__slug", flat=True)
        ))

    if not league_slugs:
        result["skipped_reason"] = "no_active_followers"
        result["duration_seconds"] = round(time.monotonic() - start, 3)
        return result

    league_objects = {
        lg.slug: lg for lg in League.objects.filter(slug__in=league_slugs)
    }

    date_from = (now - timedelta(days=days_back)).date()
    date_to = (now + timedelta(days=days_ahead)).date()

    for slug in league_slugs:
        league = league_objects.get(slug)
        if not league:
            continue

        try:
            # Link teams: match API external_ids to our DB teams
            _link_teams(provider, league)

            # Sync standings (team records) — pass resolved season for staleness tracking
            resolved_season = ""
            if hasattr(provider, '_resolve_season'):
                resolved_season = str(provider._resolve_season(league.slug) or "")
            standings_count = _sync_standings(provider, league, resolved_season)
            result["standings_updated"] += standings_count

            # Sync games
            upserted, updated = _sync_games(provider, league, date_from, date_to)
            result["games_upserted"] += upserted
            result["games_updated"] += updated

            result["leagues_synced"].append(slug)
        except Exception as e:
            logger.error("Sports sync failed for league %s: %s", slug, e, exc_info=True)
            result["errors"].append(f"{slug}: {str(e)}")

    duration = round(time.monotonic() - start, 3)
    result["duration_seconds"] = duration

    # Record sync health for observability
    set_sync_health({
        "last_sync": now.isoformat(),
        "provider": provider.provider_name(),
        "leagues_synced": result["leagues_synced"],
        "standings_updated": result["standings_updated"],
        "games_upserted": result["games_upserted"],
        "games_updated": result["games_updated"],
        "errors": len(result["errors"]),
        "duration_seconds": duration,
    })

    logger.info(
        "Sports sync complete: %d standings, %d new games, %d updated games, "
        "%d leagues (%.2fs) [%s]",
        result["standings_updated"],
        result["games_upserted"],
        result["games_updated"],
        len(result["leagues_synced"]),
        duration,
        provider.provider_name(),
    )

    return result


def _link_teams(provider, league):
    """
    Link API external_ids to existing DB teams.

    Fetches teams from the provider and matches them to our DB teams by
    abbreviation (case-insensitive). Sets external_id on the DB team so
    subsequent standings/games sync can match by external_id.

    Provider-switch safety:
    - Only resets external_id when existing prefix doesn't match current provider
    - Once linked to the current provider, NEVER re-links on future syncs
    - Idempotent — multiple sync runs don't change already-linked teams
    """
    provider_prefix = f"{provider.provider_name()}_"

    # Detect provider mismatch: teams linked to a DIFFERENT provider
    mismatched = Team.objects.filter(
        league=league
    ).exclude(
        external_id=""
    ).exclude(
        external_id__startswith=provider_prefix
    ).count()

    if mismatched > 0:
        logger.info(
            "Sports sync: clearing %d mismatched external_ids for %s "
            "(switching to %s provider)",
            mismatched, league.abbreviation, provider.provider_name(),
        )
        Team.objects.filter(
            league=league
        ).exclude(
            external_id=""
        ).exclude(
            external_id__startswith=provider_prefix
        ).update(external_id="")

        # Also clear old GameEvent external_ids from the old provider
        # so they don't conflict with new provider's IDs
        GameEvent.objects.filter(
            home_team__league=league
        ).exclude(
            external_id=""
        ).exclude(
            external_id__startswith=provider_prefix
        ).update(external_id="")

    # Check if any teams still need linking (skip if all linked to current provider)
    unlinked_count = Team.objects.filter(league=league, external_id="").count()
    if unlinked_count == 0:
        return  # All teams already linked to current provider

    api_teams = provider.fetch_teams(league.slug)
    if not api_teams:
        return

    db_teams = list(Team.objects.filter(league=league, external_id=""))

    # Build multiple lookup strategies
    # 1. Abbreviation match (case-insensitive)
    db_by_abbr = {t.abbreviation.upper(): t for t in db_teams}
    # 2. Full name match: "Location Name" (how our DB stores it)
    db_by_full_name = {f"{t.location} {t.name}".lower(): t for t in db_teams}
    # 3. Name-only match (e.g., "Yankees", "Braves")
    db_by_name = {t.name.lower(): t for t in db_teams}

    linked = 0
    for api_team in api_teams:
        if not api_team.external_id:
            continue

        db_team = None
        api_name = api_team.name.lower() if api_team.name else ""

        # Strategy 1: abbreviation match
        if api_team.abbreviation:
            db_team = db_by_abbr.get(api_team.abbreviation.upper())

        # Strategy 2: full name match (API "New York Yankees" → DB "New York Yankees")
        if not db_team and api_name:
            db_team = db_by_full_name.get(api_name)

        # Strategy 3: API name contains our team name (API "Atlanta Braves" → DB name "Braves")
        if not db_team and api_name:
            for t in db_teams:
                if t.name.lower() in api_name and t.location.lower() in api_name:
                    db_team = t
                    break

        # Strategy 4: partial name match (last word of API name = DB name)
        if not db_team and api_name:
            api_last_word = api_name.split()[-1] if api_name.split() else ""
            db_team = db_by_name.get(api_last_word)

        if db_team:
            update_fields = ["external_id"]
            db_team.external_id = api_team.external_id
            # Also store logo_url if provider supplies one
            if api_team.logo_url and db_team.logo_url != api_team.logo_url:
                db_team.logo_url = api_team.logo_url
                update_fields.append("logo_url")
            db_team.save(update_fields=update_fields)
            # Remove from lookup dicts to prevent double-matching
            db_teams.remove(db_team)
            db_by_abbr = {t.abbreviation.upper(): t for t in db_teams}
            db_by_full_name = {f"{t.location} {t.name}".lower(): t for t in db_teams}
            db_by_name = {t.name.lower(): t for t in db_teams}
            linked += 1

    # Backfill logos for already-linked teams missing logo_url
    linked_no_logo = Team.objects.filter(
        league=league,
        external_id__startswith=provider_prefix,
    ).exclude(external_id="").filter(logo_url="")

    if linked_no_logo.exists():
        # Build a lookup from the API teams we already fetched
        api_logo_map = {t.external_id: t.logo_url for t in api_teams if t.logo_url}
        logo_updated = 0
        for team in linked_no_logo:
            logo = api_logo_map.get(team.external_id, "")
            if logo:
                team.logo_url = logo
                team.save(update_fields=["logo_url"])
                logo_updated += 1
        if logo_updated:
            logger.info("Sports sync: backfilled logos for %d teams in %s", logo_updated, league.abbreviation)

    if linked:
        logger.info("Sports sync: linked %d teams for %s", linked, league.abbreviation)


def _sync_standings(provider, league, resolved_season=""):
    """
    Sync team standings (wins/losses) for a league.

    Matches teams by external_id. Updates wins/losses and record_season.
    Returns count of teams updated.
    """
    standings = provider.fetch_standings(league.slug)
    if not standings:
        return 0

    # Build external_id → Team lookup for this league
    teams_by_ext = {
        t.external_id: t
        for t in Team.objects.filter(league=league).exclude(external_id="")
    }

    updated = 0
    for entry in standings:
        team = teams_by_ext.get(entry.team_external_id)
        if not team:
            continue

        update_fields = []
        if team.wins != entry.wins:
            team.wins = entry.wins
            update_fields.append("wins")
        if team.losses != entry.losses:
            team.losses = entry.losses
            update_fields.append("losses")
        if resolved_season and team.record_season != resolved_season:
            team.record_season = resolved_season
            update_fields.append("record_season")

        if update_fields:
            team.save(update_fields=update_fields)
            updated += 1

    return updated


def _sync_games(provider, league, date_from, date_to):
    """
    Sync game events for a league's followed teams.

    Matches by external_id. Creates new games, updates existing ones.
    Returns (upserted_count, updated_count).
    """
    # Get external IDs of teams in this league that have followers
    followed_team_ids = list(
        UserTeamFollow.objects.filter(
            is_active=True, team__league=league
        ).values_list("team__external_id", flat=True).distinct()
    )
    # Filter out empty external_ids
    followed_team_ids = [eid for eid in followed_team_ids if eid]

    if not followed_team_ids:
        # Fall back to all teams in league with external_ids
        followed_team_ids = list(
            Team.objects.filter(league=league)
            .exclude(external_id="")
            .values_list("external_id", flat=True)
        )

    if not followed_team_ids:
        return 0, 0

    games = provider.fetch_games(followed_team_ids, date_from, date_to)
    if not games:
        return 0, 0

    # Build external_id → Team lookup
    all_ext_ids = set()
    for g in games:
        all_ext_ids.add(g.home_team_external_id)
        all_ext_ids.add(g.away_team_external_id)

    teams_by_ext = {
        t.external_id: t
        for t in Team.objects.filter(
            league=league, external_id__in=all_ext_ids
        )
    }

    # Existing games by external_id for update detection
    game_ext_ids = [g.external_id for g in games if g.external_id]
    existing_games = {
        ge.external_id: ge
        for ge in GameEvent.objects.filter(external_id__in=game_ext_ids)
    } if game_ext_ids else {}

    upserted = 0
    updated = 0

    for ng in games:
        home = teams_by_ext.get(ng.home_team_external_id)
        away = teams_by_ext.get(ng.away_team_external_id)
        if not home or not away:
            continue

        existing = existing_games.get(ng.external_id) if ng.external_id else None

        if existing:
            # Update existing game
            changed = _update_game_if_changed(existing, ng)
            if changed:
                updated += 1
        else:
            # Create new game
            GameEvent.objects.create(
                home_team=home,
                away_team=away,
                start_time=ng.start_time,
                status=ng.status,
                home_score=ng.home_score,
                away_score=ng.away_score,
                venue=ng.venue,
                external_id=ng.external_id,
                home_probable_pitcher=ng.home_probable_pitcher,
                away_probable_pitcher=ng.away_probable_pitcher,
                game_type=getattr(ng, 'game_type', 'regular'),
                game_note=getattr(ng, 'game_note', ''),
            )
            upserted += 1

    return upserted, updated


def _update_game_if_changed(game, normalized):
    """
    Update a GameEvent if the normalized data differs.

    Only updates fields that have actually changed to minimize DB writes.
    Returns True if any field was updated.
    """
    update_fields = []

    if game.status != normalized.status:
        game.status = normalized.status
        update_fields.append("status")

    if normalized.home_score is not None and game.home_score != normalized.home_score:
        game.home_score = normalized.home_score
        update_fields.append("home_score")

    if normalized.away_score is not None and game.away_score != normalized.away_score:
        game.away_score = normalized.away_score
        update_fields.append("away_score")

    if normalized.venue and game.venue != normalized.venue:
        game.venue = normalized.venue
        update_fields.append("venue")

    if normalized.start_time and game.start_time != normalized.start_time:
        game.start_time = normalized.start_time
        update_fields.append("start_time")

    if normalized.home_probable_pitcher and game.home_probable_pitcher != normalized.home_probable_pitcher:
        game.home_probable_pitcher = normalized.home_probable_pitcher
        update_fields.append("home_probable_pitcher")

    if normalized.away_probable_pitcher and game.away_probable_pitcher != normalized.away_probable_pitcher:
        game.away_probable_pitcher = normalized.away_probable_pitcher
        update_fields.append("away_probable_pitcher")

    ng_game_type = getattr(normalized, 'game_type', 'regular')
    if ng_game_type and game.game_type != ng_game_type:
        game.game_type = ng_game_type
        update_fields.append("game_type")

    ng_game_note = getattr(normalized, 'game_note', '')
    if ng_game_note and game.game_note != ng_game_note:
        game.game_note = ng_game_note
        update_fields.append("game_note")

    if update_fields:
        game.save(update_fields=update_fields + ["last_updated"])
        # Invalidate caches for affected users
        invalidate_user_caches_for_game(game)
        return True

    return False
