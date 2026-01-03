# ==============================================================================
# File: security.py
# Project: Whole Life Journey - Django 5.x Personal Wellness/Journaling App
# Description: Security utility functions for hashing PII (email, IP, fingerprint)
#              for privacy-preserving storage in signup fraud detection
# Owner: Danny Jenkins (dannyjenkins71@gmail.com)
# Created: 2026-01-03
# Last Updated: 2026-01-03
# ==============================================================================

"""
Security hash functions for privacy-preserving PII storage.

These functions create one-way hashes of personally identifiable information (PII)
to enable fraud detection and rate limiting without storing raw PII data.

Privacy Rationale:
    - Raw emails, IPs, and device fingerprints are sensitive personal data
    - Hashing allows matching patterns (e.g., same email across attempts) without
      storing the actual values
    - Uses Django's SECRET_KEY as salt to ensure hashes are site-specific
    - SHA-256 provides strong cryptographic security

Usage:
    from apps.users.security import hash_email, hash_ip, hash_fingerprint

    email_hash = hash_email("user@example.com")
    ip_hash = hash_ip("192.168.1.1")
    fp_hash = hash_fingerprint({"browser": "Chrome", "os": "Windows"})
"""

import hashlib
import json

from django.conf import settings


def _get_salt() -> bytes:
    """
    Get the salt for hashing operations.

    Uses Django's SECRET_KEY to ensure hashes are site-specific and cannot
    be matched across different installations.

    Returns:
        bytes: The salt value encoded as UTF-8 bytes.
    """
    return settings.SECRET_KEY.encode("utf-8")


def hash_email(email: str) -> str:
    """
    Create a privacy-preserving hash of an email address.

    The email is normalized (lowercase, stripped) before hashing to ensure
    consistent matching across different case variations.

    Args:
        email: The email address to hash.

    Returns:
        A 64-character hexadecimal SHA-256 hash of the salted email.

    Example:
        >>> hash_email("User@Example.com")
        'a1b2c3d4...'  # 64-char hex string
        >>> hash_email("user@example.com")
        'a1b2c3d4...'  # Same hash (normalized)
    """
    if not email:
        return ""

    # Normalize email: lowercase and strip whitespace
    normalized_email = email.lower().strip()

    # Create salted hash
    salted_value = _get_salt() + normalized_email.encode("utf-8")
    return hashlib.sha256(salted_value).hexdigest()


def hash_ip(ip_address: str) -> str:
    """
    Create a privacy-preserving hash of an IP address.

    Args:
        ip_address: The IP address to hash (IPv4 or IPv6).

    Returns:
        A 64-character hexadecimal SHA-256 hash of the salted IP address.

    Example:
        >>> hash_ip("192.168.1.1")
        'e5f6g7h8...'  # 64-char hex string
    """
    if not ip_address:
        return ""

    # Normalize: strip whitespace
    normalized_ip = ip_address.strip()

    # Create salted hash
    salted_value = _get_salt() + normalized_ip.encode("utf-8")
    return hashlib.sha256(salted_value).hexdigest()


def hash_fingerprint(fingerprint_data: dict) -> str:
    """
    Create a privacy-preserving hash of device fingerprint data.

    The fingerprint dictionary is serialized to JSON with sorted keys to ensure
    consistent hashing regardless of key order.

    Args:
        fingerprint_data: Dictionary containing device fingerprint attributes
                          (e.g., browser, OS, screen size, plugins).

    Returns:
        A 64-character hexadecimal SHA-256 hash of the salted fingerprint.

    Example:
        >>> hash_fingerprint({"browser": "Chrome", "os": "Windows"})
        'i9j0k1l2...'  # 64-char hex string
        >>> hash_fingerprint({"os": "Windows", "browser": "Chrome"})
        'i9j0k1l2...'  # Same hash (sorted keys)
    """
    if not fingerprint_data:
        return ""

    # Serialize with sorted keys for consistent ordering
    normalized_data = json.dumps(fingerprint_data, sort_keys=True)

    # Create salted hash
    salted_value = _get_salt() + normalized_data.encode("utf-8")
    return hashlib.sha256(salted_value).hexdigest()
