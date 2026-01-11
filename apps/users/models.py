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
        ("light", "Light"),
        ("dark", "Dark"),
        ("faith", "Christian Faith"),
        ("sports", "Sports & Performance"),
        ("nature", "Animals & Nature"),
        ("outdoors", "Outdoors & Adventure"),
        ("minimal", "Minimal / Life Focus"),
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

    # Theme settings
    theme = models.CharField(
        max_length=20,
        choices=THEME_CHOICES,
        default="minimal",
    )
    accent_color = models.CharField(
        max_length=7,
        blank=True,
        help_text="Custom hex color to override theme accent",
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
        'nutrition': {'label': 'Nutrition & Food', 'default': True, 'icon': '🥗'},
        'fasting': {'label': 'Fasting', 'default': True, 'icon': '🍽️'},
        'sleep': {'label': 'Sleep Tracking', 'default': True, 'icon': '😴'},
        'providers': {'label': 'Medical Providers', 'default': True, 'icon': '🏥'},
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
        help_text="Default Bible translation ID for Scripture lookup (e.g., 'de4e12af7f28f599-02' for KJV)",
    )

    # Onboarding status
    has_completed_onboarding = models.BooleanField(default=False)

    # Dismissed intro banners (tracks which module intros user has dismissed)
    # Format: ["journal", "health", "organize", "goals", "faith", "dashboard"]
    dismissed_intro_banners = models.JSONField(
        default=list,
        blank=True,
        help_text="List of module intro banners the user has dismissed",
    )

    # What's New popup preference
    show_whats_new = models.BooleanField(
        default=True,
        help_text="Show 'What's New' popup when new features are released",
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
        ("16:8", "16:8 Intermittent Fasting"),
        ("18:6", "18:6 Extended Fast"),
        ("20:4", "20:4 Warrior Diet"),
        ("OMAD", "OMAD (One Meal A Day)"),
        ("24h", "24 Hour Fast"),
        ("36h", "36 Hour Extended Fast"),
        ("custom", "Custom"),
    ]

    FASTING_TYPE_DESCRIPTIONS = {
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
        """Check if user has a weight goal set."""
        return self.weight_goal is not None

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
        """
        Calculate progress toward weight goal.
        Returns dict with current_weight, goal, progress_percent, remaining, on_track.
        """
        from apps.health.models import WeightEntry

        if not self.has_weight_goal:
            return None

        latest_weight = WeightEntry.objects.filter(
            user=self.user, status='active'
        ).order_by('-recorded_at').first()

        if not latest_weight:
            return {
                'current_weight': None,
                'goal': float(self.weight_goal),
                'unit': self.weight_goal_unit,
                'target_date': self.weight_goal_target_date,
                'progress_percent': 0,
                'remaining': None,
                'on_track': None,
            }

        # Get current weight in the goal's unit
        if self.weight_goal_unit == 'lb':
            current = latest_weight.value_in_lb
        else:
            current = latest_weight.value_in_kg

        goal = float(self.weight_goal)

        # Get starting weight (first entry after setting goal or just first entry)
        starting_weight = WeightEntry.objects.filter(
            user=self.user, status='active'
        ).order_by('recorded_at').first()

        if starting_weight:
            if self.weight_goal_unit == 'lb':
                start = starting_weight.value_in_lb
            else:
                start = starting_weight.value_in_kg
        else:
            start = current

        # Calculate progress
        total_change_needed = start - goal
        change_so_far = start - current

        if abs(total_change_needed) < 0.1:
            progress_percent = 100
        elif total_change_needed != 0:
            progress_percent = min(100, max(0, (change_so_far / total_change_needed) * 100))
        else:
            progress_percent = 100 if abs(current - goal) < 0.5 else 0

        remaining = current - goal

        # Determine if on track for target date
        on_track = None
        if self.weight_goal_target_date:
            from django.utils import timezone
            today = timezone.now().date()
            if self.weight_goal_target_date > today:
                days_remaining = (self.weight_goal_target_date - today).days
                if abs(remaining) <= 0.5:
                    on_track = True
                elif days_remaining > 0 and abs(remaining) > 0:
                    # Check if recent trend supports reaching goal
                    on_track = progress_percent >= 50 or remaining < abs(total_change_needed) / 2

        return {
            'current_weight': round(current, 1),
            'goal': goal,
            'unit': self.weight_goal_unit,
            'target_date': self.weight_goal_target_date,
            'progress_percent': round(progress_percent, 1),
            'remaining': round(remaining, 1) if remaining else 0,
            'on_track': on_track,
            'direction': 'lose' if remaining > 0 else 'gain' if remaining < 0 else 'maintain',
        }

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
