"""
Intent Detector Module for WLJ Personal Data Query System.

This module provides rule-based detection of user queries that relate
to their personal WLJ data (weight, journal entries, medications, food, mood, etc.).
"""

import re
from typing import Dict, List


# Dictionary mapping data types to keyword lists for personal data detection
PERSONAL_DATA_KEYWORDS: Dict[str, List[str]] = {
    'weight': [
        'weight', 'weigh', 'weighed', 'weighing', 'pounds', 'lbs', 'kg',
        'kilograms', 'scale', 'body weight', 'lost weight', 'gained weight',
        'weight loss', 'weight gain', 'heaviest', 'lightest',
    ],
    'journal': [
        'journal', 'journaled', 'journaling', 'entry', 'entries', 'wrote',
        'written', 'diary', 'note', 'notes', 'reflection', 'reflections',
        'thoughts', 'gratitude', 'grateful',
    ],
    'medication': [
        'medication', 'medications', 'medicine', 'medicines', 'pill', 'pills',
        'dose', 'doses', 'dosage', 'prescription', 'prescriptions', 'meds',
        'supplement', 'supplements', 'vitamin', 'vitamins', 'took', 'taking',
        'drug', 'drugs',
    ],
    'food': [
        'food', 'foods', 'ate', 'eaten', 'eat', 'eating', 'meal', 'meals',
        'breakfast', 'lunch', 'dinner', 'snack', 'snacks', 'calories',
        'calorie', 'nutrition', 'diet', 'carbs', 'carbohydrates', 'protein',
        'fat', 'fats', 'sugar', 'sugars', 'fiber', 'sodium', 'cholesterol',
    ],
    'mood': [
        'mood', 'moods', 'feeling', 'feelings', 'felt', 'feel', 'emotion',
        'emotions', 'emotional', 'happy', 'sad', 'anxious', 'anxiety',
        'stressed', 'stress', 'depressed', 'depression', 'angry', 'anger',
        'calm', 'peaceful', 'worried', 'worry', 'hopeful', 'hope',
        'frustrated', 'frustration', 'excited', 'excitement', 'tired',
        'exhausted', 'energetic', 'energy',
    ],
    'sleep': [
        'sleep', 'slept', 'sleeping', 'asleep', 'awake', 'woke', 'wake',
        'rest', 'rested', 'resting', 'insomnia', 'nap', 'naps', 'napped',
        'bedtime', 'hours of sleep',
    ],
    'exercise': [
        'exercise', 'exercised', 'exercising', 'workout', 'workouts',
        'worked out', 'gym', 'run', 'ran', 'running', 'walk', 'walked',
        'walking', 'steps', 'miles', 'cardio', 'strength', 'training',
        'physical activity', 'active', 'activity',
    ],
    'glucose': [
        'glucose', 'blood sugar', 'sugar level', 'sugar levels', 'a1c',
        'hba1c', 'diabetes', 'diabetic', 'cgm', 'blood glucose', 'bg',
        'fasting glucose', 'glucose reading', 'glucose readings',
    ],
    'blood_pressure': [
        'blood pressure', 'bp', 'systolic', 'diastolic', 'hypertension',
        'pressure reading', 'pressure readings',
    ],
    'faith': [
        'faith', 'prayer', 'prayers', 'prayed', 'praying', 'devotional',
        'devotionals', 'scripture', 'scriptures', 'bible', 'meditation',
        'meditated', 'spiritual', 'spirituality', 'worship', 'worshipped',
    ],
    'goals': [
        'goal', 'goals', 'habit', 'habits', 'target', 'targets', 'objective',
        'objectives', 'progress', 'streak', 'streaks', 'completed',
        'achievement', 'achievements',
    ],
}

# List of time-related keywords that indicate date context in queries
DATE_KEYWORDS: List[str] = [
    # Relative time references
    'since', 'from', 'after', 'before', 'until', 'between',
    # Aggregation keywords
    'last', 'past', 'previous', 'recent', 'recently',
    'average', 'avg', 'mean', 'total', 'sum', 'count',
    'how many', 'how much', 'how often',
    # Specific time periods
    'today', 'yesterday', 'tomorrow',
    'this week', 'last week', 'next week',
    'this month', 'last month', 'next month',
    'this year', 'last year', 'next year',
    # Days of week
    'monday', 'tuesday', 'wednesday', 'thursday', 'friday', 'saturday', 'sunday',
    # Months
    'january', 'february', 'march', 'april', 'may', 'june',
    'july', 'august', 'september', 'october', 'november', 'december',
    # Time ranges
    'week', 'weeks', 'month', 'months', 'year', 'years', 'day', 'days',
    # Ordinals and dates
    '1st', '2nd', '3rd', '4th', '5th', '6th', '7th', '8th', '9th', '10th',
    '11th', '12th', '13th', '14th', '15th', '16th', '17th', '18th', '19th', '20th',
    '21st', '22nd', '23rd', '24th', '25th', '26th', '27th', '28th', '29th', '30th', '31st',
    # Trend indicators
    'trend', 'trends', 'trending', 'over time', 'history', 'historical',
]

# Personal pronouns indicating the query is about the user's own data
PERSONAL_PRONOUNS: List[str] = [
    'my', 'i', 'me', 'mine', "i've", "i'm", "i'd", 'myself',
]


def detect_personal_data_intent(message: str) -> Dict:
    """
    Detect if a user's message relates to their personal WLJ data.

    This function analyzes the message text to determine:
    1. Whether it's a query about personal data
    2. What types of data are being referenced
    3. Whether there's a date/time context to the query

    Args:
        message: The user's message string to analyze.

    Returns:
        A dictionary containing:
            - is_personal_query (bool): True if the message appears to be
              asking about the user's personal data.
            - data_types (list): List of data type strings that were detected
              (e.g., ['weight', 'mood']).
            - has_date_context (bool): True if the message contains
              time-related keywords suggesting a date range or period.

    Example:
        >>> detect_personal_data_intent("What was my average weight last week?")
        {
            'is_personal_query': True,
            'data_types': ['weight'],
            'has_date_context': True
        }

        >>> detect_personal_data_intent("How do I reset my password?")
        {
            'is_personal_query': False,
            'data_types': [],
            'has_date_context': False
        }
    """
    if not message or not isinstance(message, str):
        return {
            'is_personal_query': False,
            'data_types': [],
            'has_date_context': False,
        }

    # Normalize message for matching
    message_lower = message.lower()

    # Detect data types mentioned in the message
    detected_data_types = []
    for data_type, keywords in PERSONAL_DATA_KEYWORDS.items():
        for keyword in keywords:
            # Use word boundary matching to avoid partial matches
            pattern = r'\b' + re.escape(keyword) + r'\b'
            if re.search(pattern, message_lower):
                if data_type not in detected_data_types:
                    detected_data_types.append(data_type)
                break  # Found a match for this data type, move to next

    # Detect date context
    has_date_context = False
    for keyword in DATE_KEYWORDS:
        pattern = r'\b' + re.escape(keyword) + r'\b'
        if re.search(pattern, message_lower):
            has_date_context = True
            break

    # Check for numeric date patterns (e.g., "12/25", "2024-01-15", "January 15")
    date_patterns = [
        r'\d{1,2}/\d{1,2}(?:/\d{2,4})?',  # MM/DD or MM/DD/YYYY
        r'\d{4}-\d{2}-\d{2}',              # YYYY-MM-DD
        r'\d{1,2}-\d{1,2}(?:-\d{2,4})?',   # MM-DD or MM-DD-YYYY
    ]
    if not has_date_context:
        for pattern in date_patterns:
            if re.search(pattern, message_lower):
                has_date_context = True
                break

    # Determine if this is a personal query
    # A query is personal if it mentions personal data types AND
    # uses personal pronouns or asks about data in a personal context
    has_personal_pronoun = False
    for pronoun in PERSONAL_PRONOUNS:
        pattern = r'\b' + re.escape(pronoun) + r'\b'
        if re.search(pattern, message_lower):
            has_personal_pronoun = True
            break

    # Question patterns that suggest querying data
    query_patterns = [
        r'\bwhat\b', r'\bhow\b', r'\bwhen\b', r'\bwhere\b',
        r'\bshow\b', r'\btell\b', r'\blist\b', r'\bget\b',
        r'\bfind\b', r'\bsearch\b', r'\blook\b', r'\bcheck\b',
        r'\bdid\b', r'\bhave\b', r'\bhas\b', r'\bwas\b', r'\bwere\b',
        r'\?',  # Question mark
    ]

    has_query_pattern = False
    for pattern in query_patterns:
        if re.search(pattern, message_lower):
            has_query_pattern = True
            break

    # Determine if it's a personal query:
    # - Must have detected at least one data type
    # - Must have either a personal pronoun OR a query pattern with data types
    is_personal_query = bool(detected_data_types) and (
        has_personal_pronoun or (has_query_pattern and len(detected_data_types) > 0)
    )

    return {
        'is_personal_query': is_personal_query,
        'data_types': detected_data_types,
        'has_date_context': has_date_context,
    }
