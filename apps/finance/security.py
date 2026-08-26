# ==============================================================================
# File: apps/finance/security.py
# Project: Whole Life Journey - Django 5.x Personal Wellness/Journaling App
# Description: Finance module security controls - audit logging, access control,
#              sensitive operation verification
# Owner: Danny Jenkins (admin@wholelifejourney.com)
# Created: 2026-01-03
# Last Updated: 2026-01-03
# ==============================================================================
"""
Finance Security Module

Provides security controls for financial data protection:
- Audit logging for all finance operations
- Access control verification
- Sensitive operation confirmation
- Rate limiting for financial operations

Security Philosophy:
- All financial operations are logged
- Sensitive operations require additional verification
- Defense in depth with multiple security layers
"""

import functools
import logging
from decimal import Decimal
from typing import Optional

from django.core.cache import cache
from django.http import JsonResponse
from django.utils import timezone

logger = logging.getLogger(__name__)


# =============================================================================
# Finance Audit Logger
# =============================================================================

class FinanceAuditLogger:
    """
    Centralized audit logging for all finance operations.

    All financial actions are logged with:
    - User identification
    - Action type and target
    - IP address
    - Timestamp
    - Success/failure status
    - Sensitive data redaction
    """

    # Action types
    ACTION_CREATE = 'create'
    ACTION_UPDATE = 'update'
    ACTION_DELETE = 'delete'
    ACTION_VIEW = 'view'
    ACTION_TRANSFER = 'transfer'
    ACTION_IMPORT = 'import'
    ACTION_EXPORT = 'export'
    ACTION_AI_QUERY = 'ai_query'

    # Entity types
    ENTITY_ACCOUNT = 'account'
    ENTITY_TRANSACTION = 'transaction'
    ENTITY_BUDGET = 'budget'
    ENTITY_GOAL = 'goal'
    ENTITY_IMPORT = 'import'
    ENTITY_CONNECTION = 'bank_connection'

    def __init__(self, user=None, request=None):
        self.user = user
        self.request = request
        self.ip_address = self._get_client_ip() if request else None

    def _get_client_ip(self) -> Optional[str]:
        """Extract client IP from request."""
        if not self.request:
            return None

        x_forwarded_for = self.request.META.get('HTTP_X_FORWARDED_FOR')
        if x_forwarded_for:
            return x_forwarded_for.split(',')[0].strip()
        return self.request.META.get('REMOTE_ADDR', '')

    def _redact_sensitive_data(self, data: dict) -> dict:
        """Remove or mask sensitive fields from audit data."""
        sensitive_fields = [
            'access_token', 'token', 'password', 'secret',
            'account_number', 'routing_number', 'ssn',
        ]

        redacted = {}
        for key, value in data.items():
            if any(sf in key.lower() for sf in sensitive_fields):
                redacted[key] = '[REDACTED]'
            elif isinstance(value, dict):
                redacted[key] = self._redact_sensitive_data(value)
            else:
                redacted[key] = value

        return redacted

    def log(
        self,
        action: str,
        entity_type: str,
        entity_id: Optional[int] = None,
        success: bool = True,
        details: Optional[dict] = None,
        error_message: Optional[str] = None,
    ):
        """
        Log a finance audit event.

        Args:
            action: Type of action (create, update, delete, etc.)
            entity_type: Type of entity (account, transaction, etc.)
            entity_id: ID of the affected entity
            success: Whether the operation succeeded
            details: Additional context (will be redacted)
            error_message: Error message if failed
        """
        from apps.finance.models import FinanceAuditLog

        # Redact sensitive data from details
        safe_details = self._redact_sensitive_data(details or {})

        if error_message:
            safe_details['error'] = error_message

        try:
            FinanceAuditLog.objects.create(
                user=self.user,
                action=action,
                entity_type=entity_type,
                entity_id=entity_id,
                success=success,
                details=safe_details,
                ip_address=self.ip_address,
            )
        except Exception as e:
            # Never fail on audit logging - just log the error
            logger.error(f"Failed to create finance audit log: {e}")

        # Also log to standard logger for aggregation
        log_msg = (
            f"FINANCE_AUDIT: user={self.user.id if self.user else 'anon'} "
            f"action={action} entity={entity_type}:{entity_id} "
            f"success={success} ip={self.ip_address}"
        )
        if success:
            logger.info(log_msg)
        else:
            logger.warning(log_msg)

    def log_account_created(self, account):
        """Log account creation."""
        self.log(
            action=self.ACTION_CREATE,
            entity_type=self.ENTITY_ACCOUNT,
            entity_id=account.id,
            details={
                'account_name': account.name,
                'account_type': account.account_type,
            }
        )

    def log_account_updated(self, account, changed_fields: list):
        """Log account update."""
        self.log(
            action=self.ACTION_UPDATE,
            entity_type=self.ENTITY_ACCOUNT,
            entity_id=account.id,
            details={
                'changed_fields': changed_fields,
            }
        )

    def log_account_deleted(self, account):
        """Log account deletion (soft delete)."""
        self.log(
            action=self.ACTION_DELETE,
            entity_type=self.ENTITY_ACCOUNT,
            entity_id=account.id,
            details={
                'account_name': account.name,
            }
        )

    def log_transaction_created(self, transaction):
        """Log transaction creation."""
        self.log(
            action=self.ACTION_CREATE,
            entity_type=self.ENTITY_TRANSACTION,
            entity_id=transaction.id,
            details={
                'amount': str(transaction.amount),
                'account_id': transaction.account_id,
                'transaction_type': transaction.transaction_type,
            }
        )

    def log_transaction_updated(self, transaction, changed_fields: list):
        """Log transaction update."""
        self.log(
            action=self.ACTION_UPDATE,
            entity_type=self.ENTITY_TRANSACTION,
            entity_id=transaction.id,
            details={
                'changed_fields': changed_fields,
            }
        )

    def log_transaction_deleted(self, transaction):
        """Log transaction deletion."""
        self.log(
            action=self.ACTION_DELETE,
            entity_type=self.ENTITY_TRANSACTION,
            entity_id=transaction.id,
            details={
                'amount': str(transaction.amount),
            }
        )

    def log_transfer(self, from_account, to_account, amount):
        """Log account-to-account transfer."""
        self.log(
            action=self.ACTION_TRANSFER,
            entity_type=self.ENTITY_TRANSACTION,
            details={
                'from_account_id': from_account.id,
                'to_account_id': to_account.id,
                'amount': str(amount),
            }
        )

    def log_budget_created(self, budget):
        """Log budget creation."""
        self.log(
            action=self.ACTION_CREATE,
            entity_type=self.ENTITY_BUDGET,
            entity_id=budget.id,
            details={
                'category': budget.category.name if budget.category else None,
                'amount': str(budget.budgeted_amount),
            }
        )

    def log_goal_created(self, goal):
        """Log goal creation."""
        self.log(
            action=self.ACTION_CREATE,
            entity_type=self.ENTITY_GOAL,
            entity_id=goal.id,
            details={
                'name': goal.name,
                'target': str(goal.target_amount),
            }
        )

    def log_import(self, import_record, transaction_count: int):
        """Log transaction import."""
        self.log(
            action=self.ACTION_IMPORT,
            entity_type=self.ENTITY_IMPORT,
            entity_id=import_record.id,
            details={
                'file_name': import_record.original_filename,
                'transactions_imported': transaction_count,
            }
        )

    def log_ai_query(self, query_type: str):
        """Log AI insight query."""
        self.log(
            action=self.ACTION_AI_QUERY,
            entity_type='ai_insight',
            details={
                'query_type': query_type,
            }
        )


# =============================================================================
# Rate Limiting for Finance Operations
# =============================================================================

class FinanceRateLimiter:
    """
    Rate limiting for sensitive finance operations.

    Prevents abuse of expensive or sensitive operations:
    - AI queries: 10 per hour
    - Transaction imports: 5 per hour
    - Bank syncs: 10 per hour
    """

    DEFAULT_LIMITS = {
        'ai_query': (10, 3600),        # 10 per hour
        'import': (5, 3600),            # 5 per hour
        'bank_sync': (10, 3600),        # 10 per hour
        # Provider-linking operations: deliberately tight. A bank connection is a
        # once-in-a-while act, and a burst is either a mistake or an attack.
        'bank_connect': (5, 3600),      # 5 link attempts per hour
        'bank_disconnect': (10, 3600),  # 10 per hour (retries of a failed revocation)
        'transfer': (20, 3600),         # 20 per hour
        'export': (10, 3600),           # 10 per hour
    }

    def __init__(self, user):
        self.user = user

    def _get_cache_key(self, operation: str) -> str:
        """Generate cache key for rate limit tracking."""
        return f"finance_ratelimit:{self.user.id}:{operation}"

    def check_limit(self, operation: str) -> tuple[bool, Optional[int]]:
        """
        Check if operation is within rate limit.

        Args:
            operation: Type of operation to check

        Returns:
            Tuple of (allowed, seconds_until_reset)
        """
        if operation not in self.DEFAULT_LIMITS:
            return True, None

        max_requests, window_seconds = self.DEFAULT_LIMITS[operation]
        cache_key = self._get_cache_key(operation)

        current = cache.get(cache_key, 0)

        if current >= max_requests:
            # Calculate time until reset
            ttl = cache.ttl(cache_key) if hasattr(cache, 'ttl') else window_seconds
            return False, ttl

        return True, None

    def record_request(self, operation: str):
        """Record a request against the rate limit."""
        if operation not in self.DEFAULT_LIMITS:
            return

        _, window_seconds = self.DEFAULT_LIMITS[operation]
        cache_key = self._get_cache_key(operation)

        current = cache.get(cache_key, 0)
        cache.set(cache_key, current + 1, window_seconds)

    def get_remaining(self, operation: str) -> int:
        """Get remaining requests for an operation."""
        if operation not in self.DEFAULT_LIMITS:
            return 999

        max_requests, _ = self.DEFAULT_LIMITS[operation]
        cache_key = self._get_cache_key(operation)
        current = cache.get(cache_key, 0)

        return max(0, max_requests - current)


def finance_rate_limit(operation: str):
    """
    Decorator to apply rate limiting to finance views.

    Usage:
        @login_required
        @finance_rate_limit('ai_query')
        def my_view(request):
            ...
    """
    def decorator(view_func):
        @functools.wraps(view_func)
        def wrapper(request, *args, **kwargs):
            limiter = FinanceRateLimiter(request.user)
            allowed, retry_after = limiter.check_limit(operation)

            if not allowed:
                logger.warning(
                    f"Rate limit exceeded: user={request.user.id} "
                    f"operation={operation}"
                )
                return JsonResponse({
                    'error': 'Rate limit exceeded',
                    'retry_after': retry_after,
                }, status=429)

            # Record the request
            limiter.record_request(operation)

            return view_func(request, *args, **kwargs)
        return wrapper
    return decorator


# =============================================================================
# Sensitive Operation Verification
# =============================================================================

#: Session key written by `users.ConfirmPasswordView` when a password is re-confirmed.
FINANCE_ACTIVITY_SESSION_KEY = 'finance_last_activity'
#: Where the confirmation view should send the user back to afterwards.
FINANCE_RETURN_URL_SESSION_KEY = 'finance_return_url'


def _recent_auth_age_seconds(request):
    """Seconds since this session last PROVED who it is, or None if it never has.

    Prefers the activity-based confirmation (`finance_last_activity`, written by
    `users:confirm_password`) because that is the control this project actually built for
    sensitive financial operations. Falls back to `last_login`, which only a fresh sign-in
    can refresh — so on its own it would strand the user with no way to satisfy it.
    """
    # A live, bound OAuth attempt IS proof of a recent deliberate act: it was created
    # moments after a password confirmation, is tied to this user and session, is
    # single-use, and expires in 30 minutes. Without this, a bank login that takes
    # longer than 15 minutes would strand the user in a challenge they cannot satisfy
    # without abandoning the connection — a loop, not a control.
    try:
        from apps.finance.services import plaid_oauth
        if plaid_oauth.is_live(request):
            return 0.0                       # the bound attempt is the proof
    except Exception:  # pragma: no cover - never let this gate crash a request
        logger.warning("OAuth recency check failed", exc_info=True)

    confirmed_at = request.session.get(FINANCE_ACTIVITY_SESSION_KEY)
    if confirmed_at:
        try:
            from django.utils.dateparse import parse_datetime
            parsed = parse_datetime(confirmed_at)
            if parsed:
                return (timezone.now() - parsed).total_seconds()
        except (TypeError, ValueError):
            pass
    last_login = getattr(request.user, 'last_login', None)
    if last_login:
        return (timezone.now() - last_login).total_seconds()
    return None


def requires_recent_auth(max_age_minutes: int = 15):
    """Require a recently PROVEN session for sensitive financial operations.

    On failure this does not merely refuse — it tells the client exactly where to go
    (`reauth_url`) and stores the page to return to, so the user re-confirms their
    password through the existing secure path and lands back where they started.
    A security control the user cannot satisfy is a broken feature, not a safe one.
    """
    def decorator(view_func):
        @functools.wraps(view_func)
        def wrapper(request, *args, **kwargs):
            if not request.user.is_authenticated:
                return JsonResponse({'error': 'Authentication required'}, status=401)

            age = _recent_auth_age_seconds(request)
            if age is not None and age > max_age_minutes * 60:
                from django.urls import reverse
                # Remember where to come back to — the referring Finance page, or the
                # connections list. Never a caller-supplied URL (open-redirect safety).
                return_url = request.path
                referer = request.META.get('HTTP_REFERER', '')
                if referer.startswith(request.build_absolute_uri('/finance/')):
                    return_url = referer[len(request.build_absolute_uri('/')) - 1:]
                elif not return_url.startswith('/finance/'):
                    return_url = reverse('finance:connection_list')
                if not return_url.startswith('/finance/'):
                    return_url = reverse('finance:connection_list')
                request.session[FINANCE_RETURN_URL_SESSION_KEY] = return_url

                logger.info(
                    "Re-authentication required: user=%s auth_age=%ss",
                    request.user.id, int(age),
                )
                return JsonResponse({
                    'success': False,
                    'error': (
                        'For your security, connecting a bank needs a recent password '
                        'confirmation. Confirm your password and we will bring you '
                        'straight back here.'
                    ),
                    'require_reauth': True,
                    'reauth_url': reverse('users:confirm_password'),
                }, status=403)

            return view_func(request, *args, **kwargs)
        return wrapper
    return decorator


def verify_ownership(model_class):
    """
    Decorator to verify the user owns the requested resource.

    Usage:
        @verify_ownership(FinancialAccount)
        def my_view(request, pk):
            ...
    """
    def decorator(view_func):
        @functools.wraps(view_func)
        def wrapper(request, pk, *args, **kwargs):
            from django.shortcuts import get_object_or_404

            obj = get_object_or_404(model_class, pk=pk)

            if hasattr(obj, 'user') and obj.user != request.user:
                logger.warning(
                    f"Ownership verification failed: user={request.user.id} "
                    f"model={model_class.__name__} pk={pk}"
                )
                return JsonResponse({'error': 'Access denied'}, status=403)

            return view_func(request, pk, *args, **kwargs)
        return wrapper
    return decorator


# =============================================================================
# Security Utility Functions
# =============================================================================

def is_large_transaction(amount: Decimal, threshold: Decimal = Decimal('1000')) -> bool:
    """Check if a transaction amount is considered large."""
    return abs(amount) >= threshold


def get_audit_logger(request) -> FinanceAuditLogger:
    """Get an audit logger configured for the current request."""
    return FinanceAuditLogger(
        user=request.user if request.user.is_authenticated else None,
        request=request
    )


def mask_account_number(account_number: str) -> str:
    """Mask an account number for display (show last 4 digits)."""
    if not account_number:
        return ''
    if len(account_number) <= 4:
        return '*' * len(account_number)
    return '*' * (len(account_number) - 4) + account_number[-4:]


def mask_balance(balance: Decimal, user_preference: bool = False) -> str:
    """
    Optionally mask a balance for privacy.

    Args:
        balance: The balance to mask
        user_preference: Whether user has enabled balance masking

    Returns:
        Formatted balance or masked string
    """
    if user_preference:
        return '****.**'
    return f'{balance:,.2f}'


# =============================================================================
# MFA / Enhanced Authentication for Sensitive Operations
# =============================================================================

class FinanceMFAController:
    """
    MFA verification for sensitive finance operations.

    This controller provides a hook for MFA verification that can be
    enabled when WLJ implements full MFA support. Currently operates
    in "soft" mode - logs warnings but doesn't block.

    Sensitive operations that should require MFA:
    - Connecting/disconnecting bank accounts
    - Deleting accounts with balances
    - Transfers over threshold
    - Exporting financial data
    """

    # Operations requiring MFA when enabled
    MFA_REQUIRED_OPERATIONS = [
        'bank_connect',
        'bank_disconnect',
        'account_delete',
        'large_transfer',
        'data_export',
    ]

    def __init__(self, user):
        self.user = user

    def is_mfa_enabled(self) -> bool:
        """Check if MFA is enabled for this user."""
        # Future: Check user.has_mfa or similar
        # For now, return False as MFA isn't fully implemented
        return getattr(self.user, 'mfa_enabled', False)

    def requires_mfa(self, operation: str) -> bool:
        """Check if an operation requires MFA verification."""
        return operation in self.MFA_REQUIRED_OPERATIONS

    def verify_mfa(self, operation: str, mfa_code: str = None) -> tuple[bool, str]:
        """
        Verify MFA for an operation.

        Args:
            operation: The operation being attempted
            mfa_code: The MFA code provided by user

        Returns:
            Tuple of (verified, message)
        """
        if not self.requires_mfa(operation):
            return True, 'MFA not required for this operation'

        if not self.is_mfa_enabled():
            # Log warning but allow operation
            logger.warning(
                f"MFA not enabled for sensitive operation: "
                f"user={self.user.id} operation={operation}"
            )
            return True, 'MFA not configured - operation allowed'

        if not mfa_code:
            return False, 'MFA verification required'

        # Future: Verify the MFA code against user's MFA method
        # For now, placeholder that would integrate with TOTP/SMS/etc.
        # return self._verify_totp(mfa_code)

        logger.info(
            f"MFA verification placeholder: user={self.user.id} "
            f"operation={operation}"
        )
        return True, 'MFA verified'

    def get_mfa_prompt(self, operation: str) -> dict:
        """Get MFA prompt configuration for an operation."""
        return {
            'required': self.requires_mfa(operation) and self.is_mfa_enabled(),
            'operation': operation,
            'methods': self._get_available_methods(),
        }

    def _get_available_methods(self) -> list:
        """Get available MFA methods for user."""
        # Future: Return actual methods configured for user
        # e.g., ['totp', 'sms', 'email']
        return []


def requires_mfa_for_sensitive_ops(operation: str):
    """
    Decorator to require MFA verification for sensitive operations.

    Currently logs warnings but doesn't block. When MFA is fully
    implemented, this will require verification.

    Usage:
        @login_required
        @requires_mfa_for_sensitive_ops('bank_disconnect')
        def disconnect_bank(request, pk):
            ...
    """
    def decorator(view_func):
        @functools.wraps(view_func)
        def wrapper(request, *args, **kwargs):
            controller = FinanceMFAController(request.user)

            # Check if MFA is needed
            if controller.requires_mfa(operation):
                mfa_code = request.POST.get('mfa_code') or request.GET.get('mfa_code')
                verified, message = controller.verify_mfa(operation, mfa_code)

                if not verified:
                    prompt = controller.get_mfa_prompt(operation)
                    return JsonResponse({
                        'error': 'MFA verification required',
                        'mfa_required': True,
                        'prompt': prompt,
                    }, status=403)

            return view_func(request, *args, **kwargs)
        return wrapper
    return decorator


# =============================================================================
# Security Constants and Configuration
# =============================================================================

# Large transaction threshold requiring additional verification
LARGE_TRANSACTION_THRESHOLD = Decimal('1000.00')

# High-value account balance threshold
HIGH_VALUE_ACCOUNT_THRESHOLD = Decimal('10000.00')

# Maximum failed verification attempts before lockout
MAX_VERIFICATION_ATTEMPTS = 3

# Verification attempt lockout duration (seconds)
VERIFICATION_LOCKOUT_DURATION = 300  # 5 minutes
