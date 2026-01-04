# ==============================================================================
# File: apps/core/security_logging.py
# Project: Whole Life Journey - Django 5.x Personal Wellness/Journaling App
# Description: Security event logging utilities for error notifications and
#              security monitoring. Integrates with Django's logging and email
#              to notify admins of security events and errors.
# Owner: Danny Jenkins (dannyjenkins71@gmail.com)
# Created: 2026-01-03
# Last Updated: 2026-01-03
# ==============================================================================
"""
Security Logging Utilities

Provides centralized logging for security-related events including:
- Authentication failures and suspicious login patterns
- Rate limiting triggers (via django-axes)
- Signup fraud detection (honeypot, reCAPTCHA)
- CSRF failures
- Permission/authorization errors
- Management command failures (nightly jobs)

Usage:
    from apps.core.security_logging import security_logger, log_security_event

    # Simple logging
    security_logger.warning("Suspicious login attempt from %s", ip_address)

    # Structured event logging
    log_security_event(
        event_type='login_failure',
        severity='warning',
        message='Multiple failed login attempts',
        details={'ip': ip_address, 'attempts': 5}
    )

All errors (severity='error' or 'critical') are automatically emailed to admins
when DEBUG=False and SMTP is configured.
"""

import logging
from typing import Any, Optional

from django.conf import settings
from django.core.mail import mail_admins
from django.utils import timezone


# Get the security logger configured in settings.py
security_logger = logging.getLogger('wlj.security')


# Event types for categorization and filtering
EVENT_TYPES = {
    'login_failure': 'Authentication failure',
    'login_lockout': 'Account locked due to failed attempts',
    'signup_blocked': 'Signup blocked (honeypot/fraud detection)',
    'rate_limit': 'Rate limit exceeded',
    'csrf_failure': 'CSRF validation failed',
    'permission_denied': 'Unauthorized access attempt',
    'data_breach_attempt': 'Potential data breach attempt',
    'command_failure': 'Management command failed',
    'job_failure': 'Scheduled job failed',
    'api_error': 'API integration error',
    'vulnerability_scan': 'Potential vulnerability scan detected',
    'bot_activity': 'Bot activity detected',
}


def log_security_event(
    event_type: str,
    severity: str = 'warning',
    message: str = '',
    details: Optional[dict[str, Any]] = None,
    request: Optional[Any] = None,
    user: Optional[Any] = None,
    notify_immediately: bool = False,
) -> None:
    """
    Log a security event with structured data.

    Args:
        event_type: Type of security event (see EVENT_TYPES)
        severity: Log level - 'info', 'warning', 'error', 'critical'
        message: Human-readable description of the event
        details: Additional context (IP, user agent, etc.)
        request: Optional HTTP request object
        user: Optional User object
        notify_immediately: Send email immediately even for warnings

    Notes:
        - Errors and critical events are always emailed to ADMINS
        - Warnings can be emailed if notify_immediately=True
        - All events are logged to logs/security.log
    """
    details = details or {}

    # Extract request details if available
    if request:
        details['ip'] = _get_client_ip(request)
        details['user_agent'] = request.META.get('HTTP_USER_AGENT', '')[:200]
        details['path'] = request.path
        details['method'] = request.method

    # Add user info if available
    if user and hasattr(user, 'email'):
        details['user_email'] = user.email
        details['user_id'] = user.id

    # Add timestamp
    details['timestamp'] = timezone.now().isoformat()

    # Build log message
    event_label = EVENT_TYPES.get(event_type, event_type)
    full_message = f"[{event_label}] {message}"

    # Add details to message for logging
    if details:
        details_str = ', '.join(f"{k}={v}" for k, v in details.items() if v)
        full_message = f"{full_message} | {details_str}"

    # Log at appropriate level
    log_level = getattr(logging, severity.upper(), logging.WARNING)
    security_logger.log(log_level, full_message)

    # Send immediate notification for errors/critical or if requested
    if (severity in ('error', 'critical') or notify_immediately) and not settings.DEBUG:
        _send_security_notification(event_type, severity, message, details)


def log_command_error(
    command_name: str,
    error: Exception,
    context: Optional[dict[str, Any]] = None,
) -> None:
    """
    Log a management command or scheduled job error.

    This ensures nightly jobs and scheduled tasks report errors via email.

    Args:
        command_name: Name of the management command or job
        error: The exception that occurred
        context: Additional context about what the command was doing
    """
    context = context or {}
    context['command'] = command_name
    context['error_type'] = type(error).__name__
    context['error_message'] = str(error)

    log_security_event(
        event_type='command_failure',
        severity='error',
        message=f"Management command '{command_name}' failed: {error}",
        details=context,
    )


def log_job_error(
    job_name: str,
    error: Exception,
    context: Optional[dict[str, Any]] = None,
) -> None:
    """
    Log a scheduled job error (APScheduler, cron, etc.).

    Args:
        job_name: Name of the scheduled job
        error: The exception that occurred
        context: Additional context
    """
    context = context or {}
    context['job'] = job_name
    context['error_type'] = type(error).__name__
    context['error_message'] = str(error)

    log_security_event(
        event_type='job_failure',
        severity='error',
        message=f"Scheduled job '{job_name}' failed: {error}",
        details=context,
    )


def log_api_error(
    api_name: str,
    error: Exception,
    context: Optional[dict[str, Any]] = None,
) -> None:
    """
    Log a third-party API integration error.

    Args:
        api_name: Name of the API (OpenAI, Cloudinary, Plaid, etc.)
        error: The exception that occurred
        context: Additional context (endpoint, request details, etc.)
    """
    context = context or {}
    context['api'] = api_name
    context['error_type'] = type(error).__name__
    context['error_message'] = str(error)

    log_security_event(
        event_type='api_error',
        severity='error',
        message=f"API error with '{api_name}': {error}",
        details=context,
    )


def _get_client_ip(request) -> str:
    """Extract client IP from request, handling proxies."""
    x_forwarded_for = request.META.get('HTTP_X_FORWARDED_FOR')
    if x_forwarded_for:
        return x_forwarded_for.split(',')[0].strip()
    return request.META.get('REMOTE_ADDR', 'unknown')


def _send_security_notification(
    event_type: str,
    severity: str,
    message: str,
    details: dict[str, Any],
) -> None:
    """
    Send email notification to admins for security events.

    Only sends in production when SMTP is configured.
    """
    try:
        event_label = EVENT_TYPES.get(event_type, event_type)
        subject = f"[WLJ {severity.upper()}] {event_label}"

        # Build email body
        body_lines = [
            f"Security Event: {event_label}",
            f"Severity: {severity.upper()}",
            f"Message: {message}",
            "",
            "Details:",
        ]

        for key, value in details.items():
            body_lines.append(f"  {key}: {value}")

        body_lines.extend([
            "",
            "---",
            "This is an automated security notification from Whole Life Journey.",
            f"Environment: {'Development' if settings.DEBUG else 'Production'}",
        ])

        body = '\n'.join(body_lines)

        # Use Django's mail_admins which respects ADMINS setting
        mail_admins(
            subject=subject,
            message=body,
            fail_silently=True,  # Don't crash if email fails
        )

    except Exception as e:
        # Log failure but don't propagate - we don't want email failures
        # to break the application
        security_logger.error(
            "Failed to send security notification email: %s", e
        )
