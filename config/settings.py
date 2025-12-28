"""
Django settings for Whole Life Journey.

A personal life operating system built with calm, clarity, and intention.
"""

import os
from pathlib import Path

import environ

OPENAI_API_KEY = os.environ.get('OPENAI_API_KEY')
OPENAI_MODEL = os.environ.get('OPENAI_MODEL', 'gpt-4o-mini')

# Log OpenAI configuration status at startup
if OPENAI_API_KEY:
    print(f"OpenAI configured with model: {OPENAI_MODEL}")
else:
    print("OpenAI NOT configured - OPENAI_API_KEY not set")

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
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "whitenoise.middleware.WhiteNoiseMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
    "allauth.account.middleware.AccountMiddleware",
    "django_htmx.middleware.HtmxMiddleware",
    "apps.users.middleware.TermsAcceptanceMiddleware",
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
            ],
        },
    },
]

WSGI_APPLICATION = "config.wsgi.application"


# Database
# https://docs.djangoproject.com/en/5.0/ref/settings/#databases

# Database
# Use DATABASE_URL if provided (Railway provides this), otherwise SQLite
DATABASE_URL = env("DATABASE_URL", default="")
if DATABASE_URL:
    DATABASES = {
        "default": env.db("DATABASE_URL"),
    }
else:
    DATABASES = {
        "default": {
            "ENGINE": "django.db.backends.sqlite3",
            "NAME": BASE_DIR / "db.sqlite3",
        }
    }




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
    print(f"Cloudinary configured with cloud_name: {_cloudinary_cloud_name}")

    # Also set CLOUDINARY_STORAGE for django-cloudinary-storage
    CLOUDINARY_STORAGE = {
        "CLOUD_NAME": _cloudinary_cloud_name,
        "API_KEY": _cloudinary_api_key,
        "API_SECRET": _cloudinary_api_secret,
    }
else:
    # Fall back to local storage if Cloudinary is not configured
    print(f"Cloudinary NOT configured - cloud_name: '{_cloudinary_cloud_name}', api_key set: {bool(_cloudinary_api_key)}, api_secret set: {bool(_cloudinary_api_secret)}")
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
        'mail_admins': {
            'level': 'ERROR',
            'filters': ['require_debug_false'],
            'class': 'django.utils.log.AdminEmailHandler',
            'include_html': True,
        },
    },
    'root': {
        'handlers': ['console', 'file_error'],
        'level': 'INFO',
    },
    'loggers': {
        'django': {
            'handlers': ['console', 'file_error'],
            'level': 'INFO',
            'propagate': False,
        },
        'django.request': {
            'handlers': ['console', 'file_error', 'mail_admins'],
            'level': 'ERROR',
            'propagate': False,
        },
        'django.security': {
            'handlers': ['console', 'file_error', 'mail_admins'],
            'level': 'ERROR',
            'propagate': False,
        },
        'cloudinary': {
            'handlers': ['console'],
            'level': 'WARNING',
            'propagate': False,
        },
        'apps': {
            'handlers': ['console', 'file_app', 'file_error'],
            'level': 'DEBUG' if DEBUG else 'INFO',
            'propagate': False,
        },
    },
}


# Custom User Model
AUTH_USER_MODEL = "users.User"


# Django Allauth Configuration
SITE_ID = 1

AUTHENTICATION_BACKENDS = [
    "axes.backends.AxesStandaloneBackend",  # Rate limiting (Security Fix H-3) - must be first
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
ACCOUNT_EMAIL_VERIFICATION = "none"  #"mandatory"
ACCOUNT_LOGIN_ON_PASSWORD_RESET = True

# New django-allauth settings (replacing deprecated ones)
ACCOUNT_LOGIN_METHODS = {"email"}  # Replaces ACCOUNT_AUTHENTICATION_METHOD
ACCOUNT_SIGNUP_FIELDS = ["email*", "password1*", "password2*"]  # Replaces ACCOUNT_EMAIL_REQUIRED, ACCOUNT_USERNAME_REQUIRED, ACCOUNT_SIGNUP_PASSWORD_ENTER_TWICE

LOGIN_REDIRECT_URL = "dashboard:home"
LOGOUT_REDIRECT_URL = "core:landing"
LOGIN_URL = "account_login"


# Crispy Forms
CRISPY_ALLOWED_TEMPLATE_PACKS = "tailwind"
CRISPY_TEMPLATE_PACK = "tailwind"


# Email Configuration
if DEBUG:
    EMAIL_BACKEND = "django.core.mail.backends.console.EmailBackend"
else:
    # Use Resend in production
    EMAIL_BACKEND = "apps.core.email_backends.ResendEmailBackend"
    RESEND_API_KEY = env("RESEND_API_KEY", default="")

DEFAULT_FROM_EMAIL = env("DEFAULT_FROM_EMAIL", default="noreply@wholelifejourney.com")


# Security Settings - ONLY apply in production (when DEBUG is False)
# These settings require HTTPS and will break local development if enabled
if not DEBUG:
    # Only enable SSL redirect if explicitly set (for production)
    SECURE_SSL_REDIRECT = env.bool("SECURE_SSL_REDIRECT", default=True)
    SESSION_COOKIE_SECURE = True
    CSRF_COOKIE_SECURE = True
    SECURE_BROWSER_XSS_FILTER = True
    SECURE_CONTENT_TYPE_NOSNIFF = True
    SECURE_HSTS_SECONDS = 31536000
    SECURE_HSTS_INCLUDE_SUBDOMAINS = True
    SECURE_HSTS_PRELOAD = True
    CSRF_TRUSTED_ORIGINS = [
        "https://wholelifejourney.com",
        "https://www.wholelifejourney.com",
    ]
else:
    # Explicitly disable SSL for local development
    SECURE_SSL_REDIRECT = False
    SESSION_COOKIE_SECURE = False
    CSRF_COOKIE_SECURE = False

# Cookie SameSite attribute (Security Fix M-1)
# Prevents CSRF attacks by restricting cookie sending on cross-site requests
SESSION_COOKIE_SAMESITE = 'Lax'  # 'Lax' allows normal navigation, 'Strict' blocks all cross-site
CSRF_COOKIE_SAMESITE = 'Lax'

# Custom Admin URL Path (Security Fix H-4)
# Moving admin to a non-default path reduces brute force attack surface
ADMIN_URL_PATH = env("ADMIN_URL_PATH", default="wlj-admin")

# Django Axes Configuration (Security Fix H-3)
# Rate limiting for authentication to prevent brute force attacks
AXES_FAILURE_LIMIT = 5  # Lock after 5 failed attempts
AXES_COOLOFF_TIME = 1  # Lock for 1 hour (in hours)
AXES_LOCKOUT_CALLABLE = None  # Use default lockout response
AXES_RESET_ON_SUCCESS = True  # Reset failed attempts on successful login
AXES_ONLY_USER_FAILURES = False  # Track failures per IP address
AXES_LOCK_OUT_BY_COMBINATION_USER_AND_IP = True  # Lock by user+IP combo
AXES_ENABLE_ACCESS_FAILURE_LOG = True  # Log failed attempts
AXES_VERBOSE = True if DEBUG else False  # Verbose logging in dev only


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
    "TERMS_VERSION": "1.0",
}

# Bible API (required for Scripture lookups in Faith module)
# Get your API key at: https://scripture.api.bible/
BIBLE_API_KEY = os.environ.get('BIBLE_API_KEY', '')



# Debug output (remove in production)
if DEBUG:
    print(f"DEBUG = {DEBUG}")
    print(f"ALLOWED_HOSTS = {ALLOWED_HOSTS}")
    print(f"SECURE_SSL_REDIRECT = {SECURE_SSL_REDIRECT}")

# Google Calendar Integration
GOOGLE_CALENDAR_CLIENT_ID = env('GOOGLE_CALENDAR_CLIENT_ID', default='')
GOOGLE_CALENDAR_CLIENT_SECRET = env('GOOGLE_CALENDAR_CLIENT_SECRET', default='')
# Redirect URI is environment-dependent
if DEBUG:
    GOOGLE_CALENDAR_REDIRECT_URI = 'http://localhost:8000/life/calendar/google/callback/'
else:
    GOOGLE_CALENDAR_REDIRECT_URI = env('GOOGLE_CALENDAR_REDIRECT_URI', default='')
    