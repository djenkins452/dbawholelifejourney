# ==============================================================================
# File: adapters.py
# Project: Whole Life Journey - Django 5.x Personal Wellness/Journaling App
# Description: Custom allauth adapter for signup security features including
#              honeypot validation, reCAPTCHA verification, and signup attempt logging
# Owner: Danny Jenkins (admin@wholelifejourney.com)
# Created: 2026-01-03
# Last Updated: 2026-01-06
# ==============================================================================

"""
Custom Account Adapter for Whole Life Journey

Extends django-allauth's DefaultAccountAdapter to add:
- Honeypot field validation to block bots
- reCAPTCHA v3 token verification and score logging
- SignupAttempt logging for fraud detection
- Integration with security hash functions
- Admin email bypass for email verification

The adapter is registered in settings.py via ACCOUNT_ADAPTER.
"""

# Admin emails that bypass email verification requirement.
# These accounts can always log in even if email verification is mandatory.
ADMIN_BYPASS_EMAILS = {
    "dannyjenkins71@gmail.com",
    "admin@wholelifejourney.com",
}

import logging

from allauth.account.adapter import DefaultAccountAdapter
from django.core.exceptions import ValidationError

from apps.core.security_logging import log_security_event
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
    - Admin email bypass for email verification
    """

    def is_email_verified(self, request, email):
        """
        Check if an email address should be considered verified.

        Admin emails in ADMIN_BYPASS_EMAILS are always considered verified,
        allowing them to log in even when ACCOUNT_EMAIL_VERIFICATION is mandatory.
        This prevents admin lockout if email delivery fails.

        Args:
            request: The HTTP request
            email: The email address to check

        Returns:
            True if the email is in the bypass list, otherwise defers to parent.
        """
        if email and email.lower() in ADMIN_BYPASS_EMAILS:
            logger.info("Admin bypass: treating %s as verified", email)
            return True
        return super().is_email_verified(request, email)

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
        Save user, log signup attempt, and process referral.

        reCAPTCHA validation is now done in CustomSignupForm.clean() to ensure
        low scores result in form validation errors (not unhandled exceptions
        that trigger Django error emails).

        Also captures referral code from session if present.
        """
        self.request = request

        # Get reCAPTCHA score from form (validated in form.clean())
        # or verify it here if form didn't do it (fallback for non-CustomSignupForm)
        captcha_score = getattr(form, '_recaptcha_score', None)
        if captcha_score is None:
            # Form didn't validate reCAPTCHA, do it here (legacy path)
            captcha_score = self._verify_recaptcha(request)

        # Save user via parent
        user = super().save_user(request, user, form, commit)

        # Log successful signup attempt with captcha score
        self._log_signup_attempt(request, user.email, captcha_score)

        # Process referral code from session
        self._process_referral(request, user)

        return user

    def _process_referral(self, request, user):
        """
        Process referral code from session after signup.

        Links the new user to their referrer if a valid referral code
        was captured during registration.
        """
        try:
            referral_code = request.session.get('referral_code')
            if not referral_code:
                return

            from apps.billing.models import BillingProfile, ReferralReward, ReferralQualification
            from datetime import timedelta
            from django.utils import timezone

            # Find the referrer
            try:
                referrer_profile = BillingProfile.objects.get(referral_code=referral_code)
                referrer = referrer_profile.user
            except BillingProfile.DoesNotExist:
                logger.warning(f"Invalid referral code at signup: {referral_code}")
                return

            # Get the new user's billing profile
            try:
                user_profile = user.billing_profile
            except BillingProfile.DoesNotExist:
                # Profile should be created by signal, but handle edge case
                user_profile = BillingProfile.objects.create(user=user)

            # Link the referral
            user_profile.referred_by = referrer
            user_profile.save(update_fields=['referred_by', 'updated_at'])

            # Create ReferralReward record
            ReferralReward.objects.get_or_create(
                referrer=referrer,
                referred_user=user,
                defaults={
                    'signup_date': timezone.now().date(),
                }
            )

            # If referrer is Founding Member, create qualification tracking
            if referrer_profile.is_founding_member:
                ReferralQualification.objects.get_or_create(
                    referrer=referrer,
                    referred_user=user,
                    defaults={
                        'signup_date': timezone.now().date(),
                        'qualified_date': timezone.now().date() + timedelta(days=90),
                    }
                )

            logger.info(f"Referral recorded at signup: {referrer.email} referred {user.email}")

            # Clear the referral code from session
            del request.session['referral_code']

        except Exception as e:
            # Don't let referral processing break signup
            logger.error(f"Error processing referral at signup: {e}")

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

            # Send security notification for bot detection
            log_security_event(
                event_type='bot_activity',
                severity='warning',
                message='Bot signup blocked via honeypot',
                request=request,
                details={'email_provided': bool(email)},
            )
        except Exception as e:
            # Don't let logging failures break signup
            logger.error("Failed to log honeypot block: %s", e)

    def _log_blocked_signup(self, request, email, captcha_score, block_reason):
        """
        Log a blocked signup attempt to SignupAttempt model.

        Args:
            request: The HTTP request
            email: Email address (may be None)
            captcha_score: The reCAPTCHA score that triggered the block
            block_reason: Reason for blocking (e.g., 'low_recaptcha_score')
        """
        try:
            ip = get_client_ip(request)
            user_agent = request.META.get("HTTP_USER_AGENT", "")[:500]

            SignupAttempt.objects.create(
                email_hash=hash_email(email) if email else "",
                ip_hash=hash_ip(ip),
                user_agent=user_agent,
                status="blocked",
                block_reason=block_reason,
                risk_level="high",
                captcha_score=captcha_score,
            )
            logger.warning(
                "Signup blocked - reason: %s, captcha_score: %s",
                block_reason,
                captcha_score,
            )
        except Exception as e:
            # Don't let logging failures break signup
            logger.error("Failed to log blocked signup: %s", e)
