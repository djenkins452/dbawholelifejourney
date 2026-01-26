"""
Brain Training Views

Hub, game play, and API endpoints for the Brain Training module.
"""

import json
from datetime import timedelta

from django.contrib.auth.decorators import login_required
from django.db.models import Avg, Count, Sum
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.decorators.http import require_GET, require_POST

from apps.billing.models import BillingProfile

from .models import (
    Challenge,
    ChallengeQueue,
    DailyStats,
    Game,
    GameSession,
    UserGameStats,
    UserOverallStats,
)
from .services.generator import get_or_create_challenges
from .services.stats import get_improvement_stats


def check_subscription(user):
    """Check if user has an active subscription."""
    try:
        profile = user.billing_profile
        return profile.has_access
    except BillingProfile.DoesNotExist:
        return False


@login_required
def hub(request):
    """
    Brain Training hub page showing all available games.
    """
    if not check_subscription(request.user):
        return redirect('billing:select_plan')

    games = Game.objects.filter(is_active=True).order_by('sort_order')

    # Get user's stats for each game
    game_stats = {}
    for game in games:
        try:
            stats = UserGameStats.objects.get(user=request.user, game=game)
            game_stats[game.slug] = {
                'total_completed': stats.total_completed,
                'current_streak': stats.current_streak,
                'best_score': stats.best_score,
            }
        except UserGameStats.DoesNotExist:
            game_stats[game.slug] = None

    # Get overall stats
    try:
        overall = UserOverallStats.objects.get(user=request.user)
    except UserOverallStats.DoesNotExist:
        overall = None

    context = {
        'games': games,
        'game_stats': game_stats,
        'overall': overall,
    }
    return render(request, 'brain_training/hub.html', context)


@login_required
def play(request, game_slug):
    """
    Game play page for a specific game.
    """
    if not check_subscription(request.user):
        return redirect('billing:select_plan')

    game = get_object_or_404(Game, slug=game_slug, is_active=True)

    # Get user's preferred difficulty
    try:
        user_stats = UserGameStats.objects.get(user=request.user, game=game)
        preferred_difficulty = user_stats.preferred_difficulty
    except UserGameStats.DoesNotExist:
        preferred_difficulty = game.default_difficulty

    context = {
        'game': game,
        'preferred_difficulty': preferred_difficulty,
        'difficulty_levels': game.difficulty_levels or ['easy', 'medium', 'hard', 'expert'],
    }
    return render(request, f'brain_training/games/{game_slug}.html', context)


@login_required
@require_GET
def api_batch(request, game_slug):
    """
    Fetch a batch of challenges for a game.

    Query params:
    - count: Number of challenges (default 10, max 20)
    - difficulty: Difficulty level (default: user's preferred or game default)
    """
    if not check_subscription(request.user):
        return JsonResponse({'error': 'Subscription required'}, status=403)

    game = get_object_or_404(Game, slug=game_slug, is_active=True)

    count = min(int(request.GET.get('count', 10)), 20)
    difficulty = request.GET.get('difficulty')

    if not difficulty:
        try:
            user_stats = UserGameStats.objects.get(user=request.user, game=game)
            difficulty = user_stats.preferred_difficulty
        except UserGameStats.DoesNotExist:
            difficulty = game.default_difficulty

    # Try to get from queue first
    challenges = []
    queue_size = ChallengeQueue.queue_size(request.user, game)

    if queue_size > 0:
        for _ in range(min(count, queue_size)):
            challenge = ChallengeQueue.get_next(request.user, game)
            if challenge:
                challenges.append(challenge)

    # Fill remaining from database or generate new ones
    needed = count - len(challenges)
    if needed > 0:
        # Get challenges the user hasn't completed recently
        recent_completed = GameSession.objects.filter(
            user=request.user,
            challenge__game=game,
            status=GameSession.STATUS_COMPLETED,
            completed_at__gte=timezone.now() - timedelta(days=7),
        ).values_list('challenge_id', flat=True)

        db_challenges = list(Challenge.objects.filter(
            game=game,
            difficulty=difficulty,
        ).exclude(
            id__in=recent_completed
        ).order_by('?')[:needed])

        # If we don't have enough challenges, generate new ones
        if len(db_challenges) < needed:
            db_challenges = get_or_create_challenges(game, difficulty, needed)

        challenges.extend(db_challenges)

    # Format response
    data = {
        'game': game.slug,
        'difficulty': difficulty,
        'challenges': [
            {
                'id': c.challenge_id,
                'puzzle': c.puzzle_data,
                'difficulty': c.difficulty,
            }
            for c in challenges
        ],
        'queue_remaining': ChallengeQueue.queue_size(request.user, game),
    }

    return JsonResponse(data)


@login_required
@require_POST
def api_session_start(request):
    """
    Start a new game session.

    Body:
    - challenge_id: The challenge identifier
    - platform: 'ios', 'android', 'web' (optional)
    """
    if not check_subscription(request.user):
        return JsonResponse({'error': 'Subscription required'}, status=403)

    try:
        data = json.loads(request.body)
    except json.JSONDecodeError:
        return JsonResponse({'error': 'Invalid JSON'}, status=400)

    challenge_id = data.get('challenge_id')
    if not challenge_id:
        return JsonResponse({'error': 'challenge_id required'}, status=400)

    try:
        challenge = Challenge.objects.get(challenge_id=challenge_id)
    except Challenge.DoesNotExist:
        return JsonResponse({'error': 'Challenge not found'}, status=404)

    # Create session
    session = GameSession.objects.create(
        user=request.user,
        challenge=challenge,
        platform=data.get('platform', 'web'),
    )

    # Increment started count in daily stats
    daily_stats, _ = DailyStats.objects.get_or_create(
        user=request.user,
        game=challenge.game,
        date=timezone.now().date(),
    )
    daily_stats.sessions_started += 1
    daily_stats.save(update_fields=['sessions_started', 'updated_at'])

    return JsonResponse({
        'session_id': session.id,
        'started_at': session.started_at.isoformat(),
    })


@login_required
@require_POST
def api_session_complete(request):
    """
    Complete a game session.

    Body:
    - session_id: The session ID
    - solution: The user's solution (for verification)
    - time_spent: Time in seconds
    - mistakes: Number of mistakes (optional)
    - hints_used: Number of hints used (optional)
    """
    if not check_subscription(request.user):
        return JsonResponse({'error': 'Subscription required'}, status=403)

    try:
        data = json.loads(request.body)
    except json.JSONDecodeError:
        return JsonResponse({'error': 'Invalid JSON'}, status=400)

    session_id = data.get('session_id')
    if not session_id:
        return JsonResponse({'error': 'session_id required'}, status=400)

    try:
        session = GameSession.objects.get(
            id=session_id,
            user=request.user,
            status=GameSession.STATUS_IN_PROGRESS,
        )
    except GameSession.DoesNotExist:
        return JsonResponse({'error': 'Session not found or already completed'}, status=404)

    # Verify solution
    solution = data.get('solution')
    if solution:
        if not session.challenge.verify_solution(solution):
            return JsonResponse({'error': 'Incorrect solution', 'verified': False}, status=400)

    # Complete the session
    time_spent = data.get('time_spent', 0)
    mistakes = data.get('mistakes', 0)
    hints_used = data.get('hints_used', 0)

    session.complete(time_spent, mistakes, hints_used)

    # Update daily stats
    daily_stats = DailyStats.get_or_create_for_session(session)
    daily_stats.record_session(session)

    # Update user game stats
    user_game_stats, created = UserGameStats.objects.get_or_create(
        user=request.user,
        game=session.challenge.game,
    )
    user_game_stats.total_sessions += 1
    user_game_stats.total_completed += 1
    user_game_stats.total_time_seconds += time_spent
    user_game_stats.total_score += session.score
    if session.score > user_game_stats.best_score:
        user_game_stats.best_score = session.score
    if user_game_stats.best_time_seconds is None or time_spent < user_game_stats.best_time_seconds:
        user_game_stats.best_time_seconds = time_spent
    user_game_stats.save()
    user_game_stats.update_streak(session.started_at.date())

    # Update overall stats
    overall_stats, created = UserOverallStats.objects.get_or_create(user=request.user)
    overall_stats.total_sessions += 1
    overall_stats.total_completed += 1
    overall_stats.total_time_seconds += time_spent
    overall_stats.save()
    overall_stats.update_streak(session.started_at.date())

    return JsonResponse({
        'success': True,
        'verified': True,
        'score': session.score,
        'time_spent': session.time_spent_seconds,
        'session_id': session.id,
    })


@login_required
@require_POST
def api_session_update(request, session_id):
    """
    Update session state (for saving progress).

    Body:
    - current_state: Current puzzle state JSON
    - time_spent: Current time spent (optional)
    """
    if not check_subscription(request.user):
        return JsonResponse({'error': 'Subscription required'}, status=403)

    try:
        data = json.loads(request.body)
    except json.JSONDecodeError:
        return JsonResponse({'error': 'Invalid JSON'}, status=400)

    try:
        session = GameSession.objects.get(
            id=session_id,
            user=request.user,
            status=GameSession.STATUS_IN_PROGRESS,
        )
    except GameSession.DoesNotExist:
        return JsonResponse({'error': 'Session not found'}, status=404)

    if 'current_state' in data:
        session.current_state = data['current_state']
    if 'time_spent' in data:
        session.time_spent_seconds = data['time_spent']

    session.save(update_fields=['current_state', 'time_spent_seconds', 'updated_at'])

    return JsonResponse({'success': True})


@login_required
@require_GET
def api_stats_overview(request):
    """
    Get overall brain training statistics for the user.
    """
    if not check_subscription(request.user):
        return JsonResponse({'error': 'Subscription required'}, status=403)

    try:
        overall = UserOverallStats.objects.get(user=request.user)
        overall_data = {
            'total_sessions': overall.total_sessions,
            'total_completed': overall.total_completed,
            'total_minutes': overall.total_minutes_trained,
            'current_streak': overall.current_streak,
            'longest_streak': overall.longest_streak,
            'last_played': overall.last_played_date.isoformat() if overall.last_played_date else None,
            'favorite_game': overall.favorite_game.slug if overall.favorite_game else None,
        }
    except UserOverallStats.DoesNotExist:
        overall_data = {
            'total_sessions': 0,
            'total_completed': 0,
            'total_minutes': 0,
            'current_streak': 0,
            'longest_streak': 0,
            'last_played': None,
            'favorite_game': None,
        }

    # Get per-game stats
    game_stats = {}
    for stats in UserGameStats.objects.filter(user=request.user).select_related('game'):
        game_stats[stats.game.slug] = {
            'total_completed': stats.total_completed,
            'average_score': stats.average_score,
            'best_score': stats.best_score,
            'current_streak': stats.current_streak,
            'completion_rate': stats.completion_rate,
        }

    return JsonResponse({
        'overall': overall_data,
        'games': game_stats,
    })


@login_required
@require_GET
def api_stats_game(request, game_slug):
    """
    Get detailed statistics for a specific game.
    """
    if not check_subscription(request.user):
        return JsonResponse({'error': 'Subscription required'}, status=403)

    game = get_object_or_404(Game, slug=game_slug)

    try:
        stats = UserGameStats.objects.get(user=request.user, game=game)
        stats_data = {
            'total_sessions': stats.total_sessions,
            'total_completed': stats.total_completed,
            'total_time_minutes': stats.total_time_seconds // 60,
            'average_score': stats.average_score,
            'best_score': stats.best_score,
            'best_time_seconds': stats.best_time_seconds,
            'current_streak': stats.current_streak,
            'longest_streak': stats.longest_streak,
            'completion_rate': stats.completion_rate,
            'preferred_difficulty': stats.preferred_difficulty,
        }
    except UserGameStats.DoesNotExist:
        stats_data = None

    # Get recent daily stats (last 14 days)
    daily = list(DailyStats.objects.filter(
        user=request.user,
        game=game,
        date__gte=timezone.now().date() - timedelta(days=14),
    ).order_by('date').values(
        'date',
        'sessions_completed',
        'total_score',
        'total_time_seconds',
        'best_score',
    ))

    # Get improvement stats
    improvement = get_improvement_stats(request.user, game)

    return JsonResponse({
        'game': game.slug,
        'stats': stats_data,
        'daily': daily,
        'improvement': improvement,
    })


@login_required
@require_GET
def api_ai_summary(request):
    """
    Get compact AI-ready summary of brain training performance.

    Used by the AI coaching system to understand user's cognitive training progress.
    """
    if not check_subscription(request.user):
        return JsonResponse({'error': 'Subscription required'}, status=403)

    timeframe_days = int(request.GET.get('days', 30))
    start_date = timezone.now().date() - timedelta(days=timeframe_days)

    # Get sessions in timeframe
    sessions = GameSession.objects.filter(
        user=request.user,
        status=GameSession.STATUS_COMPLETED,
        completed_at__date__gte=start_date,
    ).select_related('challenge__game')

    total_sessions = sessions.count()
    games_data = {}

    for game in Game.objects.filter(is_active=True):
        game_sessions = sessions.filter(challenge__game=game)
        count = game_sessions.count()

        if count == 0:
            continue

        # Calculate improvement
        improvement = get_improvement_stats(request.user, game, timeframe_days)

        game_stats = game_sessions.aggregate(
            avg_time=Avg('time_spent_seconds'),
            avg_mistakes=Avg('mistakes'),
            avg_score=Avg('score'),
        )

        games_data[game.slug] = {
            'sessions': count,
            'improvement_pct': improvement.get('score_improvement_pct', 0),
            'avg_time_sec': int(game_stats['avg_time'] or 0),
            'avg_score': int(game_stats['avg_score'] or 0),
            'mistakes_avg': round(game_stats['avg_mistakes'] or 0, 1),
        }

    return JsonResponse({
        'ai_summary': {
            'timeframe_days': timeframe_days,
            'total_sessions': total_sessions,
            'games': games_data,
        }
    })


@login_required
def stats_dashboard(request):
    """
    Stats dashboard page showing detailed progress and improvement trends.
    """
    if not check_subscription(request.user):
        return redirect('billing:select_plan')

    games = Game.objects.filter(is_active=True)

    # Get overall stats
    try:
        overall = UserOverallStats.objects.get(user=request.user)
    except UserOverallStats.DoesNotExist:
        overall = None

    # Get per-game stats
    game_stats = []
    for game in games:
        try:
            stats = UserGameStats.objects.get(user=request.user, game=game)
            improvement = get_improvement_stats(request.user, game)
            game_stats.append({
                'game': game,
                'stats': stats,
                'improvement': improvement,
            })
        except UserGameStats.DoesNotExist:
            game_stats.append({
                'game': game,
                'stats': None,
                'improvement': None,
            })

    context = {
        'overall': overall,
        'game_stats': game_stats,
    }
    return render(request, 'brain_training/stats.html', context)
