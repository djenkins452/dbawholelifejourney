# ==============================================================================
# File: web_search_service.py
# Project: Whole Life Journey - Django 5.x Personal Wellness/Journaling App
# Description: Web search service for answering real-time questions (weather, etc.)
# Owner: Danny Jenkins (admin@wholelifejourney.com)
# Created: 2026-01-17
# ==============================================================================
"""
Web Search Service for Personal Assistant

Handles questions that require real-time information from the web:
- Weather queries (via Open-Meteo API - free, no API key needed)
- General knowledge questions

Priority order for answering questions:
1. Page context (what user is viewing)
2. Personal data in the app
3. Web search / external APIs (this service)
"""
import logging
import re
import requests
from typing import Optional, Dict, Any

logger = logging.getLogger(__name__)


# Patterns that indicate web search / external knowledge is needed
WEB_SEARCH_PATTERNS = [
    # Weather
    r'\bweather\b',
    r'\bforecast\b',
    r'\btemperature\b',
    r'\brain\b.*\b(today|tomorrow|outside)\b',
    r'\bsnow\b.*\b(today|tomorrow|outside)\b',
    r'\bhot\b.*\boutside\b',
    r'\bcold\b.*\boutside\b',
    r'\bwhat.s it like outside\b',
]

# Patterns that indicate general knowledge questions (non-personal, non-action)
GENERAL_KNOWLEDGE_PATTERNS = [
    # "What is X" / "Who is X" / "How does X work" / "Explain X"
    r'^(?:what|who|where|when|how|why)\s+(?:is|are|was|were|does|do|did|can|should)\b',
    r'\bexplain\b.*\bto me\b',
    r'\btell me about\b',
    r'\bwhat does\b.*\bmean\b',
    r'\bdefine\b',
    r'\bdifference between\b',
    # Health/nutrition/fitness knowledge (not logging)
    r'\bbenefit(?:s)?\s+of\b',
    r'\bside effect(?:s)?\s+of\b',
    r'\bhow\s+(?:much|many|often|long)\b.*\bshould\b',
    r'\bis\s+(?:it|this)\s+(?:good|bad|healthy|safe|normal)\b',
    r'\bcalories?\s+in\b',
    r'\bprotein\s+in\b',
    r'\bnutrition(?:al)?\s+(?:info|value|facts)\b',
    # Recipes / cooking
    r'\brecipe\s+for\b',
    r'\bhow\s+(?:to|do\s+(?:you|i))\s+(?:cook|make|prepare|bake)\b',
    # Exercise form / technique
    r'\bproper\s+form\b',
    r'\bhow\s+(?:to|do\s+(?:you|i))\s+(?:do|perform)\b.*\b(?:exercise|stretch|lift|squat|deadlift|press)\b',
    # Bible / faith knowledge
    r'\bwhat\s+(?:does|did)\s+(?:the\s+)?bible\s+say\b',
    r'\bmeaning\s+of\b.*\b(?:verse|scripture|passage|proverb)\b',
    r'\bwho\s+(?:was|is)\b.*\bin\s+the\s+bible\b',
    # General factual
    r'\bhow\s+(?:to|do\s+(?:you|i))\b',
    r'\btips?\s+(?:for|on|to)\b',
]

# Strong general knowledge signals that override personal exclusions.
# These catch factual questions (e.g. "How much protein should I eat per day?")
# that would otherwise be blocked by broad exclusion patterns like "\bshould\s+i\b".
GENERAL_KNOWLEDGE_OVERRIDES = [
    r'\bhow\s+(?:much|many)\b.*\bper\s+(?:day|week|meal|serving)\b',
]

# Patterns that should NOT trigger general knowledge (personal data queries)
PERSONAL_DATA_EXCLUSIONS = [
    r'\bmy\s+(?:weight|sleep|mood|steps|glucose|blood|heart|calories|macros|fasting|workout|habit|goal|prayer|journal)\b',
    r'\bhow\s+(?:much|many|long)\s+(?:did|have)\s+i\b',
    r'\b(?:log|track|record|add|save|create|start|end|complete|undo|edit)\b',
    r'\bwhat\s+did\s+i\b',
    r'\bshow\s+me\s+my\b',
    r'\blast\s+(?:time|week|month|entry|workout|meal|fast|prayer|journal)\b',
    # v5: Personal advice / CoS-addressed questions must go through CoS pipeline
    r'\bmy\s+(?:day|schedule|priorities|life|routine|focus|habits?)\b',
    r'\bfor\s+(?:me|today|this\s+week|this\s+month)\b',
    r'\bshould\s+i\b',
    r'\bstructure\s+my\b',
    r'\bprioritize\b',
    r'\bfocus\s+on\b',
    r'\bimprove\s+my\b',
    r'\bbased\s+on\s+my\b',
    r'\bam\s+i\s+on\s+track\b',
    r'\bmy\s+(?:size|height|body)\b',
    r'\bsomeone\s+my\s+size\b',
    r'\bencourage\s+me\b',
    r'\bremind\s+me\b',
    r'\bhow\s+are\s+you\b',
    r'\bchief\s+of\s+staff\b',
    r'\bbiggest\s+(?:impact|improvement|difference)\b',
    r'\bhighest\s+impact\b',
    r'\bsingle\s+habit\b',
    r'\bwhat\s+(?:habit|metric|health\s+metric)\s+should\b',
    r'\bstart\s+tracking\b',
    r'\bhow\s+(?:should|do)\s+i\b.*\btoday\b',
]


def needs_web_search(message: str) -> bool:
    """
    Check if a message requires web search or external knowledge.

    Args:
        message: User's message

    Returns:
        True if web search or general knowledge would help answer
    """
    message_lower = message.lower()

    # Pre-check: Strong general knowledge signals override exclusions
    for pattern in GENERAL_KNOWLEDGE_OVERRIDES:
        if re.search(pattern, message_lower):
            return True

    # Check if this is a personal data query — those go to data handlers
    for pattern in PERSONAL_DATA_EXCLUSIONS:
        if re.search(pattern, message_lower):
            return False

    # Check weather patterns
    for pattern in WEB_SEARCH_PATTERNS:
        if re.search(pattern, message_lower):
            return True

    # Check general knowledge patterns
    for pattern in GENERAL_KNOWLEDGE_PATTERNS:
        if re.search(pattern, message_lower):
            return True

    return False


def get_query_type(message: str) -> str:
    """
    Classify a query as 'weather', 'general_knowledge', or 'unknown'.

    Args:
        message: User's message

    Returns:
        Query type string
    """
    message_lower = message.lower()

    if re.search(r'\bweather\b|\bforecast\b|\btemperature\b|\boutside\b', message_lower):
        return 'weather'

    for pattern in GENERAL_KNOWLEDGE_PATTERNS:
        if re.search(pattern, message_lower):
            return 'general_knowledge'

    return 'unknown'


def search_web(query: str, user_location: str = None) -> Optional[str]:
    """
    Search the web for real-time information or general knowledge.

    Routes to appropriate service based on query type:
    - Weather queries -> Open-Meteo API
    - General knowledge -> OpenAI focused factual response
    - Other queries -> None (falls through to main CoS conversation)

    Args:
        query: The search query / user's question
        user_location: Optional location context (city, state)

    Returns:
        Search result as formatted text, or None if search failed
    """
    query_type = get_query_type(query)

    if query_type == 'weather':
        return get_weather(query, user_location)

    if query_type == 'general_knowledge':
        return get_general_knowledge(query)

    return None


def get_general_knowledge(query: str) -> Optional[str]:
    """
    Answer a general knowledge question using OpenAI with a focused prompt.

    Uses a lightweight, fast call with a minimal system prompt focused on
    factual accuracy. Keeps responses concise and helpful.

    Args:
        query: The user's general knowledge question

    Returns:
        Formatted answer string, or None on failure
    """
    try:
        from openai import OpenAI
        from django.conf import settings

        client = OpenAI(api_key=settings.OPENAI_API_KEY)

        response = client.chat.completions.create(
            model=settings.OPENAI_MODEL,
            messages=[
                {
                    "role": "system",
                    "content": GENERAL_KNOWLEDGE_SYSTEM_PROMPT,
                },
                {
                    "role": "user",
                    "content": query,
                },
            ],
            temperature=0.3,
            max_tokens=600,
        )

        answer = response.choices[0].message.content
        if answer:
            return answer.strip()

        return None

    except Exception as e:
        logger.error(f"General knowledge query failed: {e}")
        return None


GENERAL_KNOWLEDGE_SYSTEM_PROMPT = """You are a knowledgeable assistant integrated into Whole Life Journey, a personal life management platform. Answer the user's question concisely and accurately.

Guidelines:
- Be factual and concise. Aim for 2-4 sentences unless the topic needs more detail.
- For health/nutrition/fitness questions, provide evidence-based information.
- For Bible/faith questions, reference specific scripture when relevant.
- For recipes or how-to questions, give clear, actionable steps.
- If the question is about a medical condition or medication, include a note to consult a healthcare provider.
- Never invent facts. If you're unsure, say so.
- Format for readability: use bullet points for lists, bold for key terms.
- Do NOT ask follow-up questions. Just answer what was asked.
"""


def get_weather(query: str, user_location: str = None) -> Optional[str]:
    """
    Get weather information using Open-Meteo API (free, no API key needed).

    Args:
        query: User's weather question
        user_location: City name like "Maryville, TN"

    Returns:
        Formatted weather response
    """
    # Extract location from query or use default
    location = _extract_location(query) or user_location

    if not location:
        return (
            "I'd be happy to get the weather for you! "
            "What city would you like the weather for? "
            "You can also set your location in your profile settings."
        )

    try:
        # First, geocode the location to get coordinates
        coords = _geocode_location(location)
        if not coords:
            return f"I couldn't find the location '{location}'. Could you try a different city name?"

        lat, lon, place_name = coords

        # Get weather data from Open-Meteo
        weather_url = (
            f"https://api.open-meteo.com/v1/forecast?"
            f"latitude={lat}&longitude={lon}"
            f"&current=temperature_2m,relative_humidity_2m,weather_code,wind_speed_10m"
            f"&daily=weather_code,temperature_2m_max,temperature_2m_min,precipitation_probability_max"
            f"&temperature_unit=fahrenheit"
            f"&wind_speed_unit=mph"
            f"&timezone=auto"
            f"&forecast_days=3"
        )

        response = requests.get(weather_url, timeout=10)
        response.raise_for_status()
        data = response.json()

        return _format_weather_response(data, place_name)

    except requests.RequestException as e:
        logger.error(f"Weather API request failed: {e}")
        return "I'm having trouble getting weather data right now. Please try again in a moment."
    except Exception as e:
        logger.error(f"Weather processing error: {e}")
        return "Something went wrong getting the weather. Please try again."


def _geocode_location(location: str) -> Optional[tuple]:
    """
    Convert location name to coordinates using Open-Meteo geocoding.

    Returns:
        Tuple of (latitude, longitude, display_name) or None
    """
    try:
        # Use Open-Meteo's geocoding API
        geocode_url = f"https://geocoding-api.open-meteo.com/v1/search?name={requests.utils.quote(location)}&count=1&language=en&format=json"

        response = requests.get(geocode_url, timeout=10)
        response.raise_for_status()
        data = response.json()

        if data.get('results'):
            result = data['results'][0]
            display_name = result.get('name', location)
            if result.get('admin1'):  # State/province
                display_name += f", {result['admin1']}"
            return (result['latitude'], result['longitude'], display_name)

        return None

    except Exception as e:
        logger.error(f"Geocoding failed: {e}")
        return None


def _extract_location(query: str) -> Optional[str]:
    """
    Extract location from a weather query.

    Examples:
        "what's the weather in maryville, tn" -> "maryville, tn"
        "weather for nashville" -> "nashville"
        "nashville weather" -> "nashville"
        "what is the weather" -> None (no location specified)
    """
    query_lower = query.lower()

    # Pattern: "weather in/for/at [location]"
    match = re.search(r'weather\s+(?:in|for|at)\s+([a-zA-Z\s,]+?)(?:\?|$)', query_lower)
    if match:
        return match.group(1).strip()

    # Pattern: "[location] weather" - but NOT common question words
    # Exclude question starters like "what", "how", "what's", "is the", etc.
    question_words = {'what', 'whats', "what's", 'how', 'is', 'the', 'today', 'tomorrow', 'current', 'my'}
    match = re.search(r'^([a-zA-Z\s,]+?)\s+weather', query_lower)
    if match:
        potential_location = match.group(1).strip()
        # Check if this looks like a real location (not question words)
        words = set(potential_location.lower().split())
        if not words.issubset(question_words) and len(potential_location) > 2:
            return potential_location

    return None


def _format_weather_response(data: Dict[str, Any], location: str) -> str:
    """
    Format weather data into a conversational response.

    Args:
        data: Weather data from Open-Meteo API
        location: Display name for location

    Returns:
        Formatted weather string
    """
    try:
        current = data.get('current', {})
        daily = data.get('daily', {})

        # Current conditions
        temp = current.get('temperature_2m')
        humidity = current.get('relative_humidity_2m')
        wind = current.get('wind_speed_10m')
        weather_code = current.get('weather_code', 0)
        condition = _weather_code_to_text(weather_code)

        # Build response
        lines = [f"Here's the weather for {location}:"]

        # Current
        lines.append(f"\nRight now: {condition}, {temp:.0f}°F")
        if humidity:
            lines.append(f"Humidity: {humidity}%")
        if wind:
            lines.append(f"Wind: {wind:.0f} mph")

        # Today's forecast
        if daily.get('temperature_2m_max'):
            high = daily['temperature_2m_max'][0]
            low = daily['temperature_2m_min'][0]
            precip = daily.get('precipitation_probability_max', [0])[0]
            lines.append(f"\nToday: High {high:.0f}°F, Low {low:.0f}°F")
            if precip and precip > 20:
                lines.append(f"Chance of precipitation: {precip}%")

        # Tomorrow
        if len(daily.get('temperature_2m_max', [])) > 1:
            high = daily['temperature_2m_max'][1]
            low = daily['temperature_2m_min'][1]
            code = daily.get('weather_code', [0, 0])[1]
            cond = _weather_code_to_text(code)
            lines.append(f"\nTomorrow: {cond}, High {high:.0f}°F, Low {low:.0f}°F")

        return '\n'.join(lines)

    except Exception as e:
        logger.error(f"Error formatting weather: {e}")
        return f"Got weather data for {location} but had trouble formatting it."


def _weather_code_to_text(code: int) -> str:
    """Convert WMO weather code to human-readable text."""
    codes = {
        0: "Clear sky",
        1: "Mainly clear",
        2: "Partly cloudy",
        3: "Overcast",
        45: "Foggy",
        48: "Depositing rime fog",
        51: "Light drizzle",
        53: "Moderate drizzle",
        55: "Dense drizzle",
        61: "Slight rain",
        63: "Moderate rain",
        65: "Heavy rain",
        66: "Light freezing rain",
        67: "Heavy freezing rain",
        71: "Slight snow",
        73: "Moderate snow",
        75: "Heavy snow",
        77: "Snow grains",
        80: "Slight rain showers",
        81: "Moderate rain showers",
        82: "Violent rain showers",
        85: "Slight snow showers",
        86: "Heavy snow showers",
        95: "Thunderstorm",
        96: "Thunderstorm with slight hail",
        99: "Thunderstorm with heavy hail",
    }
    return codes.get(code, "Unknown conditions")


def get_user_location(user) -> Optional[str]:
    """
    Get user's location from their preferences.

    Args:
        user: User model instance

    Returns:
        Location string like "Maryville, TN" or None
    """
    try:
        prefs = user.preferences
        city = getattr(prefs, 'location_city', None)
        if city:
            return city
        return None
    except Exception:
        return None
