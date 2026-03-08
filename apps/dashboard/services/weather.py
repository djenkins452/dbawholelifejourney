# ==============================================================================
# File: weather.py
# Project: Whole Life Journey - Django 5.x Personal Wellness/Journaling App
# Description: Weather service for dashboard widget using Open-Meteo API
# Owner: Danny Jenkins (admin@wholelifejourney.com)
# Created: 2026-01-19
# ==============================================================================
"""
Weather Service for Dashboard

Fetches weather data from Open-Meteo API (free, no API key needed) and
detects extreme weather conditions to alert users.
"""
import logging
from dataclasses import dataclass, field
from typing import Optional
import requests
from django.core.cache import cache

logger = logging.getLogger(__name__)

# Cache settings
WEATHER_CACHE_TTL = 3600  # 1 hour (reduced API calls)
GEOCODE_CACHE_TTL = 86400  # 24 hours (locations don't change)
RATE_LIMIT_BACKOFF_TTL = 300  # 5 minutes backoff on rate limit

# Extreme weather thresholds
EXTREME_HEAT_THRESHOLD = 100  # Fahrenheit
EXTREME_COLD_THRESHOLD = 20  # Fahrenheit
HIGH_WIND_THRESHOLD = 30  # mph

# Severe weather codes (WMO standard)
SEVERE_WEATHER_CODES = {
    65: "Heavy rain",
    67: "Heavy freezing rain",
    75: "Heavy snow",
    82: "Violent rain showers",
    86: "Heavy snow showers",
    95: "Thunderstorm",
    96: "Thunderstorm with hail",
    99: "Severe thunderstorm with hail",
}

# All weather codes for display
WEATHER_CODES = {
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


@dataclass
class ForecastDay:
    """Single day forecast data."""

    date: str
    day_name: str
    high: float
    low: float
    condition: str
    weather_code: int
    precip_chance: int


@dataclass
class WeatherData:
    """Weather data for dashboard display."""

    location: str
    current_temp: float
    current_condition: str
    current_code: int
    humidity: int
    wind_speed: float
    forecast: list[ForecastDay] = field(default_factory=list)
    alerts: list[str] = field(default_factory=list)

    @property
    def has_alerts(self) -> bool:
        """Check if there are any weather alerts."""
        return len(self.alerts) > 0

    def to_dict(self) -> dict:
        """Convert to dictionary for template context."""
        return {
            "location": self.location,
            "current_temp": self.current_temp,
            "current_condition": self.current_condition,
            "current_code": self.current_code,
            "humidity": self.humidity,
            "wind_speed": self.wind_speed,
            "forecast": [
                {
                    "date": f.date,
                    "day_name": f.day_name,
                    "high": f.high,
                    "low": f.low,
                    "condition": f.condition,
                    "weather_code": f.weather_code,
                    "precip_chance": f.precip_chance,
                }
                for f in self.forecast
            ],
            "alerts": self.alerts,
            "has_alerts": self.has_alerts,
        }


class WeatherService:
    """Service for fetching weather data from Open-Meteo API."""

    GEOCODE_URL = "https://geocoding-api.open-meteo.com/v1/search"
    WEATHER_URL = "https://api.open-meteo.com/v1/forecast"
    TIMEOUT = 3  # seconds — bounded for dashboard <1s target

    def get_weather_data(self, city: str) -> Optional[WeatherData]:
        """
        Fetch weather data for a city.

        Args:
            city: City name (e.g., "Maryville, TN" or "Nashville")

        Returns:
            WeatherData object or None if fetch failed
        """
        if not city:
            return None

        # Check if we're rate limited (backoff mode)
        if cache.get("weather_rate_limited"):
            logger.debug("Weather API in backoff mode, skipping request")
            return None

        # Check cache first
        cache_key = f"dashboard_weather_{city.lower().replace(' ', '_')}"
        cached = cache.get(cache_key)
        if cached:
            return cached

        try:
            # Geocode the city
            coords = self._geocode_location(city)
            if not coords:
                logger.warning(f"Could not geocode location: {city}")
                return None

            lat, lon, location_name = coords

            # Fetch weather data
            response = requests.get(
                self.WEATHER_URL,
                params={
                    "latitude": lat,
                    "longitude": lon,
                    "current": "temperature_2m,relative_humidity_2m,weather_code,wind_speed_10m",
                    "daily": "weather_code,temperature_2m_max,temperature_2m_min,precipitation_probability_max",
                    "temperature_unit": "fahrenheit",
                    "wind_speed_unit": "mph",
                    "timezone": "auto",
                    "forecast_days": 4,  # Today + 3 days
                },
                timeout=self.TIMEOUT,
            )
            response.raise_for_status()
            data = response.json()

            # Parse the response
            weather_data = self._parse_weather_data(data, location_name)

            # Cache the result
            if weather_data:
                cache.set(cache_key, weather_data, WEATHER_CACHE_TTL)

            return weather_data

        except requests.exceptions.HTTPError as e:
            if e.response is not None and e.response.status_code == 429:
                # Rate limited - set a backoff cache to prevent hammering
                logger.warning("Weather API rate limited (429). Backing off.")
                cache.set("weather_rate_limited", True, RATE_LIMIT_BACKOFF_TTL)
            else:
                logger.error(f"Weather API HTTP error: {e}")
            return None
        except requests.RequestException as e:
            logger.error(f"Weather API request failed: {e}")
            return None
        except Exception as e:
            logger.error(f"Weather processing error: {e}")
            return None

    def _geocode_location(self, city: str) -> Optional[tuple]:
        """
        Convert city name to coordinates.

        Returns:
            Tuple of (latitude, longitude, display_name) or None
        """
        # Check geocode cache
        cache_key = f"geocode_{city.lower().replace(' ', '_')}"
        cached = cache.get(cache_key)
        if cached:
            return cached

        # Extract just the city name (Open-Meteo doesn't like "City, ST" format)
        # Handle formats like "Maryville, TN" or "Maryville, Tennessee"
        search_name = city.split(",")[0].strip()

        try:
            response = requests.get(
                self.GEOCODE_URL,
                params={
                    "name": search_name,
                    "count": 1,
                    "language": "en",
                    "format": "json",
                },
                timeout=self.TIMEOUT,
            )
            response.raise_for_status()
            data = response.json()

            if data.get("results"):
                result = data["results"][0]
                display_name = result.get("name", city)
                if result.get("admin1"):  # State/province
                    display_name += f", {result['admin1']}"

                coords = (result["latitude"], result["longitude"], display_name)
                cache.set(cache_key, coords, GEOCODE_CACHE_TTL)
                return coords

            return None

        except Exception as e:
            logger.error(f"Geocoding failed for {city}: {e}")
            return None

    def _parse_weather_data(self, data: dict, location: str) -> Optional[WeatherData]:
        """Parse Open-Meteo API response into WeatherData."""
        try:
            current = data.get("current", {})
            daily = data.get("daily", {})

            # Current conditions
            current_temp = current.get("temperature_2m", 0)
            current_code = current.get("weather_code", 0)
            humidity = current.get("relative_humidity_2m", 0)
            wind_speed = current.get("wind_speed_10m", 0)

            # Build forecast (skip today, get next 3 days)
            forecast = []
            dates = daily.get("time", [])[1:4]  # Skip today
            highs = daily.get("temperature_2m_max", [])[1:4]
            lows = daily.get("temperature_2m_min", [])[1:4]
            codes = daily.get("weather_code", [])[1:4]
            precips = daily.get("precipitation_probability_max", [])[1:4]

            from datetime import datetime

            for i, date_str in enumerate(dates):
                if i < len(highs):
                    date_obj = datetime.strptime(date_str, "%Y-%m-%d")
                    forecast.append(
                        ForecastDay(
                            date=date_str,
                            day_name=date_obj.strftime("%a"),
                            high=highs[i] if i < len(highs) else 0,
                            low=lows[i] if i < len(lows) else 0,
                            condition=WEATHER_CODES.get(
                                codes[i] if i < len(codes) else 0, "Unknown"
                            ),
                            weather_code=codes[i] if i < len(codes) else 0,
                            precip_chance=precips[i] if i < len(precips) else 0,
                        )
                    )

            # Detect extreme conditions
            alerts = self._detect_extreme_conditions(data, wind_speed)

            return WeatherData(
                location=location,
                current_temp=current_temp,
                current_condition=WEATHER_CODES.get(current_code, "Unknown"),
                current_code=current_code,
                humidity=humidity,
                wind_speed=wind_speed,
                forecast=forecast,
                alerts=alerts,
            )

        except Exception as e:
            logger.error(f"Error parsing weather data: {e}")
            return None

    def _detect_extreme_conditions(self, data: dict, current_wind: float) -> list[str]:
        """
        Detect extreme weather conditions and return alert messages.

        Checks both current conditions and forecast for the next 3 days.
        """
        alerts = []
        daily = data.get("daily", {})

        # Check temperature extremes (today and tomorrow)
        highs = daily.get("temperature_2m_max", [])[:2]
        lows = daily.get("temperature_2m_min", [])[:2]

        for i, high in enumerate(highs):
            if high and high >= EXTREME_HEAT_THRESHOLD:
                day = "Today" if i == 0 else "Tomorrow"
                alerts.append(f"Extreme heat {day.lower()}: High of {high:.0f}F")
                break  # Only show one heat alert

        for i, low in enumerate(lows):
            if low and low <= EXTREME_COLD_THRESHOLD:
                day = "Today" if i == 0 else "Tomorrow"
                alerts.append(f"Cold weather {day.lower()}: Low of {low:.0f}F")
                break  # Only show one cold alert

        # Check for high winds
        if current_wind >= HIGH_WIND_THRESHOLD:
            alerts.append(f"High winds: {current_wind:.0f} mph")

        # Check for severe weather codes (today and next 2 days)
        codes = daily.get("weather_code", [])[:3]

        for i, code in enumerate(codes):
            if code in SEVERE_WEATHER_CODES:
                condition = SEVERE_WEATHER_CODES[code]
                if i == 0:
                    alerts.append(f"{condition} expected today")
                elif i == 1:
                    alerts.append(f"{condition} expected tomorrow")
                else:
                    alerts.append(f"{condition} expected in 2 days")
                break  # Only show one severe weather alert

        return alerts


# Singleton instance
weather_service = WeatherService()
