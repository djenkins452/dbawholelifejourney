# ==============================================================================
# File: apps/users/services/geoip.py
# Project: Whole Life Journey - Django 5.x Personal Wellness/Journaling App
# Description: GeoIP service for determining country from IP address
# Owner: Danny Jenkins (admin@wholelifejourney.com)
# Created: 2026-01-26
# Last Updated: 2026-01-26
# ==============================================================================

"""
GeoIP Service Module

Provides IP geolocation functionality using ipinfo.io free tier.
Used for geo-blocking signups from non-US locations (unless whitelisted).

Features:
    - Caches results to reduce API calls (50k/month free tier limit)
    - Fails open - allows signup if geolocation service is unavailable
    - Returns country code (e.g., "US", "FR", "RU")
"""

import logging
from dataclasses import dataclass
from typing import Optional

import requests
from django.core.cache import cache

logger = logging.getLogger(__name__)


@dataclass
class GeoIPResult:
    """Result of IP geolocation lookup."""

    success: bool
    country_code: Optional[str] = None
    error: Optional[str] = None

    @property
    def is_usa(self) -> bool:
        """Check if the IP is from the United States."""
        return self.country_code == "US"


class GeoIPService:
    """
    Service for determining country from IP address.

    Uses ipinfo.io free tier (50k requests/month, HTTPS).
    Results are cached to minimize API calls.

    Usage:
        service = GeoIPService()
        result = service.get_country_from_ip("8.8.8.8")
        if result.is_usa:
            print("US-based IP")
    """

    API_URL = "https://ipinfo.io/{ip}/json"
    TIMEOUT_SECONDS = 3
    CACHE_KEY_PREFIX = "geoip:"
    CACHE_TIMEOUT = 60 * 60 * 24  # 24 hours

    def get_country_from_ip(self, ip_address: str) -> GeoIPResult:
        """
        Get the country code for an IP address.

        Args:
            ip_address: The IP address to look up (IPv4 or IPv6)

        Returns:
            GeoIPResult with country_code if successful, error if failed
        """
        if not ip_address:
            logger.warning("Empty IP address provided to GeoIPService")
            return GeoIPResult(success=False, error="empty-ip")

        # Skip geolocation for localhost/private IPs
        if self._is_private_ip(ip_address):
            # Treat private IPs as US (local development, internal networks)
            return GeoIPResult(success=True, country_code="US")

        # Check cache first
        cache_key = f"{self.CACHE_KEY_PREFIX}{ip_address}"
        cached_result = cache.get(cache_key)
        if cached_result is not None:
            return GeoIPResult(success=True, country_code=cached_result)

        try:
            response = requests.get(
                self.API_URL.format(ip=ip_address),
                timeout=self.TIMEOUT_SECONDS,
            )

            if response.status_code == 429:
                # Rate limited - fail open
                logger.warning("GeoIP rate limit reached")
                return GeoIPResult(success=False, error="rate-limited")

            response.raise_for_status()
            data = response.json()

            country_code = data.get("country", "")
            if country_code:
                # Cache the result
                cache.set(cache_key, country_code, self.CACHE_TIMEOUT)
                return GeoIPResult(success=True, country_code=country_code)

            return GeoIPResult(success=False, error="no-country-in-response")

        except requests.Timeout:
            logger.warning("GeoIP lookup timed out for IP: %s", ip_address[:20])
            return GeoIPResult(success=False, error="timeout")
        except requests.RequestException as e:
            logger.warning("GeoIP lookup failed for IP %s: %s", ip_address[:20], e)
            return GeoIPResult(success=False, error="request-failed")
        except Exception as e:
            logger.error("Unexpected error in GeoIP lookup: %s", e)
            return GeoIPResult(success=False, error="unknown-error")

    def _is_private_ip(self, ip_address: str) -> bool:
        """
        Check if an IP address is private/local.

        Private IPs include:
        - 127.0.0.0/8 (localhost)
        - 10.0.0.0/8 (private)
        - 172.16.0.0/12 (private)
        - 192.168.0.0/16 (private)
        - ::1 (IPv6 localhost)
        """
        import ipaddress

        try:
            ip = ipaddress.ip_address(ip_address)
            return ip.is_private or ip.is_loopback
        except ValueError:
            # Invalid IP format - let it fail normally
            return False


def get_country_from_ip(ip_address: str) -> Optional[str]:
    """
    Convenience function to get country code from IP.

    Returns the country code string if successful, None if failed.
    This function fails open - returns None on any error.

    Args:
        ip_address: The IP address to look up

    Returns:
        Two-letter country code (e.g., "US") or None if unavailable
    """
    service = GeoIPService()
    result = service.get_country_from_ip(ip_address)
    return result.country_code if result.success else None
