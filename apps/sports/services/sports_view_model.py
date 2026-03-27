"""
Sports Domain — View Model Builder

Transforms sports state (_contract) into a structured view model for template rendering.
Reads canonical state from SAE — never generates signals or computes streaks directly.

Architecture: GameEvent → Signals → State (_contract) → View Model → Template

Presentation-only concerns owned by this layer:
- Hero selection (priority engine)
- Momentum strip layout + heat interpretation
- Game row formatting
- Ticker (ambient display)
- Filtering storylines for display
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

logger = logging.getLogger(__name__)


def build_sports_view_model(user):
    """
    Build the complete sports view model.

    Primary path: reads _contract from SAE state (pre-computed by background task).
    Fallback path: generates signals directly if _contract is not yet available
    (graceful degradation during rollout — remove after one deploy cycle).

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

    # ── Try _contract path first ─────────────────────────────────────
    contract = _get_contract(user)

    if contract and contract.get('teams'):
        return _build_from_contract(contract, follows, team_map, team_ids, now)

    # ── Fallback: signal-based path (pre-contract compat) ────────────
    logger.debug("Sports view model: _contract not available, using signal fallback")
    return _build_from_signals(user, follows, team_map, team_ids, now)


def _get_contract(user):
    """Read _contract from SAE state. Returns None on miss."""
    try:
        from apps.core.ai_state.state_engine import get_module_state
        sports_state = get_module_state(user, 'sports') or {}
        return sports_state.get('_contract')
    except Exception:
        logger.debug("Sports view model: failed to read _contract", exc_info=True)
        return None


def _build_from_contract(contract, follows, team_map, team_ids, now):
    """Build view model from _contract (primary path).

    V3 layout: Hero → Live Now → Ticker → What's Next → Momentum →
               Storylines → More Games

    Reads canonical team data and storylines from _contract.
    Derives presentation-only values: heat, priority scores, hero selection.
    """
    teams = contract.get('teams', [])
    storylines = contract.get('storylines', [])

    # ── PRIORITY ENGINE: score every team with a game ────────────────
    scored_teams = []
    for t in teams:
        if t.get('status') in ('live', 'starting_soon', 'today', 'upcoming') and t.get('next_game'):
            score = _compute_contract_priority_score(t)
            scored_teams.append((score, t))

    scored_teams.sort(key=lambda x: -x[0])

    # ── HERO: single most important game ─────────────────────────────
    hero = None
    hero_team_id = None
    hero_game_id = None
    if scored_teams:
        _, hero_team = scored_teams[0]
        hero = _build_hero_from_contract(hero_team)
        hero_team_id = hero_team.get('team_id')
        hero_game_id = (hero_team.get('next_game') or {}).get('game_id')
    else:
        for t in teams:
            if t.get('last_result'):
                hero = _build_hero_from_contract(t)
                hero_team_id = t.get('team_id')
                break

    # ── LIVE NOW: all live games except hero (max 5, deduped) ────────
    live_now = []
    live_seen = {hero_game_id} if hero_game_id else set()
    for t in teams:
        if t.get('status') != 'live' or not t.get('next_game'):
            continue
        ng = t['next_game']
        game_id = ng.get('game_id')
        if game_id and game_id in live_seen:
            continue
        if game_id:
            live_seen.add(game_id)
        live_now.append({
            "team_name": t.get('team_name', ''),
            "team_logo": t.get('logo_url', ''),
            "opponent": ng.get('opponent', ''),
            "opponent_logo": ng.get('opponent_logo', ''),
            "is_home": ng.get('is_home', True),
            "score": ng.get('score', ''),
            "league": t.get('league', ''),
        })
        if len(live_now) >= 5:
            break

    # ── TICKER: recent finals + live scores (max 15) ─────────────────
    ticker = _build_smart_ticker(teams, storylines)

    # ── WHAT'S NEXT: top 3 non-hero, non-live within 48h ────────────
    whats_next = []
    next_seen = set()
    for _, t in scored_teams:
        tid = t.get('team_id')
        if tid == hero_team_id:
            continue
        if t.get('status') == 'live':
            continue
        ng = t.get('next_game') or {}
        game_id = ng.get('game_id')
        if game_id and game_id in next_seen:
            continue
        if game_id:
            next_seen.add(game_id)
        # 48h window filter
        if ng.get('start_time'):
            try:
                from django.utils.dateparse import parse_datetime
                start = parse_datetime(ng['start_time'])
                if start and (start - now).total_seconds() > 48 * 3600:
                    continue
            except (ValueError, TypeError):
                pass
        # Context line: why this game matters
        context = _game_context_line(t)
        whats_next.append({
            "team_name": t.get('team_name', ''),
            "team_logo": t.get('logo_url', ''),
            "opponent": ng.get('opponent', ''),
            "is_home": ng.get('is_home', True),
            "start_time": ng.get('start_time', ''),
            "urgency": t.get('status', 'upcoming'),
            "league": t.get('league', ''),
            "context": context,
        })
        if len(whats_next) >= 3:
            break

    # ── MOMENTUM: teams with streak >= 3, sorted by count desc ────────
    momentum = []
    for t in sorted(teams, key=lambda x: x.get('streak_count', 0), reverse=True):
        if t.get('streak_count', 0) < 3:
            continue
        sc = t['streak_count']
        st = t.get('streak_type', '')
        # Interpret the streak
        if st == 'W' and sc >= 7:
            label = "Dominant"
        elif st == 'W' and sc >= 5:
            label = "On fire"
        elif st == 'W':
            label = "Hot"
        elif st == 'L' and sc >= 7:
            label = "Freefall"
        elif st == 'L' and sc >= 5:
            label = "Struggling"
        else:
            label = "Cold"
        momentum.append({
            "team_name": t.get('team_name', ''),
            "streak_type": st,
            "streak_count": sc,
            "heat": "hot" if st == 'W' else "cold",
            "label": label,
        })
        if len(momentum) >= 5:
            break

    # ── KEY STORYLINES: high+medium importance, max 5 ─────────────────
    key_storylines = []
    for importance in ('high', 'medium'):
        for sl in storylines:
            if sl.get('importance') == importance:
                key_storylines.append({
                    "message": sl.get('message', ''),
                    "type": sl.get('type', 'streak'),
                    "importance": importance,
                })
                if len(key_storylines) >= 5:
                    break
        if len(key_storylines) >= 5:
            break

    # ── MORE GAMES: remaining today/upcoming games not already shown ──
    shown_ids = {hero_game_id} if hero_game_id else set()
    shown_ids.update(g.get('game_id') for g in live_now if 'game_id' in g)
    shown_ids.update(next_seen)
    shown_ids.discard(None)

    more_games = []
    for _, t in scored_teams:
        ng = t.get('next_game') or {}
        game_id = ng.get('game_id')
        if game_id in shown_ids:
            continue
        if game_id:
            shown_ids.add(game_id)
        if t.get('status') not in ('today', 'starting_soon', 'upcoming'):
            continue
        more_games.append({
            "team_name": t.get('team_name', ''),
            "team_logo": t.get('logo_url', ''),
            "opponent": ng.get('opponent', ''),
            "is_home": ng.get('is_home', True),
            "start_time": ng.get('start_time', ''),
            "urgency": t.get('status', 'upcoming'),
            "league": t.get('league', ''),
        })
        if len(more_games) >= 8:
            break

    meta = _build_meta(team_ids, now)

    return {
        "hero": hero,
        "live_now": live_now,
        "ticker": ticker,
        "whats_next": whats_next,
        "momentum": momentum,
        "storylines": key_storylines,
        "more_games": more_games,
        "meta": meta,
    }


def _build_smart_ticker(teams, storylines):
    """Build a slow, meaningful ticker from recent results and live scores.

    Content: finals, live scores, high-importance storylines.
    Max 15 items. Designed for 3-4 second per-item display.
    """
    items = []

    # Live scores first
    for t in teams:
        if t.get('status') == 'live':
            ng = t.get('next_game') or {}
            items.append({
                "text": f"{t['team_name']} vs {ng.get('opponent', '')} — {ng.get('score', '')}",
                "type": "live",
            })

    # Recent finals
    for t in teams:
        lr = t.get('last_result')
        if not lr:
            continue
        result = lr.get('result', '')
        prefix = "W" if result == "W" else ("L" if result == "L" else "T")
        items.append({
            "text": f"{t['team_name']} {prefix} {lr.get('score', '')} vs {lr.get('opponent', '')}",
            "type": "final",
        })

    # High-importance storylines as ticker items
    for sl in storylines:
        if sl.get('importance') == 'high' and sl.get('type') != 'live':
            items.append({
                "text": sl.get('message', ''),
                "type": "storyline",
            })

    return items[:15]


def _game_context_line(team_entry):
    """Generate a short context line for why a game matters."""
    sc = team_entry.get('streak_count', 0)
    st = team_entry.get('streak_type', '')
    record = team_entry.get('record', '')

    if st == 'W' and sc >= 5:
        return f"On a {sc}-game win streak"
    if st == 'W' and sc >= 3:
        return f"Won {sc} straight"
    if st == 'L' and sc >= 5:
        return f"Lost {sc} straight — looking to bounce back"
    if st == 'L' and sc >= 3:
        return f"Need a win after {sc} losses"
    if record:
        return record
    return ""


def _build_from_signals(user, follows, team_map, team_ids, now):
    """Fallback: build view model from signals directly (pre-contract compat)."""
    from apps.sports.services.cache_manager import get_user_signals, set_user_signals
    from apps.sports.services.streaks import compute_streaks_for_teams

    signals = get_user_signals(user)
    if signals is None:
        signals = generate_sports_signals(user)
        set_user_signals(user.id, signals)

    streak_map = compute_streaks_for_teams(team_ids)

    # Index signals by type and team
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

    # Priority engine
    all_game_signals = live_signals + soon_signals + today_signals + upcoming_signals
    scored_games = []
    seen_game_ids = set()

    for s in all_game_signals:
        gid = s["game_id"]
        dedup_key = (gid, s["team_id"])
        if dedup_key in seen_game_ids:
            continue
        seen_game_ids.add(dedup_key)
        score = _compute_priority_score(s, streak_map)
        scored_games.append((score, s))

    scored_games.sort(key=lambda x: -x[0])

    # Hero
    hero = None
    if scored_games:
        _, hero_signal = scored_games[0]
        follow = team_map.get(hero_signal["team_id"])
        team = follow.team if follow else None
        hero = _build_hero(hero_signal, team, streak_map, now)
    elif final_signals:
        fs = final_signals[0]
        follow = team_map.get(fs["team_id"])
        team = follow.team if follow else None
        hero = _build_hero(fs, team, streak_map, now)

    # Live Now: live games except hero (max 5)
    hero_team_id = hero_signal["team_id"] if scored_games else None
    hero_game_id = hero_signal["game_id"] if scored_games else None
    live_now = []
    live_seen = {hero_game_id} if hero_game_id else set()
    for s in live_signals:
        gid = s["game_id"]
        if gid in live_seen:
            continue
        live_seen.add(gid)
        follow = team_map.get(s["team_id"])
        if follow:
            live_now.append({
                "team_name": s["team_name"],
                "team_logo": follow.team.logo_url or "",
                "opponent": s["data"].get("opponent", ""),
                "opponent_logo": s["data"].get("opponent_logo", ""),
                "is_home": s["data"].get("is_home", True),
                "score": s["data"].get("score", ""),
                "league": s["data"].get("league", ""),
            })
        if len(live_now) >= 5:
            break

    # What's Next: top 3 non-hero, non-live games
    whats_next = []
    next_seen = set()
    for _, s in scored_games:
        if s["team_id"] == hero_team_id:
            continue
        if s["signal_type"] == SIGNAL_GAME_LIVE:
            continue
        gid = s["game_id"]
        if gid in next_seen:
            continue
        next_seen.add(gid)
        follow = team_map.get(s["team_id"])
        if follow:
            streak = streak_map.get(s["team_id"], "")
            context = ""
            if streak and len(streak) >= 2:
                try:
                    sc = int(streak[1:])
                    if streak[0] == 'W' and sc >= 3:
                        context = f"Won {sc} straight"
                    elif streak[0] == 'L' and sc >= 3:
                        context = f"Need a win after {sc} losses"
                except ValueError:
                    pass
            if not context:
                context = follow.team.record_display or ""
            whats_next.append({
                "team_name": s["team_name"],
                "team_logo": follow.team.logo_url or "",
                "opponent": s["data"].get("opponent", ""),
                "is_home": s["data"].get("is_home", True),
                "start_time": s["data"].get("start_time", ""),
                "urgency": _signal_to_urgency(s["signal_type"]),
                "league": s["data"].get("league", ""),
                "context": context,
            })
        if len(whats_next) >= 3:
            break

    # Momentum: teams with streak >= 3
    momentum = []
    for tid, streak in sorted(streak_map.items(), key=lambda x: int(x[1][1:]) if x[1] and len(x[1]) >= 2 else 0, reverse=True):
        if not streak or len(streak) < 2:
            continue
        try:
            s_count = int(streak[1:])
        except ValueError:
            continue
        if s_count < 3:
            continue
        follow = team_map.get(tid)
        st = streak[0]
        if st == 'W' and s_count >= 7:
            label = "Dominant"
        elif st == 'W' and s_count >= 5:
            label = "On fire"
        elif st == 'W':
            label = "Hot"
        elif st == 'L' and s_count >= 7:
            label = "Freefall"
        elif st == 'L' and s_count >= 5:
            label = "Struggling"
        else:
            label = "Cold"
        if follow:
            momentum.append({
                "team_name": follow.team.full_name,
                "streak_type": st,
                "streak_count": s_count,
                "heat": "hot" if st == "W" else "cold",
                "label": label,
            })
        if len(momentum) >= 5:
            break

    # Storylines
    stories = _build_stories(streak_signals, final_signals, live_signals, team_map)
    storylines = [
        {"message": s["text"], "type": s["type"], "importance": "medium"}
        for s in stories
    ]

    # Ticker from signal-derived data
    ticker_items = []
    for s in live_signals:
        d = s["data"]
        ticker_items.append({
            "text": f"{s['team_name']} vs {d.get('opponent', '')} — {d.get('score', '')}",
            "type": "live",
        })
    for s in final_signals[:8]:
        d = s["data"]
        result = d.get("result", "")
        ticker_items.append({
            "text": f"{s['team_name']} {result} {d.get('score', '')} vs {d.get('opponent', '')}",
            "type": "final",
        })

    # More games: remaining scored games not shown
    shown_ids = {hero_game_id} if hero_game_id else set()
    shown_ids.update(s["game_id"] for s in live_signals if s["game_id"] in live_seen)
    shown_ids.update(next_seen)
    shown_ids.discard(None)
    more_games = []
    for _, s in scored_games:
        gid = s["game_id"]
        if gid in shown_ids:
            continue
        shown_ids.add(gid)
        if s["signal_type"] == SIGNAL_GAME_LIVE:
            continue
        follow = team_map.get(s["team_id"])
        if follow:
            more_games.append({
                "team_name": s["team_name"],
                "team_logo": follow.team.logo_url or "",
                "opponent": s["data"].get("opponent", ""),
                "is_home": s["data"].get("is_home", True),
                "start_time": s["data"].get("start_time", ""),
                "urgency": _signal_to_urgency(s["signal_type"]),
                "league": s["data"].get("league", ""),
            })
        if len(more_games) >= 8:
            break

    meta = _build_meta(team_ids, now)

    return {
        "hero": hero,
        "live_now": live_now,
        "ticker": ticker_items[:15],
        "whats_next": whats_next,
        "momentum": momentum,
        "storylines": storylines,
        "more_games": more_games,
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


# ═══════════════════════════════════════════════════════════════════════
# CONTRACT-BASED BUILDERS (primary path)
# ═══════════════════════════════════════════════════════════════════════

def _compute_contract_priority_score(team_entry):
    """Priority scoring from _contract team entry (presentation-only)."""
    score = 0
    priority = team_entry.get('priority', 3)
    status = team_entry.get('status', 'upcoming')

    # Team importance
    if priority == 1:
        score += 50
    elif priority == 2:
        score += 35
    else:
        score += 20

    # Temporal urgency
    if status == 'live':
        score += 40
    elif status == 'starting_soon':
        score += 30
    elif status == 'today':
        score += 25
    elif status == 'upcoming':
        ng = team_entry.get('next_game')
        if ng and ng.get('start_time'):
            try:
                from django.utils.dateparse import parse_datetime
                start = parse_datetime(ng['start_time'])
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
    streak_count = team_entry.get('streak_count', 0)
    if streak_count >= 5:
        score += 20
    elif streak_count >= 3:
        score += 15

    return score


def _build_hero_from_contract(team_entry):
    """Build hero section from _contract team entry."""
    ng = team_entry.get('next_game') or {}
    lr = team_entry.get('last_result') or {}
    status = team_entry.get('status', 'upcoming')

    hero = {
        "team_name": team_entry.get('team_name', ''),
        "team_logo": team_entry.get('logo_url', ''),
        "opponent": ng.get('opponent', '') or lr.get('opponent', ''),
        "opponent_logo": ng.get('opponent_logo', ''),
        "urgency": status,
        "start_time": ng.get('start_time', ''),
        "venue": ng.get('venue', ''),
        "is_home": ng.get('is_home', True),
        "league": team_entry.get('league', ''),
        "record": team_entry.get('record_display', '') or team_entry.get('record', ''),
        "streak": f"{team_entry.get('streak_type', '')}{team_entry.get('streak_count', 0)}" if team_entry.get('streak_type') else "",
        "score": ng.get('score', ''),
        "insight": "",
        "pitcher": ng.get('pitcher', ''),
    }

    # Signal-derived insight line
    streak_count = team_entry.get('streak_count', 0)
    streak_type = team_entry.get('streak_type', '')
    if status == 'live':
        hero["insight"] = "Game in progress"
    elif status == 'starting_soon':
        hero["insight"] = "Starting soon"
    elif streak_type == 'W' and streak_count >= 3:
        hero["insight"] = f"On a {streak_count}-game win streak"
    elif streak_type == 'L' and streak_count >= 3:
        hero["insight"] = f"{streak_count} straight losses"

    return hero


def _build_momentum_strip_from_contract(teams):
    """Build momentum strip from _contract teams (presentation-only heat derivation)."""
    strip = []
    for t in teams:
        status = t.get('status', 'upcoming')
        ng = t.get('next_game') or {}
        lr = t.get('last_result') or {}

        # Determine status label and line
        status_label = ""
        display_status = "neutral"
        line = ""

        if status == 'live':
            status_label = "LIVE"
            display_status = "live"
            prefix = "vs" if ng.get('is_home') else "@"
            line = f"{prefix} {ng.get('opponent', '')} · {ng.get('score', '')}"
        elif status == 'starting_soon':
            status_label = "SOON"
            display_status = "soon"
            prefix = "vs" if ng.get('is_home') else "@"
            line = f"{prefix} {ng.get('opponent', '')}"
        elif status == 'today':
            status_label = "TODAY"
            display_status = "today"
            prefix = "vs" if ng.get('is_home') else "@"
            line = f"{prefix} {ng.get('opponent', '')} · {_format_time(ng.get('start_time', ''))}"
        elif status == 'upcoming' and ng:
            status_label = "NEXT"
            display_status = "next"
            prefix = "vs" if ng.get('is_home') else "@"
            line = f"{prefix} {ng.get('opponent', '')} · {_format_datetime_short(ng.get('start_time', ''))}"
        elif lr:
            result = lr.get('result', '')
            status_label = "FINAL"
            display_status = "final"
            line = f"{result} vs {lr.get('opponent', '')} · {lr.get('score', '')}"
        else:
            continue  # Off-season — skip

        # Heat: derived from streak (presentation-only)
        heat = "neutral"
        streak_type = t.get('streak_type', '')
        streak_count = t.get('streak_count', 0)
        if streak_type == 'W' and streak_count >= 3:
            heat = "hot"
        elif streak_type == 'L' and streak_count >= 3:
            heat = "cold"

        streak_display = f"{streak_type}{streak_count}" if streak_type and streak_count else ""

        strip.append({
            "team_name": t.get('team_name', ''),
            "team_abbr": "",  # Not in _contract, populated from team model in fallback
            "logo_url": t.get('logo_url', ''),
            "league": t.get('league', ''),
            "record": t.get('record_display', '') or t.get('record', ''),
            "streak": streak_display,
            "heat": heat,
            "status": display_status,
            "status_label": status_label,
            "line": line,
        })

    return strip


def _build_game_item_from_contract(team_entry, urgency):
    """Build a game row item from _contract team entry."""
    ng = team_entry.get('next_game') or {}
    return {
        "team_name": team_entry.get('team_name', ''),
        "team_logo": team_entry.get('logo_url', ''),
        "opponent": ng.get('opponent', ''),
        "opponent_logo": ng.get('opponent_logo', ''),
        "urgency": urgency,
        "is_home": ng.get('is_home', True),
        "start_time": ng.get('start_time', ''),
        "venue": ng.get('venue', ''),
        "score": ng.get('score', ''),
        "home_score": None,
        "away_score": None,
        "league": team_entry.get('league', ''),
        "pitcher": ng.get('pitcher', ''),
    }


def _build_stories_from_contract(storylines):
    """Build display stories from _contract.storylines.

    Maps storyline types to display types and filters for display (max 5).
    """
    type_map = {
        'streak': 'hot',   # Positive streak → hot
        'live': 'live',
        'blowout': 'blowout',
        'close': 'close',
    }
    stories = []
    for sl in storylines:
        # Check for losing streak → cold
        display_type = type_map.get(sl.get('type', ''), 'hot')
        if sl.get('type') == 'streak' and 'dropped' in sl.get('message', ''):
            display_type = 'cold'
        stories.append({
            'text': sl.get('message', ''),
            'type': display_type,
        })
    return stories[:5]


# ═══════════════════════════════════════════════════════════════════════
# SIGNAL-BASED BUILDERS (fallback path — legacy)
# ═══════════════════════════════════════════════════════════════════════

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
        "live_now": [],
        "ticker": [],
        "whats_next": [],
        "momentum": [],
        "storylines": [],
        "more_games": [],
        "meta": {"last_updated": None, "data_source": ""},
    }
