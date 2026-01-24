"""
Whole Life Journey - Django Settings Configuration

Project: Whole Life Journey
Path: config/settings.py
Purpose: Central Django configuration for the personal wellness/journaling application

Description:
    This file contains all Django settings for the Whole Life Journey application.
    It configures database connections, authentication, static/media files, security
    settings, logging, third-party integrations, and application-specific options.

Key Responsibilities:
    - Configure Django core settings (installed apps, middleware, templates)
    - Database configuration (PostgreSQL for production, SQLite for development)
    - Authentication via django-allauth with email-based login
    - Static files served via WhiteNoise, media files via Cloudinary
    - Security settings (HTTPS, CSRF, rate limiting via django-axes)
    - OpenAI API integration for AI coaching features
    - Cloudinary integration for user-uploaded media
    - Logging configuration with rotating file handlers

Dependencies:
    - django-environ: Environment variable parsing
    - django-allauth: Authentication system
    - django-axes: Rate limiting for login attempts
    - whitenoise: Static file serving
    - cloudinary: Media file storage
    - openai: AI coaching features

Environment Variables Required:
    - SECRET_KEY: Django secret key (required)
    - DATABASE_URL: PostgreSQL connection string (optional, defaults to SQLite)
    - OPENAI_API_KEY: OpenAI API key for AI features
    - CLOUDINARY_*: Cloud storage credentials
    - BIBLE_API_KEY: API.Bible key for Scripture lookups

Copyright:
    (c) Whole Life Journey. All rights reserved.
    This code is proprietary and may not be copied, modified, or distributed
    without explicit permission.
"""

import logging
import os
import sys
from pathlib import Path

import environ
from django.core.exceptions import ImproperlyConfigured

# Detect if we're running tests
TESTING = len(sys.argv) > 1 and sys.argv[1] == 'test'

# Sentry SDK is optional - only import if available
try:
    import sentry_sdk
    from sentry_sdk.integrations.django import DjangoIntegration
    from sentry_sdk.integrations.logging import LoggingIntegration
    SENTRY_AVAILABLE = True
except ImportError:
    SENTRY_AVAILABLE = False

OPENAI_API_KEY = os.environ.get('OPENAI_API_KEY')
OPENAI_MODEL = os.environ.get('OPENAI_MODEL', 'gpt-4o-mini')
OPENAI_VISION_MODEL = os.environ.get('OPENAI_VISION_MODEL', 'gpt-4o')

# Claude Code API Key for task fetching
# Used by Claude Code to authenticate with the Ready Tasks API endpoint
CLAUDE_API_KEY = os.environ.get('CLAUDE_API_KEY', '')


# Build paths inside the project like this: BASE_DIR / 'subdir'.
BASE_DIR = Path(__file__).resolve().parent.parent

# Environment variables
env = environ.Env(
    DEBUG=(bool, False),
)

# Read .env file if it exists
env_file = BASE_DIR / ".env"
if env_file.exists():
    environ.Env.read_env(env_file)

# SECURITY WARNING: keep the secret key used in production secret!
SECRET_KEY = env("SECRET_KEY")

# SECURITY WARNING: don't run with debug turned on in production!
DEBUG = env.bool("DEBUG", default=False)

# Allowed hosts for production and development
ALLOWED_HOSTS = [
    "wholelifejourney.com",
    "www.wholelifejourney.com",
    ".up.railway.app",
    "localhost",
    "127.0.0.1",
]

# Application definition
INSTALLED_APPS = [
    # Django core
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "django.contrib.sites",
    "django.contrib.humanize",  # For intcomma template filter
    # Third-party apps
    "allauth",
    "allauth.account",
    "axes",  # Rate limiting for authentication (Security Fix H-3)
    "crispy_forms",
    "crispy_tailwind",
    "django_htmx",
    "cloudinary",
    "cloudinary_storage",
    # Local apps
    "apps.core",
    "apps.users",
    "apps.dashboard",
    "apps.journal",
    "apps.faith",
    "apps.health",
    "apps.admin_console",
    "apps.life",
    'apps.purpose',
    'apps.ai',
    'apps.help',
    'apps.scan',
    'apps.capture',
    'apps.sms',
    'apps.finance',
    'apps.billing',
    'apps.security',
    'assistant',
    'django_apscheduler',
    'djstripe',
]

# Development-only: Add django-watchfiles for efficient autoreload (fixes Python 3.14 StatReloader issue)
# Only loads if DEBUG=True and the package is installed
if DEBUG:
    try:
        import django_watchfiles  # noqa: F401
        INSTALLED_APPS.insert(0, "django_watchfiles")
    except ImportError:
        pass  # Package not installed, use default StatReloader

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "whitenoise.middleware.WhiteNoiseMiddleware",
    "apps.core.middleware.NoCacheHTMLMiddleware",  # Prevent FOUC by disabling HTML caching
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
    "allauth.account.middleware.AccountMiddleware",
    "django_htmx.middleware.HtmxMiddleware",
    "apps.users.middleware.TermsAcceptanceMiddleware",
    "apps.users.middleware.SubscriptionRequiredMiddleware",  # Check subscription/trial status
    "apps.users.middleware.MFAEnforcementMiddleware",  # Require MFA for staff/admin accounts
    "apps.users.middleware.TimezoneMiddleware",  # Convert UTC to user's timezone
    "apps.core.middleware.PageViewTrackingMiddleware",  # Track page views for Favorites
    # CSP disabled temporarily - causing FOUC issues
    # "apps.core.middleware.CSPNonceMiddleware",  # Generate CSP nonce (CISO Review) - must be before CSP
    # "apps.core.middleware.ContentSecurityPolicyMiddleware",  # CSP headers for XSS protection
    "apps.core.middleware.APIRequestLoggingMiddleware",  # API logging with anomaly detection (CISO Review)
    "axes.middleware.AxesMiddleware",  # Rate limiting (Security Fix H-3) - must be last
]

ROOT_URLCONF = "config.urls"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [BASE_DIR / "templates"],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.debug",
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
                "apps.core.context_processors.theme_context",
                "apps.core.context_processors.site_context",
                "apps.core.context_processors.favorites_context",
                "apps.core.context_processors.csp_nonce",  # CSP nonce for inline scripts (CISO Review)
                "apps.core.context_processors.pending_captures_context",  # Pending capture banner
                "apps.billing.context_processors.billing_config",
            ],
        },
    },
]

WSGI_APPLICATION = "config.wsgi.application"


# Database
# https://docs.djangoproject.com/en/5.0/ref/settings/#databases

# Database
# Use DATABASE_URL if provided (Railway provides this), otherwise SQLite for development only
DATABASE_URL = env("DATABASE_URL", default="")
if DATABASE_URL:
    DATABASES = {
        "default": {
            **env.db("DATABASE_URL"),
            "CONN_MAX_AGE": 600,  # Keep connections alive for 10 minutes
            "CONN_HEALTH_CHECKS": True,  # Verify connections before reuse
        },
    }
elif DEBUG:
    # SQLite is only allowed in development mode
    DATABASES = {
        "default": {
            "ENGINE": "django.db.backends.sqlite3",
            "NAME": BASE_DIR / "db.sqlite3",
        }
    }
else:
    raise ImproperlyConfigured(
        "DATABASE_URL environment variable is required in production. "
        "SQLite is not supported for production use."
    )




# Password validation
# https://docs.djangoproject.com/en/5.0/ref/settings/#auth-password-validators

AUTH_PASSWORD_VALIDATORS = [
    {
        "NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator",
    },
    {
        "NAME": "django.contrib.auth.password_validation.MinimumLengthValidator",
    },
    {
        "NAME": "django.contrib.auth.password_validation.CommonPasswordValidator",
    },
    {
        "NAME": "django.contrib.auth.password_validation.NumericPasswordValidator",
    },
]


# Internationalization
# https://docs.djangoproject.com/en/5.0/topics/i18n/

LANGUAGE_CODE = "en-us"

TIME_ZONE = "UTC"

USE_I18N = True

USE_TZ = True


# Static files (CSS, JavaScript, Images)
# https://docs.djangoproject.com/en/5.0/howto/static-files/

STATIC_URL = "static/"
STATIC_ROOT = BASE_DIR / "staticfiles"
STATICFILES_DIRS = [BASE_DIR / "static"]

# WhiteNoise for static file serving
# Use simpler storage during tests to avoid manifest requirement
if TESTING:
    STORAGES = {
        "staticfiles": {
            "BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage",
        },
        "default": {
            "BACKEND": "django.core.files.storage.FileSystemStorage",
        },
    }
else:
    STORAGES = {
        "staticfiles": {
            "BACKEND": "whitenoise.storage.CompressedManifestStaticFilesStorage",
        },
        "default": {
            "BACKEND": "cloudinary_storage.storage.MediaCloudinaryStorage",
        },
    }

# Media files (user uploads)
# Cloudinary handles media in production, local filesystem in development
MEDIA_URL = "media/"
MEDIA_ROOT = BASE_DIR / "media"

# Cloudinary Configuration
# Requires CLOUDINARY_CLOUD_NAME, CLOUDINARY_API_KEY, CLOUDINARY_API_SECRET env vars
_cloudinary_cloud_name = env("CLOUDINARY_CLOUD_NAME", default="")
_cloudinary_api_key = env("CLOUDINARY_API_KEY", default="")
_cloudinary_api_secret = env("CLOUDINARY_API_SECRET", default="")

if _cloudinary_cloud_name and _cloudinary_api_key and _cloudinary_api_secret:
    # Configure cloudinary library directly
    import cloudinary
    cloudinary.config(
        cloud_name=_cloudinary_cloud_name,
        api_key=_cloudinary_api_key,
        api_secret=_cloudinary_api_secret,
        secure=True
    )

    # Also set CLOUDINARY_STORAGE for django-cloudinary-storage
    CLOUDINARY_STORAGE = {
        "CLOUD_NAME": _cloudinary_cloud_name,
        "API_KEY": _cloudinary_api_key,
        "API_SECRET": _cloudinary_api_secret,
    }
else:
    # Fall back to local storage if Cloudinary is not configured
    STORAGES["default"] = {
        "BACKEND": "django.core.files.storage.FileSystemStorage",
    }


# Default primary key field type
# https://docs.djangoproject.com/en/5.0/ref/settings/#default-auto-field

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"


# Logging configuration
# In production, logs go to console (captured by Railway) AND file for persistence
LOG_DIR = BASE_DIR / 'logs'
LOG_DIR.mkdir(exist_ok=True)

# JSON log formatter for production (structured logging)
# Enables easier parsing by log aggregation tools (Railway, Datadog, ELK, etc.)


class JsonFormatter(logging.Formatter):
    """
    Custom JSON formatter for structured logging in production.

    Outputs logs as single-line JSON objects with consistent fields:
    - timestamp: ISO 8601 format
    - level: Log level (INFO, WARNING, ERROR, etc.)
    - logger: Logger name
    - message: Log message
    - module: Python module name
    - line: Line number
    - Additional fields from extra dict
    """

    def format(self, record):
        import json as json_module
        from datetime import datetime, timezone

        log_obj = {
            'timestamp': datetime.now(timezone.utc).isoformat(),
            'level': record.levelname,
            'logger': record.name,
            'message': record.getMessage(),
            'module': record.module,
            'line': record.lineno,
        }

        # Add exception info if present
        if record.exc_info:
            log_obj['exception'] = self.formatException(record.exc_info)

        # Add any extra fields
        if hasattr(record, 'request_id'):
            log_obj['request_id'] = record.request_id
        if hasattr(record, 'user_id'):
            log_obj['user_id'] = record.user_id

        return json_module.dumps(log_obj)


# Import logging module for JsonFormatter
import logging

LOGGING = {
    'version': 1,
    'disable_existing_loggers': False,
    'formatters': {
        'verbose': {
            'format': '{levelname} {asctime} {module} {process:d} {thread:d} {message}',
            'style': '{',
        },
        'simple': {
            'format': '{levelname} {asctime} {module} {message}',
            'style': '{',
        },
        'detailed': {
            'format': '[{asctime}] {levelname} {name} {module}:{lineno} - {message}',
            'style': '{',
        },
        'json': {
            '()': JsonFormatter,
        },
    },
    'filters': {
        'require_debug_false': {
            '()': 'django.utils.log.RequireDebugFalse',
        },
        'require_debug_true': {
            '()': 'django.utils.log.RequireDebugTrue',
        },
    },
    'handlers': {
        'console': {
            'class': 'logging.StreamHandler',
            'formatter': 'simple',
        },
        'console_json': {
            'class': 'logging.StreamHandler',
            'formatter': 'json',
            'filters': ['require_debug_false'],
        },
        'file_error': {
            'level': 'ERROR',
            'class': 'logging.handlers.RotatingFileHandler',
            'filename': LOG_DIR / 'error.log',
            'maxBytes': 1024 * 1024 * 5,  # 5 MB
            'backupCount': 5,
            'formatter': 'detailed',
        },
        'file_app': {
            'level': 'INFO',
            'class': 'logging.handlers.RotatingFileHandler',
            'filename': LOG_DIR / 'app.log',
            'maxBytes': 1024 * 1024 * 10,  # 10 MB
            'backupCount': 3,
            'formatter': 'detailed',
        },
        'file_security': {
            'level': 'WARNING',
            'class': 'logging.handlers.RotatingFileHandler',
            'filename': LOG_DIR / 'security.log',
            'maxBytes': 1024 * 1024 * 5,  # 5 MB
            'backupCount': 10,  # Keep more security logs for audit
            'formatter': 'detailed',
        },
        'mail_admins': {
            'level': 'ERROR',
            'filters': ['require_debug_false'],
            'class': 'django.utils.log.AdminEmailHandler',
            'include_html': True,
        },
    },
    'root': {
        'handlers': ['console', 'console_json', 'file_error'],
        'level': 'INFO',
    },
    'loggers': {
        'django': {
            'handlers': ['console', 'console_json', 'file_error'],
            'level': 'INFO',
            'propagate': False,
        },
        'django.request': {
            'handlers': ['console', 'console_json', 'file_error', 'mail_admins'],
            'level': 'ERROR',
            'propagate': False,
        },
        'django.security': {
            'handlers': ['console', 'console_json', 'file_error', 'file_security', 'mail_admins'],
            'level': 'WARNING',
            'propagate': False,
        },
        'cloudinary': {
            'handlers': ['console'],
            'level': 'WARNING',
            'propagate': False,
        },
        'apps': {
            'handlers': ['console', 'console_json', 'file_app', 'file_error', 'mail_admins'],
            'level': 'DEBUG' if DEBUG else 'INFO',
            'propagate': False,
        },
        # Security-related loggers - send all warnings/errors to email
        'wlj.security': {
            'handlers': ['console', 'console_json', 'file_security', 'mail_admins'],
            'level': 'WARNING',
            'propagate': False,
        },
        # Axes (brute force protection) logs
        'axes': {
            'handlers': ['console', 'console_json', 'file_security'],
            'level': 'WARNING',
            'propagate': False,
        },
        # Management command errors (nightly jobs, scheduled tasks)
        'django.management': {
            'handlers': ['console', 'console_json', 'file_error', 'mail_admins'],
            'level': 'ERROR',
            'propagate': False,
        },
        # Sentry SDK logs
        'sentry_sdk': {
            'handlers': ['console'],
            'level': 'WARNING',
            'propagate': False,
        },
    },
}


# Custom User Model
AUTH_USER_MODEL = "users.User"


# Django Allauth Configuration
SITE_ID = 1

# Authentication backends
# Note: AxesStandaloneBackend is NOT included here because it breaks Django's test client
# (requires request parameter in authenticate()). Axes rate limiting still works via
# AxesMiddleware. The warning (axes.W003) is suppressed in SILENCED_SYSTEM_CHECKS.
AUTHENTICATION_BACKENDS = [
    "django.contrib.auth.backends.ModelBackend",
    "allauth.account.auth_backends.AuthenticationBackend",
]

ACCOUNT_USER_MODEL_USERNAME_FIELD = None

ACCOUNT_LOGIN_ON_EMAIL_CONFIRMATION = True
ACCOUNT_LOGOUT_ON_GET = True
ACCOUNT_PRESERVE_USERNAME_CASING = False
ACCOUNT_PREVENT_ENUMERATION = True
ACCOUNT_SESSION_REMEMBER = True
ACCOUNT_UNIQUE_EMAIL = True
ACCOUNT_EMAIL_VERIFICATION = "mandatory"  # Admin emails bypass via WLJAccountAdapter.is_email_verified()
ACCOUNT_EMAIL_CONFIRMATION_EXPIRE_DAYS = 3
ACCOUNT_RATE_LIMITS = {
    "confirm_email": "3/m",  # 3 confirmation emails per minute (replaces deprecated COOLDOWN setting)
}
ACCOUNT_LOGIN_ON_PASSWORD_RESET = True

# New django-allauth settings (replacing deprecated ones)
ACCOUNT_LOGIN_METHODS = {"email"}  # Replaces ACCOUNT_AUTHENTICATION_METHOD
ACCOUNT_SIGNUP_FIELDS = ["email*", "password1*", "password2*"]  # Replaces ACCOUNT_EMAIL_REQUIRED, ACCOUNT_USERNAME_REQUIRED, ACCOUNT_SIGNUP_PASSWORD_ENTER_TWICE

# Custom account adapter for security features (honeypot, signup logging)
ACCOUNT_ADAPTER = "apps.users.adapters.WLJAccountAdapter"

# Custom signup form for age verification (COPPA compliance)
ACCOUNT_FORMS = {
    "signup": "apps.users.forms.CustomSignupForm",
}

LOGIN_REDIRECT_URL = "dashboard:home"
LOGOUT_REDIRECT_URL = "core:landing"
LOGIN_URL = "account_login"


# Crispy Forms
CRISPY_ALLOWED_TEMPLATE_PACKS = "tailwind"
CRISPY_TEMPLATE_PACK = "tailwind"


# ==============================================================================
# Email Configuration (Namecheap Private Email SMTP)
# ==============================================================================
# Uses SMTP with TLS encryption for all transactional emails:
# - Account verification, password reset, admin alerts, notifications
#
# IMPORTANT: The FROM address must match the authenticated SMTP user
# to maintain SPF/DKIM alignment. Do not change DEFAULT_FROM_EMAIL
# without also updating EMAIL_HOST_USER.

if DEBUG:
    # Development: Print emails to console
    EMAIL_BACKEND = "django.core.mail.backends.console.EmailBackend"
else:
    # Production: Use SMTP via Namecheap Private Email
    EMAIL_BACKEND = "django.core.mail.backends.smtp.EmailBackend"
    EMAIL_HOST = env("EMAIL_HOST", default="mail.privateemail.com")
    EMAIL_PORT = env.int("EMAIL_PORT", default=587)
    EMAIL_USE_TLS = env.bool("EMAIL_USE_TLS", default=True)
    EMAIL_USE_SSL = False  # Use TLS, not SSL (they're mutually exclusive)
    EMAIL_HOST_USER = env("EMAIL_HOST_USER", default="")
    EMAIL_HOST_PASSWORD = env("EMAIL_HOST_PASSWORD", default="")
    EMAIL_TIMEOUT = 30  # Seconds - prevent hanging on SMTP connection issues

# Sender address for all outgoing emails
# MUST match EMAIL_HOST_USER for SPF/DKIM alignment
DEFAULT_FROM_EMAIL = env("DEFAULT_FROM_EMAIL", default="admin@wholelifejourney.com")

# Server email for error notifications to ADMINS
SERVER_EMAIL = env("SERVER_EMAIL", default="admin@wholelifejourney.com")

# Admin recipients for error emails (optional)
# Format: [("Name", "email@example.com"), ...]
ADMINS = [
    ("WLJ Admin", env("ADMIN_EMAIL", default="admin@wholelifejourney.com")),
]


# Site domain for email links and absolute URLs
SITE_DOMAIN = env("SITE_DOMAIN", default="https://wholelifejourney.com")

# CSRF Trusted Origins - must be set for both production and development
# Django 4.0+ requires this for HTTPS requests
CSRF_TRUSTED_ORIGINS = [
    "https://wholelifejourney.com",
    "https://www.wholelifejourney.com",
]

# Security Settings - ONLY apply in production (when DEBUG is False)
# These settings require HTTPS and will break local development if enabled
if not DEBUG:
    # Railway handles SSL termination at the proxy level
    # Trust the X-Forwarded-Proto header from Railway's load balancer
    SECURE_PROXY_SSL_HEADER = ('HTTP_X_FORWARDED_PROTO', 'https')

    # SSL redirect is handled by Railway's proxy, so we disable it in Django
    # to avoid redirect loops. The proxy ensures all traffic is HTTPS.
    SECURE_SSL_REDIRECT = env.bool("SECURE_SSL_REDIRECT", default=False)

    SESSION_COOKIE_SECURE = True
    CSRF_COOKIE_SECURE = True
    SECURE_BROWSER_XSS_FILTER = True
    SECURE_CONTENT_TYPE_NOSNIFF = True
    SECURE_HSTS_SECONDS = 31536000
    SECURE_HSTS_INCLUDE_SUBDOMAINS = True
    SECURE_HSTS_PRELOAD = True
else:
    # Explicitly disable SSL for local development
    SECURE_SSL_REDIRECT = False
    SESSION_COOKIE_SECURE = False
    CSRF_COOKIE_SECURE = False

# Cookie SameSite attribute (Security Fix M-1)
# Prevents CSRF attacks by restricting cookie sending on cross-site requests
SESSION_COOKIE_SAMESITE = 'Lax'  # 'Lax' allows normal navigation, 'Strict' blocks all cross-site
CSRF_COOKIE_SAMESITE = 'Lax'

# Session timeout (Security Fix - CISO Review 2026-01-12)
# Sessions expire after 24 hours of inactivity
SESSION_COOKIE_AGE = 60 * 60 * 24  # 24 hours in seconds

# Custom Admin URL Path (Security Fix H-4)
# Moving admin to a non-default path reduces brute force attack surface
ADMIN_URL_PATH = env("ADMIN_URL_PATH", default="wlj-admin")

# Django Axes Configuration (Security Fix H-3)
# Rate limiting for authentication to prevent brute force attacks
AXES_FAILURE_LIMIT = 5  # Lock after 5 failed attempts
AXES_COOLOFF_TIME = 1  # Lock for 1 hour (in hours)
AXES_LOCKOUT_CALLABLE = None  # Use default lockout response
AXES_RESET_ON_SUCCESS = True  # Reset failed attempts on successful login
AXES_LOCKOUT_PARAMETERS = ["ip_address", "username"]  # New v6+ config replaces deprecated settings
AXES_ENABLE_ACCESS_FAILURE_LOG = True  # Log failed attempts
AXES_VERBOSE = True if DEBUG else False  # Verbose logging in dev only

# Silenced System Checks
# axes.W003: We intentionally don't include AxesStandaloneBackend in AUTHENTICATION_BACKENDS
# because it requires a request parameter that Django's test client doesn't provide.
# Rate limiting still works via AxesMiddleware.
SILENCED_SYSTEM_CHECKS = [
    "axes.W003",
]


# Whole Life Journey Custom Settings
WLJ_SETTINGS = {
    # Default theme for new users
    "DEFAULT_THEME": "minimal",
    # Available themes
    "THEMES": {
        "faith": {
            "name": "Christian Faith",
            "description": "Peaceful, grounded, spiritually respectful",
            "primary": "#1e3a5f",
            "secondary": "#faf8f5",
            "accent": "#d4a574",
            "text": "#2d3748",
        },
        "sports": {
            "name": "Sports & Performance",
            "description": "Goal-driven, disciplined, focused",
            "primary": "#1f2937",
            "secondary": "#ffffff",
            "accent": "#dc2626",
            "text": "#111827",
        },
        "nature": {
            "name": "Animals & Nature",
            "description": "Warm, calming, emotionally safe",
            "primary": "#2d5a27",
            "secondary": "#fefce8",
            "accent": "#7dd3fc",
            "text": "#1a2e05",
        },
        "outdoors": {
            "name": "Outdoors & Adventure",
            "description": "Curious, expansive, journey-focused",
            "primary": "#475569",
            "secondary": "#fffbeb",
            "accent": "#f97316",
            "text": "#1e293b",
        },
        "minimal": {
            "name": "Minimal / Life Focus",
            "description": "Quiet, clear, intentional",
            "primary": "#6b7280",
            "secondary": "#f9fafb",
            "accent": "#6366f1",
            "text": "#374151",
        },
    },
    # Soft delete retention period (days)
    "SOFT_DELETE_RETENTION_DAYS": 30,
    # Terms of Service version (increment when terms change)
    "TERMS_VERSION": "1.1",
    # Finance activity timeout (minutes) - CISO Review 2026-01-12
    # Requires re-authentication for sensitive financial operations after this period
    "FINANCE_ACTIVITY_TIMEOUT_MINUTES": 15,
    # Admin override timeout (minutes) - CISO Review 2026-01-12
    # Requires re-authentication for destructive admin operations after this period
    "ADMIN_OVERRIDE_TIMEOUT_MINUTES": 30,
    # Set to False to disable admin override confirmation entirely (emergency bypass)
    "ADMIN_OVERRIDE_REQUIRE_CONFIRMATION": True,
    # API Request Logging with Anomaly Detection (CISO Review 2026-01-12)
    "API_LOGGING_ENABLED": True,
    "API_LOGGING_PATHS": ["/api/", "/admin-console/api/"],
    "API_ANOMALY_DETECTION": True,
    "API_LOG_RETENTION_DAYS": 30,
}

# YouVersion Bible API (required for Scripture lookups in Faith module)
# Get your API key at: https://platform.youversion.com/
YOUVERSION_API_KEY = os.environ.get('YOUVERSION_API_KEY', '')

# Camera Scan Settings
# Vision analysis uses OpenAI's vision-capable models
SCAN_MAX_IMAGE_MB = int(os.environ.get('SCAN_MAX_IMAGE_MB', '10'))
SCAN_RATE_LIMIT_PER_HOUR = int(os.environ.get('SCAN_RATE_LIMIT_PER_HOUR', '30'))
SCAN_RATE_LIMIT_IP_PER_HOUR = int(os.environ.get('SCAN_RATE_LIMIT_IP_PER_HOUR', '60'))
SCAN_REQUEST_TIMEOUT_SECONDS = int(os.environ.get('SCAN_REQUEST_TIMEOUT_SECONDS', '30'))


# Google Calendar Integration
GOOGLE_CALENDAR_CLIENT_ID = env('GOOGLE_CALENDAR_CLIENT_ID', default='')
GOOGLE_CALENDAR_CLIENT_SECRET = env('GOOGLE_CALENDAR_CLIENT_SECRET', default='')

# Redirect URI - must match exactly what's registered in Google Cloud Console
if DEBUG:
    GOOGLE_CALENDAR_REDIRECT_URI = 'http://localhost:8000/life/calendar/google/callback/'
else:
    GOOGLE_CALENDAR_REDIRECT_URI = env(
        'GOOGLE_CALENDAR_REDIRECT_URI',
        default='https://wholelifejourney.com/life/calendar/google/callback/'
    )


# ==============================================================================
# Gmail Integration
# ==============================================================================
# Gmail OAuth credentials - use the same Google Cloud project as Calendar
GMAIL_CLIENT_ID = env('GMAIL_CLIENT_ID', default='')
GMAIL_CLIENT_SECRET = env('GMAIL_CLIENT_SECRET', default='')

# Redirect URI - must match exactly what's registered in Google Cloud Console
if DEBUG:
    GMAIL_REDIRECT_URI = 'http://localhost:8000/life/gmail/callback/'
else:
    GMAIL_REDIRECT_URI = env(
        'GMAIL_REDIRECT_URI',
        default='https://wholelifejourney.com/life/gmail/callback/'
    )

# API key for external cron trigger (generate a secure random string)
GMAIL_SYNC_API_KEY = env('GMAIL_SYNC_API_KEY', default='')


# ==============================================================================
# Plaid Bank Integration Configuration
# ==============================================================================
# Get your credentials at: https://dashboard.plaid.com/overview
# Environments: sandbox (testing), development (limited real banks), production

PLAID_CLIENT_ID = env('PLAID_CLIENT_ID', default='')
PLAID_SECRET = env('PLAID_SECRET', default='')
PLAID_ENV = env('PLAID_ENV', default='sandbox')  # sandbox, development, production

# Token encryption key - generate with: Fernet.generate_key()
BANK_TOKEN_ENCRYPTION_KEY = env('BANK_TOKEN_ENCRYPTION_KEY', default='')

# ==============================================================================
# OAuth Token Encryption (CISO Review 2026-01-12)
# ==============================================================================
# Encryption key for OAuth tokens (Google Calendar, Dexcom, etc.)
# Generate with: from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())
OAUTH_TOKEN_ENCRYPTION_KEY = env('OAUTH_TOKEN_ENCRYPTION_KEY', default='')

# Webhook URL for real-time transaction updates
if DEBUG:
    PLAID_WEBHOOK_URL = ''  # Webhooks don't work with localhost
else:
    PLAID_WEBHOOK_URL = env(
        'PLAID_WEBHOOK_URL',
        default='https://wholelifejourney.com/finance/webhooks/plaid/'
    )

# OAuth redirect URI (for OAuth-enabled banks)
if DEBUG:
    PLAID_REDIRECT_URI = ''  # Not needed for sandbox
else:
    PLAID_REDIRECT_URI = env(
        'PLAID_REDIRECT_URI',
        default='https://wholelifejourney.com/finance/plaid/oauth/'
    )


# ==============================================================================
# Twilio SMS Configuration
# ==============================================================================
# Get your credentials at: https://www.twilio.com/console
# Twilio Verify requires a Verify Service - create one in the Twilio Console

TWILIO_ACCOUNT_SID = env('TWILIO_ACCOUNT_SID', default='')
TWILIO_AUTH_TOKEN = env('TWILIO_AUTH_TOKEN', default='')
TWILIO_PHONE_NUMBER = env('TWILIO_PHONE_NUMBER', default='')  # E.164 format: +1XXXXXXXXXX
TWILIO_VERIFY_SERVICE_SID = env('TWILIO_VERIFY_SERVICE_SID', default='')

# Test mode - when True, logs SMS instead of sending (useful for development)
TWILIO_TEST_MODE = env.bool('TWILIO_TEST_MODE', default=DEBUG)

# Trigger token for protected API endpoints (used by external cron)
SMS_TRIGGER_TOKEN = env('SMS_TRIGGER_TOKEN', default='')


# ==============================================================================
# Dexcom CGM Integration
# ==============================================================================
# Register your app at: https://developer.dexcom.com/
# OAuth 2.0 credentials for blood glucose data access

DEXCOM_CLIENT_ID = env('DEXCOM_CLIENT_ID', default='')
DEXCOM_CLIENT_SECRET = env('DEXCOM_CLIENT_SECRET', default='')

# Redirect URI - must match exactly what's registered in Dexcom developer portal
if DEBUG:
    DEXCOM_REDIRECT_URI = 'http://localhost:8000/health/glucose/dexcom/callback/'
else:
    DEXCOM_REDIRECT_URI = env(
        'DEXCOM_REDIRECT_URI',
        default='https://wholelifejourney.com/health/glucose/dexcom/callback/'
    )

# Use sandbox for development (simulated data, no real Dexcom account needed)
DEXCOM_USE_SANDBOX = env.bool('DEXCOM_USE_SANDBOX', default=DEBUG)


# ==============================================================================
# APScheduler Configuration (Background Jobs)
# ==============================================================================
# Used for scheduling SMS reminders and sending pending notifications
# Jobs are stored in the database and survive restarts

APSCHEDULER_DATETIME_FORMAT = "N j, Y, f:s a"

# Run scheduler only in production (managed by run_scheduler command)
APSCHEDULER_RUN_NOW_TIMEOUT = 25  # Seconds


# ==============================================================================
# Google reCAPTCHA v3 Configuration
# ==============================================================================
# Get your keys at: https://www.google.com/recaptcha/admin
# reCAPTCHA v3 returns a score (0.0-1.0) - no user interaction required

RECAPTCHA_V3_SITE_KEY = env('RECAPTCHA_V3_SITE_KEY', default='')
RECAPTCHA_V3_SECRET_KEY = env('RECAPTCHA_V3_SECRET_KEY', default='')

# Score threshold (0.0-1.0) - higher is more likely human
# 0.5 is recommended default, adjust based on observed traffic
RECAPTCHA_SCORE_THRESHOLD = float(env('RECAPTCHA_SCORE_THRESHOLD', default='0.5'))


# ==============================================================================
# GitHub API Configuration (for Codebase Metrics)
# ==============================================================================
# Used by the codebase metrics report to fetch git history when deployed
# without a local .git directory (e.g., on Railway)

GITHUB_REPO_OWNER = env('GITHUB_REPO_OWNER', default='djenkins452')
GITHUB_REPO_NAME = env('GITHUB_REPO_NAME', default='dbawholelifejourney')
GITHUB_API_TOKEN = env('GITHUB_API_TOKEN', default=None)  # Optional, for higher rate limits


# ==============================================================================
# Sentry Error Tracking Configuration
# ==============================================================================
# Get your DSN at: https://sentry.io/
# Sentry provides real-time error tracking, performance monitoring, and alerting

SENTRY_DSN = env('SENTRY_DSN', default='')


# ==============================================================================
# Stripe Payment Configuration
# ==============================================================================
# Get your keys at: https://dashboard.stripe.com/apikeys
# Webhook signing secret: https://dashboard.stripe.com/webhooks

STRIPE_PUBLIC_KEY = env('STRIPE_PUBLIC_KEY', default='')
STRIPE_SECRET_KEY = env('STRIPE_SECRET_KEY', default='')
STRIPE_WEBHOOK_SECRET = env('STRIPE_WEBHOOK_SECRET', default='')

# Stripe Price IDs - create products in Stripe Dashboard first
# These should be set in environment variables for each environment
STRIPE_PRICE_STUDENT_MONTHLY = env('STRIPE_PRICE_STUDENT_MONTHLY', default='')
STRIPE_PRICE_STUDENT_ANNUAL = env('STRIPE_PRICE_STUDENT_ANNUAL', default='')
STRIPE_PRICE_ADULT_MONTHLY = env('STRIPE_PRICE_ADULT_MONTHLY', default='')
STRIPE_PRICE_ADULT_ANNUAL = env('STRIPE_PRICE_ADULT_ANNUAL', default='')
STRIPE_PRICE_FOUNDING = env('STRIPE_PRICE_FOUNDING', default='')

# dj-stripe configuration
STRIPE_LIVE_MODE = not DEBUG  # Use live mode in production
DJSTRIPE_WEBHOOK_SECRET = STRIPE_WEBHOOK_SECRET
DJSTRIPE_FOREIGN_KEY_TO_FIELD = 'id'
DJSTRIPE_USE_NATIVE_JSONFIELD = True

# ==============================================================================
# Billing Configuration
# ==============================================================================
# Billing configuration (pricing, rewards, age thresholds) is stored in the database
# via the BillingConfiguration model and managed via Django Admin.
# See: /admin/billing/billingconfiguration/
# Docs: docs/billing_go_live_checklist.md


# ==============================================================================
# Capture Audio S3 Storage Configuration
# ==============================================================================
# S3-compatible storage for temporary audio file storage (7-day retention)
# Supports AWS S3 or any S3-compatible service (DigitalOcean Spaces, MinIO, etc.)
# Get your credentials at: https://console.aws.amazon.com/s3/

# AWS credentials (or S3-compatible service credentials)
CAPTURE_AWS_ACCESS_KEY_ID = env('CAPTURE_AWS_ACCESS_KEY_ID', default='')
CAPTURE_AWS_SECRET_ACCESS_KEY = env('CAPTURE_AWS_SECRET_ACCESS_KEY', default='')
CAPTURE_AWS_REGION = env('CAPTURE_AWS_REGION', default='us-east-1')

# S3 bucket name for audio files (separate from main media storage)
CAPTURE_AUDIO_BUCKET = env('CAPTURE_AUDIO_BUCKET', default='')

# Optional: Custom endpoint URL for S3-compatible services (e.g., DigitalOcean Spaces)
# Leave empty for standard AWS S3
CAPTURE_S3_ENDPOINT_URL = env('CAPTURE_S3_ENDPOINT_URL', default='')

# Audio file retention period in days (default 7)
# S3 lifecycle policy should match this setting
CAPTURE_AUDIO_RETENTION_DAYS = env.int('CAPTURE_AUDIO_RETENTION_DAYS', default=7)

# Presigned URL expiration in seconds (default 1 hour for uploads, matches retention for downloads)
CAPTURE_PRESIGNED_URL_EXPIRATION = env.int('CAPTURE_PRESIGNED_URL_EXPIRATION', default=3600)


# ==============================================================================
# Email Intake Configuration (IMAP polling for task creation)
# ==============================================================================
# Used by process_email_tasks management command to poll for emails
# Emails in the "Automate" folder are converted to AdminTasks
#
# Usage workflow:
# 1. Move an email to the "Automate" folder in your mailbox
# 2. Wait for next polling cycle (runs 3x daily)
# 3. Receive confirmation email with task details
# 4. Email is moved to "New Requests" folder

EMAIL_INTAKE_HOST = env('EMAIL_INTAKE_HOST', default='mail.privateemail.com')
EMAIL_INTAKE_PORT = env.int('EMAIL_INTAKE_PORT', default=993)
EMAIL_INTAKE_USER = env('EMAIL_INTAKE_USER', default='')
EMAIL_INTAKE_PASSWORD = env('EMAIL_INTAKE_PASSWORD', default='')


if SENTRY_DSN and not DEBUG and SENTRY_AVAILABLE:
    sentry_sdk.init(
        dsn=SENTRY_DSN,
        integrations=[
            DjangoIntegration(
                transaction_style='url',
                middleware_spans=True,
            ),
            LoggingIntegration(
                level=None,  # Capture all log levels as breadcrumbs
                event_level='ERROR',  # Send ERROR and above as events
            ),
        ],
        # Performance monitoring - sample 10% of transactions
        traces_sample_rate=float(env('SENTRY_TRACES_SAMPLE_RATE', default='0.1')),
        # Profile 10% of sampled transactions for performance insights
        profiles_sample_rate=float(env('SENTRY_PROFILES_SAMPLE_RATE', default='0.1')),
        # Associate errors with releases for tracking
        release=env('RAILWAY_GIT_COMMIT_SHA', default='development'),
        # Environment tag (production, staging, development)
        environment=env('SENTRY_ENVIRONMENT', default='production'),
        # Send user info (ID only, no PII)
        send_default_pii=False,
        # Filter out health check endpoints from performance monitoring
        before_send_transaction=lambda event, hint: None if event.get('transaction') == '/health/' else event,
    )
    