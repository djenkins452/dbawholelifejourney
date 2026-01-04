# ==============================================================================
# File: services.py
# Project: Whole Life Journey - Django 5.x Personal Wellness/Journaling App
# Description: Service classes for user-related operations including reCAPTCHA
#              verification for bot detection during signup
# Owner: Danny Jenkins (dannyjenkins71@gmail.com)
# Created: 2026-01-03
# Last Updated: 2026-01-03
# ==============================================================================

"""
User Services Module

Contains service classes for:
- RecaptchaService: Verifies reCAPTCHA v3 tokens with Google's API
"""

import logging
from dataclasses import dataclass
from typing import Optional

import requests
from django.conf import settings

logger = logging.getLogger(__name__)


@dataclass
class RecaptchaResult:
    """Result of reCAPTCHA verification."""

    success: bool
    score: Optional[float] = None
    action: Optional[str] = None
    error_codes: Optional[list] = None

    @property
    def is_human(self) -> bool:
        """Check if score meets threshold for human classification."""
        if not self.success or self.score is None:
            return False
        return self.score >= settings.RECAPTCHA_SCORE_THRESHOLD


class RecaptchaService:
    """
    Service for verifying reCAPTCHA v3 tokens.

    reCAPTCHA v3 returns a score (0.0-1.0) indicating likelihood of human:
    - 1.0: Very likely human
    - 0.0: Very likely bot

    The threshold for blocking is configured via RECAPTCHA_SCORE_THRESHOLD.

    Usage:
        service = RecaptchaService()
        result = service.verify(token, client_ip)
        if result.success:
            print(f"Score: {result.score}")
    """

    VERIFY_URL = "https://www.google.com/recaptcha/api/siteverify"
    TIMEOUT_SECONDS = 5

    def __init__(self):
        self.secret_key = settings.RECAPTCHA_V3_SECRET_KEY

    def verify(self, token: str, remote_ip: Optional[str] = None) -> RecaptchaResult:
        """
        Verify a reCAPTCHA v3 token with Google's API.

        Args:
            token: The reCAPTCHA token from the frontend
            remote_ip: Optional client IP address for additional security

        Returns:
            RecaptchaResult with success status and score
        """
        if not self.secret_key:
            logger.warning("reCAPTCHA secret key not configured")
            return RecaptchaResult(
                success=False,
                error_codes=["missing-secret-key"],
            )

        if not token:
            logger.warning("Empty reCAPTCHA token received")
            return RecaptchaResult(
                success=False,
                error_codes=["missing-input-response"],
            )

        try:
            payload = {
                "secret": self.secret_key,
                "response": token,
            }
            if remote_ip:
                payload["remoteip"] = remote_ip

            response = requests.post(
                self.VERIFY_URL,
                data=payload,
                timeout=self.TIMEOUT_SECONDS,
            )
            response.raise_for_status()
            data = response.json()

            return RecaptchaResult(
                success=data.get("success", False),
                score=data.get("score"),
                action=data.get("action"),
                error_codes=data.get("error-codes"),
            )

        except requests.Timeout:
            logger.error("reCAPTCHA verification timed out")
            return RecaptchaResult(
                success=False,
                error_codes=["timeout"],
            )
        except requests.RequestException as e:
            logger.error("reCAPTCHA verification failed: %s", e)
            return RecaptchaResult(
                success=False,
                error_codes=["request-failed"],
            )
        except Exception as e:
            logger.error("Unexpected error during reCAPTCHA verification: %s", e)
            return RecaptchaResult(
                success=False,
                error_codes=["unknown-error"],
            )
