"""
Sports Domain — View Model Builder

Transforms sports signals into a structured view model for template rendering.
This is the ONLY layer between signals and the template — no raw GameEvent queries.

Architecture: GameEvent → Signals → View Model → Template
"""
import logging
from datetime import timedelta

from django.db.models import Q
from django.utils import timezone

from apps.sports.models import GameEvent, UserTeamFollow
from apps.sports.services.signal_generator import (
    SIGNAL_GAME_FINAL,
    SIGNAL_GAME_LIVE,
    SIGNAL_GAME_STARTING_SOON,
    SIGNAL_GAME_TODAY,
    SIGNAL_GAME_UPCOMING,
    SIGNAL_LOSING_STREAK,
    SIGNAL_WIN_STREAK,
    generate_sports_signals,
)
from apps.sports.services.streaks import compute_streaks_for_teams

logger = logging.getLogger(__name__)


def build_sports_view_model(user):
    """
    Build the complete sports view model from signals.

    Returns a dict with all keys needed by the template:
    {
        "hero": {...} or None,
        "momentum_strip": [...],
        "live_games": [...],
        "my_schedule": [...],
        "league_boards": [...],
        "stories": [...],
        "ticker": [...],
        "recent_action": [...],
        "meta": {"last_updated": ..., "data_source": ...},
    }
    """
    now = timezone.now()

    # ── Get follows and team data ────────────────────────────────────
    follows = (
        UserTeamFollow.objects.filter(user=user, is_active=True)
        .select_related("team__league__sport")
        .order_by("priority", "team__location")
    )

    if not follows.exists():
        return _empty_view_model()

    team_map = {f.team_id: f for f in follows}
    team_ids = list(team_map.keys())

    # ── Generate signals (or read from cache) ────────────────────────
    from apps.sports.services.cache_manager import get_user_signals, set_user_signals

    signals = get_user_signals(user)
    if signals is None:
        signals = generate_sports_signals(user)
        set_user_signals(user.id, signals)

    # ── Batch compute streaks (reuse existing utility) ───────────────
    streak_map = compute_streaks_for_teams(team_ids)

    # ── Index signals by type and team ───────────────────────────────
    signals_by_team = {}
    live_signals = []
    today_signals = []
    soon_signals = []
    upcoming_signals = []
    final_signals = []
    streak_signals = []

    for s in signals:
        tid = s["team_id"]
        if tid not in signals_by_team:
            signals_by_team[tid] = []
        signals_by_team[tid].append(s)

        st = s["signal_type"]
        if st == SIGNAL_GAME_LIVE:
            live_signals.append(s)
        elif st == SIGNAL_GAME_STARTING_SOON:
            soon_signals.append(s)
        elif st == SIGNAL_GAME_TODAY:
            today_signals.append(s)
        elif st == SIGNAL_GAME_UPCOMING:
            upcoming_signals.append(s)
        elif st == SIGNAL_GAME_FINAL:
            final_signals.append(s)
        elif st in (SIGNAL_WIN_STREAK, SIGNAL_LOSING_STREAK):
            streak_signals.append(s)

    # ── PRIORITY ENGINE: score every game signal ─────────────────────
    all_game_signals = live_signals + soon_signals + today_signals + upcoming_signals
    scored_games = []
    seen_game_ids = set()

    for s in all_game_signals:
        gid = s["game_id"]
        # Deduplicate: same game can appear for multiple signal types
        dedup_key = (gid, s["team_id"])
        if dedup_key in seen_game_ids:
            continue
        seen_game_ids.add(dedup_key)

        score = _compute_priority_score(s, streak_map)
        scored_games.append((score, s))

    scored_games.sort(key=lambda x: -x[0])  # Highest priority first

    # ── BUILD HERO ───────────────────────────────────────────────────
    hero = None
    if scored_games:
        _, hero_signal = scored_games[0]
        follow = team_map.get(hero_signal["team_id"])
        team = follow.team if follow else None
        hero = _build_hero(hero_signal, team, streak_map, now)
    elif final_signals:
        # Fallback: most recent completed game
        fs = final_signals[0]
        follow = team_map.get(fs["team_id"])
        team = follow.team if follow else None
        hero = _build_hero(fs, team, streak_map, now)

    # ── BUILD MOMENTUM STRIP ────────────────────────────────────────
    momentum_strip = _build_momentum_strip(follows, signals_by_team, streak_map, final_signals)

    # ── BUILD LIVE GAMES ────────────────────────────────────────────
    live_games = []
    for s in live_signals:
        follow = team_map.get(s["team_id"])
        if follow:
            live_games.append(_build_game_item(s, follow.team, "live"))

    # ── BUILD MY SCHEDULE (scored, deduped, top 5) ──────────────────
    my_schedule = []
    schedule_game_ids = set()
    for _, s in scored_games:
        if s["signal_type"] == SIGNAL_GAME_LIVE:
            continue  # Already in live_games
        gid = s["game_id"]
        if gid in schedule_game_ids:
            continue
        schedule_game_ids.add(gid)
        follow = team_map.get(s["team_id"])
        if follow:
            urgency = _signal_to_urgency(s["signal_type"])
            my_schedule.append(_build_game_item(s, follow.team, urgency))
        if len(my_schedule) >= 5:
            break

    # ── BUILD LEAGUE BOARDS (bounded GameEvent query — for league context) ──
    league_boards = _build_league_boards(follows, now)

    # ── BUILD STORIES (signal-derived narratives) ───────────────────
    stories = _build_stories(streak_signals, final_signals, live_signals, team_map)

    # ── BUILD TICKER (all recent games — ambient awareness) ─────────
    ticker = _build_ticker(now)

    # ── BUILD RECENT ACTION ─────────────────────────────────────────
    recent_action = _build_recent_action()

    # ── METADATA ────────────────────────────────────────────────────
    meta = _build_meta(team_ids, now)

    return {
        "hero": hero,
        "momentum_strip": momentum_strip,
        "live_games": live_games,
        "my_schedule": my_schedule,
        "league_boards": league_boards,
        "stories": stories,
        "ticker": ticker,
        "recent_action": recent_action,
        "meta": meta,
    }


# ═══════════════════════════════════════════════════════════════════════
# PRIORITY ENGINE
# ═══════════════════════════════════════════════════════════════════════

def _compute_priority_score(signal, streak_map):
    """
    Deterministic priority scoring for a game signal.

    Higher score = more prominent display position.
    """
    score = 0
    priority = signal.get("priority", 3)
    sig_type = signal["signal_type"]

    # Team importance
    if priority == 1:
        score += 50
    elif priority == 2:
        score += 35
    else:
        score += 20

    # Temporal urgency
    if sig_type == SIGNAL_GAME_LIVE:
        score += 40
    elif sig_type == SIGNAL_GAME_STARTING_SOON:
        score += 30
    elif sig_type == SIGNAL_GAME_TODAY:
        score += 25
    elif sig_type == SIGNAL_GAME_UPCOMING:
        # Closer upcoming games score higher
        start_str = signal["data"].get("start_time", "")
        if start_str:
            try:
                from django.utils.dateparse import parse_datetime
                start = parse_datetime(start_str)
                if start:
                    hours_away = (start - timezone.now()).total_seconds() / 3600
                    if hours_away <= 6:
                        score += 15
                    elif hours_away <= 24:
                        score += 10
                    else:
                        score += 5
            except (ValueError, TypeError):
                score += 5

    # Streak heat
    tid = signal["team_id"]
    streak = streak_map.get(tid, "")
    if streak and len(streak) >= 2:
        try:
            streak_count = int(streak[1:])
            if streak_count >= 5:
                score += 20
            elif streak_count >= 3:
                score += 15
        except ValueError:
            pass

    return score


# ═══════════════════════════════════════════════════════════════════════
# BUILDERS
# ═══════════════════════════════════════════════════════════════════════

def _build_hero(signal, team, streak_map, now):
    """Build hero section data from highest-priority signal."""
    data = signal["data"]
    sig_type = signal["signal_type"]

    urgency = _signal_to_urgency(sig_type)
    streak = streak_map.get(signal["team_id"], "")

    hero = {
        "team_name": signal["team_name"],
        "team_logo": team.logo_url if team else "",
        "opponent": data.get("opponent", ""),
        "opponent_logo": data.get("opponent_logo", ""),
        "urgency": urgency,
        "start_time": data.get("start_time", ""),
        "venue": data.get("venue", ""),
        "is_home": data.get("is_home", True),
        "league": data.get("league", ""),
        "record": team.record_display if team else "",
        "streak": streak,
        "score": "",
        "insight": "",
    }

    # Score display
    if sig_type in (SIGNAL_GAME_LIVE, SIGNAL_GAME_FINAL):
        hs = data.get("home_score", 0)
        aws = data.get("away_score", 0)
        if data.get("is_home"):
            hero["score"] = f"{hs} – {aws}"
        else:
            hero["score"] = f"{aws} – {hs}"

    # Pitcher for baseball
    if data.get("is_home") and data.get("home_pitcher"):
        hero["pitcher"] = data["home_pitcher"]
    elif not data.get("is_home") and data.get("away_pitcher"):
        hero["pitcher"] = data["away_pitcher"]
    else:
        hero["pitcher"] = ""

    # Signal-derived insight line
    if sig_type == SIGNAL_GAME_LIVE:
        hero["insight"] = "Game in progress"
    elif sig_type == SIGNAL_GAME_STARTING_SOON:
        hero["insight"] = "Starting soon"
    elif streak:
        try:
            s_count = int(streak[1:])
            if streak.startswith("W") and s_count >= 3:
                hero["insight"] = f"On a {s_count}-game win streak"
            elif streak.startswith("L") and s_count >= 3:
                hero["insight"] = f"{s_count} straight losses"
        except ValueError:
            pass

    return hero


def _build_momentum_strip(follows, signals_by_team, streak_map, final_signals):
    """
    Build compact momentum strip — team status at a glance.

    Only includes teams with ACTIVE data (has game signals or streak).
    Off-season teams excluded.
    """
    # Index final signals by team for last result
    final_by_team = {}
    for s in final_signals:
        tid = s["team_id"]
        if tid not in final_by_team:
            final_by_team[tid] = s

    strip = []
    for follow in follows:
        team = follow.team
        tid = team.id
        team_signals = signals_by_team.get(tid, [])
        streak = streak_map.get(tid, "")
        final = final_by_team.get(tid)

        # Determine status
        status = "neutral"
        status_label = ""
        line = ""

        # Check for active game signals
        has_live = any(s["signal_type"] == SIGNAL_GAME_LIVE for s in team_signals)
        has_soon = any(s["signal_type"] == SIGNAL_GAME_STARTING_SOON for s in team_signals)
        has_today = any(s["signal_type"] == SIGNAL_GAME_TODAY for s in team_signals)
        has_upcoming = any(s["signal_type"] == SIGNAL_GAME_UPCOMING for s in team_signals)

        if has_live:
            sig = next(s for s in team_signals if s["signal_type"] == SIGNAL_GAME_LIVE)
            status_label = "LIVE"
            status = "live"
            d = sig["data"]
            prefix = "vs" if d.get("is_home") else "@"
            line = f"{prefix} {d.get('opponent', '')} · {d.get('score', '')}"
        elif has_soon:
            sig = next(s for s in team_signals if s["signal_type"] == SIGNAL_GAME_STARTING_SOON)
            status_label = "SOON"
            status = "soon"
            d = sig["data"]
            prefix = "vs" if d.get("is_home") else "@"
            line = f"{prefix} {d.get('opponent', '')}"
        elif has_today:
            sig = next(s for s in team_signals if s["signal_type"] == SIGNAL_GAME_TODAY)
            status_label = "TODAY"
            status = "today"
            d = sig["data"]
            prefix = "vs" if d.get("is_home") else "@"
            _format_time(d.get("start_time", ""))
            line = f"{prefix} {d.get('opponent', '')} · {_format_time(d.get('start_time', ''))}"
        elif has_upcoming:
            sig = next(s for s in team_signals if s["signal_type"] == SIGNAL_GAME_UPCOMING)
            status_label = "NEXT"
            status = "next"
            d = sig["data"]
            prefix = "vs" if d.get("is_home") else "@"
            line = f"{prefix} {d.get('opponent', '')} · {_format_datetime_short(d.get('start_time', ''))}"
        elif final:
            d = final["data"]
            result = d.get("result", "")
            status_label = "FINAL"
            status = "final"
            prefix = "vs" if d.get("is_home") else "@"
            line = f"{result} {prefix} {d.get('opponent', '')} · {d.get('score', '')}"
        else:
            # No signals at all — off-season
            continue  # Skip off-season teams from momentum strip

        # Heat indicator from streak
        heat = "neutral"
        if streak and len(streak) >= 2:
            try:
                s_count = int(streak[1:])
                if streak.startswith("W") and s_count >= 3:
                    heat = "hot"
                elif streak.startswith("L") and s_count >= 3:
                    heat = "cold"
            except ValueError:
                pass

        strip.append({
            "team_name": team.full_name,
            "team_abbr": team.abbreviation,
            "logo_url": team.logo_url or "",
            "league": team.league.abbreviation,
            "record": team.record_display,
            "streak": streak,
            "heat": heat,
            "status": status,
            "status_label": status_label,
            "line": line,
        })

    return strip


def _build_game_item(signal, team, urgency):
    """Build a game row item from a signal."""
    data = signal["data"]
    return {
        "team_name": signal["team_name"],
        "team_logo": team.logo_url or "",
        "opponent": data.get("opponent", ""),
        "opponent_logo": data.get("opponent_logo", ""),
        "urgency": urgency,
        "is_home": data.get("is_home", True),
        "start_time": data.get("start_time", ""),
        "venue": data.get("venue", ""),
        "score": data.get("score", ""),
        "home_score": data.get("home_score"),
        "away_score": data.get("away_score"),
        "league": data.get("league", ""),
        "pitcher": data.get("home_pitcher", "") if data.get("is_home") else data.get("away_pitcher", ""),
    }


def _build_league_boards(follows, now):
    """
    Build per-league scoreboards from recent GameEvents.

    This is the ONE place we query GameEvent for league-wide context.
    Bounded query, runs in background task (cached), not request path.
    """
    followed_leagues = list(set(f.team.league for f in follows))
    boards = []

    for league in sorted(followed_leagues, key=lambda l: l.abbreviation):
        # Games in the last 24h + next 48h
        league_games = (
            GameEvent.objects.filter(
                home_team__league=league,
                start_time__gte=now - timedelta(hours=24),
                start_time__lte=now + timedelta(hours=48),
            )
            .select_related("home_team", "away_team")
            .order_by("start_time")[:6]
        )

        # Fallback: last completed if nothing in window
        if not league_games.exists():
            league_games = (
                GameEvent.objects.filter(
                    home_team__league=league,
                    status=GameEvent.STATUS_FINAL,
                )
                .select_related("home_team", "away_team")
                .order_by("-start_time")[:6]
            )

        items = []
        for g in league_games:
            item = {
                "home": g.home_team.full_name,
                "away": g.away_team.full_name,
                "home_abbr": g.home_team.abbreviation,
                "away_abbr": g.away_team.abbreviation,
                "home_logo": g.home_team.logo_url or "",
                "away_logo": g.away_team.logo_url or "",
            }
            if g.status == GameEvent.STATUS_FINAL:
                item.update({
                    "home_score": g.home_score, "away_score": g.away_score,
                    "status_label": "FINAL", "status_class": "final",
                })
            elif g.status == GameEvent.STATUS_LIVE:
                item.update({
                    "home_score": g.home_score or 0, "away_score": g.away_score or 0,
                    "status_label": "LIVE", "status_class": "live",
                })
            else:
                item.update({
                    "home_score": None, "away_score": None,
                    "status_label": g.start_time.strftime("%-I:%M %p"),
                    "status_class": "upcoming",
                })
            items.append(item)

        if items:
            boards.append({
                "league_abbr": league.abbreviation,
                "league_name": league.name,
                "label": f"{league.abbreviation} — Today",
                "items": items,
            })

    return boards


def _build_stories(streak_signals, final_signals, live_signals, team_map):
    """
    Build signal-derived narrative items.

    Rules: deterministic, from signals only, no LLM.
    """
    stories = []

    # Streak stories
    for s in streak_signals:
        count = s["data"].get("streak_length", 0)
        name = s["team_name"]
        if s["signal_type"] == SIGNAL_WIN_STREAK:
            if count >= 5:
                stories.append({"text": f"{name} on fire — {count}-game win streak", "type": "hot"})
            else:
                stories.append({"text": f"{name} on a {count}-game win streak", "type": "hot"})
        else:
            stories.append({"text": f"{name} have dropped {count} straight", "type": "cold"})

    # Live game stories
    for s in live_signals:
        d = s["data"]
        name = s["team_name"]
        opp = d.get("opponent", "")
        score = d.get("score", "")
        if score:
            stories.append({"text": f"{name} vs {opp} — {score} (LIVE)", "type": "live"})

    # Blowout/close game stories from recent finals
    for s in final_signals[:8]:
        d = s["data"]
        hs = d.get("home_score", 0) or 0
        aws = d.get("away_score", 0) or 0
        diff = abs(hs - aws)
        if diff >= 8:
            winner = s["team_name"] if d.get("result") == "W" else d.get("opponent", "")
            stories.append({
                "text": f"{winner} cruise to {max(hs, aws)}–{min(hs, aws)} blowout",
                "type": "blowout",
            })
        elif diff <= 1 and (hs + aws) > 0:
            stories.append({
                "text": f"{s['team_name']} edge {d.get('opponent', '')} {hs}–{aws}",
                "type": "close",
            })

    return stories[:5]


def _build_ticker(now):
    """Build ambient ticker from all recent + upcoming games."""
    ticker_games = []
    ticker_window = (
        GameEvent.objects.filter(
            start_time__gte=now - timedelta(hours=48),
            start_time__lte=now + timedelta(hours=48),
        )
        .select_related("home_team__league", "away_team")
        .order_by("-start_time")[:60]
    )

    if not ticker_window.exists():
        ticker_window = (
            GameEvent.objects.filter(status=GameEvent.STATUS_FINAL)
            .select_related("home_team__league", "away_team")
            .order_by("-start_time")[:30]
        )

    for g in ticker_window:
        if g.status == GameEvent.STATUS_FINAL:
            label = f"{g.home_team.full_name} {g.home_score}–{g.away_score} {g.away_team.full_name}"
            badge = "FINAL"
            badge_class = "final"
        elif g.status == GameEvent.STATUS_LIVE:
            label = f"{g.home_team.full_name} {g.home_score or 0}–{g.away_score or 0} {g.away_team.full_name}"
            badge = "LIVE"
            badge_class = "live"
        else:
            label = f"{g.home_team.full_name} vs {g.away_team.full_name}"
            badge = g.start_time.strftime("%-I:%M %p")
            badge_class = "upcoming"
        ticker_games.append({
            "label": label,
            "badge": badge,
            "badge_class": badge_class,
            "league": g.home_team.league.abbreviation,
        })

    return ticker_games


def _build_recent_action():
    """Build recent completed games for the recent action section."""
    recent = (
        GameEvent.objects.filter(status=GameEvent.STATUS_FINAL)
        .select_related("home_team__league", "away_team")
        .order_by("-start_time")[:15]
    )
    items = []
    for g in recent:
        items.append({
            "home_team": g.home_team.full_name,
            "away_team": g.away_team.full_name,
            "home_score": g.home_score,
            "away_score": g.away_score,
            "league": g.home_team.league.abbreviation,
            "home_logo": g.home_team.logo_url or "",
            "away_logo": g.away_team.logo_url or "",
        })
    return items


def _build_meta(team_ids, now):
    """Build metadata (last updated, data source)."""
    from apps.sports.services.cache_manager import get_sync_health
    from apps.sports.services.provider_adapter import get_provider

    meta = {
        "last_updated": None,
        "data_source": "Live data",
    }

    # Data source
    provider = get_provider()
    if provider.provider_name() == "fixture":
        meta["data_source"] = "Simulated"

    # Last updated
    sync_health = get_sync_health()
    if sync_health and sync_health.get("last_run"):
        try:
            from django.utils.dateparse import parse_datetime
            ts = parse_datetime(sync_health["last_run"])
            if ts:
                delta = now - ts
                if delta.total_seconds() < 120:
                    relative = "Just now"
                elif delta.total_seconds() < 3600:
                    mins = int(delta.total_seconds() / 60)
                    relative = f"{mins} minutes ago"
                else:
                    hours = int(delta.total_seconds() / 3600)
                    relative = f"{hours} hours ago"
                meta["last_updated"] = {"timestamp": ts, "relative": relative}
        except (ValueError, TypeError):
            pass

    return meta


# ═══════════════════════════════════════════════════════════════════════
# HELPERS
# ═══════════════════════════════════════════════════════════════════════

def _signal_to_urgency(signal_type):
    """Map signal type to urgency label."""
    return {
        SIGNAL_GAME_LIVE: "live",
        SIGNAL_GAME_STARTING_SOON: "starting_soon",
        SIGNAL_GAME_TODAY: "today",
        SIGNAL_GAME_UPCOMING: "upcoming",
        SIGNAL_GAME_FINAL: "final",
    }.get(signal_type, "upcoming")


def _format_time(iso_str):
    """Format ISO datetime string to '7:10 PM'."""
    if not iso_str:
        return ""
    try:
        from django.utils.dateparse import parse_datetime
        dt = parse_datetime(iso_str)
        if dt:
            return dt.strftime("%-I:%M %p")
    except (ValueError, TypeError):
        pass
    return ""


def _format_datetime_short(iso_str):
    """Format ISO datetime string to 'Fri 7:10 PM'."""
    if not iso_str:
        return ""
    try:
        from django.utils.dateparse import parse_datetime
        dt = parse_datetime(iso_str)
        if dt:
            return dt.strftime("%a %-I:%M %p")
    except (ValueError, TypeError):
        pass
    return ""


def _empty_view_model():
    """Return empty view model structure."""
    return {
        "hero": None,
        "momentum_strip": [],
        "live_games": [],
        "my_schedule": [],
        "league_boards": [],
        "stories": [],
        "ticker": [],
        "recent_action": [],
        "meta": {"last_updated": None, "data_source": ""},
    }
