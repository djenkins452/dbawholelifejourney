"""
Sports Domain — Background Tasks

All sports processing happens in background workers.
NO external API calls or heavy queries on request paths.

Tasks:
- sync_games_from_provider: Raw data sync (standings, games, pitchers)
- compute_sports_signals: Generate signals + populate caches for all sports-enabled users
"""
import logging
import time

from celery import shared_task
from django.contrib.auth import get_user_model
from django.utils import timezone

from apps.sports.models import GameEvent, UserTeamFollow
from apps.sports.services.cache_manager import (
    set_sync_health,
    set_user_signals,
    set_user_sports_summary,
    set_user_today_games,
    set_user_view_model,
)
from apps.sports.services.signal_generator import (
    SIGNAL_GAME_COMPLETED,
    SIGNAL_GAME_LIVE,
    SIGNAL_GAME_STARTING_SOON,
    SIGNAL_GAME_TODAY,
    SIGNAL_TEAM_LOSS,
    SIGNAL_TEAM_WIN,
    generate_sports_signals,
)

logger = logging.getLogger(__name__)
User = get_user_model()


def compute_sports_signals():
    """
    Background task: Generate signals and populate caches for all sports-enabled users.

    Called by SAME cycle or ISE scheduler.
    Runs for users with sports_enabled=True and at least one active team follow.
    """
    start = time.monotonic()
    now = timezone.now()

    # One-time bootstrap: if no games exist, queue a sync on the Celery worker.
    # This is safe — .delay() just enqueues a Redis message, no DB/API work here.
    # Syncs all leagues with active followers (not just MLB).
    if not GameEvent.objects.exists():
        logger.warning("Sports: 0 GameEvents — queueing sync_games_from_provider to worker")
        try:
            sync_games_from_provider.delay()  # None = sync all leagues with followers
        except Exception:
            logger.error("Sports: failed to queue bootstrap sync", exc_info=True)

    # Only process users with sports enabled AND active follows
    user_ids_with_follows = (
        UserTeamFollow.objects.filter(is_active=True)
        .values_list("user_id", flat=True)
        .distinct()
    )
    users = User.objects.filter(
        id__in=user_ids_with_follows,
        preferences__sports_enabled=True,
        is_active=True,
    ).select_related("preferences")

    processed = 0
    signal_count = 0
    errors = 0

    for user in users:
        try:
            signals = generate_sports_signals(user)
            signal_count += len(signals)

            # Cache raw signals for view model builder
            set_user_signals(user.id, signals)

            # Build and cache team summaries from signals (legacy)
            summaries = _build_summaries_from_signals(user, signals, now)
            set_user_sports_summary(user.id, summaries)

            # Cache today's games (extracted from signals)
            today_games = [
                s["data"] for s in signals
                if s["signal_type"] == SIGNAL_GAME_TODAY
            ]
            set_user_today_games(user.id, today_games)

            # Build and cache the view model (pre-compute for fast page loads)
            try:
                from apps.sports.services.sports_view_model import build_sports_view_model
                vm = build_sports_view_model(user)
                set_user_view_model(user.id, vm)
            except Exception:
                logger.warning("Sports view model build failed for user %s", user.id, exc_info=True)

            processed += 1
        except Exception:
            errors += 1
            logger.error(
                "Sports signal generation failed for user %s",
                user.id,
                exc_info=True,
            )

    duration = time.monotonic() - start

    # Record sync health telemetry
    set_sync_health({
        "last_run": now.isoformat(),
        "users_processed": processed,
        "signals_generated": signal_count,
        "errors": errors,
        "duration_seconds": round(duration, 2),
    })

    logger.info(
        "Sports signals computed: %d users, %d signals, %d errors (%.2fs)",
        processed, signal_count, errors, duration,
    )
    return {"processed": processed, "signals": signal_count, "errors": errors}


def _build_summaries_from_signals(user, signals, now):
    """
    Build per-team summaries from generated signals.

    State builder consumes signals — never re-derives from raw GameEvent.
    Includes enriched fields (record_display, logo_url, game_id, opponent_logo,
    is_home, streak) needed by _contract overlay.
    """
    from apps.sports.services.signal_generator import (
        SIGNAL_GAME_FINAL,
        SIGNAL_GAME_UPCOMING,
    )

    team_data = {}

    for signal in signals:
        team_id = signal["team_id"]
        if team_id not in team_data:
            team_data[team_id] = {
                "team_id": team_id,
                "team_name": signal["team_name"],
                "league": "",
                "priority": signal["priority"],
                "next_game": None,
                "last_result": None,
                "status": "upcoming",
                "record": "",
                "record_display": "",
                "logo_url": "",
                "streak": "",
                "active_signals": [],
            }

        entry = team_data[team_id]
        entry["active_signals"].append(signal["signal_type"])
        data = signal["data"]

        sig_type = signal["signal_type"]

        if sig_type == SIGNAL_GAME_LIVE:
            entry["status"] = "live"
            entry["next_game"] = {
                "game_id": signal.get("game_id"),
                "opponent": data.get("opponent", ""),
                "opponent_logo": data.get("opponent_logo", ""),
                "start_time": data.get("start_time", ""),
                "time": data.get("start_time", ""),
                "venue": data.get("venue", ""),
                "is_home": data.get("is_home", True),
                "pitcher": data.get("home_pitcher", "") if data.get("is_home") else data.get("away_pitcher", ""),
                "score": data.get("score", ""),
            }
        elif sig_type == SIGNAL_GAME_STARTING_SOON:
            if entry["status"] != "live":
                entry["status"] = "starting_soon"
            if not entry["next_game"] or entry["status"] == "starting_soon":
                entry["next_game"] = {
                    "game_id": signal.get("game_id"),
                    "opponent": data.get("opponent", ""),
                    "opponent_logo": data.get("opponent_logo", ""),
                    "start_time": data.get("start_time", ""),
                    "time": data.get("start_time", ""),
                    "venue": data.get("venue", ""),
                    "is_home": data.get("is_home", True),
                    "pitcher": data.get("home_pitcher", "") if data.get("is_home") else data.get("away_pitcher", ""),
                }
        elif sig_type == SIGNAL_GAME_TODAY:
            if entry["status"] not in ("live", "starting_soon"):
                entry["status"] = "today"
            if not entry["next_game"]:
                entry["next_game"] = {
                    "game_id": signal.get("game_id"),
                    "opponent": data.get("opponent", ""),
                    "opponent_logo": data.get("opponent_logo", ""),
                    "start_time": data.get("start_time", ""),
                    "time": data.get("start_time", ""),
                    "venue": data.get("venue", ""),
                    "is_home": data.get("is_home", True),
                    "pitcher": data.get("home_pitcher", "") if data.get("is_home") else data.get("away_pitcher", ""),
                }
        elif sig_type == SIGNAL_GAME_UPCOMING:
            if entry["status"] == "upcoming" and not entry["next_game"]:
                entry["next_game"] = {
                    "game_id": signal.get("game_id"),
                    "opponent": data.get("opponent", ""),
                    "opponent_logo": data.get("opponent_logo", ""),
                    "start_time": data.get("start_time", ""),
                    "time": data.get("start_time", ""),
                    "venue": data.get("venue", ""),
                    "is_home": data.get("is_home", True),
                    "pitcher": data.get("home_pitcher", "") if data.get("is_home") else data.get("away_pitcher", ""),
                }
        elif sig_type == SIGNAL_GAME_FINAL:
            if not entry.get("last_result"):
                entry["last_result"] = {
                    "opponent": data.get("opponent", ""),
                    "result": data.get("result", "T"),
                    "score": data.get("score", ""),
                }
        elif sig_type in (SIGNAL_TEAM_WIN, SIGNAL_TEAM_LOSS):
            result = "W" if sig_type == SIGNAL_TEAM_WIN else "L"
            entry["last_result"] = {
                "opponent": data.get("opponent", ""),
                "result": result,
                "score": data.get("score", ""),
            }
        elif sig_type == SIGNAL_GAME_COMPLETED:
            if not entry.get("last_result"):
                entry["last_result"] = {
                    "opponent": data.get("opponent", ""),
                    "result": "T",
                    "score": data.get("score", ""),
                }

    # Populate team metadata from follows (league, record, logo, streak)
    from apps.sports.services.streaks import compute_streaks_for_teams

    follows = UserTeamFollow.objects.filter(
        user=user, is_active=True
    ).select_related("team__league")

    team_ids_present = [f.team_id for f in follows if f.team_id in team_data]
    streak_map = compute_streaks_for_teams(team_ids_present) if team_ids_present else {}

    for f in follows:
        if f.team_id in team_data:
            team_data[f.team_id]["league"] = f.team.league.abbreviation
            team_data[f.team_id]["record"] = f.team.record
            team_data[f.team_id]["record_display"] = f.team.record_display
            team_data[f.team_id]["logo_url"] = f.team.logo_url or ""
            team_data[f.team_id]["streak"] = streak_map.get(f.team_id, "")

    # Deduplicate signal types
    for entry in team_data.values():
        entry["active_signals"] = list(set(entry["active_signals"]))

    return sorted(team_data.values(), key=lambda x: x["priority"])


@shared_task(
    name="sports.sync_games_from_provider",
    max_retries=2,
    default_retry_delay=30,
    acks_late=True,
    reject_on_worker_lost=True,
)
def sync_games_from_provider(leagues=None):
    """
    Background task: Sync sports data from the configured provider.

    Fetches standings (team records) and game events (schedule, scores, pitchers)
    for all leagues with active followers. Idempotent — safe on every tick.

    Args:
        leagues: Optional list of league slugs to force sync (bypasses
                 follower check). Used by bootstrap to ensure initial data.

    Raw sync only: no streak computation, no urgency, no signals.
    Those are handled by compute_sports_signals().
    """
    from apps.sports.services.sync_service import sync_sports_data
    result = sync_sports_data(leagues=leagues)
    logger.info("sync_games_from_provider: %s", result)
    return result
