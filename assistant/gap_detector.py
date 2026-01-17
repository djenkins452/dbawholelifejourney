"""
Gap Detection Module for WLJ Personal Data Query System.

Owner: admin@wholelifejourney.com

This module provides functions to detect and categorize knowledge gaps
when the assistant cannot answer a user's personal data question.
It captures context for improvement and helps prioritize enhancement tasks.
"""

from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional

from django.utils import timezone


class GapType(Enum):
    """Types of knowledge gaps that can be detected."""

    UNKNOWN_DATA_TYPE = "unknown_data_type"
    MISSING_KEYWORDS = "missing_keywords"
    NO_DATA_METHOD = "no_data_method"
    UNSUPPORTED_QUERY_PATTERN = "unsupported_query_pattern"


class GapSeverity(Enum):
    """Severity levels for knowledge gaps."""

    LOW = "low"  # Keyword addition
    MEDIUM = "medium"  # New query method
    HIGH = "high"  # Application change


# Keywords from intent_detector that are currently supported
SUPPORTED_DATA_TYPES = [
    'weight', 'journal', 'medication', 'food', 'mood',
    'sleep', 'exercise', 'glucose', 'blood_pressure', 'faith', 'goals',
]

# Data types that have query methods in PersonalDataService
DATA_TYPES_WITH_METHODS = [
    'weight', 'journal', 'medication', 'food', 'mood',
    'glucose', 'faith', 'goals',
]

# Common words to exclude from potential keyword extraction
STOP_WORDS = {
    'a', 'an', 'the', 'is', 'are', 'was', 'were', 'be', 'been', 'being',
    'have', 'has', 'had', 'do', 'does', 'did', 'will', 'would', 'could',
    'should', 'may', 'might', 'must', 'shall', 'can', 'need', 'dare',
    'ought', 'used', 'to', 'of', 'in', 'for', 'on', 'with', 'at', 'by',
    'from', 'as', 'into', 'through', 'during', 'before', 'after', 'above',
    'below', 'between', 'under', 'again', 'further', 'then', 'once',
    'here', 'there', 'when', 'where', 'why', 'how', 'all', 'each', 'few',
    'more', 'most', 'other', 'some', 'such', 'no', 'nor', 'not', 'only',
    'own', 'same', 'so', 'than', 'too', 'very', 'just', 'and', 'but',
    'if', 'or', 'because', 'until', 'while', 'what', 'which', 'who',
    'whom', 'this', 'that', 'these', 'those', 'am', 'i', 'my', 'me',
    'mine', 'you', 'your', 'yours', 'he', 'him', 'his', 'she', 'her',
    'hers', 'it', 'its', 'we', 'us', 'our', 'ours', 'they', 'them',
    'their', 'theirs', 'any', 'both', 'each', 'much', 'many', 'out',
}

# Contraction fragments - words that result from splitting contractions
# e.g., "didn't" -> "didn", "wouldn't" -> "wouldn"
CONTRACTION_FRAGMENTS = {
    'didn', 'doesn', 'don', 'won', 'wouldn', 'couldn', 'shouldn', 'wasn',
    'weren', 'isn', 'aren', 'hasn', 'haven', 'hadn', 'ain', 'can', 'shan',
    'mustn', 'needn', 'oughtn', 'mightn', 'daren', 'll', 've', 're', 'd',
}

# Common conversational words that are never data types
# These are pronouns, quantifiers, and abstract words that appear in everyday speech
CONVERSATIONAL_WORDS = {
    # Pronouns and determiners
    'everything', 'something', 'nothing', 'anything',
    'everyone', 'someone', 'anyone', 'noone', 'nobody', 'somebody', 'everybody',
    'somewhere', 'anywhere', 'nowhere', 'everywhere',
    'sometime', 'anytime',
    # Common abstract words
    'thing', 'things', 'stuff', 'way', 'ways', 'place', 'places',
    'time', 'times', 'day', 'days', 'week', 'weeks', 'month', 'months',
    'year', 'years', 'today', 'yesterday', 'tomorrow',
    # Question/answer words - these are conversational, not data types
    'question', 'questions', 'answer', 'answers', 'answering', 'answered',
    'reply', 'replies', 'response', 'responses',
    # Meta/conversation words - about the assistant or dialog itself
    'conversation', 'conversations', 'dialog', 'dialogue', 'chat', 'chats',
    'message', 'messages', 'context', 'current', 'session', 'sessions',
    # External data that should use APIs, not stored data types
    'weather', 'forecast', 'temperature', 'climate',
    'news', 'headline', 'headlines', 'article', 'articles',
    'definition', 'definitions', 'meaning', 'meanings',
    # Location words
    'city', 'cities', 'town', 'towns', 'state', 'states', 'country', 'countries',
    'location', 'locations', 'address', 'addresses',
    # Common verbs that might get extracted
    'want', 'wanted', 'wanting', 'like', 'liked', 'liking',
    'think', 'thought', 'thinking', 'know', 'knew', 'knowing',
    'make', 'made', 'making', 'take', 'took', 'taking',
    'get', 'got', 'getting', 'put', 'putting',
    'say', 'said', 'saying', 'tell', 'told', 'telling',
    'ask', 'asked', 'asking', 'use', 'used', 'using',
    'find', 'found', 'finding', 'give', 'gave', 'giving',
    'work', 'worked', 'working', 'seem', 'seemed', 'seeming',
    'feel', 'felt', 'feeling', 'try', 'tried', 'trying',
    'leave', 'left', 'leaving', 'call', 'called', 'calling',
    'keep', 'kept', 'keeping', 'let', 'letting',
    'begin', 'began', 'beginning', 'help', 'helped', 'helping',
    'show', 'showed', 'showing', 'hear', 'heard', 'hearing',
    'play', 'played', 'playing', 'run', 'ran', 'running',
    'move', 'moved', 'moving', 'live', 'lived', 'living',
    'believe', 'believed', 'believing', 'bring', 'brought', 'bringing',
    'happen', 'happened', 'happening', 'write', 'wrote', 'writing',
    'provide', 'provided', 'providing', 'sit', 'sat', 'sitting',
    'stand', 'stood', 'standing', 'lose', 'lost', 'losing',
    'pay', 'paid', 'paying', 'meet', 'met', 'meeting',
    'include', 'included', 'including', 'continue', 'continued', 'continuing',
    'set', 'setting', 'learn', 'learned', 'learning',
    'change', 'changed', 'changing', 'lead', 'led', 'leading',
    'understand', 'understood', 'understanding',
    'watch', 'watched', 'watching', 'follow', 'followed', 'following',
    'stop', 'stopped', 'stopping', 'create', 'created', 'creating',
    'speak', 'spoke', 'speaking', 'read', 'reading',
    'allow', 'allowed', 'allowing', 'add', 'added', 'adding',
    'spend', 'spent', 'spending', 'grow', 'grew', 'growing',
    'open', 'opened', 'opening', 'walk', 'walked', 'walking',
    'win', 'winning', 'offer', 'offered', 'offering',
    'remember', 'remembered', 'remembering', 'love', 'loved', 'loving',
    'consider', 'considered', 'considering', 'appear', 'appeared', 'appearing',
    'buy', 'bought', 'buying', 'wait', 'waited', 'waiting',
    'serve', 'served', 'serving', 'die', 'died', 'dying',
    'send', 'sent', 'sending', 'expect', 'expected', 'expecting',
    'build', 'built', 'building', 'stay', 'stayed', 'staying',
    'fall', 'fell', 'falling', 'cut', 'cutting',
    'reach', 'reached', 'reaching', 'kill', 'killed', 'killing',
    'remain', 'remained', 'remaining',
    # Common adjectives
    'good', 'better', 'best', 'bad', 'worse', 'worst',
    'new', 'old', 'young', 'long', 'short', 'big', 'small',
    'high', 'low', 'great', 'little', 'large', 'right', 'wrong',
    'different', 'important', 'sure', 'real', 'true', 'false',
    'possible', 'able', 'late', 'early', 'hard', 'easy',
    'whole', 'full', 'empty', 'ready', 'clear', 'certain',
    'fine', 'free', 'strong', 'special', 'open', 'close',
    # Discourse markers and fillers
    'well', 'now', 'also', 'still', 'even', 'back', 'yes', 'yeah', 'okay',
    'please', 'thanks', 'thank', 'sorry', 'hello', 'hey', 'hi',
    # UI/navigation terms - not data types
    'dashboard', 'page', 'pages', 'screen', 'screens', 'menu', 'menus',
    'settings', 'preferences', 'profile', 'account', 'navigation', 'navigate',
    'button', 'buttons', 'link', 'links', 'click', 'clicked', 'clicking',
    'tab', 'tabs', 'section', 'sections', 'sidebar', 'header', 'footer',
    'home', 'homepage', 'landing', 'view', 'views', 'display', 'displays',
}

# Query pattern keywords we currently support
SUPPORTED_QUERY_PATTERNS = [
    'what', 'how', 'when', 'show', 'tell', 'list', 'get', 'find',
    'search', 'look', 'check', 'did', 'have', 'has', 'was', 'were',
    'average', 'total', 'count', 'sum', 'last', 'latest', 'recent',
]

# Bible book names - used to detect scripture references (e.g., "1 John 5:14")
BIBLE_BOOKS = {
    'genesis', 'exodus', 'leviticus', 'numbers', 'deuteronomy',
    'joshua', 'judges', 'ruth', 'samuel', 'kings', 'chronicles',
    'ezra', 'nehemiah', 'esther', 'job', 'psalms', 'psalm', 'proverbs',
    'ecclesiastes', 'song', 'isaiah', 'jeremiah', 'lamentations',
    'ezekiel', 'daniel', 'hosea', 'joel', 'amos', 'obadiah', 'jonah',
    'micah', 'nahum', 'habakkuk', 'zephaniah', 'haggai', 'zechariah',
    'malachi', 'matthew', 'mark', 'luke', 'john', 'acts', 'romans',
    'corinthians', 'galatians', 'ephesians', 'philippians', 'colossians',
    'thessalonians', 'timothy', 'titus', 'philemon', 'hebrews', 'james',
    'peter', 'jude', 'revelation', 'revelations',
}


def is_meta_question(query: str) -> bool:
    """
    Detect if a query is a meta question about the assistant itself.

    These are questions directed AT the assistant about its capabilities,
    context, or behavior - not requests for personal data.

    Args:
        query: The user's query string.

    Returns:
        True if this is a meta question about the assistant.

    Examples:
        >>> is_meta_question("Can you answer that question?")
        True
        >>> is_meta_question("Are you looking at the page I am on?")
        True
        >>> is_meta_question("What was my weight yesterday?")
        False
    """
    query_lower = query.lower().strip()

    # Patterns that indicate questions directed at the assistant
    meta_patterns = [
        # Questions about assistant capabilities
        'can you ', 'could you ', 'are you ', 'do you ', 'will you ',
        'would you ', 'should you ', 'how do you ', 'how can you ',
        'are you able', 'can you see', 'can you read', 'can you access',
        # Questions about what the assistant is doing/using
        'are you looking', 'are you using', 'are you based',
        'is that based on', 'is this based on',
        # Questions about the interface/page context
        'based on the current page', 'based on this page',
        'based on our conversation', 'based on the page',
        'looking at the page', 'see the page', 'read the page',
        # Complaints/feedback about assistant behavior
        "why didn't you", "why did you", "you should have",
        "you didn't", "you forgot", "you missed",
        # Questions about how the assistant works
        'how does this work', 'how do you work', 'what can you do',
        'what are you', 'who are you',
    ]

    for pattern in meta_patterns:
        if pattern in query_lower:
            return True

    return False


def is_bible_reference(query: str) -> bool:
    """
    Detect if a query contains a Bible verse reference.

    Bible references follow patterns like "1 John 5:14-15", "John 3:16",
    "Psalm 23", etc.

    Args:
        query: The user's query string.

    Returns:
        True if the query contains a Bible reference.

    Examples:
        >>> is_bible_reference("What is 1 John 5:14-15")
        True
        >>> is_bible_reference("Read me Psalm 23")
        True
        >>> is_bible_reference("What was my weight?")
        False
    """
    import re
    query_lower = query.lower()

    # Check if any Bible book name appears in the query
    for book in BIBLE_BOOKS:
        if book in query_lower:
            # Look for chapter:verse pattern near the book name
            # Pattern: optional number + book name + chapter(:verse)?
            pattern = rf'\b\d?\s*{book}\s+\d+(?::\d+)?'
            if re.search(pattern, query_lower):
                return True
            # Also match just the book name with a number after it
            if re.search(rf'\b{book}\s+\d', query_lower):
                return True

    return False


def is_external_data_query(query: str) -> bool:
    """
    Detect if a query is asking for external/real-time data.

    These are queries that should be answered by external APIs,
    not by creating new data types in the system.

    Args:
        query: The user's query string.

    Returns:
        True if this is an external data query.

    Examples:
        >>> is_external_data_query("What is the weather in Nashville?")
        True
        >>> is_external_data_query("What time is it in Tokyo?")
        True
        >>> is_external_data_query("What was my weight yesterday?")
        False
    """
    query_lower = query.lower()

    # External data patterns
    external_patterns = [
        # Weather
        'weather in', 'weather for', 'temperature in', 'forecast for',
        'is it raining', 'is it sunny', 'is it cold', 'is it hot',
        # Time
        'what time is it', 'current time', 'time in',
        # General knowledge/definitions
        'what is a ', 'what is an ', 'what is the definition',
        'define ', 'meaning of ',
        # News
        'news about', 'latest news', 'headlines',
        # Stock/crypto prices
        'stock price', 'price of', 'how much is',
    ]

    for pattern in external_patterns:
        if pattern in query_lower:
            return True

    return False


def detect_knowledge_gap(
    original_query: str,
    intent_result: Optional[Dict[str, Any]] = None,
    data_result: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """
    Detect and categorize why a query couldn't be answered.

    This function analyzes the query, intent detection results, and data query
    results to determine if there's a knowledge gap and what type it is.

    Args:
        original_query: The user's original query string.
        intent_result: The result from detect_personal_data_intent().
                      Contains is_personal_query, data_types, has_date_context, etc.
        data_result: The result from PersonalDataService.query_by_intent().
                    None or empty dict means no data was found.

    Returns:
        A dictionary containing:
            - gap_detected (bool): True if a knowledge gap was identified.
            - gap_type (GapType or None): The type of gap detected.
            - original_query (str): The original user query.
            - detected_intent (dict or None): The intent detection result.
            - suggested_category (str or None): Suggested data category for improvement.
            - timestamp (datetime): When the gap was detected.

    Example:
        >>> result = detect_knowledge_gap(
        ...     "How many steps did I take yesterday?",
        ...     {'is_personal_query': True, 'data_types': ['exercise']},
        ...     None
        ... )
        >>> result['gap_detected']
        True
        >>> result['gap_type']
        <GapType.NO_DATA_METHOD: 'no_data_method'>
    """
    timestamp = timezone.now()

    # Default response for no gap
    base_response = {
        'gap_detected': False,
        'gap_type': None,
        'original_query': original_query,
        'detected_intent': intent_result,
        'suggested_category': None,
        'timestamp': timestamp,
    }

    # If intent_result is None or query is empty, no gap to detect
    if not original_query or intent_result is None:
        return base_response

    query_lower = original_query.lower()

    # Case 1: Check for unsupported query patterns FIRST
    # (comparison, correlation, prediction patterns that we can't handle yet)
    if intent_result.get('is_personal_query'):
        unsupported_patterns = _check_unsupported_patterns(query_lower)
        if unsupported_patterns:
            return {
                **base_response,
                'gap_detected': True,
                'gap_type': GapType.UNSUPPORTED_QUERY_PATTERN,
                'suggested_category': unsupported_patterns[0],
            }

    # Case 2: Intent detected a personal query but we couldn't get data
    if intent_result.get('is_personal_query'):
        detected_types = intent_result.get('data_types', [])

        # Check if any detected types don't have query methods
        types_without_methods = [
            dt for dt in detected_types
            if dt in SUPPORTED_DATA_TYPES and dt not in DATA_TYPES_WITH_METHODS
        ]

        if types_without_methods:
            # We recognize the data type but don't have a method to query it
            return {
                **base_response,
                'gap_detected': True,
                'gap_type': GapType.NO_DATA_METHOD,
                'suggested_category': types_without_methods[0],
            }

        # If we have methods but got no data, that's not a gap - just no data
        if data_result is not None and len(data_result) > 0:
            return base_response

        # If we detected data types and have methods but no data returned,
        # the user simply has no data logged (not a knowledge gap)
        if detected_types and all(dt in DATA_TYPES_WITH_METHODS for dt in detected_types):
            return base_response

    # Case 3: Query looks personal but we didn't detect any data types
    if intent_result.get('is_personal_query') and not intent_result.get('data_types'):
        # Might be missing keywords - extract potential keywords
        potential_keywords = extract_potential_keywords(original_query)
        suggested = potential_keywords[0] if potential_keywords else None
        return {
            **base_response,
            'gap_detected': True,
            'gap_type': GapType.MISSING_KEYWORDS,
            'suggested_category': suggested,
        }

    # Case 4: Not detected as personal query but might be one
    # First, filter out queries that should NEVER trigger data type suggestions:
    # - Meta questions about the assistant itself
    # - Bible verse references
    # - External data queries (weather, time, definitions, etc.)
    if is_meta_question(original_query):
        return base_response

    if is_bible_reference(original_query):
        return base_response

    if is_external_data_query(original_query):
        return base_response

    # Check for query patterns that suggest it should be personal
    has_personal_indicators = any(
        word in query_lower
        for word in ['my', 'i', 'me', "i've", "i'm"]
    )

    if has_personal_indicators and not intent_result.get('is_personal_query'):
        potential_keywords = extract_potential_keywords(original_query)
        if potential_keywords:
            # Query has personal indicators but no recognized data type
            return {
                **base_response,
                'gap_detected': True,
                'gap_type': GapType.UNKNOWN_DATA_TYPE,
                'suggested_category': potential_keywords[0],
            }

    return base_response


def _check_unsupported_patterns(query_lower: str) -> List[str]:
    """
    Check for query patterns that aren't fully supported yet.

    Args:
        query_lower: The lowercase query string.

    Returns:
        List of unsupported pattern descriptions found.
    """
    unsupported = []

    # Comparison patterns (not yet supported)
    comparison_patterns = [
        ('compare', 'comparison queries'),
        ('versus', 'comparison queries'),
        ('vs', 'comparison queries'),
        ('better than', 'comparison queries'),
        ('worse than', 'comparison queries'),
    ]

    for pattern, description in comparison_patterns:
        if pattern in query_lower and description not in unsupported:
            unsupported.append(description)

    # Correlation patterns (not yet supported)
    correlation_patterns = [
        ('correlation', 'correlation analysis'),
        ('relate', 'correlation analysis'),
        ('affect', 'correlation analysis'),
        ('impact', 'correlation analysis'),
        ('influence', 'correlation analysis'),
    ]

    for pattern, description in correlation_patterns:
        if pattern in query_lower and description not in unsupported:
            unsupported.append(description)

    # Prediction patterns (not yet supported)
    prediction_patterns = [
        ('predict', 'predictive queries'),
        ('forecast', 'predictive queries'),
        ('will i', 'predictive queries'),
        ('going to', 'predictive queries'),
    ]

    for pattern, description in prediction_patterns:
        if pattern in query_lower and description not in unsupported:
            unsupported.append(description)

    return unsupported


def extract_potential_keywords(query: str) -> List[str]:
    """
    Extract words that might be new data type indicators.

    This function identifies words in the query that could represent
    data types we don't currently recognize but should consider adding.

    Args:
        query: The user's query string.

    Returns:
        List of potential keyword strings, ordered by likelihood
        of being a data type indicator.

    Example:
        >>> extract_potential_keywords("What was my hydration level yesterday?")
        ['hydration', 'level']
    """
    if not query:
        return []

    # Normalize and tokenize
    query_lower = query.lower()

    # Remove punctuation and split into words
    import re
    words = re.findall(r'\b[a-z]+\b', query_lower)

    # Filter out stop words, contraction fragments, conversational words,
    # and words that are too short (minimum 4 characters to be a data type)
    candidates = [
        word for word in words
        if word not in STOP_WORDS
        and word not in CONTRACTION_FRAGMENTS
        and word not in CONVERSATIONAL_WORDS
        and len(word) >= 4  # Increased from 3 to 4 to reduce noise
        and not word.isdigit()
    ]

    # Filter out words that are already known keywords
    # Import here to avoid circular imports
    from assistant.intent_detector import PERSONAL_DATA_KEYWORDS, DATE_KEYWORDS

    known_words = set()
    for keyword_list in PERSONAL_DATA_KEYWORDS.values():
        for kw in keyword_list:
            known_words.update(kw.lower().split())
    known_words.update(word.lower() for word in DATE_KEYWORDS)
    known_words.update(SUPPORTED_QUERY_PATTERNS)

    # Remove known words
    candidates = [word for word in candidates if word not in known_words]

    # Score candidates based on position and context
    scored = []
    for word in candidates:
        score = 0

        # Words after "my" or possessive context score higher
        if f"my {word}" in query_lower:
            score += 3
        if f"i {word}" in query_lower:
            score += 2

        # Nouns typically come after articles
        if f"the {word}" in query_lower or f"a {word}" in query_lower:
            score += 1

        # Words with health/wellness connotations
        health_suffixes = ['tion', 'ing', 'ness', 'ity', 'ment']
        if any(word.endswith(suffix) for suffix in health_suffixes):
            score += 1

        scored.append((word, score))

    # Sort by score descending, then alphabetically
    scored.sort(key=lambda x: (-x[1], x[0]))

    # Return unique words in order
    seen = set()
    result = []
    for word, _ in scored:
        if word not in seen:
            seen.add(word)
            result.append(word)

    return result


def categorize_gap_severity(gap_type: Optional[GapType]) -> GapSeverity:
    """
    Categorize the severity of a knowledge gap.

    Args:
        gap_type: The type of gap detected.

    Returns:
        GapSeverity indicating the effort required to fix:
            - LOW: Keyword addition (simple config change)
            - MEDIUM: New query method (code addition)
            - HIGH: Application change (architecture/model change)

    Example:
        >>> categorize_gap_severity(GapType.MISSING_KEYWORDS)
        <GapSeverity.LOW: 'low'>
        >>> categorize_gap_severity(GapType.NO_DATA_METHOD)
        <GapSeverity.MEDIUM: 'medium'>
    """
    if gap_type is None:
        return GapSeverity.LOW

    severity_map = {
        GapType.MISSING_KEYWORDS: GapSeverity.LOW,
        GapType.NO_DATA_METHOD: GapSeverity.MEDIUM,
        GapType.UNKNOWN_DATA_TYPE: GapSeverity.HIGH,
        GapType.UNSUPPORTED_QUERY_PATTERN: GapSeverity.HIGH,
    }

    return severity_map.get(gap_type, GapSeverity.MEDIUM)
