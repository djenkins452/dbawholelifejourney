"""
Sports Domain — Page Contract Builder

Single source of truth for the sports page structure.

Architecture: GameEvent → Signals → State (_contract) → Page Contract → Template

The canonical entry point is `build_sports_page_view(user)` which returns a
deterministic contract with ALL keys always present. Templates render this
contract directly — no grouping, filtering, or ordering in templates.

Contract shape (non-negotiable):
{
    "hero": {} | None,
    "live_context": {} | None,
    "scoreboard": {"header": str, "live": [], "final": [], "upcoming": []},
    "timeline": {"now": [], "today": [], "tomorrow": []},
    "ticker": [],
    "momentum": [],
    "storylines": [],
    "more_games": [],
    "meta": {},
}
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


# ═══════════════════════════════════════════════════════════════════════
# CANONICAL ENTRY POINT
# ═══════════════════════════════════════════════════════════════════════

def build_sports_page_view(user):
    """Single canonical entry point for the sports page contract.

    Returns a deterministic dict with ALL keys always present.
    No conditional key omission. Empty = empty list/dict or None.

    This is the ONLY function templates and views should consume.
    """
    now = timezone.now()

    follows = (
        UserTeamFollow.objects.filter(user=user, is_active=True)
        .select_related("team__league__sport")
        .order_by("priority", "team__location")
    )

    if not follows.exists():
        return _empty_page_contract()

    team_map = {f.team_id: f for f in follows}
    team_ids = list(team_map.keys())

    contract = _get_contract(user)

    if contract and contract.get('teams'):
        return _assemble_page_contract(contract, follows, team_map, team_ids, now)

    # Fallback: signal-based path (pre-contract compat)
    logger.debug("Sports page view: _contract not available, using signal fallback")
    return _assemble_page_contract_from_signals(user, follows, team_map, team_ids, now)


def build_sports_view_model(user):
    """Legacy entry point — delegates to build_sports_page_view().

    Kept for backward compatibility with cache_manager and tasks.
    """
    return build_sports_page_view(user)


def _get_contract(user):
    """Read _contract from SAE state. Returns None on miss."""
    try:
        from apps.core.ai_state.state_engine import get_module_state
        sports_state = get_module_state(user, 'sports') or {}
        return sports_state.get('_contract')
    except Exception:
        logger.debug("Sports view model: failed to read _contract", exc_info=True)
        return None


def _assemble_page_contract(contract, follows, team_map, team_ids, now):
    """Assemble the canonical page contract from _contract (primary path).

    Page flow: Hero → Live Context → Scoreboard → Timeline → Ticker
    All keys always present. No conditional omission.
    """
    teams = contract.get('teams', [])
    storylines_raw = contract.get('storylines', [])

    # ── DEDUP TRACKING ─────────────────────────────────────────────
    shown_keys = set()

    def _game_key(team_entry):
        ng = team_entry.get('next_game') or {}
        gid = ng.get('game_id')
        if gid:
            return f"gid:{gid}"
        names = sorted([team_entry.get('team_name', ''), ng.get('opponent', '')])
        return f"match:{names[0]}|{names[1]}"

    def _is_shown(team_entry):
        return _game_key(team_entry) in shown_keys

    def _mark_shown(team_entry):
        shown_keys.add(_game_key(team_entry))

    # ── PRIORITY ENGINE ────────────────────────────────────────────
    scored_teams = []
    for t in teams:
        if t.get('status') in ('live', 'starting_soon', 'today', 'upcoming') and t.get('next_game'):
            score = _compute_contract_priority_score(t)
            scored_teams.append((score, t))
    scored_teams.sort(key=lambda x: -x[0])

    # ── 1. HERO ────────────────────────────────────────────────────
    hero = None
    hero_team_id = None
    if scored_teams:
        _, hero_team = scored_teams[0]
        hero = _build_hero_from_contract(hero_team)
        hero_team_id = hero_team.get('team_id')
        _mark_shown(hero_team)
    else:
        for t in teams:
            if t.get('last_result'):
                hero = _build_hero_from_contract(t)
                hero_team_id = t.get('team_id')
                break

    if hero:
        _enhance_hero_context(hero)

    # ── 2. LIVE CONTEXT (only if hero is LIVE, else None) ──────────
    live_context = None
    if hero and hero.get('urgency') == 'live':
        live_context = _build_live_context(hero)

    # ── 3. SCOREBOARD (grouped: live/final/upcoming) ───────────────
    scoreboard = _build_scoreboard_grouped(hero, now)

    # Collect scoreboard game_ids for ticker exclusion
    scoreboard_game_ids = set()
    for bucket in ('live', 'final', 'upcoming'):
        for g in scoreboard.get(bucket, []):
            gid = g.get('game_id')
            if gid:
                scoreboard_game_ids.add(gid)

    # ── 4. TIMELINE (dict: now/today/tomorrow) ─────────────────────
    timeline = _build_timeline(scored_teams, hero_team_id, _is_shown, _mark_shown, now)

    # ── 5. TICKER (excludes hero + scoreboard games) ───────────────
    hero_game_id = None
    if hero:
        hero_game_id = hero.get('game_id')
    excluded_game_ids = scoreboard_game_ids
    if hero_game_id:
        excluded_game_ids = excluded_game_ids | {hero_game_id}
    ticker = _build_filtered_ticker(teams, storylines_raw, excluded_game_ids)

    # ── 6. MOMENTUM ────────────────────────────────────────────────
    momentum = _build_momentum(teams)

    # ── 7. STORYLINES ──────────────────────────────────────────────
    storylines = _build_storylines(storylines_raw)

    # ── 8. MORE GAMES ──────────────────────────────────────────────
    more_games = []
    for _, t in scored_teams:
        if _is_shown(t):
            continue
        if t.get('status') not in ('today', 'starting_soon', 'upcoming'):
            continue
        _mark_shown(t)
        ng = t.get('next_game') or {}
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
        "live_context": live_context,
        "scoreboard": scoreboard,
        "timeline": timeline,
        "ticker": ticker,
        "momentum": momentum,
        "storylines": storylines,
        "more_games": more_games,
        "meta": meta,
    }


def _enhance_hero_context(hero):
    """Add tournament context line and game state line to hero.

    Tournament context: "Sweet 16 — Elite Eight on the line"
    Game state: status-based display ("LIVE", scheduled time, "FINAL")
    """
    game_note = hero.get('game_note', '') or ''
    note_lower = game_note.lower()

    # Tournament context line
    tournament_context = ""
    if game_note:
        round_label = ""
        for phrase in ('sweet 16', 'elite eight', 'final four', 'championship',
                       'round of 32', 'round of 64', 'first round', 'second round'):
            if phrase in note_lower:
                round_label = phrase.title()
                break
        if round_label:
            next_round = _NEXT_ROUND.get(round_label.lower(), "")
            if next_round:
                tournament_context = f"{round_label} — {next_round.replace('the ', '').title()} on the line"
            else:
                tournament_context = round_label

    hero["tournament_context"] = tournament_context
    hero["game_type"] = hero.get("game_type", "")


def _build_live_context(hero):
    """Build the deterministic live context block shown under hero when game is live.

    Line 1: "{team} leads {opponent} {score}" (or "tied with")
    Line 2: Game status
    """
    team = hero.get('team_name', '')
    opponent = hero.get('opponent', '')
    score_str = hero.get('score', '')

    # Parse score to determine leader
    lead_line = f"{team} vs {opponent}"
    if score_str:
        parts = score_str.replace('–', '-').split('-')
        if len(parts) == 2:
            try:
                s1 = int(parts[0].strip())
                s2 = int(parts[1].strip())
                if s1 > s2:
                    lead_line = f"{team} leads {opponent} {score_str}"
                elif s2 > s1:
                    lead_line = f"{opponent} leads {team} {score_str}"
                else:
                    lead_line = f"{team} and {opponent} tied {score_str}"
            except (ValueError, IndexError):
                lead_line = f"{team} vs {opponent} {score_str}"

    status_line = "Game in progress"

    return {
        "lead_line": lead_line,
        "status_line": status_line,
    }


def _build_scoreboard_grouped(hero, now):
    """Build the scoreboard as a grouped dict: live/final/upcoming.

    Queries GameEvent for same-day tournament games.
    Hero game is included. Max 6 games total. No duplicates.
    Returns the canonical shape even when no data exists.
    """
    empty = {"header": "", "live": [], "final": [], "upcoming": []}

    if not hero:
        return empty

    game_note = hero.get('game_note', '') or ''
    note_lower = game_note.lower()

    # Derive round label for header
    round_label = ""
    for phrase in ('sweet 16', 'elite eight', 'final four', 'championship',
                   'round of 32', 'round of 64', 'first round', 'second round'):
        if phrase in note_lower:
            round_label = phrase.title()
            break

    game_type = hero.get('game_type', '') or ''
    if not round_label and game_type not in ('tournament', 'postseason'):
        return empty

    header = f"{round_label} Scoreboard" if round_label else "Tournament Scoreboard"

    # Query tournament games from same day
    live_games = []
    final_games = []
    upcoming_games = []

    try:
        from django.utils.dateparse import parse_datetime
        hero_time = parse_datetime(hero.get('start_time', ''))
        if not hero_time:
            hero_time = now

        day_start = hero_time.replace(hour=0, minute=0, second=0, microsecond=0)
        day_end = hero_time.replace(hour=23, minute=59, second=59, microsecond=999999)

        tourney_games = (
            GameEvent.objects
            .filter(game_type='tournament', start_time__range=(day_start, day_end))
            .select_related('home_team', 'away_team')
            .order_by('start_time')[:6]
        )

        for g in tourney_games:
            context_line = ""
            if g.game_note:
                parts = g.game_note.split(" - ")
                if len(parts) > 1:
                    context_line = parts[0]

            score_display = ""
            if g.status in (GameEvent.STATUS_LIVE, GameEvent.STATUS_FINAL):
                score_display = f"{g.home_score or 0}-{g.away_score or 0}"

            entry = {
                "game_id": g.id,
                "home": g.home_team.name if hasattr(g.home_team, 'name') else str(g.home_team),
                "away": g.away_team.name if hasattr(g.away_team, 'name') else str(g.away_team),
                "home_logo": getattr(g.home_team, 'logo_url', '') or '',
                "away_logo": getattr(g.away_team, 'logo_url', '') or '',
                "home_score": g.home_score or 0,
                "away_score": g.away_score or 0,
                "score": score_display,
                "start_time": g.start_time.isoformat() if g.start_time else "",
                "context": context_line,
            }

            if g.status == GameEvent.STATUS_LIVE:
                live_games.append(entry)
            elif g.status == GameEvent.STATUS_FINAL:
                final_games.append(entry)
            else:
                upcoming_games.append(entry)

    except Exception:
        logger.debug("Scoreboard cluster query failed", exc_info=True)

    if not live_games and not final_games and not upcoming_games:
        return empty

    return {
        "header": header,
        "live": live_games,
        "final": final_games,
        "upcoming": upcoming_games,
    }


def _build_timeline(scored_teams, hero_team_id, _is_shown, _mark_shown, now):
    """Build grouped timeline as a dict: now/today/tomorrow.

    now = LIVE games only
    today = future same-day games (strictly > now)
    tomorrow = next calendar day only

    Strict chronological sorting within each group. No overlaps.
    All keys always present.
    """
    from django.utils.dateparse import parse_datetime

    now_games = []
    today_games = []
    tomorrow_games = []

    tomorrow_start = (now + timedelta(days=1)).replace(hour=0, minute=0, second=0, microsecond=0)
    tomorrow_end = tomorrow_start.replace(hour=23, minute=59, second=59, microsecond=999999)

    for _, t in scored_teams:
        tid = t.get('team_id')
        if tid == hero_team_id:
            continue
        if _is_shown(t):
            continue

        ng = t.get('next_game') or {}
        start_time_str = ng.get('start_time', '')
        status = t.get('status', 'upcoming')
        context = _game_context_line(t)

        game_entry = {
            "team_name": t.get('team_name', ''),
            "team_logo": t.get('logo_url', ''),
            "opponent": ng.get('opponent', ''),
            "is_home": ng.get('is_home', True),
            "start_time": start_time_str,
            "urgency": status,
            "league": t.get('league', ''),
            "context": context,
        }

        if status == 'live':
            _mark_shown(t)
            now_games.append(game_entry)
        elif status in ('starting_soon', 'today'):
            _mark_shown(t)
            today_games.append(game_entry)
        elif status == 'upcoming' and start_time_str:
            try:
                start = parse_datetime(start_time_str)
                if start and tomorrow_start <= start <= tomorrow_end:
                    _mark_shown(t)
                    tomorrow_games.append(game_entry)
                elif start and start < tomorrow_start:
                    _mark_shown(t)
                    today_games.append(game_entry)
            except (ValueError, TypeError):
                pass

    # Chronological sort within each group
    def _sort_key(g):
        return g.get('start_time', '') or 'zzzz'

    today_games.sort(key=_sort_key)
    tomorrow_games.sort(key=_sort_key)

    return {
        "now": now_games,
        "today": today_games,
        "tomorrow": tomorrow_games,
    }


def _build_filtered_ticker(teams, storylines, excluded_game_ids):
    """Build ticker excluding hero and scoreboard games.

    Ticker is background ambient display only.
    Priority: live scores → starting soon → finals → high storylines.
    Max 12 items. No duplicates.
    """
    live = []
    soon = []
    finals = []
    seen_teams = set()

    sorted_teams = sorted(teams, key=lambda t: t.get('priority', 3))

    for t in sorted_teams:
        name = t.get('team_name', '')
        if name in seen_teams:
            continue

        ng = t.get('next_game') or {}
        gid = ng.get('game_id')

        # Skip games already in hero or scoreboard
        if gid and gid in excluded_game_ids:
            seen_teams.add(name)
            continue

        if t.get('status') == 'live':
            seen_teams.add(name)
            score = ng.get('score', '')
            opp = ng.get('opponent', '')
            live.append({
                "text": f"{name} {score} vs {opp}" if score else f"{name} vs {opp} — Live",
                "type": "live",
            })

        elif t.get('status') == 'starting_soon':
            seen_teams.add(name)
            opp = ng.get('opponent', '')
            game_note = ng.get('game_note', '')
            note_tag = ""
            if game_note:
                parts = game_note.split(" - ")
                note_tag = f" ({parts[-1]})" if parts else ""
            soon.append({
                "text": f"{name} vs {opp} tips off soon{note_tag}",
                "type": "soon",
            })

        if t.get('priority', 3) <= 2:
            lr = t.get('last_result')
            if lr and name not in seen_teams:
                result = lr.get('result', '')
                verb = "beat" if result == "W" else ("fell to" if result == "L" else "tied")
                opp = lr.get('opponent', '')
                score = lr.get('score', '')
                finals.append({
                    "text": f"{name} {verb} {opp} {score}",
                    "type": "final",
                })
                seen_teams.add(name)

    story_items = []
    for sl in storylines:
        if sl.get('importance') == 'high' and sl.get('type') != 'live':
            story_items.append({
                "text": sl.get('message', ''),
                "type": "storyline",
            })

    return (live + soon + finals + story_items)[:12]


def _build_momentum(teams):
    """Build momentum section: teams with streak >= 3, sorted by count desc. Max 5."""
    momentum = []
    for t in sorted(teams, key=lambda x: x.get('streak_count', 0), reverse=True):
        if t.get('streak_count', 0) < 3:
            continue
        sc = t['streak_count']
        st = t.get('streak_type', '')
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
    return momentum


def _build_storylines(storylines_raw):
    """Build storylines: high+medium importance, max 5."""
    result = []
    for importance in ('high', 'medium'):
        for sl in storylines_raw:
            if sl.get('importance') == importance:
                result.append({
                    "message": sl.get('message', ''),
                    "type": sl.get('type', 'streak'),
                    "importance": importance,
                })
                if len(result) >= 5:
                    break
        if len(result) >= 5:
            break
    return result


def _game_context_line(team_entry):
    """Generate a short, human context line for why a game matters.

    Priority: game significance > streak narrative > record.
    Must sound like a sports anchor, not a database.
    """
    ng = team_entry.get('next_game') or {}
    game_type = ng.get('game_type', 'regular')
    game_note = ng.get('game_note', '')

    # Game significance
    if game_note:
        parts = game_note.split(" - ")
        return parts[-1] if parts else game_note
    if game_type == 'tournament':
        return "Tournament game"
    if game_type == 'postseason':
        return "Playoff game"

    # Streak narrative
    sc = team_entry.get('streak_count', 0)
    st = team_entry.get('streak_type', '')
    if st == 'W' and sc >= 7:
        return f"Red hot — {sc} wins in a row"
    if st == 'W' and sc >= 5:
        return f"Rolling with {sc} straight wins"
    if st == 'W' and sc >= 3:
        return f"Won {sc} straight"
    if st == 'L' and sc >= 5:
        return f"Need this one — {sc} straight losses"
    if st == 'L' and sc >= 3:
        return f"Looking to snap a {sc}-game skid"

    record = team_entry.get('record', '')
    if record:
        return record
    return ""


def _assemble_page_contract_from_signals(user, follows, team_map, team_ids, now):
    """Fallback: build page contract from signals directly (pre-contract compat).

    Returns the same canonical shape as _assemble_page_contract.
    """
    from apps.sports.services.cache_manager import get_user_signals, set_user_signals
    from apps.sports.services.streaks import compute_streaks_for_teams

    signals = get_user_signals(user)
    if signals is None:
        signals = generate_sports_signals(user)
        set_user_signals(user.id, signals)

    streak_map = compute_streaks_for_teams(team_ids)

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
    hero_signal = None
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

    hero_team_id = hero_signal["team_id"] if hero_signal else None
    shown_keys_fb = set()

    def _sig_key(sig):
        gid = sig.get("game_id")
        if gid:
            return f"gid:{gid}"
        d = sig.get("data", {})
        names = sorted([sig.get('team_name', ''), d.get('opponent', '')])
        return f"match:{names[0]}|{names[1]}"

    if hero_signal:
        shown_keys_fb.add(_sig_key(hero_signal))

    # Live context
    live_context = None
    if hero and hero.get('urgency') == 'live':
        live_context = _build_live_context(hero)

    # Timeline: now/today/tomorrow from signals
    now_games = []
    today_games = []
    tomorrow_games = []
    tomorrow_start = (now + timedelta(days=1)).replace(hour=0, minute=0, second=0, microsecond=0)
    tomorrow_end = tomorrow_start.replace(hour=23, minute=59, second=59, microsecond=999999)

    for _, s in scored_games:
        if s["team_id"] == hero_team_id:
            continue
        key = _sig_key(s)
        if key in shown_keys_fb:
            continue
        follow = team_map.get(s["team_id"])
        if not follow:
            continue
        d = s["data"]
        streak = streak_map.get(s["team_id"], "")
        game_note = (d.get("game_note", "") or "").lower()
        if "sweet 16" in game_note:
            context = "Sweet 16"
        elif "elite eight" in game_note:
            context = "Elite Eight"
        elif "final four" in game_note:
            context = "Final Four"
        elif d.get("game_type") == "tournament":
            context = "Tournament"
        elif d.get("game_type") == "postseason":
            context = "Playoffs"
        elif streak and len(streak) >= 2:
            try:
                sc = int(streak[1:])
                if streak[0] == 'W' and sc >= 3:
                    context = f"Won {sc} straight"
                elif streak[0] == 'L' and sc >= 3:
                    context = f"Need a win after {sc} losses"
                else:
                    context = follow.team.record_display or ""
            except ValueError:
                context = follow.team.record_display or ""
        else:
            context = follow.team.record_display or ""

        entry = {
            "team_name": s["team_name"],
            "team_logo": follow.team.logo_url or "",
            "opponent": d.get("opponent", ""),
            "is_home": d.get("is_home", True),
            "start_time": d.get("start_time", ""),
            "urgency": _signal_to_urgency(s["signal_type"]),
            "league": d.get("league", ""),
            "context": context,
        }

        sig_type = s["signal_type"]
        if sig_type == SIGNAL_GAME_LIVE:
            shown_keys_fb.add(key)
            now_games.append(entry)
        elif sig_type in (SIGNAL_GAME_STARTING_SOON, SIGNAL_GAME_TODAY):
            shown_keys_fb.add(key)
            today_games.append(entry)
        elif sig_type == SIGNAL_GAME_UPCOMING:
            start_str = d.get("start_time", "")
            if start_str:
                try:
                    from django.utils.dateparse import parse_datetime
                    start = parse_datetime(start_str)
                    if start and tomorrow_start <= start <= tomorrow_end:
                        shown_keys_fb.add(key)
                        tomorrow_games.append(entry)
                    elif start and start < tomorrow_start:
                        shown_keys_fb.add(key)
                        today_games.append(entry)
                except (ValueError, TypeError):
                    pass

    timeline = {
        "now": now_games,
        "today": today_games,
        "tomorrow": tomorrow_games,
    }

    # Momentum
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

    # Ticker
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

    # More games
    more_games = []
    for _, s in scored_games:
        key = _sig_key(s)
        if key in shown_keys_fb:
            continue
        shown_keys_fb.add(key)
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
        "live_context": live_context,
        "scoreboard": {"header": "", "live": [], "final": [], "upcoming": []},
        "timeline": timeline,
        "ticker": ticker_items[:15],
        "momentum": momentum,
        "storylines": storylines,
        "more_games": more_games,
        "meta": meta,
    }


# ═══════════════════════════════════════════════════════════════════════
# PRIORITY ENGINE
# ═══════════════════════════════════════════════════════════════════════

def _compute_priority_score(signal, streak_map):
    """Importance engine (signal fallback path).

    Same 4-dimension scoring as _compute_contract_priority_score:
    1. User relevance, 2. Game significance, 3. Time sensitivity, 4. Momentum.
    """
    score = 0
    priority = signal.get("priority", 3)
    sig_type = signal["signal_type"]
    data = signal.get("data", {})
    game_type = data.get("game_type", "regular")
    game_note = (data.get("game_note", "") or "").lower()

    # 1. User relevance
    if priority == 1:
        score += 100
    elif priority == 2:
        score += 60
    else:
        score += 30

    # 2. Game significance
    if game_type == 'tournament':
        score += 80
        if any(w in game_note for w in ('final four', 'championship', 'elite eight')):
            score += 30
        elif 'sweet 16' in game_note:
            score += 20
    elif game_type == 'postseason':
        score += 70
        if any(w in game_note for w in ('world series', 'super bowl', 'stanley cup', 'nba finals')):
            score += 30
        elif any(w in game_note for w in ('conference', 'championship', 'nlcs', 'alcs')):
            score += 20
    else:
        score += 10

    # 3. Time sensitivity
    if sig_type == SIGNAL_GAME_LIVE:
        score += 70
    elif sig_type == SIGNAL_GAME_STARTING_SOON:
        score += 60
    elif sig_type == SIGNAL_GAME_TODAY:
        score += 40
    elif sig_type == SIGNAL_GAME_UPCOMING:
        start_str = data.get("start_time", "")
        if start_str:
            try:
                from django.utils.dateparse import parse_datetime
                start = parse_datetime(start_str)
                if start:
                    hours_away = (start - timezone.now()).total_seconds() / 3600
                    if hours_away <= 6:
                        score += 25
                    elif hours_away <= 24:
                        score += 15
                    else:
                        score += 5
            except (ValueError, TypeError):
                score += 5

    # 4. Momentum
    tid = signal["team_id"]
    streak = streak_map.get(tid, "")
    if streak and len(streak) >= 2:
        try:
            streak_count = int(streak[1:])
            if streak_count >= 7:
                score += 20
            elif streak_count >= 5:
                score += 15
            elif streak_count >= 3:
                score += 10
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

    # Game significance (signal fallback path)
    game_type = data.get("game_type", "regular")
    game_note = data.get("game_note", "")
    if game_note:
        parts = game_note.split(" - ")
        hero["insight"] = parts[-1] if parts else game_note
        hero["game_note"] = game_note
    elif game_type == 'tournament':
        hero["insight"] = "Tournament"
    elif game_type == 'postseason':
        hero["insight"] = "Playoffs"

    # Headline (signal fallback path)
    hero["headline"] = ""
    team_name = signal["team_name"]
    opponent = data.get("opponent", "")
    short = team_name.split()[-1] if team_name else team_name
    if len(short) < 4 and len(team_name.split()) > 1:
        short = team_name
    opp_short = opponent.split()[-1] if opponent else opponent
    if len(opp_short) < 4 and len(opponent.split()) > 1:
        opp_short = opponent

    # Tournament headlines take priority
    if game_note:
        note_lower = game_note.lower()
        round_name = ""
        for key in ("sweet 16", "elite eight", "final four", "championship",
                     "round of 32", "round of 64", "first round", "second round"):
            if key in note_lower:
                round_name = key.title()
                break
        if round_name:
            next_round = _NEXT_ROUND.get(round_name.lower(), "")
            if sig_type == SIGNAL_GAME_LIVE:
                hero["headline"] = f"{round_name} — {short} fighting for a spot in {next_round}" if next_round else f"{round_name} — {short} vs {opp_short}"
            else:
                hero["headline"] = f"{round_name} matchup — {short} takes on {opp_short}"
        else:
            hero["headline"] = f"{short} take on {opp_short}"
    elif sig_type == SIGNAL_GAME_LIVE:
        hs = data.get("home_score", 0) or 0
        aws = data.get("away_score", 0) or 0
        diff = abs(hs - aws)
        if diff == 0:
            hero["headline"] = f"All tied up between {short} and {opp_short}"
        elif diff <= 3:
            hero["headline"] = f"Tight battle between {short} and {opp_short}"
        else:
            hero["headline"] = f"{short} and {opp_short} going at it"
    elif streak and len(streak) >= 2:
        try:
            sc = int(streak[1:])
            st = streak[0]
            if st == 'W' and sc >= 5:
                hero["headline"] = f"{short} riding a hot streak into this one"
            elif st == 'W' and sc >= 3:
                hero["headline"] = f"{short} looking to keep the momentum going"
            elif st == 'L' and sc >= 3:
                hero["headline"] = f"{short} looking to snap a {sc}-game skid"
        except ValueError:
            pass
    if not hero["headline"] and opponent:
        hero["headline"] = f"{short} take on {opp_short}"

    # Pitcher for baseball
    if data.get("is_home") and data.get("home_pitcher"):
        hero["pitcher"] = data["home_pitcher"]
    elif not data.get("is_home") and data.get("away_pitcher"):
        hero["pitcher"] = data["away_pitcher"]
    else:
        hero["pitcher"] = ""

    # Signal-derived insight line (only if game significance didn't set one)
    if not hero.get("insight"):
        if sig_type == SIGNAL_GAME_LIVE:
            hero["insight"] = "Game in progress"
        elif sig_type == SIGNAL_GAME_STARTING_SOON:
            hero["insight"] = "Starting soon"
    if not hero.get("insight") and streak:
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
    """Importance engine: score every game on 4 dimensions.

    1. User relevance  — follow priority (primary > secondary > casual)
    2. Game significance — tournament/postseason > regular season
    3. Time sensitivity — live > starting soon > today > future
    4. Momentum context — streaks amplify importance

    Scores are additive. Hero = highest score. All sections sort by score.
    """
    score = 0
    priority = team_entry.get('priority', 3)
    status = team_entry.get('status', 'upcoming')
    ng = team_entry.get('next_game') or {}
    game_type = ng.get('game_type', '')
    game_note = ng.get('game_note', '') or ''

    # Defensive: if contract is stale and missing game_type, check DB directly
    if not game_type and ng.get('game_id'):
        try:
            ge = GameEvent.objects.only('game_type', 'game_note').get(id=ng['game_id'])
            game_type = ge.game_type or 'regular'
            game_note = ge.game_note or ''
        except GameEvent.DoesNotExist:
            game_type = 'regular'
    elif not game_type:
        game_type = 'regular'

    game_note = game_note.lower()

    # ── 1. USER RELEVANCE (max 100) ─────────────────────────────────
    if priority == 1:
        score += 100  # Primary team — always highest weight
    elif priority == 2:
        score += 60   # Secondary — follow closely
    else:
        score += 30   # Casual — light awareness

    # ── 2. GAME SIGNIFICANCE (max 80) ───────────────────────────────
    if game_type == 'tournament':
        # Tournament games — highest significance
        score += 80
        # Bonus for later rounds
        if any(w in game_note for w in ('final four', 'championship', 'elite eight')):
            score += 30  # Final Four / Championship = massive
        elif 'sweet 16' in game_note:
            score += 20
    elif game_type == 'postseason':
        score += 70
        # Bonus for later rounds
        if any(w in game_note for w in ('world series', 'super bowl', 'stanley cup', 'nba finals')):
            score += 30
        elif any(w in game_note for w in ('conference', 'championship', 'nlcs', 'alcs')):
            score += 20
        elif any(w in game_note for w in ('divisional', 'wild card')):
            score += 10
    else:
        score += 10  # Regular season baseline

    # ── 3. TIME SENSITIVITY (max 70) ────────────────────────────────
    if status == 'live':
        score += 70   # Live = highest temporal urgency
    elif status == 'starting_soon':
        score += 60   # Within 2 hours
    elif status == 'today':
        score += 40   # Today but not imminent
    elif status == 'upcoming':
        if ng.get('start_time'):
            try:
                from django.utils.dateparse import parse_datetime
                start = parse_datetime(ng['start_time'])
                if start:
                    hours_away = (start - timezone.now()).total_seconds() / 3600
                    if hours_away <= 6:
                        score += 25
                    elif hours_away <= 24:
                        score += 15
                    else:
                        score += 5
            except (ValueError, TypeError):
                score += 5

    # ── 4. MOMENTUM CONTEXT (max 20) ────────────────────────────────
    streak_count = team_entry.get('streak_count', 0)
    if streak_count >= 7:
        score += 20   # Dominant streak
    elif streak_count >= 5:
        score += 15   # Hot/struggling
    elif streak_count >= 3:
        score += 10   # Notable streak

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
        "game_type": ng.get('game_type', 'regular'),
        "game_id": ng.get('game_id'),
    }

    # ── Insight tag: short significance label for badge area ────────
    game_type = ng.get('game_type', 'regular')
    game_note = ng.get('game_note', '')

    if game_note:
        parts = game_note.split(" - ")
        hero["insight"] = parts[-1] if parts else game_note
        hero["game_note"] = game_note
    elif game_type == 'tournament':
        hero["insight"] = "Tournament"
    elif game_type == 'postseason':
        hero["insight"] = "Playoffs"

    # ── Headline: single compelling narrative line ────────────────
    hero["headline"] = _build_hero_headline(team_entry, status, ng, lr)

    return hero


# ── Tournament round progression map ─────────────────────────────
_NEXT_ROUND = {
    "round of 64": "the Round of 32",
    "first round": "the Second Round",
    "round of 32": "the Sweet 16",
    "second round": "the Sweet 16",
    "sweet 16": "the Elite Eight",
    "elite eight": "the Final Four",
    "final four": "the Championship",
    "wild card": "the Divisional Round",
    "divisional": "the Conference Championship",
    "conference championship": "the Championship",
}


def _build_hero_headline(team_entry, status, ng, lr):
    """Build a single compelling narrative headline for the hero.

    Must be short, human, high-impact. Never generic.
    Reads game significance, streaks, and results to compose a line
    that answers: why should I care about this game RIGHT NOW?
    """
    team = team_entry.get('team_name', '')
    # Short name: "Atlanta Braves" → "Braves", "Alabama Crimson Tide" → "Alabama"
    short = team.split()[-1] if team else team
    if len(short) < 4 and len(team.split()) > 1:
        short = team  # Keep full name for short words like "LSU"

    opponent = ng.get('opponent', '') or lr.get('opponent', '')
    opp_short = opponent.split()[-1] if opponent else opponent
    if len(opp_short) < 4 and len(opponent.split()) > 1:
        opp_short = opponent

    game_note = (ng.get('game_note', '') or '').lower()
    game_type = ng.get('game_type', 'regular')
    streak_count = team_entry.get('streak_count', 0)
    streak_type = team_entry.get('streak_type', '')

    # ── Tournament / postseason headlines ────────────────────────
    if game_type in ('tournament', 'postseason') and game_note:
        # Find what round they're playing for advancement
        for round_key, next_round in _NEXT_ROUND.items():
            if round_key in game_note:
                if status == 'live':
                    return f"{short} fighting to reach {next_round}"
                return f"{short} play for a spot in {next_round}"

        # Generic tournament/postseason
        if status == 'live':
            return f"Win or go home for {short}"
        return f"Do-or-die for {short} tonight"

    # ── Live game headlines ──────────────────────────────────────
    if status == 'live':
        score = ng.get('score', '')
        if score:
            parts = score.split('-')
            if len(parts) == 2:
                try:
                    s1, s2 = int(parts[0].strip()), int(parts[1].strip())
                    diff = abs(s1 - s2)
                    if diff == 0:
                        return f"All tied up between {short} and {opp_short}"
                    elif diff <= 3:
                        return f"Tight battle between {short} and {opp_short}"
                    elif s1 > s2:
                        return f"{short} in control"
                    else:
                        return f"{short} trying to claw back"
                except (ValueError, IndexError):
                    pass
        return f"{short} and {opp_short} going at it"

    # ── Streak-based headlines ───────────────────────────────────
    if streak_type == 'W' and streak_count >= 7:
        return f"{short} can't be stopped right now"
    if streak_type == 'W' and streak_count >= 5:
        return f"{short} riding a hot streak into this one"
    if streak_type == 'W' and streak_count >= 3:
        return f"{short} looking to keep the momentum going"
    if streak_type == 'L' and streak_count >= 5:
        return f"{short} desperate for a turnaround"
    if streak_type == 'L' and streak_count >= 3:
        return f"{short} looking to snap a {streak_count}-game skid"

    # ── Fallback: opponent-based ─────────────────────────────────
    if opponent:
        return f"{short} take on {opp_short}"
    return ""


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


def _empty_page_contract():
    """Return empty page contract — all keys present, no conditional omission."""
    return {
        "hero": None,
        "live_context": None,
        "scoreboard": {"header": "", "live": [], "final": [], "upcoming": []},
        "timeline": {"now": [], "today": [], "tomorrow": []},
        "ticker": [],
        "momentum": [],
        "storylines": [],
        "more_games": [],
        "meta": {"last_updated": None, "data_source": ""},
    }
