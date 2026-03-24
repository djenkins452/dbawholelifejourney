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
from django.db.models import Q
from django.utils import timezone

from apps.sports.models import GameEvent, UserTeamFollow
from apps.sports.services.cache_manager import (
    set_sync_health,
    set_user_sports_summary,
    set_user_today_games,
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
from apps.sports.services.time_windows import GameTimeWindow

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

            # Build and cache team summaries from signals
            summaries = _build_summaries_from_signals(user, signals, now)
            set_user_sports_summary(user.id, summaries)

            # Cache today's games (extracted from signals)
            today_games = [
                s["data"] for s in signals
                if s["signal_type"] == SIGNAL_GAME_TODAY
            ]
            set_user_today_games(user.id, today_games)

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
    """
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
                "active_signals": [],
            }

        entry = team_data[team_id]
        entry["active_signals"].append(signal["signal_type"])
        data = signal["data"]

        sig_type = signal["signal_type"]

        if sig_type == SIGNAL_GAME_LIVE:
            entry["status"] = "live"
            entry["next_game"] = {
                "opponent": data.get("opponent", ""),
                "time": data.get("start_time", ""),
                "venue": data.get("venue", ""),
                "score": f"{data.get('away_score', 0)}-{data.get('home_score', 0)}",
            }
        elif sig_type == SIGNAL_GAME_STARTING_SOON:
            if entry["status"] != "live":
                entry["status"] = "starting_soon"
            entry["next_game"] = {
                "opponent": data.get("opponent", ""),
                "time": data.get("start_time", ""),
                "venue": data.get("venue", ""),
            }
        elif sig_type == SIGNAL_GAME_TODAY:
            if entry["status"] not in ("live", "starting_soon"):
                entry["status"] = "today"
            if not entry["next_game"]:
                entry["next_game"] = {
                    "opponent": data.get("opponent", ""),
                    "time": data.get("start_time", ""),
                    "venue": data.get("venue", ""),
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
                    "result": "T",  # Tie or unknown
                    "score": data.get("score", ""),
                }

    # Populate league names from follows
    follows = UserTeamFollow.objects.filter(
        user=user, is_active=True
    ).select_related("team__league")
    for f in follows:
        if f.team_id in team_data:
            team_data[f.team_id]["league"] = f.team.league.abbreviation

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
def sync_games_from_provider():
    """
    Background task: Sync sports data from the configured provider.

    Fetches standings (team records) and game events (schedule, scores, pitchers)
    for all leagues with active followers. Idempotent — safe on every tick.

    Raw sync only: no streak computation, no urgency, no signals.
    Those are handled by compute_sports_signals().
    """
    from apps.sports.services.sync_service import sync_sports_data
    return sync_sports_data()
