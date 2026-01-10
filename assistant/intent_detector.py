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
        # Additional weight keywords
        'bmi', 'body mass', 'mass', 'heavy', 'lighter', 'heavier',
        'weight trend', 'weight history', 'weight progress', 'weight change',
    ],
    'journal': [
        'journal', 'journaled', 'journaling', 'entry', 'entries', 'wrote',
        'written', 'diary', 'note', 'notes', 'reflection', 'reflections',
        'thoughts', 'gratitude', 'grateful',
        # Additional journal keywords
        'log', 'logged', 'logging', 'record', 'recorded', 'recording',
        'morning pages', 'evening reflection', 'daily entry', 'journalling',
    ],
    'medication': [
        'medication', 'medications', 'medicine', 'medicines', 'pill', 'pills',
        'dose', 'doses', 'dosage', 'prescription', 'prescriptions', 'meds',
        'supplement', 'supplements', 'vitamin', 'vitamins', 'took', 'taking',
        'drug', 'drugs',
        # Additional medication keywords
        'rx', 'refill', 'pharmacy', 'tablet', 'tablets', 'capsule', 'capsules',
        'treatment', 'treatments', 'regimen', 'med schedule', 'med log',
    ],
    'food': [
        'food', 'foods', 'ate', 'eaten', 'eat', 'eating', 'meal', 'meals',
        'breakfast', 'lunch', 'dinner', 'snack', 'snacks', 'calories',
        'calorie', 'nutrition', 'diet', 'carbs', 'carbohydrates', 'protein',
        'fat', 'fats', 'fiber', 'sodium', 'cholesterol',
        # Note: 'sugar' is ambiguous - handled separately for clarification
        # Additional food keywords
        'macros', 'micronutrients', 'nutrients', 'kcal', 'brunch', 'supper',
        'food log', 'food diary', 'what i ate', 'food intake', 'consumption',
    ],
    'mood': [
        'mood', 'moods', 'feeling', 'feelings', 'felt', 'feel', 'emotion',
        'emotions', 'emotional', 'happy', 'sad', 'anxious', 'anxiety',
        'stressed', 'stress', 'depressed', 'depression', 'angry', 'anger',
        'calm', 'peaceful', 'worried', 'worry', 'hopeful', 'hope',
        'frustrated', 'frustration', 'excited', 'excitement', 'tired',
        'exhausted', 'energetic', 'energy',
        # Additional mood keywords
        'mental state', 'wellbeing', 'well-being', 'mental health', 'mindset',
        'overwhelmed', 'content', 'joyful', 'joy', 'low mood', 'mood swing',
        'irritable', 'irritated', 'nervous', 'relaxed', 'motivated',
    ],
    'sleep': [
        'sleep', 'slept', 'sleeping', 'asleep', 'awake', 'woke', 'wake',
        'rest', 'rested', 'resting', 'insomnia', 'nap', 'naps', 'napped',
        'bedtime', 'hours of sleep',
        # Additional sleep keywords
        'sleep quality', 'sleep schedule', 'sleep pattern', 'sleep log',
        'wake up', 'woke up', 'dream', 'dreams', 'nightmare', 'nightmares',
        'sleep duration', 'time in bed', 'sleep cycle',
    ],
    'exercise': [
        'exercise', 'exercised', 'exercising', 'workout', 'workouts',
        'worked out', 'gym', 'run', 'ran', 'running', 'walk', 'walked',
        'walking', 'steps', 'miles', 'cardio', 'strength', 'training',
        'physical activity', 'active', 'activity',
        # Additional exercise keywords
        'fitness', 'fit', 'swim', 'swimming', 'swam', 'bike', 'biking',
        'cycling', 'hike', 'hiking', 'hiked', 'yoga', 'stretching',
        'lifting', 'weights', 'reps', 'sets', 'distance', 'pace', 'marathon',
    ],
    'glucose': [
        'glucose', 'blood sugar', 'sugar level', 'sugar levels', 'a1c',
        'hba1c', 'diabetes', 'diabetic', 'cgm', 'blood glucose', 'bg',
        'fasting glucose', 'glucose reading', 'glucose readings',
        # Additional glucose keywords
        'insulin', 'hyperglycemia', 'hypoglycemia', 'blood sugar level',
        'glucose monitor', 'glucose log', 'sugar check', 'glucose check',
        # Note: standalone 'sugar' is ambiguous - handled separately for clarification
    ],
    'blood_pressure': [
        'blood pressure', 'bp', 'systolic', 'diastolic', 'hypertension',
        'pressure reading', 'pressure readings',
        # Additional blood pressure keywords
        'pulse', 'heart rate', 'bpm', 'resting heart rate', 'bp reading',
        'high blood pressure', 'low blood pressure', 'blood pressure log',
    ],
    'faith': [
        'faith', 'prayer', 'prayers', 'prayed', 'praying', 'devotional',
        'devotionals', 'scripture', 'scriptures', 'bible', 'meditation',
        'meditated', 'spiritual', 'spirituality', 'worship', 'worshipped',
        # Additional faith keywords
        'quiet time', 'devotion', 'verse', 'verses', 'reading plan',
        'church', 'sermon', 'sermons', 'praise', 'thankful', 'blessing',
        'blessings', 'faith journey', 'spiritual practice',
    ],
    'goals': [
        'goal', 'goals', 'habit', 'habits', 'target', 'targets', 'objective',
        'objectives', 'progress', 'streak', 'streaks', 'completed',
        'achievement', 'achievements',
        # Additional goals keywords
        'milestone', 'milestones', 'resolution', 'resolutions', 'challenge',
        'challenges', 'commitment', 'commitments', 'routine', 'routines',
        'daily goal', 'weekly goal', 'monthly goal', 'tracking',
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

# Keywords indicating meta-questions about data existence or logging status
META_QUESTION_KEYWORDS: List[str] = [
    'have i logged', 'did i log', 'did i record', 'have i recorded',
    'have i tracked', 'did i track', 'have i entered', 'did i enter',
    'did i write', 'have i written', 'is there any', 'are there any',
    'do i have any', 'any entries', 'any data', 'any records',
]

# Compound query connectors for detecting multi-data-type queries
COMPOUND_CONNECTORS: List[str] = [
    ' and ', ' or ', ' with ', ' plus ', ' along with ', ' as well as ',
    ', ', ' & ',
]

# Ambiguous keywords that could match multiple data types and need clarification
# Format: {keyword: {possible_types: [...], clarifying_question: "..."}}
AMBIGUOUS_KEYWORDS: Dict[str, Dict] = {
    'sugar': {
        'possible_types': ['glucose', 'food'],
        'clarifying_question': (
            "When you mention 'sugar', are you referring to:\n"
            "• Your **blood sugar** (glucose readings), or\n"
            "• The **sugar in your food** (dietary intake)?"
        ),
    },
    'sugars': {
        'possible_types': ['glucose', 'food'],
        'clarifying_question': (
            "When you mention 'sugars', are you referring to:\n"
            "• Your **blood sugar** readings, or\n"
            "• The **sugars in your food** (dietary intake)?"
        ),
    },
}


def detect_personal_data_intent(message: str) -> Dict:
    """
    Detect if a user's message relates to their personal WLJ data.

    This function analyzes the message text to determine:
    1. Whether it's a query about personal data
    2. What types of data are being referenced
    3. Whether there's a date/time context to the query
    4. Whether it's a meta-question (asking about data existence vs. data values)
    5. Whether it's a compound query (asking about multiple data types)

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
            - is_meta_question (bool): True if the message asks about data
              existence (e.g., 'have I logged') rather than data values.
            - is_compound_query (bool): True if the message asks about multiple
              data types together.

    Example:
        >>> detect_personal_data_intent("What was my average weight last week?")
        {
            'is_personal_query': True,
            'data_types': ['weight'],
            'has_date_context': True,
            'is_meta_question': False,
            'is_compound_query': False
        }

        >>> detect_personal_data_intent("Have I logged my weight today?")
        {
            'is_personal_query': True,
            'data_types': ['weight'],
            'has_date_context': True,
            'is_meta_question': True,
            'is_compound_query': False
        }

        >>> detect_personal_data_intent("How do I reset my password?")
        {
            'is_personal_query': False,
            'data_types': [],
            'has_date_context': False,
            'is_meta_question': False,
            'is_compound_query': False
        }
    """
    if not message or not isinstance(message, str):
        return {
            'is_personal_query': False,
            'data_types': [],
            'has_date_context': False,
            'is_meta_question': False,
            'is_compound_query': False,
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

    # Detect meta-questions (asking about data existence vs. values)
    is_meta_question = False
    for meta_keyword in META_QUESTION_KEYWORDS:
        if meta_keyword in message_lower:
            is_meta_question = True
            break

    # Detect compound queries (multiple data types with connectors)
    is_compound_query = len(detected_data_types) > 1
    if not is_compound_query and len(detected_data_types) == 1:
        # Check if there are connector keywords that might indicate a compound intent
        for connector in COMPOUND_CONNECTORS:
            if connector in message_lower:
                # Connector present, but only one data type detected
                # This is still valid but not a compound query
                break

    # Detect ambiguous keywords that need clarification
    ambiguous_keyword_found = None
    ambiguous_info = None
    for keyword, info in AMBIGUOUS_KEYWORDS.items():
        pattern = r'\b' + re.escape(keyword) + r'\b'
        if re.search(pattern, message_lower):
            # Check if the query already has context that resolves ambiguity
            # Blood sugar context - unambiguous glucose
            glucose_context = ['blood sugar', 'sugar level', 'glucose', 'reading', 'a1c', 'diabetes']
            # Food context - unambiguous dietary sugar
            food_context = ['ate', 'eat', 'eaten', 'food', 'meal', 'diet', 'calories', 'carbs']

            has_glucose_context = any(term in message_lower for term in glucose_context)
            has_food_context = any(term in message_lower for term in food_context)

            # Only ambiguous if neither context is clear, or both are present
            if has_glucose_context and not has_food_context:
                # Clear glucose context - not ambiguous
                pass
            elif has_food_context and not has_glucose_context:
                # Clear food context - not ambiguous
                pass
            else:
                # Truly ambiguous - no clear context
                ambiguous_keyword_found = keyword
                ambiguous_info = info
                break

    # Determine if it's a personal query:
    # - Must have detected at least one data type OR have an ambiguous keyword
    # - Must have either a personal pronoun OR a query pattern with data types
    # - Meta-questions about personal data are also personal queries
    has_data_indicator = bool(detected_data_types) or ambiguous_keyword_found
    is_personal_query = has_data_indicator and (
        has_personal_pronoun or (has_query_pattern and has_data_indicator)
        or is_meta_question
    )

    return {
        'is_personal_query': is_personal_query,
        'data_types': detected_data_types,
        'has_date_context': has_date_context,
        'is_meta_question': is_meta_question,
        'is_compound_query': is_compound_query,
        'has_ambiguous_keyword': ambiguous_keyword_found is not None,
        'ambiguous_keyword': ambiguous_keyword_found,
        'ambiguous_info': ambiguous_info,
    }
