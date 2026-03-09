# ==============================================================================
# File: apps/journal/services/content_intelligence.py
# Project: Whole Life Journey - Django 5.x Personal Wellness/Journaling App
# Description: Journal content analysis — theme extraction, concern tracking,
#              and sentiment trajectory for CoS context integration.
# Owner: Danny Jenkins (admin@wholelifejourney.com)
# Created: 2026-03-09
# ==============================================================================
"""
Journal Content Intelligence

Analyzes journal entry text to extract life themes, track recurring concerns,
and compute sentiment trajectory. Results are stored in JournalTheme model
and surfaced in CoS context.

Uses keyword-based theme classification (no LLM cost for scheduled runs).
"""

import logging
import re
from collections import Counter
from datetime import timedelta

from django.db import models
from django.utils import timezone

logger = logging.getLogger(__name__)

# ──────────────────────────────────────────────────────────────────────
# Theme Classification — keyword-based (zero API cost)
# ──────────────────────────────────────────────────────────────────────

THEME_KEYWORDS = {
    'work': {
        'work', 'job', 'career', 'office', 'meeting', 'deadline', 'boss',
        'coworker', 'project', 'promotion', 'salary', 'client', 'presentation',
        'interview', 'resign', 'hire', 'fired', 'burnout', 'commute',
        'professional', 'business', 'corporate', 'colleague',
    },
    'family': {
        'family', 'mom', 'dad', 'mother', 'father', 'brother', 'sister',
        'son', 'daughter', 'wife', 'husband', 'spouse', 'kids', 'children',
        'grandma', 'grandpa', 'nana', 'papa', 'uncle', 'aunt', 'cousin',
        'parent', 'sibling', 'baby', 'toddler', 'teen',
    },
    'health': {
        'health', 'doctor', 'medicine', 'medication', 'sick', 'pain',
        'exercise', 'workout', 'gym', 'weight', 'diet', 'sleep', 'tired',
        'energy', 'fatigue', 'anxiety', 'stress', 'therapy', 'hospital',
        'diagnosis', 'symptom', 'recovery', 'healing', 'chronic',
    },
    'faith': {
        'god', 'pray', 'prayer', 'church', 'bible', 'scripture', 'faith',
        'worship', 'jesus', 'christ', 'spirit', 'soul', 'sermon', 'pastor',
        'grateful', 'blessing', 'blessed', 'devotion', 'spiritual',
        'meditation', 'forgive', 'forgiveness', 'grace', 'hope',
    },
    'finances': {
        'money', 'budget', 'savings', 'debt', 'bills', 'rent', 'mortgage',
        'invest', 'investment', 'expense', 'income', 'spending', 'financial',
        'loan', 'credit', 'bank', 'retirement', 'tax', 'insurance',
    },
    'relationships': {
        'friend', 'friendship', 'relationship', 'dating', 'love', 'partner',
        'breakup', 'divorce', 'lonely', 'loneliness', 'social', 'trust',
        'conflict', 'argument', 'forgive', 'apologize', 'boundaries',
        'connection', 'support', 'community', 'neighbor',
    },
    'goals': {
        'goal', 'dream', 'ambition', 'plan', 'future', 'purpose', 'mission',
        'accomplish', 'achieve', 'milestone', 'progress', 'growth', 'improve',
        'habit', 'discipline', 'routine', 'intention', 'resolution',
    },
    'grief': {
        'grief', 'loss', 'death', 'died', 'passed', 'funeral', 'mourning',
        'miss', 'missing', 'gone', 'memorial', 'heaven', 'afterlife',
        'widow', 'bereave',
    },
}

# Stopwords to exclude from concern detection
STOPWORDS = frozenset({
    'the', 'a', 'an', 'is', 'are', 'was', 'were', 'be', 'been', 'being',
    'have', 'has', 'had', 'do', 'does', 'did', 'will', 'would', 'could',
    'should', 'may', 'might', 'can', 'shall', 'to', 'of', 'in', 'for',
    'on', 'with', 'at', 'by', 'from', 'as', 'into', 'through', 'during',
    'before', 'after', 'above', 'below', 'between', 'out', 'off', 'over',
    'under', 'again', 'further', 'then', 'once', 'here', 'there', 'when',
    'where', 'why', 'how', 'all', 'each', 'every', 'both', 'few', 'more',
    'most', 'other', 'some', 'such', 'no', 'nor', 'not', 'only', 'own',
    'same', 'so', 'than', 'too', 'very', 'just', 'about', 'up', 'down',
    'and', 'but', 'or', 'if', 'while', 'because', 'until', 'that', 'this',
    'these', 'those', 'it', 'its', 'my', 'me', 'i', 'we', 'you', 'your',
    'he', 'she', 'they', 'them', 'his', 'her', 'our', 'their', 'what',
    'which', 'who', 'whom', 'also', 'really', 'much', 'many', 'like',
    'got', 'get', 'went', 'going', 'go', 'come', 'came', 'make', 'made',
    'know', 'knew', 'think', 'thought', 'feel', 'felt', 'want', 'need',
    'say', 'said', 'tell', 'told', 'see', 'saw', 'day', 'today', 'time',
    'thing', 'things', 'lot', 'way', 'even', 'still', 'back', 'well',
    'one', 'two', 'first', 'last', 'new', 'good', 'bad', 'right', 'now',
    'been', 'being', 'bit', 'something', 'anything', 'nothing', 'everything',
})

# Sentiment word lists for trajectory
POSITIVE_WORDS = frozenset({
    'happy', 'grateful', 'blessed', 'joy', 'peaceful', 'excited', 'proud',
    'hopeful', 'content', 'amazing', 'wonderful', 'great', 'love', 'loved',
    'strong', 'confident', 'accomplished', 'thriving', 'inspired', 'calm',
    'relieved', 'energized', 'motivated', 'thankful', 'optimistic',
})

NEGATIVE_WORDS = frozenset({
    'sad', 'angry', 'frustrated', 'anxious', 'worried', 'stressed', 'tired',
    'overwhelmed', 'lonely', 'afraid', 'scared', 'disappointed', 'hurt',
    'exhausted', 'depressed', 'hopeless', 'lost', 'confused', 'stuck',
    'defeated', 'drained', 'bitter', 'guilty', 'ashamed', 'numb',
})


def extract_themes(entry_body: str) -> list[dict]:
    """
    Extract life themes from journal entry text using keyword matching.

    Returns list of {'theme': str, 'confidence': float} sorted by confidence.
    """
    if not entry_body or len(entry_body.strip()) < 20:
        return []

    words = set(re.findall(r'\b[a-z]+\b', entry_body.lower()))
    results = []

    for theme, keywords in THEME_KEYWORDS.items():
        matches = words & keywords
        if matches:
            # Confidence = matched keywords / total theme keywords, capped at 1.0
            confidence = min(len(matches) / 3.0, 1.0)
            results.append({
                'theme': theme,
                'confidence': round(confidence, 2),
                'matched_keywords': sorted(matches)[:5],
            })

    return sorted(results, key=lambda x: x['confidence'], reverse=True)


def compute_sentiment_score(entry_body: str) -> float:
    """
    Compute a simple sentiment score for an entry.

    Returns float from -1.0 (very negative) to 1.0 (very positive).
    0.0 means neutral or balanced.
    """
    if not entry_body:
        return 0.0

    words = set(re.findall(r'\b[a-z]+\b', entry_body.lower()))
    pos = len(words & POSITIVE_WORDS)
    neg = len(words & NEGATIVE_WORDS)
    total = pos + neg

    if total == 0:
        return 0.0

    return round((pos - neg) / total, 2)


def detect_recurring_concerns(user, days: int = 14, min_occurrences: int = 3) -> list[dict]:
    """
    Detect recurring themes/concerns across recent journal entries.

    Scans entries from the last `days` days and finds content words
    that appear across multiple entries (not just within one).

    Returns list of {'term': str, 'count': int, 'entries': int}
    sorted by frequency.
    """
    from apps.journal.models import JournalEntry

    cutoff = timezone.now().date() - timedelta(days=days)
    entries = JournalEntry.objects.filter(
        user=user,
        entry_date__gte=cutoff,
        deleted_at__isnull=True,
    ).values_list('body', flat=True)

    # Count terms across entries (not total occurrences, but entry count)
    term_entries = Counter()
    for body in entries:
        if not body:
            continue
        words = set(re.findall(r'\b[a-z]{4,}\b', body.lower()))
        content_words = words - STOPWORDS
        for word in content_words:
            term_entries[word] += 1

    # Filter to terms appearing in min_occurrences+ entries
    concerns = [
        {'term': term, 'entries': count}
        for term, count in term_entries.most_common(20)
        if count >= min_occurrences
    ]

    return concerns


def get_sentiment_trajectory(user, days: int = 14) -> dict:
    """
    Compute sentiment trajectory over recent journal entries.

    Returns dict with:
    - direction: 'improving', 'declining', 'stable', 'insufficient_data'
    - recent_avg: float (-1.0 to 1.0)
    - prior_avg: float (-1.0 to 1.0)
    - mood_distribution: dict of mood -> count
    """
    from apps.journal.models import JournalEntry

    cutoff = timezone.now().date() - timedelta(days=days)
    midpoint = timezone.now().date() - timedelta(days=days // 2)

    entries = JournalEntry.objects.filter(
        user=user,
        entry_date__gte=cutoff,
        deleted_at__isnull=True,
    ).values('body', 'mood', 'entry_date')

    if not entries:
        return {'direction': 'insufficient_data'}

    prior_scores = []
    recent_scores = []
    mood_dist = Counter()

    for entry in entries:
        score = compute_sentiment_score(entry['body'] or '')
        if entry['entry_date'] < midpoint:
            prior_scores.append(score)
        else:
            recent_scores.append(score)

        if entry['mood']:
            mood_dist[entry['mood']] += 1

    if len(prior_scores) < 2 or len(recent_scores) < 2:
        return {
            'direction': 'insufficient_data',
            'mood_distribution': dict(mood_dist),
        }

    prior_avg = sum(prior_scores) / len(prior_scores)
    recent_avg = sum(recent_scores) / len(recent_scores)
    delta = recent_avg - prior_avg

    if delta > 0.15:
        direction = 'improving'
    elif delta < -0.15:
        direction = 'declining'
    else:
        direction = 'stable'

    return {
        'direction': direction,
        'recent_avg': round(recent_avg, 2),
        'prior_avg': round(prior_avg, 2),
        'delta': round(delta, 2),
        'mood_distribution': dict(mood_dist),
    }


def analyze_journal_for_cos(user) -> dict:
    """
    Main entry point: analyze journal content for CoS context injection.

    Returns dict ready for cos_context integration:
    {
        'themes_14d': [{'theme': 'work', 'confidence': 0.8}, ...],
        'concerns_14d': [{'term': 'stress', 'entries': 5}, ...],
        'sentiment_trajectory': {'direction': 'improving', ...},
        'entry_count_14d': int,
    }
    """
    from apps.journal.models import JournalEntry

    cutoff = timezone.now().date() - timedelta(days=14)
    recent_entries = JournalEntry.objects.filter(
        user=user,
        entry_date__gte=cutoff,
        deleted_at__isnull=True,
    )

    entry_count = recent_entries.count()
    if entry_count == 0:
        return {
            'themes_14d': [],
            'concerns_14d': [],
            'sentiment_trajectory': {'direction': 'insufficient_data'},
            'entry_count_14d': 0,
        }

    # Aggregate themes across all recent entries
    theme_scores = Counter()
    for entry in recent_entries.values_list('body', flat=True):
        themes = extract_themes(entry or '')
        for t in themes:
            theme_scores[t['theme']] += t['confidence']

    # Normalize by entry count
    top_themes = [
        {'theme': theme, 'strength': round(score / entry_count, 2)}
        for theme, score in theme_scores.most_common(5)
        if score / entry_count >= 0.2  # Threshold: at least 20% average confidence
    ]

    concerns = detect_recurring_concerns(user, days=14, min_occurrences=2)
    trajectory = get_sentiment_trajectory(user, days=14)

    return {
        'themes_14d': top_themes,
        'concerns_14d': concerns[:5],  # Top 5 concerns
        'sentiment_trajectory': trajectory,
        'entry_count_14d': entry_count,
    }
