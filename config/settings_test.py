"""
Test Settings

Override settings for running tests.
Uses simpler configurations that don't require collectstatic.

Usage:
    python manage.py test --settings=config.settings_test

Or set in pytest.ini / setup.cfg if using pytest.
"""

from .settings import *  # noqa: F401, F403

# =============================================================================
# Static Files - Use simple storage (no manifest required)
# =============================================================================
STORAGES = {
    "staticfiles": {
        "BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage",
    },
    "default": {
        "BACKEND": "django.core.files.storage.FileSystemStorage",
    },
}

# =============================================================================
# Database - Use faster in-memory SQLite for tests
# =============================================================================
DATABASES = {
    'default': {
        'ENGINE': 'django.db.backends.sqlite3',
        'NAME': ':memory:',
    }
}

# =============================================================================
# Password Hashing - Use faster hasher for tests
# =============================================================================
PASSWORD_HASHERS = [
    'django.contrib.auth.hashers.MD5PasswordHasher',
]

# =============================================================================
# Email - Use in-memory backend
# =============================================================================
EMAIL_BACKEND = 'django.core.mail.backends.locmem.EmailBackend'

# =============================================================================
# Caching - Use dummy cache
# =============================================================================
CACHES = {
    'default': {
        'BACKEND': 'django.core.cache.backends.dummy.DummyCache',
    }
}

# =============================================================================
# Security - Disable for tests
# =============================================================================
SECURE_SSL_REDIRECT = False
SESSION_COOKIE_SECURE = False
CSRF_COOKIE_SECURE = False

# =============================================================================
# Debug - Enable for better error messages in tests
# =============================================================================
DEBUG = True

# =============================================================================
# Logging - Reduce noise during tests
# =============================================================================
LOGGING = {
    'version': 1,
    'disable_existing_loggers': False,
    'handlers': {
        'null': {
            'class': 'logging.NullHandler',
        },
    },
    'root': {
        'handlers': ['null'],
        'level': 'CRITICAL',
    },
}

# =============================================================================
# Silence system check warnings during tests
# =============================================================================
SILENCED_SYSTEM_CHECKS = [
    'django_recaptcha.recaptcha_test_key_error',  # If using recaptcha
]
