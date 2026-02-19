"""
Whole Life Journey - User Models

Project: Whole Life Journey
Path: apps/users/models.py
Purpose: Custom user model, preferences, and authentication-related models

Description:
    Defines the custom User model that uses email for authentication
    (no username field), UserPreferences for storing all personalization
    settings, TermsAcceptance for version-tracked terms of service,
    and WebAuthnCredential for biometric login support.

Key Models:
    - User: Custom user with email as unique identifier, avatar support
    - UserManager: Custom manager for email-based user creation
    - UserPreferences: Theme, modules, AI settings, timezone, notifications
    - TermsAcceptance: Tracks which terms version each user accepted
    - WebAuthnCredential: Stores biometric credentials for passwordless login

Design Notes:
    - User model uses AbstractBaseUser for full customization
    - UserPreferences is auto-created via signal when User is created
    - One-to-one relationship between User and UserPreferences
    - Soft delete via UserOwnedModel is NOT used here (users are not soft-deleted)

Dependencies:
    - django.contrib.auth.models for authentication base classes
    - apps.ai.models for CoachingStyle foreign key

Copyright:
    (c) Whole Life Journey. All rights reserved.
    This code is proprietary and may not be copied, modified, or distributed
    without explicit permission.
"""

import datetime
import secrets
import uuid

from django.conf import settings
from django.contrib.auth.models import AbstractBaseUser, BaseUserManager, PermissionsMixin
from django.db import models
from django.utils import timezone


def user_avatar_path(instance, filename):
    """Generate upload path for user avatars."""
    # File will be uploaded to MEDIA_ROOT/avatars/user_<id>/<filename>
    ext = filename.split('.')[-1]
    return f'avatars/user_{instance.id}/avatar.{ext}'


class UserManager(BaseUserManager):
    """
    Custom user manager for email-based authentication.
    """
    def create_user(self, email, password=None, **extra_fields):
        """Create and return a regular user with an email and password."""
        if not email:
            raise ValueError("The Email field must be set")

        email = self.normalize_email(email)
        user = self.model(email=email, **extra_fields)
        user.set_password(password)
        user.save(using=self._db)
        return user

    def create_superuser(self, email, password=None, **extra_fields):
        extra_fields.setdefault("is_staff", True)
        extra_fields.setdefault("is_superuser", True)
        extra_fields.setdefault("is_active", True)

        if extra_fields.get("is_staff") is not True:
            raise ValueError("Superuser must have is_staff=True.")
        if extra_fields.get("is_superuser") is not True:
            raise ValueError("Superuser must have is_superuser=True.")

        return self.create_user(email, password, **extra_fields)


class User(AbstractBaseUser, PermissionsMixin):
    """
    Custom User model using email for authentication.
    
    No username field - email is the unique identifier.
    """

    email = models.EmailField(
        verbose_name="email address",
        max_length=255,
        unique=True,
    )
    first_name = models.CharField(max_length=150, blank=True)
    last_name = models.CharField(max_length=150, blank=True)
    
    # Avatar image
    avatar = models.ImageField(
        upload_to=user_avatar_path,
        blank=True,
        null=True,
        help_text="Profile picture (optional)",
    )

    # Date of birth for age verification (COPPA compliance)
    date_of_birth = models.DateField(
        null=True,
        blank=True,
        help_text="Date of birth for age verification (must be 13+ to use service)",
    )
    
    # App review account flag (bypasses MFA and security checks for Apple reviewers)
    is_app_review_account = models.BooleanField(
        default=False,
        help_text="App review demo account - bypasses MFA and security checks.",
    )

    is_staff = models.BooleanField(
        default=False,
        help_text="Designates whether the user can log into the admin site.",
    )
    is_active = models.BooleanField(
        default=True,
        help_text="Designates whether this user should be treated as active.",
    )

    date_joined = models.DateTimeField(default=timezone.now)

    objects = UserManager()

    USERNAME_FIELD = "email"
    REQUIRED_FIELDS = []

    class Meta:
        verbose_name = "user"
        verbose_name_plural = "users"

    def __str__(self):
        return self.email

    def get_full_name(self):
        """Return the first_name plus the last_name, with a space in between."""
        full_name = f"{self.first_name} {self.last_name}".strip()
        return full_name or self.email

    def get_short_name(self):
        """Return the short name for the user."""
        return self.first_name or self.email.split("@")[0]
    
    def get_initials(self):
        """Return user's initials for avatar fallback."""
        if self.first_name and self.last_name:
            return f"{self.first_name[0]}{self.last_name[0]}".upper()
        elif self.first_name:
            return self.first_name[0].upper()
        else:
            return self.email[0].upper()

    @property
    def has_accepted_current_terms(self):
        """Check if user has accepted the current version of terms."""
        current_version = settings.WLJ_SETTINGS.get("TERMS_VERSION", "1.0")
        try:
            acceptance = self.terms_acceptances.latest("accepted_at")
            return acceptance.terms_version == current_version
        except TermsAcceptance.DoesNotExist:
            return False


class UserPreferences(models.Model):
    """
    User preferences for personalization.
    
    Includes:
    - Theme selection
    - Accent color override
    - Module toggles (Journal, Faith, Health, Goals, Finances, Relationships)
    - AI features toggle
    - Location for weather
    - Dashboard configuration
    """

    THEME_CHOICES = [
        # 10 Personality-Based Themes
        ("scholar", "Scholar"),
        ("momentum", "Momentum"),
        ("wanderer", "Wanderer"),
        ("creature", "Creature"),
        ("sanctuary", "Sanctuary"),
        ("zen", "Zen"),
        ("electric", "Electric"),
        ("coastal", "Coastal"),
        ("ember", "Ember"),
        ("midnight", "Midnight"),
        # Custom theme (user-defined colors)
        ("custom", "Custom"),
    ]

    GENDER_CHOICES = [
        ("male", "Male"),
        ("female", "Female"),
        ("prefer_not_to_say", "Prefer not to say"),
    ]

    # AI_COACHING_STYLE_CHOICES - Now loaded dynamically from database
    # See apps.ai.models.CoachingStyle

    # IANA timezone names - required for PostgreSQL compatibility
    # Note: Legacy US/Eastern format is not recognized by PostgreSQL
    TIMEZONE_CHOICES = [
        ("America/New_York", "Eastern Time (US/Eastern)"),
        ("America/Chicago", "Central Time (US/Central)"),
        ("America/Denver", "Mountain Time (US/Mountain)"),
        ("America/Los_Angeles", "Pacific Time (US/Pacific)"),
        ("America/Anchorage", "Alaska Time"),
        ("Pacific/Honolulu", "Hawaii Time"),
        ("UTC", "UTC (Coordinated Universal Time)"),
    ]

    # Mapping for converting legacy timezone names to IANA format
    TIMEZONE_LEGACY_MAP = {
        "US/Eastern": "America/New_York",
        "US/Central": "America/Chicago",
        "US/Mountain": "America/Denver",
        "US/Pacific": "America/Los_Angeles",
    }

    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="preferences",
    )

    # Gender (used for personalized health features like cycle tracking)
    # Note: null=True allows existing users to skip gender selection.
    # Code checking gender must handle None (no gender set) gracefully.
    # Cycle tracking features should check: if prefs.gender == 'female'
    gender = models.CharField(
        max_length=20,
        choices=GENDER_CHOICES,
        blank=True,
        null=True,
        help_text="Used to personalize health features such as cycle tracking",
    )

    # Theme settings
    theme = models.CharField(
        max_length=20,
        choices=THEME_CHOICES,
        default="sanctuary",
    )
    accent_color = models.CharField(
        max_length=7,
        blank=True,
        help_text="Custom hex color to override theme accent",
    )
    # Custom theme colors (used when theme='custom')
    custom_primary = models.CharField(
        max_length=7,
        blank=True,
        default="",
        help_text="Custom primary/header color (hex)",
    )
    custom_accent = models.CharField(
        max_length=7,
        blank=True,
        default="",
        help_text="Custom accent color (hex)",
    )
    custom_background = models.CharField(
        max_length=7,
        blank=True,
        default="",
        help_text="Custom background color (hex)",
    )
    custom_surface = models.CharField(
        max_length=7,
        blank=True,
        default="",
        help_text="Custom surface/card color (hex)",
    )
    custom_text = models.CharField(
        max_length=7,
        blank=True,
        default="",
        help_text="Custom text color (hex)",
    )

    # Navigation behavior (mobile)
    hide_nav_on_scroll = models.BooleanField(
        default=False,
        help_text="Hide navigation bars when scrolling down on mobile (show on scroll up)",
    )

    # Navigation behavior (desktop)
    desktop_nav_collapsed = models.BooleanField(
        default=False,
        help_text="Collapse the desktop left rail to icons only",
    )

    # ===================
    # MODULE TOGGLES
    # ===================
    
    # Core Modules (always available)
    journal_enabled = models.BooleanField(
        default=True,
        help_text="Enable Journal module for daily reflections and entries",
    )
    
    # Faith Module
    faith_enabled = models.BooleanField(
        default=True,
        help_text="Enable Faith module with Scripture, prayers, and faith-aware content",
    )
    
    # Health Module
    health_enabled = models.BooleanField(
        default=True,
        help_text="Enable Health module for tracking weight, fasting, heart rate, and glucose",
    )
    
    # Life Module
    life_enabled = models.BooleanField(
        default=True,
        help_text="Enable Life module for projects, tasks, calendar, inventory, pets, recipes, and documents",
    )
    
    # Purpose Module
    purpose_enabled = models.BooleanField(
        default=True,
        help_text="Enable Purpose module for annual direction, goals, intentions, and reflections",
    )
    
    # Goals Module (Coming Soon)
    goals_enabled = models.BooleanField(
        default=False,
        help_text="Enable Goals module for setting and tracking personal goals",
    )
    
    # Finances Module (Coming Soon)
    finances_enabled = models.BooleanField(
        default=False,
        help_text="Enable Finances module for budget tracking and financial goals",
    )
    
    # Relationships Module (Coming Soon)
    relationships_enabled = models.BooleanField(
        default=False,
        help_text="Enable Relationships module for tracking connections and interactions",
    )
    
    # Habits Module (Coming Soon)
    habits_enabled = models.BooleanField(
        default=False,
        help_text="Enable Habits module for building and tracking daily habits",
    )

    # Capture Module
    capture_enabled = models.BooleanField(
        default=True,
        help_text="Enable Capture module for audio recording and transcription",
    )

    # ===================
    # SUB-FEATURE TOGGLES
    # ===================
    # These JSON fields allow users to enable/disable specific features within each module.
    # All features default to True (enabled). The structure is {"feature_key": True/False}

    # Health sub-features: weight, fasting, medicine, workouts, nutrition, heart_rate, glucose
    health_features = models.JSONField(
        default=dict,
        blank=True,
        help_text="Sub-feature toggles for Health module",
    )

    # Organize (Life) sub-features: tasks, calendar, projects, inventory, pets, recipes, documents, significant_events
    organize_features = models.JSONField(
        default=dict,
        blank=True,
        help_text="Sub-feature toggles for Organize module",
    )

    # Goals (Purpose) sub-features: goals, annual_direction, intentions, reflections
    goals_features = models.JSONField(
        default=dict,
        blank=True,
        help_text="Sub-feature toggles for Goals module",
    )

    # Faith sub-features: prayers, scripture, memory_verses, devotionals
    faith_features = models.JSONField(
        default=dict,
        blank=True,
        help_text="Sub-feature toggles for Faith module",
    )

    # Reading plan difficulty level preference
    READING_PLAN_DIFFICULTY_CHOICES = [
        ("beginner", "Beginner - New to Bible study"),
        ("intermediate", "Intermediate - Familiar but want more context"),
        ("advanced", "Advanced - Deep dive with scholarly insights"),
    ]
    reading_plan_difficulty = models.CharField(
        max_length=20,
        choices=READING_PLAN_DIFFICULTY_CHOICES,
        default="intermediate",
        help_text="Preferred difficulty level for reading plan commentary",
    )

    # Journal sub-features: mood_tracking, tags, ai_reflections
    journal_features = models.JSONField(
        default=dict,
        blank=True,
        help_text="Sub-feature toggles for Journal module",
    )

    # Sub-feature defaults and metadata
    # These define what features exist and their default states
    HEALTH_FEATURES = {
        'weight': {'label': 'Weight Tracking', 'default': True, 'icon': '⚖️'},
        'heart_rate': {'label': 'Heart Rate', 'default': True, 'icon': '❤️'},
        'blood_pressure': {'label': 'Blood Pressure', 'default': True, 'icon': '🩺'},
        'blood_oxygen': {'label': 'Blood Oxygen', 'default': True, 'icon': '💨'},
        'glucose': {'label': 'Glucose', 'default': True, 'icon': '🩸'},
        'medicine': {'label': 'Medicine Tracker', 'default': True, 'icon': '💊'},
        'workouts': {'label': 'Workouts & Fitness', 'default': True, 'icon': '🏋️'},
        'steps': {'label': 'Steps Tracking', 'default': True, 'icon': '👟'},
        'sleep': {'label': 'Sleep Tracking', 'default': True, 'icon': '😴'},
        'nutrition': {'label': 'Nutrition & Food', 'default': True, 'icon': '🥗'},
        'fasting': {'label': 'Fasting', 'default': True, 'icon': '🍽️'},
        'providers': {'label': 'Medical Providers', 'default': True, 'icon': '🏥'},
        # Advanced metrics (default off - opt-in for users who track these)
        'hrv': {'label': 'Heart Rate Variability', 'default': False, 'icon': '💓'},
        'vo2_max': {'label': 'VO2 Max', 'default': False, 'icon': '🫁'},
        'respiratory_rate': {'label': 'Respiratory Rate', 'default': False, 'icon': '🌬️'},
        'body_temperature': {'label': 'Body Temperature', 'default': False, 'icon': '🌡️'},
        'caffeine': {'label': 'Caffeine Tracking', 'default': False, 'icon': '☕'},
        'mindful_minutes': {'label': 'Mindful Minutes', 'default': False, 'icon': '🧘'},
        'activity_details': {'label': 'Activity Details', 'default': False, 'icon': '🏃'},
    }

    ORGANIZE_FEATURES = {
        'tasks': {'label': 'Tasks', 'default': True, 'icon': '✅'},
        'calendar': {'label': 'Calendar & Events', 'default': True, 'icon': '📅'},
        'projects': {'label': 'Projects', 'default': True, 'icon': '📁'},
        'inventory': {'label': 'Home Inventory', 'default': True, 'icon': '📦'},
        'pets': {'label': 'Pets', 'default': True, 'icon': '🐾'},
        'recipes': {'label': 'Recipes', 'default': True, 'icon': '🍳'},
        'maintenance': {'label': 'Home Maintenance', 'default': True, 'icon': '🔧'},
        'documents': {'label': 'Documents', 'default': True, 'icon': '📄'},
        'significant_events': {'label': 'Significant Events', 'default': True, 'icon': '🎂'},
    }

    GOALS_FEATURES = {
        'goals': {'label': 'Life Goals', 'default': True, 'icon': '🎯'},
        'habit_goals': {'label': 'Habit Goals', 'default': True, 'icon': '🔁'},
        'annual_direction': {'label': 'Yearly Focus', 'default': True, 'icon': '🧭'},
        'intentions': {'label': 'Intentions', 'default': True, 'icon': '💭'},
        'reflections': {'label': 'Goal Reflections', 'default': True, 'icon': '🪞'},
    }

    FAITH_FEATURES = {
        'scripture': {'label': 'Scripture Reading', 'default': True, 'icon': '📖'},
        'reading_plans': {'label': 'Reading Plans', 'default': True, 'icon': '📚'},
        'study_tools': {'label': 'Study Tools', 'default': True, 'icon': '✏️'},
        'prayers': {'label': 'Prayer List', 'default': True, 'icon': '🙏'},
        'milestones': {'label': 'Faith Milestones', 'default': True, 'icon': '🏆'},
        'reflections': {'label': 'Faith Reflections', 'default': True, 'icon': '🪞'},
        'memory_verses': {'label': 'Memory Verses', 'default': True, 'icon': '💬'},
        'devotionals': {'label': 'Devotionals', 'default': True, 'icon': '✝️'},
    }

    JOURNAL_FEATURES = {
        'prompts': {'label': 'Writing Prompts', 'default': True, 'icon': '💡'},
        'mood_tracking': {'label': 'Mood Tracking', 'default': True, 'icon': '😊'},
        'tags': {'label': 'Tags & Categories', 'default': True, 'icon': '🏷️'},
        'ai_reflections': {'label': 'AI Reflections', 'default': True, 'icon': '🤖'},
    }

    def is_feature_enabled(self, module: str, feature: str) -> bool:
        """
        Check if a specific sub-feature is enabled.

        Args:
            module: One of 'health', 'organize', 'goals', 'faith', 'journal'
            feature: The feature key (e.g., 'weight', 'medicine', 'tasks')

        Returns:
            True if the feature is enabled (defaults to True if not explicitly set)
        """
        # First check if the parent module is enabled
        module_enabled_map = {
            'health': self.health_enabled,
            'organize': self.life_enabled,
            'goals': self.purpose_enabled,
            'faith': self.faith_enabled,
            'journal': self.journal_enabled,
        }

        if not module_enabled_map.get(module, True):
            return False

        # Get the features dict and defaults for this module
        features_map = {
            'health': (self.health_features, self.HEALTH_FEATURES),
            'organize': (self.organize_features, self.ORGANIZE_FEATURES),
            'goals': (self.goals_features, self.GOALS_FEATURES),
            'faith': (self.faith_features, self.FAITH_FEATURES),
            'journal': (self.journal_features, self.JOURNAL_FEATURES),
        }

        features_dict, defaults = features_map.get(module, ({}, {}))
        if not features_dict:
            features_dict = {}

        # Check if feature exists in defaults
        if feature not in defaults:
            return True  # Unknown features default to enabled

        # Return the user's setting, or the default if not set
        return features_dict.get(feature, defaults[feature]['default'])

    def get_enabled_features(self, module: str) -> list:
        """
        Get a list of enabled feature keys for a module.

        Args:
            module: One of 'health', 'organize', 'goals', 'faith', 'journal'

        Returns:
            List of enabled feature keys
        """
        features_map = {
            'health': self.HEALTH_FEATURES,
            'organize': self.ORGANIZE_FEATURES,
            'goals': self.GOALS_FEATURES,
            'faith': self.FAITH_FEATURES,
            'journal': self.JOURNAL_FEATURES,
        }

        defaults = features_map.get(module, {})
        return [key for key in defaults.keys() if self.is_feature_enabled(module, key)]

    def set_feature_enabled(self, module: str, feature: str, enabled: bool):
        """
        Enable or disable a specific sub-feature.

        Args:
            module: One of 'health', 'organize', 'goals', 'faith', 'journal'
            feature: The feature key
            enabled: True to enable, False to disable
        """
        features_attr_map = {
            'health': 'health_features',
            'organize': 'organize_features',
            'goals': 'goals_features',
            'faith': 'faith_features',
            'journal': 'journal_features',
        }

        attr_name = features_attr_map.get(module)
        if not attr_name:
            return

        features_dict = getattr(self, attr_name) or {}
        features_dict[feature] = enabled
        setattr(self, attr_name, features_dict)

    # AI Features
    ai_enabled = models.BooleanField(
        default=False,
        help_text="Enable AI-powered insights and reflections",
    )

    # AI Data Sharing Consent (Security Fix C-3)
    # Users must explicitly consent to having their data processed by AI
    ai_data_consent = models.BooleanField(
        default=False,
        help_text="User has consented to AI processing of their personal data (journal entries, health data, etc.)",
    )
    ai_data_consent_date = models.DateTimeField(
        null=True,
        blank=True,
        help_text="Date when user consented to AI data processing",
    )

    ai_coaching_style = models.CharField(
        max_length=50,
        default='supportive',
        help_text='AI coaching style key (loaded from CoachingStyle model)',
    )

    # AI Personal Profile - user-provided context for personalized AI responses
    ai_profile = models.TextField(
        blank=True,
        default='',
        max_length=2000,
        help_text='Personal details for AI personalization (age, family, interests, goals, health conditions, etc.)',
    )

    # AI Profile nudge settings - track when user has dismissed the profile reminder
    ai_profile_nudge_dismissed = models.BooleanField(
        default=False,
        help_text="User has permanently dismissed the AI profile setup nudge",
    )
    ai_profile_nudge_snoozed_until = models.DateTimeField(
        null=True,
        blank=True,
        help_text="If set, hide the AI profile nudge until this datetime (for 'remind me later')",
    )

    # AI Personal Context - automatically learned facts about the user from conversations
    # This is encrypted at rest for privacy. Users can view and edit this in settings.
    # Format: Human-readable text, one fact per line (e.g., "Your parents divorced when you were young")
    _ai_personal_context = models.TextField(
        blank=True,
        default='',
        db_column='ai_personal_context',
        help_text='Encrypted: Facts learned about the user from AI conversations for personalized responses',
    )

    @property
    def ai_personal_context(self) -> str:
        """Get decrypted personal context."""
        if not self._ai_personal_context:
            return ''
        from apps.core.encryption import decrypt_personal_data_safe
        decrypted, success = decrypt_personal_data_safe(self._ai_personal_context)
        return decrypted if success else ''

    @ai_personal_context.setter
    def ai_personal_context(self, value: str):
        """Set and encrypt personal context."""
        if not value:
            self._ai_personal_context = ''
            return
        from apps.core.encryption import encrypt_personal_data
        self._ai_personal_context = encrypt_personal_data(value)

    # ===================
    # PERSONAL ASSISTANT MODULE
    # ===================
    # Personal Assistant is a separate module that requires AI Features to be enabled.
    # It provides deeper AI integration with daily priorities, coaching, and accountability.
    personal_assistant_enabled = models.BooleanField(
        default=False,
        help_text="Enable Personal Assistant for AI-powered daily guidance, priorities, and coaching",
    )

    # Personal Assistant Consent (separate from general AI consent)
    # Required because the Personal Assistant has deeper access to user data
    personal_assistant_consent = models.BooleanField(
        default=False,
        help_text="User consents to Personal Assistant accessing journal entries, tasks, goals, health data for personalized coaching",
    )
    personal_assistant_consent_date = models.DateTimeField(
        null=True,
        blank=True,
        help_text="Date when user consented to Personal Assistant data access",
    )

    # Personal Assistant Confirmation Preference
    # When enabled, the assistant asks for confirmation before logging data
    assistant_confirm_actions = models.BooleanField(
        default=False,
        help_text="Require confirmation before AI assistant logs health data (default: log immediately)",
    )

    # Chief of Staff Display Name
    # User-configurable name for the CoS (e.g., "Max", "Jarvis")
    # If blank, defaults to "Chief of Staff"
    cos_display_name = models.CharField(
        max_length=50,
        default='',
        blank=True,
        help_text="Custom display name for the Chief of Staff (leave blank for default)",
    )

    def get_cos_name(self):
        """Return the user's chosen CoS name, or 'Chief of Staff' if not set."""
        return self.cos_display_name.strip() or 'Chief of Staff'

    # ===================
    # PROACTIVE CHECK-INS
    # ===================
    # These control whether the assistant proactively sends interactive check-in messages
    # in the chat (e.g., "Did you take your 9:00am medicine yet?")
    assistant_proactive_checkins = models.BooleanField(
        default=True,
        help_text="Enable proactive check-in messages in assistant chat",
    )
    assistant_medicine_checkins = models.BooleanField(
        default=True,
        help_text="Proactive medicine dose reminders in chat (requires proactive checkins)",
    )
    assistant_workout_checkins = models.BooleanField(
        default=True,
        help_text="Proactive workout reminders in chat (requires proactive checkins)",
    )
    assistant_journal_checkins = models.BooleanField(
        default=True,
        help_text="Proactive journal reminders in chat (requires proactive checkins)",
    )
    assistant_mood_checkins = models.BooleanField(
        default=True,
        help_text="Proactive mood check-ins after difficult days (requires proactive checkins)",
    )

    # Location for weather (manual entry)
    location_city = models.CharField(max_length=100, blank=True)
    location_country = models.CharField(max_length=100, blank=True)
    timezone = models.CharField(
        max_length=50,
        default="UTC",
        help_text="User's timezone for date/time display",
    )

    # Dashboard configuration (JSON field for flexibility)
    dashboard_config = models.JSONField(
        default=dict,
        blank=True,
        help_text="Dashboard tile layout and visibility settings",
    )

    # Hobbies/interests for accent personalization
    hobbies = models.JSONField(
        default=list,
        blank=True,
        help_text="List of user's hobbies/interests for personalization",
    )

    # Faith settings
    default_bible_translation = models.CharField(
        max_length=50,
        blank=True,
        default="",
        help_text="Default Bible translation ID for Scripture lookup (e.g., '3034' for BSB)",
    )

    # Onboarding status
    has_completed_onboarding = models.BooleanField(default=False)

    # Dashboard setup status - tracks if user has gone through dashboard customization
    dashboard_setup_complete = models.BooleanField(
        default=False,
        help_text="Whether user has completed dashboard tile customization setup",
    )

    # Dismissed intro banners (tracks which module intros user has dismissed)
    # Format: ["journal", "health", "organize", "goals", "faith", "dashboard"]
    dismissed_intro_banners = models.JSONField(
        default=list,
        blank=True,
        help_text="List of module intro banners the user has dismissed",
    )

    # Dismissed quarterly reviews
    # Format: ["2026-Q1", "2026-Q2", ...] - quarters that user has dismissed the review for
    dismissed_quarterly_reviews = models.JSONField(
        default=list,
        blank=True,
        help_text="List of quarterly reviews the user has dismissed (e.g., '2026-Q1')",
    )

    # Development notice modal
    # Shows after 48 hours to remind users we're still building
    development_notice_seen_at = models.DateTimeField(
        null=True,
        blank=True,
        help_text="When the user saw the development notice modal",
    )

    # What's New popup preference
    show_whats_new = models.BooleanField(
        default=True,
        help_text="Show 'What's New' popup when new features are released",
    )

    # Goal deadline badges preference
    show_goal_deadline_badges = models.BooleanField(
        default=True,
        help_text="Show deadline badges on goals (Due in X days, Past target date, etc.)",
    )

    # Search history for suggestions
    search_history = models.JSONField(
        default=list,
        blank=True,
        help_text="List of recent search queries (max 10 items)",
    )

    # Biometric/Face ID login preference
    biometric_login_enabled = models.BooleanField(
        default=False,
        help_text="Enable Face ID, Touch ID, or device biometrics for quick login",
    )

    # ===================
    # SMS NOTIFICATIONS
    # ===================
    # Phone number and verification
    phone_number = models.CharField(
        max_length=20,
        blank=True,
        help_text="Phone number in E.164 format (e.g., +1XXXXXXXXXX)",
    )
    phone_verified = models.BooleanField(
        default=False,
        help_text="Has the phone number been verified via SMS code?",
    )
    phone_verified_at = models.DateTimeField(
        null=True,
        blank=True,
        help_text="When the phone was verified",
    )

    # SMS master toggle and consent
    sms_enabled = models.BooleanField(
        default=False,
        help_text="Master toggle for SMS notifications",
    )
    sms_consent = models.BooleanField(
        default=False,
        help_text="User has consented to receive SMS notifications",
    )
    sms_consent_date = models.DateTimeField(
        null=True,
        blank=True,
        help_text="When user consented to SMS notifications",
    )

    # Category preferences (what to text about)
    sms_medicine_reminders = models.BooleanField(
        default=True,
        help_text="Send SMS reminders for medicine doses",
    )
    sms_medicine_refill_alerts = models.BooleanField(
        default=True,
        help_text="Send SMS alerts when medicine supply is low",
    )
    sms_task_reminders = models.BooleanField(
        default=True,
        help_text="Send SMS reminders for task due dates",
    )
    sms_event_reminders = models.BooleanField(
        default=True,
        help_text="Send SMS reminders for calendar events",
    )
    sms_prayer_reminders = models.BooleanField(
        default=False,
        help_text="Send daily prayer reminders",
    )
    sms_fasting_reminders = models.BooleanField(
        default=False,
        help_text="Send fasting window reminders",
    )
    sms_significant_event_reminders = models.BooleanField(
        default=True,
        help_text="Send SMS reminders for significant events (birthdays, anniversaries)",
    )
    sms_milestone_reminders = models.BooleanField(
        default=True,
        help_text="Send SMS reminders for approaching goal milestones",
    )

    # Quiet hours
    sms_quiet_hours_enabled = models.BooleanField(
        default=True,
        help_text="Respect quiet hours for SMS notifications",
    )
    sms_quiet_start = models.TimeField(
        default=datetime.time(22, 0),
        help_text="Start of quiet hours (no SMS)",
    )
    sms_quiet_end = models.TimeField(
        default=datetime.time(7, 0),
        help_text="End of quiet hours",
    )

    # =============================
    # IN-APP & EMAIL NOTIFICATIONS
    # =============================
    # Master toggles
    notifications_enabled = models.BooleanField(
        default=True,
        help_text="Master toggle for in-app notifications",
    )
    email_notifications_enabled = models.BooleanField(
        default=True,
        help_text="Master toggle for email notifications",
    )

    # Email notification frequency
    EMAIL_FREQUENCY_CHOICES = [
        ("immediate", "Immediate (as they occur)"),
        ("daily_digest", "Daily Digest"),
    ]
    email_notification_frequency = models.CharField(
        max_length=20,
        choices=EMAIL_FREQUENCY_CHOICES,
        default="daily_digest",
        help_text="How often to receive email notifications",
    )

    # Global reminder time for reading plans
    notification_reminder_time = models.TimeField(
        default=datetime.time(7, 0),
        help_text="Daily reminder time for reading plans and other scheduled notifications",
    )

    # One-time notification setup popup
    notification_setup_shown = models.BooleanField(
        default=False,
        help_text="Has the notification setup popup been shown to this user?",
    )

    # Per-category in-app notification toggles (default: ON for new users)
    notify_inapp_medicine = models.BooleanField(
        default=True,
        help_text="In-app notifications for medicine reminders",
    )
    notify_inapp_task = models.BooleanField(
        default=True,
        help_text="In-app notifications for task due dates",
    )
    notify_inapp_event = models.BooleanField(
        default=True,
        help_text="In-app notifications for calendar events",
    )
    notify_inapp_prayer = models.BooleanField(
        default=True,
        help_text="In-app notifications for prayer reminders",
    )
    notify_inapp_reading_plan = models.BooleanField(
        default=True,
        help_text="In-app notifications for reading plan reminders",
    )
    notify_inapp_milestone = models.BooleanField(
        default=True,
        help_text="In-app notifications for goal milestones",
    )
    notify_inapp_significant_event = models.BooleanField(
        default=True,
        help_text="In-app notifications for significant events",
    )
    notify_inapp_finance = models.BooleanField(
        default=True,
        help_text="In-app notifications for finance alerts",
    )
    notify_inapp_journal = models.BooleanField(
        default=True,
        help_text="In-app notifications for journal prompts",
    )
    notify_inapp_capture = models.BooleanField(
        default=True,
        help_text="In-app notifications for capture processing completion",
    )

    # Per-category email notification toggles (default: ON for new users)
    notify_email_medicine = models.BooleanField(
        default=True,
        help_text="Email notifications for medicine reminders",
    )
    notify_email_task = models.BooleanField(
        default=True,
        help_text="Email notifications for task due dates",
    )
    notify_email_event = models.BooleanField(
        default=True,
        help_text="Email notifications for calendar events",
    )
    notify_email_prayer = models.BooleanField(
        default=True,
        help_text="Email notifications for prayer reminders",
    )
    notify_email_reading_plan = models.BooleanField(
        default=True,
        help_text="Email notifications for reading plan reminders",
    )
    notify_email_milestone = models.BooleanField(
        default=True,
        help_text="Email notifications for goal milestones",
    )
    notify_email_significant_event = models.BooleanField(
        default=True,
        help_text="Email notifications for significant events",
    )
    notify_email_finance = models.BooleanField(
        default=True,
        help_text="Email notifications for finance alerts",
    )
    notify_email_journal = models.BooleanField(
        default=True,
        help_text="Email notifications for journal prompts",
    )
    notify_email_capture = models.BooleanField(
        default=True,
        help_text="Email notifications for capture processing completion",
    )

    # ========================================
    # INTELLIGENCE NOTIFICATION SETTINGS (DNE)
    # ========================================
    intelligence_inapp_enabled = models.BooleanField(
        default=True,
        help_text="In-app notifications for intelligence outputs (guidance, briefings, reports)",
    )
    intelligence_email_enabled = models.BooleanField(
        default=False,
        help_text="Email notifications for intelligence outputs (opt-in, off by default)",
    )
    intelligence_sms_enabled = models.BooleanField(
        default=False,
        help_text="SMS notifications for intelligence outputs (opt-in, off by default)",
    )
    intelligence_push_enabled = models.BooleanField(
        default=False,
        help_text="Push notifications for intelligence outputs (opt-in, off by default)",
    )
    intelligence_max_per_day = models.PositiveIntegerField(
        default=6,
        help_text="Maximum intelligence notifications per day",
    )
    intelligence_max_per_hour = models.PositiveIntegerField(
        default=2,
        help_text="Maximum intelligence notifications per hour",
    )

    # ===================
    # WEIGHT GOALS
    # ===================
    weight_goal = models.DecimalField(
        max_digits=5,
        decimal_places=1,
        null=True,
        blank=True,
        help_text="Target weight goal",
    )
    weight_goal_unit = models.CharField(
        max_length=2,
        choices=[("lb", "Pounds"), ("kg", "Kilograms")],
        default="lb",
        help_text="Unit for weight goal",
    )
    weight_goal_target_date = models.DateField(
        null=True,
        blank=True,
        help_text="Target date to achieve weight goal",
    )

    # ===================
    # NUTRITION GOALS
    # ===================
    daily_calorie_goal = models.PositiveIntegerField(
        null=True,
        blank=True,
        help_text="Daily caloric intake goal",
    )
    protein_percentage = models.PositiveSmallIntegerField(
        null=True,
        blank=True,
        help_text="Target percentage of calories from protein (0-100)",
    )
    carbs_percentage = models.PositiveSmallIntegerField(
        null=True,
        blank=True,
        help_text="Target percentage of calories from carbohydrates (0-100)",
    )
    fat_percentage = models.PositiveSmallIntegerField(
        null=True,
        blank=True,
        help_text="Target percentage of calories from fat (0-100)",
    )

    # ===================
    # FASTING PREFERENCES
    # ===================
    FASTING_TYPE_CHOICES = [
        ("none", "No Fasting"),
        ("16:8", "16:8 Intermittent Fasting"),
        ("18:6", "18:6 Extended Fast"),
        ("20:4", "20:4 Warrior Diet"),
        ("OMAD", "OMAD (One Meal A Day)"),
        ("24h", "24 Hour Fast"),
        ("36h", "36 Hour Extended Fast"),
        ("custom", "Custom"),
    ]

    FASTING_TYPE_DESCRIPTIONS = {
        "none": "You don't practice intermittent fasting. The fasting tracker will not be shown in your dashboard.",
        "16:8": "The most popular fasting method. Fast for 16 hours and eat within an 8-hour window. Example: Eat between 12pm-8pm.",
        "18:6": "A more advanced fast. 18 hours of fasting with a 6-hour eating window. Example: Eat between 1pm-7pm.",
        "20:4": "Also known as the Warrior Diet. 20 hours fasting with a 4-hour eating window. Example: Eat between 4pm-8pm.",
        "OMAD": "One Meal A Day. Fast for approximately 23 hours and consume all daily calories in a single meal.",
        "24h": "A full 24-hour fast, typically done once or twice per week. Example: Dinner to dinner.",
        "36h": "An extended fast of 36 hours. More advanced, typically done occasionally for deeper benefits.",
        "custom": "Set your own fasting duration and schedule.",
    }

    default_fasting_type = models.CharField(
        max_length=10,
        choices=FASTING_TYPE_CHOICES,
        default="16:8",
        help_text="Your preferred fasting schedule. This will be pre-selected when starting a new fast.",
    )

    # ===================
    # FAITH ONLY PLAN TRACKING
    # ===================
    # Tracks when user selected Faith Only plan and upgrade prompt schedule
    faith_only_selected_at = models.DateTimeField(
        null=True,
        blank=True,
        help_text="When the user selected the Faith Only plan (used for upgrade prompt scheduling)",
    )

    # Upgrade prompt schedule tracking (Week 1, Month 2, Month 3, then stop)
    faith_only_upgrade_week1_shown = models.BooleanField(
        default=False,
        help_text="Has the Week 1 upgrade prompt been shown?",
    )
    faith_only_upgrade_week1_shown_at = models.DateTimeField(
        null=True,
        blank=True,
        help_text="When the Week 1 upgrade prompt was shown",
    )
    faith_only_upgrade_month2_shown = models.BooleanField(
        default=False,
        help_text="Has the Month 2 upgrade prompt been shown?",
    )
    faith_only_upgrade_month2_shown_at = models.DateTimeField(
        null=True,
        blank=True,
        help_text="When the Month 2 upgrade prompt was shown",
    )
    faith_only_upgrade_month3_shown = models.BooleanField(
        default=False,
        help_text="Has the Month 3 (final) upgrade prompt been shown?",
    )
    faith_only_upgrade_month3_shown_at = models.DateTimeField(
        null=True,
        blank=True,
        help_text="When the Month 3 upgrade prompt was shown",
    )

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "user preferences"
        verbose_name_plural = "user preferences"

    def __str__(self):
        return f"Preferences for {self.user.email}"

    @property
    def timezone_iana(self):
        """
        Get the IANA timezone string, converting legacy US/Eastern format if needed.

        PostgreSQL requires IANA timezone names (e.g., 'America/New_York').
        This property handles legacy timezone values that may have been stored
        in the old US/Eastern format.
        """
        tz = self.timezone or "UTC"
        # Convert legacy timezone names to IANA format
        return self.TIMEZONE_LEGACY_MAP.get(tz, tz)

    @property
    def has_weight_goal(self):
        """Check if user has a weight goal set. Delegates to HealthProfile."""
        from apps.health.models import HealthProfile
        try:
            return self.user.health_profile.has_weight_goal
        except HealthProfile.DoesNotExist:
            return False

    @property
    def has_nutrition_goals(self):
        """Check if user has nutrition goals set."""
        return self.daily_calorie_goal is not None

    @property
    def macro_percentages_valid(self):
        """Check if macro percentages add up to 100%."""
        if self.protein_percentage is None or self.carbs_percentage is None or self.fat_percentage is None:
            return True  # If not all set, skip validation
        total = (self.protein_percentage or 0) + (self.carbs_percentage or 0) + (self.fat_percentage or 0)
        return total == 100

    def get_weight_progress(self):
        """Delegates to HealthProfile.get_weight_progress()."""
        from apps.health.models import HealthProfile
        try:
            return self.user.health_profile.get_weight_progress()
        except HealthProfile.DoesNotExist:
            return None

    def get_nutrition_progress(self, date=None):
        """
        Calculate today's nutrition progress toward goals.
        Returns dict with current totals, goals, and progress percentages.
        """
        from django.utils import timezone
        from apps.health.models import FoodEntry, DailyNutritionSummary
        from apps.core.utils import get_user_today

        if not self.has_nutrition_goals:
            return None

        if date is None:
            date = get_user_today(self.user) if self.user_id else timezone.now().date()

        # Get today's nutrition data
        summary = DailyNutritionSummary.objects.filter(
            user=self.user,
            summary_date=date,
            status='active'
        ).first()

        if not summary:
            # Calculate from food entries if no summary
            entries = FoodEntry.objects.filter(
                user=self.user,
                logged_date=date,
                status='active'
            )
            total_calories = sum(float(e.total_calories) for e in entries)
            total_protein_g = sum(float(e.total_protein_g) for e in entries)
            total_carbs_g = sum(float(e.total_carbohydrates_g) for e in entries)
            total_fat_g = sum(float(e.total_fat_g) for e in entries)
        else:
            total_calories = float(summary.total_calories)
            total_protein_g = float(summary.total_protein_g)
            total_carbs_g = float(summary.total_carbohydrates_g)
            total_fat_g = float(summary.total_fat_g)

        # Calculate goal targets in grams from percentages
        calorie_goal = self.daily_calorie_goal or 2000
        protein_goal_g = None
        carbs_goal_g = None
        fat_goal_g = None

        if self.protein_percentage is not None:
            # Protein: 4 calories per gram
            protein_goal_g = round((calorie_goal * self.protein_percentage / 100) / 4)
        if self.carbs_percentage is not None:
            # Carbs: 4 calories per gram
            carbs_goal_g = round((calorie_goal * self.carbs_percentage / 100) / 4)
        if self.fat_percentage is not None:
            # Fat: 9 calories per gram
            fat_goal_g = round((calorie_goal * self.fat_percentage / 100) / 9)

        # Calculate progress percentages
        calorie_progress = round((total_calories / calorie_goal) * 100, 1) if calorie_goal else 0
        protein_progress = round((total_protein_g / protein_goal_g) * 100, 1) if protein_goal_g else None
        carbs_progress = round((total_carbs_g / carbs_goal_g) * 100, 1) if carbs_goal_g else None
        fat_progress = round((total_fat_g / fat_goal_g) * 100, 1) if fat_goal_g else None

        return {
            'date': date,
            'calories': {
                'current': round(total_calories),
                'goal': calorie_goal,
                'remaining': calorie_goal - round(total_calories),
                'progress_percent': min(100, calorie_progress),
            },
            'protein': {
                'current_g': round(total_protein_g, 1),
                'goal_g': protein_goal_g,
                'goal_percent': self.protein_percentage,
                'progress_percent': min(100, protein_progress) if protein_progress else None,
            },
            'carbs': {
                'current_g': round(total_carbs_g, 1),
                'goal_g': carbs_goal_g,
                'goal_percent': self.carbs_percentage,
                'progress_percent': min(100, carbs_progress) if carbs_progress else None,
            },
            'fat': {
                'current_g': round(total_fat_g, 1),
                'goal_g': fat_goal_g,
                'goal_percent': self.fat_percentage,
                'progress_percent': min(100, fat_progress) if fat_progress else None,
            },
        }


class WebAuthnCredential(models.Model):
    """
    Store WebAuthn credentials for biometric login (Face ID, Touch ID, etc).

    Each user can have multiple credentials (e.g., Face ID on phone, Touch ID on laptop).
    The credential_id and public_key are used to verify authentication assertions.
    """

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="webauthn_credentials",
    )

    # Credential identifiers
    credential_id = models.BinaryField(
        help_text="Unique identifier for this credential (from authenticator)",
    )
    credential_id_b64 = models.CharField(
        max_length=500,
        unique=True,
        help_text="Base64-encoded credential ID for lookups",
    )

    # Public key for verification
    public_key = models.BinaryField(
        help_text="COSE public key from authenticator",
    )

    # Sign count for replay attack prevention
    sign_count = models.PositiveIntegerField(
        default=0,
        help_text="Signature counter from authenticator",
    )

    # Device info for user to identify their credentials
    device_name = models.CharField(
        max_length=100,
        blank=True,
        help_text="User-friendly name for this device (e.g., 'iPhone 15')",
    )

    # Metadata
    created_at = models.DateTimeField(auto_now_add=True)
    last_used_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        verbose_name = "WebAuthn credential"
        verbose_name_plural = "WebAuthn credentials"
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.user.email} - {self.device_name or 'Unknown device'}"


class MFAEmailCode(models.Model):
    """
    Store temporary email codes for MFA verification.

    Codes are 6-digit numeric strings, valid for 10 minutes.
    Rate limited to 5 requests per hour per user.
    """

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="mfa_email_codes",
    )

    code = models.CharField(
        max_length=6,
        help_text="6-digit verification code",
    )

    created_at = models.DateTimeField(auto_now_add=True)

    expires_at = models.DateTimeField(
        help_text="When this code expires (10 minutes from creation)",
    )

    used = models.BooleanField(
        default=False,
        help_text="Whether this code has been used",
    )

    used_at = models.DateTimeField(
        null=True,
        blank=True,
        help_text="When the code was used",
    )

    ip_address = models.GenericIPAddressField(
        null=True,
        blank=True,
        help_text="IP address that requested the code",
    )

    class Meta:
        verbose_name = "MFA email code"
        verbose_name_plural = "MFA email codes"
        ordering = ["-created_at"]

    def __str__(self):
        status = "used" if self.used else ("expired" if self.is_expired else "valid")
        return f"{self.user.email} - {self.code} ({status})"

    @property
    def is_expired(self):
        """Check if the code has expired."""
        return timezone.now() > self.expires_at

    @property
    def is_valid(self):
        """Check if the code is still valid (not used and not expired)."""
        return not self.used and not self.is_expired

    def mark_used(self):
        """Mark the code as used."""
        self.used = True
        self.used_at = timezone.now()
        self.save(update_fields=["used", "used_at"])

    @classmethod
    def generate_code(cls):
        """Generate a random 6-digit code."""
        return f"{secrets.randbelow(1000000):06d}"

    @classmethod
    def create_for_user(cls, user, ip_address=None):
        """
        Create a new MFA code for a user.

        Returns tuple of (code_object, error_message).
        Error message is None if successful, or string if rate limited.
        """
        # Rate limiting: max 5 codes per hour
        one_hour_ago = timezone.now() - datetime.timedelta(hours=1)
        recent_count = cls.objects.filter(
            user=user,
            created_at__gte=one_hour_ago,
        ).count()

        if recent_count >= 5:
            return None, "Too many code requests. Please wait before requesting another code."

        # Invalidate any existing unused codes
        cls.objects.filter(user=user, used=False).update(used=True)

        # Create new code
        code = cls.generate_code()
        expires_at = timezone.now() + datetime.timedelta(minutes=10)

        mfa_code = cls.objects.create(
            user=user,
            code=code,
            expires_at=expires_at,
            ip_address=ip_address,
        )

        return mfa_code, None

    @classmethod
    def verify_code(cls, user, code):
        """
        Verify an MFA code for a user.

        Returns True if code is valid and marks it as used.
        Returns False if code is invalid, expired, or already used.
        """
        try:
            mfa_code = cls.objects.get(
                user=user,
                code=code,
                used=False,
            )
            if mfa_code.is_valid:
                mfa_code.mark_used()
                return True
            return False
        except cls.DoesNotExist:
            return False


class TermsAcceptance(models.Model):
    """
    Track when users accept terms of service.
    
    Each time terms are updated (new version), users must re-accept.
    This creates an audit trail of acceptances.
    """

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="terms_acceptances",
    )
    terms_version = models.CharField(max_length=20)
    accepted_at = models.DateTimeField(auto_now_add=True)
    ip_address = models.GenericIPAddressField(null=True, blank=True)
    user_agent = models.TextField(blank=True)

    class Meta:
        ordering = ["-accepted_at"]
        verbose_name = "terms acceptance"
        verbose_name_plural = "terms acceptances"

    def __str__(self):
        return f"{self.user.email} accepted v{self.terms_version} on {self.accepted_at}"


class IPBlocklist(models.Model):
    """
    Store blocked IP addresses for security purposes.

    Supports individual IPs, CIDR ranges, and temporary blocks.
    Used to prevent abuse from known bad actors.
    """

    BLOCK_TYPE_CHOICES = [
        ("manual", "Manual Block"),
        ("automated", "Automated Block"),
        ("temporary", "Temporary Block"),
    ]

    ip_address = models.CharField(
        max_length=45,
        db_index=True,
        help_text="IPv4 or IPv6 address to block",
    )
    cidr_range = models.CharField(
        max_length=50,
        blank=True,
        help_text="Optional CIDR notation for range blocks (e.g., /24)",
    )
    block_type = models.CharField(
        max_length=20,
        choices=BLOCK_TYPE_CHOICES,
        default="manual",
    )
    reason = models.TextField(
        blank=True,
        help_text="Reason for blocking this IP",
    )
    created_at = models.DateTimeField(default=timezone.now)
    expires_at = models.DateTimeField(
        null=True,
        blank=True,
        help_text="When this block expires (null = permanent)",
    )
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="ip_blocks_created",
        help_text="Admin who created this block",
    )

    class Meta:
        db_table = "users_ip_blocklist"
        verbose_name = "IP blocklist entry"
        verbose_name_plural = "IP blocklist entries"
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.ip_address} ({self.block_type})"

    @classmethod
    def is_blocked(cls, ip_address: str) -> bool:
        """
        Check if an IP address is currently blocked.

        Args:
            ip_address: The IP address to check

        Returns:
            True if the IP is blocked, False otherwise
        """
        now = timezone.now()

        # Check for exact IP match that hasn't expired
        blocked = cls.objects.filter(
            ip_address=ip_address
        ).filter(
            models.Q(expires_at__isnull=True) | models.Q(expires_at__gt=now)
        ).exists()

        return blocked


class DisposableEmailDomain(models.Model):
    """
    Store known disposable/temporary email domains.

    Used to prevent signups from throwaway email services
    that are commonly used for spam or fraud.
    """

    domain = models.CharField(
        max_length=255,
        unique=True,
        db_index=True,
        help_text="Domain name (e.g., 'tempmail.com')",
    )
    added_at = models.DateTimeField(default=timezone.now)
    source = models.CharField(
        max_length=50,
        default="manual",
        help_text="How this domain was added (manual, import, api)",
    )
    confirmed = models.BooleanField(
        default=True,
        help_text="Whether this domain is confirmed as disposable",
    )

    class Meta:
        db_table = "users_disposable_email_domain"
        verbose_name = "Disposable email domain"
        verbose_name_plural = "Disposable email domains"
        ordering = ["domain"]

    def __str__(self):
        return self.domain

    @classmethod
    def is_disposable(cls, email: str) -> bool:
        """
        Check if an email address uses a disposable domain.

        Args:
            email: The email address to check

        Returns:
            True if the domain is in the disposable list, False otherwise
        """
        if not email or "@" not in email:
            return False

        # Extract domain from email
        domain = email.lower().split("@")[-1]

        # Check if domain is in confirmed disposable list
        return cls.objects.filter(domain=domain, confirmed=True).exists()


class AllowedInternationalEmail(models.Model):
    """
    Whitelist for international email addresses allowed to sign up.

    By default, signups are geo-blocked to USA-only. This model allows
    specific email addresses from international locations to bypass the
    geo-block. Use this to whitelist friends, family, or known contacts
    before they attempt to sign up.
    """

    email = models.EmailField(
        unique=True,
        db_index=True,
        help_text="Email address allowed to sign up from outside the USA",
    )
    name = models.CharField(
        max_length=100,
        blank=True,
        help_text="Friendly name for reference (e.g., 'Mom', 'Friend John')",
    )
    note = models.TextField(
        blank=True,
        help_text="Optional note about why this email was whitelisted",
    )
    added_at = models.DateTimeField(default=timezone.now)
    added_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="international_email_whitelist",
        help_text="Admin who added this whitelist entry",
    )
    used_at = models.DateTimeField(
        null=True,
        blank=True,
        help_text="When this email was used to sign up",
    )

    class Meta:
        db_table = "users_allowed_international_email"
        verbose_name = "Allowed international email"
        verbose_name_plural = "Allowed international emails"
        ordering = ["-added_at"]

    def __str__(self):
        if self.name:
            return f"{self.email} ({self.name})"
        return self.email

    @classmethod
    def is_allowed(cls, email: str) -> bool:
        """
        Check if an email address is whitelisted for international signup.

        Args:
            email: The email address to check

        Returns:
            True if the email is in the whitelist, False otherwise
        """
        if not email:
            return False
        return cls.objects.filter(email__iexact=email.strip()).exists()

    @classmethod
    def mark_used(cls, email: str):
        """
        Mark a whitelisted email as used (signup completed).

        Args:
            email: The email address that was used to sign up
        """
        cls.objects.filter(email__iexact=email.strip()).update(used_at=timezone.now())


class ModuleDefinition(models.Model):
    """
    System-defined module registry for mobile navigation.

    Each module represents a major life area in the app (Journal, Health, Faith, etc.).
    This model stores the canonical list of modules with their metadata.
    Users can enable/disable and reorder modules via UserModulePreference.
    """

    # Unique identifier for the module (matches existing *_enabled fields)
    slug = models.CharField(
        max_length=50,
        unique=True,
        help_text="Unique identifier (e.g., 'journal', 'health', 'faith')",
    )

    # Display name
    name = models.CharField(
        max_length=50,
        help_text="Display name shown in navigation (e.g., 'Journal', 'Health')",
    )

    # Description for settings/help
    description = models.CharField(
        max_length=200,
        blank=True,
        help_text="Brief description of what this module does",
    )

    # SVG icon path data (for inline SVG rendering)
    icon_svg = models.TextField(
        help_text="SVG path data for the module icon",
    )

    # URL route name (Django URL name, e.g., 'journal:home')
    route_name = models.CharField(
        max_length=100,
        help_text="Django URL name for the module home (e.g., 'journal:home')",
    )

    # Default sort order (used for new users)
    default_order = models.PositiveIntegerField(
        default=0,
        help_text="Default display order for new users",
    )

    # Whether this module is available (admin can disable globally)
    is_active = models.BooleanField(
        default=True,
        help_text="Whether this module is available to users",
    )

    # Field name in UserPreferences for the *_enabled toggle
    # e.g., 'journal_enabled', 'health_enabled'
    preference_field = models.CharField(
        max_length=50,
        blank=True,
        help_text="UserPreferences field name for enable toggle (e.g., 'journal_enabled')",
    )

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['default_order', 'name']
        verbose_name = "Module Definition"
        verbose_name_plural = "Module Definitions"

    def __str__(self):
        return self.name


class UserModulePreference(models.Model):
    """
    User-specific module ordering and visibility preferences.

    Each user has one record per module, tracking:
    - Whether they have the module enabled
    - Their custom sort order for the module
    - When they last changed the setting

    The bottom navigation bar shows:
    - Home (always first)
    - Up to 4 enabled modules in user's order
    - More (always last)
    """

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="module_preferences",
    )

    module = models.ForeignKey(
        ModuleDefinition,
        on_delete=models.CASCADE,
        related_name="user_preferences",
    )

    # Whether user has this module enabled
    is_enabled = models.BooleanField(
        default=True,
        help_text="Whether this module appears in navigation",
    )

    # User's custom sort order (lower = higher priority)
    sort_order = models.PositiveIntegerField(
        default=0,
        help_text="User's custom display order (lower numbers appear first)",
    )

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['sort_order', 'module__default_order']
        unique_together = ['user', 'module']
        verbose_name = "User Module Preference"
        verbose_name_plural = "User Module Preferences"

    def __str__(self):
        status = "enabled" if self.is_enabled else "disabled"
        return f"{self.user.email} - {self.module.name} ({status}, order={self.sort_order})"

    @classmethod
    def get_user_modules(cls, user, enabled_only=True, limit=None):
        """
        Get modules for a user in their preferred order.

        Args:
            user: The user
            enabled_only: If True, only return enabled modules
            limit: Maximum number to return (for bottom nav, use 4)

        Returns:
            QuerySet of UserModulePreference objects with module data
        """
        qs = cls.objects.filter(
            user=user,
            module__is_active=True,
        ).select_related('module')

        if enabled_only:
            qs = qs.filter(is_enabled=True)

        qs = qs.order_by('sort_order', 'module__default_order')

        if limit:
            qs = qs[:limit]

        return qs

    @classmethod
    def initialize_for_user(cls, user):
        """
        Create default module preferences for a new user.

        Creates a UserModulePreference for each active ModuleDefinition,
        using the module's default_order and checking the user's
        existing *_enabled preferences.
        """
        modules = ModuleDefinition.objects.filter(is_active=True)

        for module in modules:
            # Check if user already has this module preference
            if cls.objects.filter(user=user, module=module).exists():
                continue

            # Check user's existing preference field if it exists
            is_enabled = True
            if module.preference_field and hasattr(user, 'preferences'):
                try:
                    prefs = user.preferences
                    is_enabled = getattr(prefs, module.preference_field, True)
                except Exception:
                    pass

            cls.objects.create(
                user=user,
                module=module,
                is_enabled=is_enabled,
                sort_order=module.default_order,
            )


class SignupAttempt(models.Model):
    """
    Log all signup attempts for audit and fraud detection.

    Stores hashed PII (email, IP, fingerprint) rather than raw values
    to enable pattern matching while preserving privacy.

    Used for:
    - Rate limiting by IP or email
    - Fraud detection and risk scoring
    - Audit trail for security investigations
    - Analytics on signup funnel
    """

    STATUS_CHOICES = [
        ("pending", "Pending"),
        ("allowed", "Allowed"),
        ("challenged", "Challenged"),
        ("blocked", "Blocked"),
        ("completed", "Completed"),
        ("abandoned", "Abandoned"),
    ]

    BLOCK_REASON_CHOICES = [
        ("rate_limited", "Rate Limited"),
        ("high_risk", "High Risk Score"),
        ("disposable_email", "Disposable Email"),
        ("honeypot", "Honeypot Triggered"),
        ("blocklist", "IP/Email Blocklist"),
        ("captcha_failed", "CAPTCHA Failed"),
    ]

    RISK_LEVEL_CHOICES = [
        ("unknown", "Unknown"),
        ("low", "Low"),
        ("medium", "Medium"),
        ("high", "High"),
        ("critical", "Critical"),
    ]

    id = models.UUIDField(
        primary_key=True,
        default=uuid.uuid4,
        editable=False,
    )

    # Hashed PII for privacy-preserving storage
    email_hash = models.CharField(
        max_length=64,
        help_text="SHA-256 hash of normalized email address",
    )
    ip_hash = models.CharField(
        max_length=64,
        help_text="SHA-256 hash of IP address",
    )
    fingerprint_hash = models.CharField(
        max_length=64,
        blank=True,
        help_text="SHA-256 hash of device fingerprint data",
    )

    # Additional metadata (not hashed - not directly identifying)
    user_agent = models.CharField(
        max_length=500,
        blank=True,
        help_text="Browser user agent string",
    )
    country_code = models.CharField(
        max_length=2,
        blank=True,
        help_text="Two-letter country code from IP geolocation",
    )

    # Risk assessment
    risk_score = models.FloatField(
        default=0.0,
        help_text="Composite risk score (0.0 = safe, 1.0 = high risk)",
    )
    risk_level = models.CharField(
        max_length=20,
        choices=RISK_LEVEL_CHOICES,
        default="unknown",
        help_text="Categorized risk level",
    )

    # Individual risk components
    captcha_score = models.FloatField(
        null=True,
        blank=True,
        help_text="reCAPTCHA v3 score (0.0-1.0, higher is more human)",
    )
    ip_reputation_score = models.FloatField(
        null=True,
        blank=True,
        help_text="IP reputation score from external service",
    )
    email_risk_score = models.FloatField(
        null=True,
        blank=True,
        help_text="Email risk score (disposable, typosquat, etc.)",
    )
    behavioral_score = models.FloatField(
        null=True,
        blank=True,
        help_text="Behavioral analysis score (timing, mouse movement)",
    )
    device_score = models.FloatField(
        null=True,
        blank=True,
        help_text="Device fingerprint uniqueness/trust score",
    )

    # Status tracking
    status = models.CharField(
        max_length=20,
        choices=STATUS_CHOICES,
        default="pending",
        help_text="Current status of signup attempt",
    )
    block_reason = models.CharField(
        max_length=30,
        choices=BLOCK_REASON_CHOICES,
        blank=True,
        help_text="Reason for blocking if status is 'blocked'",
    )

    # Verification flags
    captcha_verified = models.BooleanField(
        default=False,
        help_text="CAPTCHA challenge passed",
    )
    phone_verified = models.BooleanField(
        default=False,
        help_text="Phone number verified via SMS",
    )
    email_verified = models.BooleanField(
        default=False,
        help_text="Email address verified via link",
    )

    # Timestamps
    created_at = models.DateTimeField(
        default=timezone.now,
        db_index=True,
        help_text="When the signup attempt was initiated",
    )
    completed_at = models.DateTimeField(
        null=True,
        blank=True,
        help_text="When the signup was completed (user created)",
    )

    # Link to created user (if signup completed)
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="signup_attempts",
        help_text="User created from this attempt (if completed)",
    )

    class Meta:
        db_table = "users_signup_attempt"
        ordering = ["-created_at"]
        verbose_name = "Signup attempt"
        verbose_name_plural = "Signup attempts"
        indexes = [
            models.Index(fields=["created_at", "status"]),
            models.Index(fields=["ip_hash", "created_at"]),
            models.Index(fields=["email_hash", "created_at"]),
        ]

    def __str__(self):
        return f"SignupAttempt {self.id} - {self.status}"


class AccountDeletionAudit(models.Model):
    """
    Audit trail for account deletions.

    This model stores a permanent record of when accounts are deleted,
    what data was removed, and why. This is required for:
    - GDPR compliance (proving erasure was performed)
    - Apple App Store requirements (account deletion)
    - Legal/audit purposes

    Note: This record does NOT contain any user PII after deletion.
    The user's email is hashed for fraud detection, not identification.
    """

    # Hashed email for fraud detection (can detect if same person re-registers)
    email_hash = models.CharField(
        max_length=64,
        db_index=True,
        help_text="SHA-256 hash of the deleted user's email (for fraud detection)",
    )

    # Basic metadata about the deleted account (non-PII)
    user_id_was = models.PositiveIntegerField(
        help_text="The original user ID (for reference, user no longer exists)",
    )
    account_created_at = models.DateTimeField(
        help_text="When the account was originally created",
    )
    account_deleted_at = models.DateTimeField(
        default=timezone.now,
        help_text="When the account was deleted",
    )

    # How the deletion was initiated
    DELETION_METHOD_CHOICES = [
        ("user_self_service", "User Self-Service"),
        ("admin_request", "Admin Request"),
        ("gdpr_request", "GDPR Right to Erasure"),
        ("legal_request", "Legal/Court Order"),
        ("fraud_account", "Fraud Account Removal"),
        ("inactive_cleanup", "Inactive Account Cleanup"),
    ]
    deletion_method = models.CharField(
        max_length=32,
        choices=DELETION_METHOD_CHOICES,
        default="user_self_service",
    )

    # IP address of requester (hashed for privacy but fraud detection)
    ip_hash = models.CharField(
        max_length=64,
        blank=True,
        help_text="SHA-256 hash of IP address that initiated deletion",
    )

    # Summary of what was deleted (no PII, just counts)
    deletion_summary = models.JSONField(
        default=dict,
        help_text="Summary of data deleted: {'journal_entries': 50, 'health_entries': 100, ...}",
    )

    # User's stated reason (optional, free text sanitized of PII)
    reason = models.TextField(
        blank=True,
        help_text="User's stated reason for deletion (optional, sanitized of PII)",
    )

    # Did user download their data first?
    data_exported = models.BooleanField(
        default=False,
        help_text="Whether user downloaded their data before deletion",
    )

    # For audit trail
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "users_account_deletion_audit"
        ordering = ["-account_deleted_at"]
        verbose_name = "Account Deletion Audit"
        verbose_name_plural = "Account Deletion Audits"

    def __str__(self):
        return f"Account Deletion #{self.id} - User {self.user_id_was} deleted {self.account_deleted_at.strftime('%Y-%m-%d')}"

    @classmethod
    def create_audit_record(cls, user, deletion_method, ip_address, reason="", data_exported=False):
        """
        Create an audit record before deleting the user.

        Args:
            user: The User object being deleted
            deletion_method: One of DELETION_METHOD_CHOICES
            ip_address: IP address of the requester
            reason: User's stated reason (will be sanitized)
            data_exported: Whether user downloaded their data

        Returns:
            AccountDeletionAudit instance
        """
        import hashlib

        # Hash email and IP for privacy
        email_hash = hashlib.sha256(user.email.lower().encode()).hexdigest()
        ip_hash = hashlib.sha256(ip_address.encode()).hexdigest() if ip_address else ""

        # Count user's data (before deletion)
        deletion_summary = cls._count_user_data(user)

        return cls.objects.create(
            email_hash=email_hash,
            user_id_was=user.id,
            account_created_at=user.date_joined,
            deletion_method=deletion_method,
            ip_hash=ip_hash,
            deletion_summary=deletion_summary,
            reason=cls._sanitize_reason(reason),
            data_exported=data_exported,
        )

    @staticmethod
    def _count_user_data(user):
        """
        Count all user data that will be deleted.
        Returns dict of model name -> count.
        """
        counts = {}

        # Journal
        try:
            from apps.journal.models import JournalEntry
            counts['journal_entries'] = JournalEntry.all_objects.filter(user=user).count()
        except Exception:
            pass

        # Health
        try:
            from apps.health.models import (
                WeightEntry, StepsEntry, WaterEntry, SleepEntry,
                FastingWindow, Medicine, MedicineLog, WorkoutSession,
                GlucoseEntry, BloodPressureEntry, FoodEntry
            )
            counts['weight_entries'] = WeightEntry.all_objects.filter(user=user).count()
            counts['steps_entries'] = StepsEntry.all_objects.filter(user=user).count()
            counts['water_entries'] = WaterEntry.all_objects.filter(user=user).count()
            counts['sleep_entries'] = SleepEntry.all_objects.filter(user=user).count()
            counts['fasting_windows'] = FastingWindow.all_objects.filter(user=user).count()
            counts['medicines'] = Medicine.all_objects.filter(user=user).count()
            counts['medicine_logs'] = MedicineLog.all_objects.filter(user=user).count()
            counts['workout_sessions'] = WorkoutSession.all_objects.filter(user=user).count()
            counts['glucose_entries'] = GlucoseEntry.all_objects.filter(user=user).count()
            counts['blood_pressure_entries'] = BloodPressureEntry.all_objects.filter(user=user).count()
            counts['food_entries'] = FoodEntry.all_objects.filter(user=user).count()
        except Exception:
            pass

        # Faith
        try:
            from apps.faith.models import PrayerRequest, SavedVerse, BibleStudyNote
            counts['prayer_requests'] = PrayerRequest.all_objects.filter(user=user).count()
            counts['saved_verses'] = SavedVerse.all_objects.filter(user=user).count()
            counts['bible_notes'] = BibleStudyNote.all_objects.filter(user=user).count()
        except Exception:
            pass

        # Life/Organize
        try:
            from apps.life.models import Task, LifeEvent, Project, Document
            counts['tasks'] = Task.all_objects.filter(user=user).count()
            counts['events'] = LifeEvent.all_objects.filter(user=user).count()
            counts['projects'] = Project.all_objects.filter(user=user).count()
            counts['documents'] = Document.all_objects.filter(user=user).count()
        except Exception:
            pass

        # Purpose/Goals
        try:
            from apps.purpose.models import LifeGoal, HabitGoal, Reflection
            counts['life_goals'] = LifeGoal.all_objects.filter(user=user).count()
            counts['habit_goals'] = HabitGoal.all_objects.filter(user=user).count()
            counts['reflections'] = Reflection.all_objects.filter(user=user).count()
        except Exception:
            pass

        # AI
        try:
            from apps.ai.models import AssistantConversation, AssistantMessage
            counts['ai_conversations'] = AssistantConversation.objects.filter(user=user).count()
            counts['ai_messages'] = AssistantMessage.objects.filter(user=user).count()
        except Exception:
            pass

        # Capture
        try:
            from apps.capture.models import CaptureEntry
            counts['capture_entries'] = CaptureEntry.objects.filter(user=user).count()
        except Exception:
            pass

        # Core
        try:
            from apps.core.models import FavoritePage, Notification, CameraScan
            counts['favorites'] = FavoritePage.objects.filter(user=user).count()
            counts['notifications'] = Notification.objects.filter(user=user).count()
            counts['camera_scans'] = CameraScan.all_objects.filter(user=user).count()
        except Exception:
            pass

        # Total non-zero counts
        counts['total_records'] = sum(v for v in counts.values() if isinstance(v, int))

        return counts

    @staticmethod
    def _sanitize_reason(reason):
        """
        Sanitize the deletion reason to remove any potential PII.
        """
        if not reason:
            return ""

        # Limit length
        reason = reason[:500]

        # Remove email patterns
        import re
        reason = re.sub(r'\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b', '[EMAIL REMOVED]', reason)

        # Remove phone patterns
        reason = re.sub(r'\b\d{3}[-.]?\d{3}[-.]?\d{4}\b', '[PHONE REMOVED]', reason)

        return reason


class ExternalLink(models.Model):
    """
    User-defined external links for quick access from the profile dropdown.

    Examples: Patient portal, bank login, favorite websites.
    Links open in a new browser tab.
    """

    MAX_LINKS = 10

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='external_links',
    )
    name = models.CharField(
        max_length=100,
        help_text="Display name for the link (e.g., 'Patient Portal')",
    )
    url = models.URLField(
        max_length=500,
        help_text="Full URL including https:// (e.g., 'https://myportal.com')",
    )
    sort_order = models.IntegerField(
        default=0,
        help_text="Order in which links appear (lower = first)",
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['sort_order', 'created_at']
        verbose_name = "External Link"
        verbose_name_plural = "External Links"

    def __str__(self):
        return f"{self.name} ({self.url})"

    @classmethod
    def get_links_for_user(cls, user, limit=None):
        """Get all external links for a user, ordered by sort_order."""
        qs = cls.objects.filter(user=user)
        if limit:
            qs = qs[:limit]
        return qs

    @classmethod
    def can_add_link(cls, user):
        """Check if user hasn't reached the maximum link count."""
        return cls.objects.filter(user=user).count() < cls.MAX_LINKS
