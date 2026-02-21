"""
Intent Detector Module for WLJ Personal Data Query System.

This module provides rule-based detection of user queries that relate
to their personal WLJ data across all WLJ modules:
- Health (weight, glucose, blood pressure, medications, food, workouts, heart rate, etc.)
- Journal (entries, reflections, prompts)
- Faith (scripture, prayers, reading plans, milestones)
- Life (tasks, events, projects, pets, recipes, maintenance, inventory)
- Purpose (goals, habits, reflections, annual direction)
- Finance (accounts, transactions, budgets, financial goals)
"""

import re
from typing import Dict, List


# =============================================================================
# PERSONAL DATA KEYWORDS - Comprehensive mapping for all WLJ data types
# =============================================================================

PERSONAL_DATA_KEYWORDS: Dict[str, List[str]] = {
    # =========================================================================
    # HEALTH MODULE
    # =========================================================================
    'weight': [
        'weight', 'weigh', 'weighed', 'weighing', 'pounds', 'lbs', 'kg',
        'kilograms', 'scale', 'body weight', 'lost weight', 'gained weight',
        'weight loss', 'weight gain', 'heaviest', 'lightest',
        'bmi', 'body mass', 'mass', 'heavy', 'lighter', 'heavier',
        'weight trend', 'weight history', 'weight progress', 'weight change',
    ],

    'glucose': [
        'glucose', 'blood sugar', 'sugar level', 'sugar levels', 'a1c',
        'hba1c', 'diabetes', 'diabetic', 'cgm', 'blood glucose', 'bg',
        'fasting glucose', 'glucose reading', 'glucose readings',
        'insulin', 'hyperglycemia', 'hypoglycemia', 'blood sugar level',
        'glucose monitor', 'glucose log', 'sugar check', 'glucose check',
        'dexcom', 'continuous glucose', 'glucose trend', 'in range',
        'time in range', 'high glucose', 'low glucose', 'glucose spike',
        # Note: standalone 'sugar' is ambiguous - handled separately
    ],

    'blood_pressure': [
        'blood pressure', 'bp', 'systolic', 'diastolic', 'hypertension',
        'pressure reading', 'pressure readings', 'bp reading',
        'high blood pressure', 'low blood pressure', 'blood pressure log',
        'pulse pressure', 'bp trend', 'bp history',
    ],

    'heart_rate': [
        'heart rate', 'pulse', 'bpm', 'beats per minute', 'resting heart rate',
        'resting pulse', 'heart rate variability', 'hrv', 'pulse rate',
        'heart beat', 'heartbeat', 'cardio heart rate', 'active heart rate',
    ],

    'blood_oxygen': [
        'blood oxygen', 'oxygen level', 'oxygen levels', 'spo2', 'o2 sat',
        'oxygen saturation', 'pulse ox', 'pulse oximeter', 'oximetry',
    ],

    'medication': [
        'medication', 'medications', 'medicine', 'medicines', 'pill', 'pills',
        'dose', 'doses', 'dosage', 'prescription', 'prescriptions', 'meds',
        'supplement', 'supplements', 'vitamin', 'vitamins', 'took', 'taking',
        'drug', 'drugs', 'rx', 'refill', 'pharmacy', 'tablet', 'tablets',
        'capsule', 'capsules', 'treatment', 'treatments', 'regimen',
        'med schedule', 'med log', 'missed dose', 'took my', 'take my',
        'prn', 'as needed', 'medication schedule', 'medicine schedule',
        'medication reminder', 'medicine reminder', 'drug interaction',
    ],

    'food': [
        'food', 'foods', 'ate', 'eaten', 'eat', 'eating', 'meal', 'meals',
        'breakfast', 'lunch', 'dinner', 'snack', 'snacks', 'calories',
        'calorie', 'nutrition', 'diet', 'carbs', 'carbohydrates', 'protein',
        'fat', 'fats', 'fiber', 'sodium', 'cholesterol',
        'macros', 'micronutrients', 'nutrients', 'kcal', 'brunch', 'supper',
        'food log', 'food diary', 'what i ate', 'food intake', 'consumption',
        'net carbs', 'saturated fat', 'trans fat', 'potassium', 'calcium',
        'iron', 'vitamin', 'food entry', 'logged food', 'daily calories',
        'calorie intake', 'calorie count', 'macro breakdown', 'macro split',
        'hunger', 'fullness', 'eating pace', 'meal type',
        # Note: 'sugar' is ambiguous - handled separately for clarification
    ],

    'nutrition_goals': [
        'calorie target', 'calorie goal', 'macro target', 'macro goal',
        'protein target', 'protein goal', 'carb target', 'carb goal',
        'fat target', 'fat goal', 'nutrition goal', 'nutrition target',
        'dietary goal', 'diet goal', 'calorie limit', 'sugar limit',
        'sodium limit', 'daily allowance', 'nutritional needs',
    ],

    'workout': [
        'workout', 'workouts', 'exercise', 'exercises', 'exercised',
        'exercising', 'worked out', 'gym', 'strength training', 'lifting',
        'weights', 'weight training', 'resistance training', 'reps', 'sets',
        'volume', 'personal record', 'pr', 'one rep max', '1rm',
        'workout session', 'training session', 'gym session', 'routine',
        'workout routine', 'exercise routine', 'lift', 'lifted', 'bench',
        'squat', 'deadlift', 'curl', 'press', 'row', 'pullup', 'pushup',
        'dumbbell', 'barbell', 'kettlebell', 'machine', 'free weights',
    ],

    'cardio': [
        'cardio', 'run', 'ran', 'running', 'walk', 'walked', 'walking',
        'steps', 'miles', 'kilometers', 'distance', 'pace', 'swim', 'swam',
        'swimming', 'bike', 'biked', 'biking', 'cycling', 'cycle', 'hike',
        'hiked', 'hiking', 'jog', 'jogged', 'jogging', 'treadmill',
        'elliptical', 'stair', 'stairs', 'rowing', 'rower', 'marathon',
        'half marathon', '5k', '10k', 'sprint', 'interval', 'hiit',
    ],

    'fitness': [
        'fitness', 'fit', 'physical activity', 'active', 'activity',
        'yoga', 'stretching', 'flexibility', 'mobility', 'warm up',
        'cool down', 'recovery', 'rest day', 'active recovery',
        'workout template', 'workout plan', 'training plan', 'exercise plan',
    ],

    'medical_provider': [
        'doctor', 'doctors', 'physician', 'physicians', 'provider', 'providers',
        'healthcare provider', 'medical provider', 'specialist', 'specialists',
        'cardiologist', 'endocrinologist', 'primary care', 'pcp',
        'nurse practitioner', 'np', 'physician assistant', 'pa',
        'dentist', 'optometrist', 'dermatologist', 'psychiatrist',
        'therapist', 'counselor', 'vet', 'veterinarian',
        'doctor appointment', 'doctor visit', 'medical appointment',
        'patient portal', 'office hours', 'doctor phone', 'doctor address',
    ],

    # =========================================================================
    # JOURNAL MODULE
    # =========================================================================
    'journal': [
        'journal', 'journaled', 'journaling', 'entry', 'entries', 'wrote',
        'written', 'diary', 'note', 'notes', 'reflection', 'reflections',
        'thoughts', 'gratitude', 'grateful', 'log', 'logged', 'logging',
        'record', 'recorded', 'recording', 'morning pages', 'evening reflection',
        'daily entry', 'journalling', 'write', 'writing', 'journaled about',
        'wrote about', 'reflected on', 'journal prompt', 'writing prompt',
    ],

    # =========================================================================
    # FAITH MODULE
    # =========================================================================
    'faith': [
        'faith', 'spiritual', 'spirituality', 'devotional', 'devotionals',
        'quiet time', 'devotion', 'faith journey', 'spiritual practice',
        'worship', 'worshipped', 'church', 'sermon', 'sermons',
    ],

    'prayer': [
        'prayer', 'prayers', 'prayed', 'praying', 'prayer request',
        'prayer requests', 'answered prayer', 'answered prayers',
        'prayer list', 'pray for', 'praying for', 'intercession',
        'petition', 'supplication', 'prayer journal',
    ],

    'scripture': [
        'scripture', 'scriptures', 'bible', 'verse', 'verses', 'passage',
        'passages', 'chapter', 'book of', 'biblical', 'bible verse',
        'memory verse', 'memory verses', 'daily verse', 'verse of the day',
        'bible reading', 'scripture reading', 'bible study', 'study notes',
        'highlighted', 'highlight', 'bookmarked', 'bookmark', 'saved verse',
    ],

    'reading_plan': [
        'reading plan', 'reading plans', 'bible plan', 'devotional plan',
        'reading progress', 'plan progress', 'day of plan', 'reading streak',
        'bible in a year', 'chronological', 'topical study',
    ],

    'faith_milestone': [
        'salvation', 'baptism', 'baptized', 'rededication', 'spiritual milestone',
        'faith milestone', 'accepted christ', 'born again', 'confirmation',
    ],

    # =========================================================================
    # LIFE MODULE
    # =========================================================================
    'task': [
        'task', 'tasks', 'to do', 'todo', 'to-do', 'to dos', 'todos',
        'to-dos', 'due', 'overdue', 'deadline', 'deadlines', 'complete',
        'completed', 'incomplete', 'pending', 'priority', 'priorities',
        'urgent', 'important', 'quick task', 'small task', 'big task',
        'recurring task', 'daily task', 'weekly task', 'task list',
    ],

    'project': [
        'project', 'projects', 'project status', 'project progress',
        'active project', 'completed project', 'paused project',
        'project task', 'project tasks', 'milestone', 'milestones',
    ],

    'event': [
        'event', 'events', 'appointment', 'appointments', 'meeting', 'meetings',
        'calendar', 'schedule', 'scheduled', 'upcoming', 'coming up',
        'happening', 'planned', 'plans', 'reminder', 'reminders',
    ],

    'significant_event': [
        'birthday', 'birthdays', 'anniversary', 'anniversaries', 'memorial',
        'holiday', 'holidays', 'special day', 'special days', 'celebration',
        'turning', 'years old', 'years together', 'years married',
    ],

    'pet': [
        'pet', 'pets', 'dog', 'dogs', 'cat', 'cats', 'puppy', 'kitten',
        'bird', 'fish', 'rabbit', 'hamster', 'pet vet', 'pet appointment',
        'pet vaccination', 'pet medication', 'pet weight', 'microchip',
        'pet grooming', 'pet food', 'pet record', 'vet visit',
    ],

    'recipe': [
        'recipe', 'recipes', 'cook', 'cooking', 'bake', 'baking',
        'ingredient', 'ingredients', 'prep time', 'cook time', 'servings',
        'favorite recipe', 'family recipe', 'how to make', 'how to cook',
    ],

    'inventory': [
        'inventory', 'item', 'items', 'appliance', 'appliances', 'furniture',
        'electronics', 'warranty', 'warranties', 'serial number', 'model number',
        'purchase date', 'purchase price', 'home inventory', 'asset', 'assets',
        'household item', 'household items', 'insurance inventory',
    ],

    'maintenance': [
        'maintenance', 'repair', 'repairs', 'service', 'serviced', 'hvac',
        'plumbing', 'electrical', 'roof', 'appliance repair', 'home repair',
        'contractor', 'handyman', 'service provider', 'maintenance log',
        'when was', 'last serviced', 'next service', 'follow up',
    ],

    'document': [
        'document', 'documents', 'file', 'files', 'paperwork', 'record',
        'records', 'insurance policy', 'legal document', 'tax document',
        'warranty document', 'expiring', 'expires', 'expiration',
        'medical record', 'financial document', 'important document',
    ],

    # =========================================================================
    # PURPOSE MODULE
    # =========================================================================
    'goals': [
        'goal', 'goals', 'objective', 'objectives', 'target', 'targets',
        'life goal', 'life goals', 'long term goal', 'short term goal',
        'annual goal', 'yearly goal', 'goal progress', 'goal status',
        'achieved', 'achievement', 'achievements', 'accomplish', 'accomplished',
    ],

    'habit': [
        'habit', 'habits', 'habit goal', 'habit goals', 'streak', 'streaks',
        'habit streak', 'daily habit', 'habit tracker', 'habit tracking',
        'habit matrix', 'completion rate', 'habit progress', 'habit history',
        'did i', 'have i', 'days in a row', 'consecutive days',
    ],

    'intention': [
        'intention', 'intentions', 'change intention', 'behavior change',
        'identity', 'becoming', 'want to be', 'working on', 'improving',
        'personal growth', 'self improvement', 'development',
    ],

    'reflection': [
        'reflection', 'reflections', 'year end', 'year start', 'quarterly',
        'annual review', 'year in review', 'looking back', 'lessons learned',
        'what worked', 'what didnt work', 'gratitude', 'grateful for',
    ],

    'annual_direction': [
        'word of the year', 'yearly theme', 'annual theme', 'guiding word',
        'anchor scripture', 'anchor verse', 'focus for the year',
        'theme for the year', 'year ahead',
    ],

    # =========================================================================
    # FINANCE MODULE
    # =========================================================================
    'account': [
        'account', 'accounts', 'bank account', 'checking', 'savings',
        'credit card', 'credit cards', 'loan', 'loans', 'mortgage',
        'student loan', 'investment', 'investments', 'balance', 'balances',
        'account balance', 'available balance', 'current balance',
    ],

    'transaction': [
        'transaction', 'transactions', 'spent', 'spend', 'spending',
        'purchase', 'purchases', 'bought', 'paid', 'payment', 'payments',
        'charge', 'charges', 'deposit', 'deposits', 'transfer', 'transfers',
        'withdrew', 'withdrawal', 'income', 'expense', 'expenses',
    ],

    'budget': [
        'budget', 'budgets', 'budgeted', 'budgeting', 'over budget',
        'under budget', 'on budget', 'budget status', 'remaining budget',
        'budget category', 'monthly budget', 'spending limit',
        'how much left', 'how much can i spend', 'budget progress',
    ],

    'financial_goal': [
        'savings goal', 'saving for', 'emergency fund', 'debt payoff',
        'pay off', 'paying off', 'financial goal', 'money goal',
        'savings target', 'savings progress', 'how much saved',
        'how much more', 'when will i', 'monthly contribution',
    ],

    'net_worth': [
        'net worth', 'total assets', 'total liabilities', 'total debt',
        'financial health', 'financial snapshot', 'debt to income',
        'savings rate', 'cash flow', 'monthly cash flow',
    ],

    # =========================================================================
    # FASTING
    # =========================================================================
    'fasting': [
        'fasting', 'fast', 'fasts', 'fasted', 'intermittent fasting', 'if',
        'eating window', 'fasting window', '16:8', '18:6', '20:4', 'omad',
        'one meal a day', 'time restricted eating', 'time-restricted',
        'hours fasted', 'fasting hours', 'when did i start fasting',
        'fasting streak', 'broke my fast', 'break fast', 'breaking fast',
        'extended fast', 'water fast', 'autophagy',
    ],

    # =========================================================================
    # WATER / HYDRATION
    # =========================================================================
    'water': [
        'water', 'hydration', 'hydrated', 'hydrating', 'dehydrated', 'dehydration',
        'water intake', 'water consumption', 'drinking water', 'drank water',
        'glasses of water', 'cups of water', 'ounces of water', 'oz water',
        'liters of water', 'bottles of water', 'how much water', 'enough water',
        'daily water', 'water goal', 'water today', 'water yesterday',
        'staying hydrated', 'drink more water', 'fluid intake', 'fluids',
        'h2o', 'thirsty', 'thirst',
    ],

    # =========================================================================
    # MOOD & MENTAL STATE
    # =========================================================================
    'mood': [
        'mood', 'moods', 'feeling', 'feelings', 'felt', 'feel', 'emotion',
        'emotions', 'emotional', 'happy', 'sad', 'anxious', 'anxiety',
        'stressed', 'stress', 'depressed', 'depression', 'angry', 'anger',
        'calm', 'peaceful', 'worried', 'worry', 'hopeful', 'hope',
        'frustrated', 'frustration', 'excited', 'excitement', 'tired',
        'exhausted', 'energetic', 'energy', 'mental state', 'wellbeing',
        'well-being', 'mental health', 'mindset', 'overwhelmed', 'content',
        'joyful', 'joy', 'low mood', 'mood swing', 'irritable', 'irritated',
        'nervous', 'relaxed', 'motivated', 'unmotivated', 'burned out',
        'burnout', 'how am i feeling', 'how do i feel', 'mood today',
    ],

    # =========================================================================
    # SLEEP
    # =========================================================================
    'sleep': [
        'sleep', 'slept', 'sleeping', 'asleep', 'awake', 'woke', 'wake',
        'rest', 'rested', 'resting', 'insomnia', 'nap', 'naps', 'napped',
        'bedtime', 'hours of sleep', 'sleep quality', 'sleep schedule',
        'sleep pattern', 'sleep log', 'wake up', 'woke up', 'dream',
        'dreams', 'nightmare', 'nightmares', 'sleep duration', 'time in bed',
        'sleep cycle', 'well rested', 'sleep deprived',
    ],

    # =========================================================================
    # STEPS / ACTIVITY
    # =========================================================================
    'steps': [
        'steps', 'step count', 'daily steps', 'steps today', 'steps yesterday',
        'step goal', 'step average', 'walking steps', 'how many steps',
        'flights climbed', 'flights of stairs', 'stand hours', 'standing hours',
        'exercise minutes', 'active calories', 'calories burned',
        'distance walked', 'miles walked', 'activity rings',
    ],

    # =========================================================================
    # MOBILITY & GAIT (HealthKit)
    # =========================================================================
    'mobility': [
        'mobility', 'gait', 'walking speed', 'walking pace', 'step length',
        'walking asymmetry', 'walking steadiness', 'double support time',
        'stair speed', 'stair ascent', 'stair descent', 'six minute walk',
        '6 minute walk', 'gait analysis', 'fall risk', 'balance',
        'mobility score', 'walking ability',
    ],

    # =========================================================================
    # HEART RATE EVENTS (HealthKit alerts)
    # =========================================================================
    'heart_rate_events': [
        'heart rate event', 'heart rate alert', 'heart rate notification',
        'high heart rate', 'low heart rate', 'irregular rhythm',
        'irregular heartbeat', 'afib', 'atrial fibrillation',
        'heart rate warning', 'tachycardia', 'bradycardia',
        'heart rate notification', 'apple watch alert',
    ],

    # =========================================================================
    # AUDIO EXPOSURE (HealthKit)
    # =========================================================================
    'audio_exposure': [
        'audio exposure', 'headphone audio', 'headphone volume',
        'headphone level', 'environmental noise', 'noise exposure',
        'hearing health', 'hearing damage', 'loud noise', 'decibel',
        'decibels', 'db level', 'headphone safety', 'noise level',
        'environmental sound', 'audio level', 'listening time',
    ],

    # =========================================================================
    # DIETARY NUTRIENTS (HealthKit aggregated from external apps)
    # =========================================================================
    'dietary_nutrients': [
        'dietary nutrients', 'healthkit nutrition', 'apple health nutrition',
        'nutrient intake', 'nutrient data', 'macro intake',
        'daily protein', 'daily carbs', 'daily fat', 'daily fiber',
        'daily sodium', 'daily cholesterol', 'daily potassium',
        'daily calcium', 'daily iron', 'vitamin d intake',
    ],

    # =========================================================================
    # HEALTH SUMMARY — Catches generic "health data" / "HealthKit" queries
    # When users ask broadly about "my health data" or "HealthKit data"
    # without specifying a type, pull a comprehensive summary.
    # =========================================================================
    'health_summary': [
        'health data', 'health records', 'healthkit', 'healthkit data',
        'apple health', 'apple health data', 'health information',
        'health metrics', 'health stats', 'health statistics',
        'health summary', 'health overview', 'health snapshot',
        'my health', 'all my health', 'all health data',
        'new health data', 'new health records', 'new activity',
        'synced data', 'synced health', 'sync data', 'sync health',
        'health tracking', 'what health', 'any health',
        'vitals', 'my vitals', 'vital signs',
    ],
}


# =============================================================================
# DATE/TIME KEYWORDS - Indicate temporal context in queries
# =============================================================================

DATE_KEYWORDS: List[str] = [
    # Relative time references
    'since', 'from', 'after', 'before', 'until', 'between', 'during',
    # Aggregation keywords
    'last', 'past', 'previous', 'recent', 'recently', 'latest',
    'average', 'avg', 'mean', 'total', 'sum', 'count', 'minimum', 'maximum',
    'min', 'max', 'highest', 'lowest', 'best', 'worst',
    'how many', 'how much', 'how often', 'how long',
    # Specific time periods
    'today', 'yesterday', 'tomorrow', 'tonight', 'this morning', 'this afternoon',
    'this week', 'last week', 'next week', 'this weekend',
    'this month', 'last month', 'next month',
    'this year', 'last year', 'next year', 'this quarter', 'last quarter',
    # Days of week
    'monday', 'tuesday', 'wednesday', 'thursday', 'friday', 'saturday', 'sunday',
    # Months
    'january', 'february', 'march', 'april', 'may', 'june',
    'july', 'august', 'september', 'october', 'november', 'december',
    'jan', 'feb', 'mar', 'apr', 'jun', 'jul', 'aug', 'sep', 'oct', 'nov', 'dec',
    # Time ranges
    'week', 'weeks', 'month', 'months', 'year', 'years', 'day', 'days',
    'hour', 'hours', 'morning', 'afternoon', 'evening', 'night',
    # Ordinals and dates
    '1st', '2nd', '3rd', '4th', '5th', '6th', '7th', '8th', '9th', '10th',
    '11th', '12th', '13th', '14th', '15th', '16th', '17th', '18th', '19th', '20th',
    '21st', '22nd', '23rd', '24th', '25th', '26th', '27th', '28th', '29th', '30th', '31st',
    # Trend indicators
    'trend', 'trends', 'trending', 'over time', 'history', 'historical',
    'progress', 'change', 'changed', 'changes', 'compared to', 'comparison',
    # Frequency
    'daily', 'weekly', 'monthly', 'yearly', 'annually', 'quarterly',
    'every day', 'each day', 'per day', 'per week', 'per month',
]


# =============================================================================
# PERSONAL PRONOUNS - Indicate query is about user's own data
# =============================================================================

PERSONAL_PRONOUNS: List[str] = [
    'my', 'i', 'me', 'mine', "i've", "i'm", "i'd", 'myself',
    'we', 'our', 'ours', "we've", "we're",  # for family/household data
]


# =============================================================================
# META-QUESTION KEYWORDS - Questions about data existence
# =============================================================================

META_QUESTION_KEYWORDS: List[str] = [
    'have i logged', 'did i log', 'did i record', 'have i recorded',
    'have i tracked', 'did i track', 'have i entered', 'did i enter',
    'did i write', 'have i written', 'is there any', 'are there any',
    'do i have any', 'any entries', 'any data', 'any records',
    'do i have', 'have i', 'did i', 'when did i', 'when was',
    'how many times', 'how many days', 'am i tracking', 'have i been',
]


# =============================================================================
# COMPOUND QUERY CONNECTORS
# =============================================================================

COMPOUND_CONNECTORS: List[str] = [
    ' and ', ' or ', ' with ', ' plus ', ' along with ', ' as well as ',
    ', ', ' & ', ' also ', ' including ',
]


# =============================================================================
# BIBLE STUDY CONTEXT - Indicates message is about scripture, not personal data
# =============================================================================

# Bible characters that indicate the message is about scripture, not personal data
# When these names appear, don't flag personal data keywords like "sleep"
BIBLE_CHARACTERS: List[str] = [
    # Old Testament figures
    'abraham', 'isaac', 'jacob', 'joseph', 'moses', 'aaron', 'joshua', 'david',
    'solomon', 'elijah', 'elisha', 'isaiah', 'jeremiah', 'ezekiel', 'daniel',
    'jonah', 'ruth', 'esther', 'job', 'noah', 'adam', 'eve', 'sarah', 'rebecca',
    'rachel', 'leah', 'samson', 'gideon', 'samuel', 'saul', 'goliath',
    # New Testament figures
    'jesus', 'christ', 'mary', 'martha', 'lazarus', 'peter', 'paul', 'john',
    'james', 'matthew', 'mark', 'luke', 'andrew', 'philip', 'thomas', 'judas',
    'nicodemus', 'pilate', 'herod', 'barabbas', 'stephen', 'timothy', 'barnabas',
    'silas', 'apollos', 'priscilla', 'aquila', 'cornelius', 'lydia', 'phoebe',
    # Groups/roles from Bible narratives
    'wiseman', 'wise men', 'magi', 'shepherd', 'shepherds', 'pharaoh',
]

# Bible study terms that indicate scriptural discussion
BIBLE_STUDY_TERMS: List[str] = [
    'metaphor', 'parable', 'allegory', 'symbolism', 'prophecy', 'scripture',
    'verse', 'passage', 'gospel', 'epistle', 'testament', 'covenant', 'apostle',
    'disciple', 'pharisee', 'sadducee', 'sanhedrin', 'sabbath', 'resurrection',
    'crucifixion', 'salvation', 'baptism', 'communion', 'sermon', 'miracle',
    # Marriage/cultural terms from Bible
    'betrothed', 'betroth',
    # Divine communication in Bible
    'dream', 'dreams', 'vision', 'visions', 'angel', 'angels',
]


def is_bible_study_context(message: str) -> bool:
    """
    Detect if a message is about Bible study/scripture rather than personal data.

    This helps avoid false positives where words like "asleep" in
    "Was Joseph asleep?" refer to Bible stories, not personal sleep data.

    Args:
        message: The user's message string.

    Returns:
        True if the message appears to be about Bible/scripture study.
    """
    message_lower = message.lower()

    # Check for Bible character names
    for character in BIBLE_CHARACTERS:
        pattern = r'\b' + re.escape(character) + r'\b'
        if re.search(pattern, message_lower):
            return True

    # Check for Bible study terms
    for term in BIBLE_STUDY_TERMS:
        pattern = r'\b' + re.escape(term) + r'\b'
        if re.search(pattern, message_lower):
            return True

    return False


# =============================================================================
# AMBIGUOUS KEYWORDS - Need clarification before processing
# =============================================================================

# Format: {keyword: {possible_types: [...], clarifying_questions: {style: "..."}}}
# Coaching styles: direct, gentle, supportive (default)
AMBIGUOUS_KEYWORDS: Dict[str, Dict] = {
    'sugar': {
        'possible_types': ['glucose', 'food'],
        'clarifying_questions': {
            'direct': "Blood sugar or dietary sugar?",
            'gentle': (
                "I want to make sure I understand - are you asking about "
                "your blood sugar readings, or the sugar in what you've been eating?"
            ),
            'supportive': (
                "Just to make sure I pull the right info - are you asking about "
                "your blood sugar readings or the sugar in your food?"
            ),
        },
    },
    'sugars': {
        'possible_types': ['glucose', 'food'],
        'clarifying_questions': {
            'direct': "Blood sugar readings or dietary sugars?",
            'gentle': (
                "Just checking - do you mean your blood sugar levels, "
                "or the sugars in your food?"
            ),
            'supportive': (
                "Quick question - do you mean your blood sugar levels or "
                "the sugars you've been eating?"
            ),
        },
    },
}


def get_clarifying_question(keyword: str, coaching_style: str = 'supportive') -> str:
    """
    Get the clarifying question for an ambiguous keyword in the user's preferred style.

    Args:
        keyword: The ambiguous keyword (e.g., 'sugar')
        coaching_style: The user's preferred coaching style

    Returns:
        The clarifying question string in the appropriate style.
    """
    if keyword not in AMBIGUOUS_KEYWORDS:
        return "Could you clarify what you mean?"

    questions = AMBIGUOUS_KEYWORDS[keyword].get('clarifying_questions', {})
    # Fall back to supportive style if user's style not available
    return questions.get(coaching_style, questions.get('supportive', "Could you clarify?"))


def detect_personal_data_intent(message: str) -> Dict:
    """
    Detect if a user's message relates to their personal WLJ data.

    This function analyzes the message text to determine:
    1. Whether it's a query about personal data
    2. What types of data are being referenced
    3. Whether there's a date/time context to the query
    4. Whether it's a meta-question (asking about data existence vs. data values)
    5. Whether it's a compound query (asking about multiple data types)
    6. Whether an ambiguous keyword requires clarification

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
            - has_ambiguous_keyword (bool): True if an ambiguous keyword was found.
            - ambiguous_keyword (str): The ambiguous keyword if found.
            - ambiguous_info (dict): Info about the ambiguous keyword.

    Example:
        >>> detect_personal_data_intent("What was my average weight last week?")
        {
            'is_personal_query': True,
            'data_types': ['weight'],
            'has_date_context': True,
            'is_meta_question': False,
            'is_compound_query': False,
            'has_ambiguous_keyword': False,
            'ambiguous_keyword': None,
            'ambiguous_info': None
        }
    """
    if not message or not isinstance(message, str):
        return {
            'is_personal_query': False,
            'data_types': [],
            'has_date_context': False,
            'is_meta_question': False,
            'is_compound_query': False,
            'has_ambiguous_keyword': False,
            'ambiguous_keyword': None,
            'ambiguous_info': None,
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
        r'\bwhat\b', r'\bhow\b', r'\bwhen\b', r'\bwhere\b', r'\bwhich\b',
        r'\bshow\b', r'\btell\b', r'\blist\b', r'\bget\b', r'\bgive\b',
        r'\bfind\b', r'\bsearch\b', r'\blook\b', r'\bcheck\b',
        r'\bdid\b', r'\bhave\b', r'\bhas\b', r'\bwas\b', r'\bwere\b',
        r'\bis\b', r'\bare\b', r'\bam\b', r'\bdo\b', r'\bdoes\b',
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
            glucose_context = ['blood sugar', 'sugar level', 'glucose', 'reading', 'a1c', 'diabetes', 'dexcom', 'cgm']
            # Food context - unambiguous dietary sugar
            food_context = ['ate', 'eat', 'eaten', 'food', 'meal', 'diet', 'calories', 'carbs', 'dietary']

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
    # - BUT NOT if it's a Bible study question (e.g., "Was Joseph asleep?")
    has_data_indicator = bool(detected_data_types) or ambiguous_keyword_found

    # Check for Bible study context - if present, this is NOT a personal data query
    # This prevents false positives like "Was Joseph asleep?" triggering sleep data
    is_bible_context = is_bible_study_context(message)

    is_personal_query = has_data_indicator and (
        has_personal_pronoun or (has_query_pattern and has_data_indicator)
        or is_meta_question
    ) and not is_bible_context

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
