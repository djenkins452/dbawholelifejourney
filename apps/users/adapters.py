# ==============================================================================
# File: adapters.py
# Project: Whole Life Journey - Django 5.x Personal Wellness/Journaling App
# Description: Custom allauth adapter for signup security features including
#              honeypot validation, reCAPTCHA verification, and signup attempt logging
# Owner: Danny Jenkins (dannyjenkins71@gmail.com)
# Created: 2026-01-03
# Last Updated: 2026-01-03
# ==============================================================================

"""
Custom Account Adapter for Whole Life Journey

Extends django-allauth's DefaultAccountAdapter to add:
- Honeypot field validation to block bots
- reCAPTCHA v3 token verification and score logging
- SignupAttempt logging for fraud detection
- Integration with security hash functions

The adapter is registered in settings.py via ACCOUNT_ADAPTER.
"""

import logging

from allauth.account.adapter import DefaultAccountAdapter
from django.core.exceptions import ValidationError

from apps.users.models import SignupAttempt
from apps.users.security import hash_email, hash_ip
from apps.users.services import RecaptchaService

logger = logging.getLogger(__name__)


def get_client_ip(request):
    """
    Extract client IP address from request, handling proxies.

    Checks X-Forwarded-For header first (for reverse proxy setups),
    then falls back to REMOTE_ADDR.
    """
    x_forwarded_for = request.META.get("HTTP_X_FORWARDED_FOR")
    if x_forwarded_for:
        # Take the first IP in the chain (client's IP)
        ip = x_forwarded_for.split(",")[0].strip()
    else:
        ip = request.META.get("REMOTE_ADDR", "")
    return ip


class WLJAccountAdapter(DefaultAccountAdapter):
    """
    Custom account adapter with security enhancements.

    Features:
    - Honeypot field validation to detect bots
    - SignupAttempt logging for all signup attempts
    - Integration with hash functions for privacy-preserving storage
    """

    def is_open_for_signup(self, request):
        """
        Check if signup is allowed and validate honeypot field.

        This method is called before the signup form is processed.
        If the honeypot field is filled, the request is from a bot.
        """
        # Check honeypot field - bots will fill this hidden field
        honeypot_value = request.POST.get("website", "")

        if honeypot_value:
            # Log the blocked attempt
            self._log_honeypot_block(request)

            # Return False to block signup (shows "signup closed" message)
            # We'll raise a ValidationError in clean_email for better UX
            logger.warning(
                "Honeypot triggered - blocking signup attempt from IP: %s",
                get_client_ip(request),
            )

        return True  # Allow signup to proceed to form validation

    def clean_email(self, email):
        """
        Validate email and check for honeypot field.

        Raises ValidationError if honeypot is filled.
        """
        # Get the request from the adapter's context
        request = getattr(self, "request", None)

        if request:
            honeypot_value = request.POST.get("website", "")
            if honeypot_value:
                # Log the blocked attempt
                self._log_honeypot_block(request, email)
                # Raise generic error to not reveal honeypot detection
                raise ValidationError("Unable to create account. Please try again later.")

        # Call parent's clean_email for standard validation
        return super().clean_email(email)

    def pre_save(self, request, user):
        """
        Called before saving a new user.

        We override this to capture the request for honeypot checking.
        """
        self.request = request
        return super().pre_save(request, user)

    def save_user(self, request, user, form, commit=True):
        """
        Save user, verify reCAPTCHA, and log signup attempt.

        Verifies the reCAPTCHA token and logs the score to SignupAttempt.
        For TIER 1: Logs score only, does not block based on score.
        """
        self.request = request

        # Verify reCAPTCHA token and get score
        captcha_score = self._verify_recaptcha(request)

        # Save user via parent
        user = super().save_user(request, user, form, commit)

        # Log successful signup attempt with captcha score
        self._log_signup_attempt(request, user.email, captcha_score)

        return user

    def _verify_recaptcha(self, request):
        """
        Verify reCAPTCHA v3 token from the signup form.

        Returns the captcha score (0.0-1.0) or None if verification failed.
        For TIER 1: Fails open - verification failures don't block signup.
        """
        token = request.POST.get("recaptcha_token", "")
        if not token:
            logger.warning("No reCAPTCHA token in signup request")
            return None

        try:
            ip = get_client_ip(request)
            service = RecaptchaService()
            result = service.verify(token, ip)

            if result.success:
                logger.info(
                    "reCAPTCHA verified - score: %.2f, action: %s",
                    result.score or 0.0,
                    result.action,
                )
                return result.score
            else:
                logger.warning(
                    "reCAPTCHA verification failed: %s",
                    result.error_codes,
                )
                return None

        except Exception as e:
            # Fail open - don't block signup if reCAPTCHA fails
            logger.error("reCAPTCHA verification error: %s", e)
            return None

    def _log_signup_attempt(self, request, email, captcha_score):
        """
        Log a successful signup attempt to SignupAttempt model.

        Args:
            request: The HTTP request
            email: User's email address
            captcha_score: reCAPTCHA score (0.0-1.0) or None
        """
        try:
            ip = get_client_ip(request)
            user_agent = request.META.get("HTTP_USER_AGENT", "")[:500]

            SignupAttempt.objects.create(
                email_hash=hash_email(email),
                ip_hash=hash_ip(ip),
                user_agent=user_agent,
                status="completed",
                risk_level="unknown",
                captcha_score=captcha_score,
            )
            logger.info(
                "Signup attempt logged - captcha_score: %s",
                captcha_score,
            )
        except Exception as e:
            # Don't let logging failures break signup
            logger.error("Failed to log signup attempt: %s", e)

    def _log_honeypot_block(self, request, email=None):
        """
        Log a blocked signup attempt to SignupAttempt model.

        Args:
            request: The HTTP request
            email: Optional email address (may not be available)
        """
        try:
            ip = get_client_ip(request)
            user_agent = request.META.get("HTTP_USER_AGENT", "")[:500]

            SignupAttempt.objects.create(
                email_hash=hash_email(email) if email else "",
                ip_hash=hash_ip(ip),
                user_agent=user_agent,
                status="blocked",
                block_reason="honeypot",
                risk_level="high",
                risk_score=1.0,
            )
        except Exception as e:
            # Don't let logging failures break signup
            logger.error("Failed to log honeypot block: %s", e)
