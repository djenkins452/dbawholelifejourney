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
from django.conf import settings

logger = logging.getLogger(__name__)


# Patterns that indicate web search is needed
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


def needs_web_search(message: str) -> bool:
    """
    Check if a message requires web search to answer.

    Args:
        message: User's message

    Returns:
        True if web search would help answer the question
    """
    message_lower = message.lower()

    for pattern in WEB_SEARCH_PATTERNS:
        if re.search(pattern, message_lower):
            return True

    return False


def search_web(query: str, user_location: str = None) -> Optional[str]:
    """
    Search the web for real-time information.

    Routes to appropriate service based on query type:
    - Weather queries -> Open-Meteo API
    - Other queries -> helpful fallback

    Args:
        query: The search query / user's question
        user_location: Optional location context (city, state)

    Returns:
        Search result as formatted text, or None if search failed
    """
    query_lower = query.lower()

    # Route weather queries to weather API
    if re.search(r'\bweather\b|\bforecast\b|\btemperature\b|\boutside\b', query_lower):
        return get_weather(query, user_location)

    # For other queries, return helpful message
    return None


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
        return f"I'm having trouble getting weather data right now. Please try again in a moment."
    except Exception as e:
        logger.error(f"Weather processing error: {e}")
        return f"Something went wrong getting the weather. Please try again."


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
    """
    query_lower = query.lower()

    # Pattern: "weather in/for/at [location]"
    match = re.search(r'weather\s+(?:in|for|at)\s+([a-zA-Z\s,]+?)(?:\?|$)', query_lower)
    if match:
        return match.group(1).strip()

    # Pattern: "[location] weather"
    match = re.search(r'^([a-zA-Z\s,]+?)\s+weather', query_lower)
    if match:
        return match.group(1).strip()

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
