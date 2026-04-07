"""
Whole Life Journey - Core Models

Project: Whole Life Journey
Path: apps/core/models.py
Purpose: Abstract base models and system-wide data models

Description:
    This module defines abstract base classes that provide common functionality
    to all other models in the application, plus system-wide concrete models
    for site configuration, theming, and feature tracking.

Key Responsibilities:
    - TimeStampedModel: Auto-updating created_at/updated_at timestamps
    - SoftDeleteModel: Soft delete with 30-day retention before hard delete
    - UserOwnedModel: User ownership with created_via tracking for AI features
    - SiteConfiguration: Singleton for site-wide settings
    - Theme: Database-driven theme configuration
    - ChoiceCategory/ChoiceOption: Dynamic dropdown options for forms
    - TestRun/TestRunDetail: Test execution history tracking
    - CameraScan: Raw camera input for AI processing
    - ReleaseNote: What's New feature content

Design Patterns:
    - Soft Delete: Records are marked deleted rather than removed, with 30-day
      retention before permanent deletion. Managers filter deleted records
      by default.
    - Singleton: SiteConfiguration uses pk=1 enforcement for single instance
    - Caching: Theme and choice lookups use Django cache for performance

Dependencies:
    - django.conf.settings for AUTH_USER_MODEL and WLJ_SETTINGS
    - django.core.cache for performance optimization
    - django.utils.timezone for datetime handling

Copyright:
    (c) Whole Life Journey. All rights reserved.
    This code is proprietary and may not be copied, modified, or distributed
    without explicit permission.
"""

from django.conf import settings
from django.db import models
from django.utils import timezone


class TimeStampedModel(models.Model):
    """
    Abstract base model that provides self-updating
    created_at and updated_at fields.
    """

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        abstract = True


class SoftDeleteManager(models.Manager):
    """
    Manager that excludes soft-deleted and archived records by default.
    
    Use .all_with_deleted() to include deleted records.
    Use .deleted_only() to get only deleted records.
    Use .archived_only() to get only archived records.
    """

    def get_queryset(self):
        return super().get_queryset().filter(status="active")

    def all_with_deleted(self):
        return super().get_queryset()

    def deleted_only(self):
        return super().get_queryset().filter(status="deleted")

    def archived_only(self):
        return super().get_queryset().filter(status="archived")

    def include_archived(self):
        """Returns active and archived, but not deleted."""
        return super().get_queryset().filter(status__in=["active", "archived"])


class SoftDeleteModel(TimeStampedModel):
    """
    Abstract model that provides soft delete functionality.
    
    Instead of deleting records, they are marked as deleted
    and hidden from normal queries. After 30 days, a background
    job will permanently delete them.
    
    Records can also be archived (hidden but preserved).
    
    Status choices:
    - active: Normal, visible record
    - archived: Hidden from view, but preserved (user chose to hide)
    - deleted: Marked for deletion, 30-day grace period
    """

    STATUS_CHOICES = [
        ("active", "Active"),
        ("archived", "Archived"),
        ("deleted", "Deleted"),
    ]

    status = models.CharField(
        max_length=10,
        choices=STATUS_CHOICES,
        default="active",
        db_index=True,
    )
    deleted_at = models.DateTimeField(null=True, blank=True)

    objects = SoftDeleteManager()
    all_objects = models.Manager()  # Bypass soft delete filter

    class Meta:
        abstract = True

    def soft_delete(self):
        """Mark the record as deleted. Will be hard deleted after 30 days."""
        self.status = "deleted"
        self.deleted_at = timezone.now()
        self.save(update_fields=["status", "deleted_at", "updated_at"])

        # Emit domain event so caches (CoS, SAE) are invalidated.
        # Only emit for user-owned models that have a user attribute.
        _user = getattr(self, 'user', None)
        if _user:
            try:
                from apps.core.events.domain_events import safe_emit_event, EventTypes
                # Use the model's class name to derive a domain-specific event
                _model_name = self.__class__.__name__.lower()
                if _model_name == 'task':
                    safe_emit_event(EventTypes.TASK_DELETED, _user, {
                        "task_id": self.pk, "source": "soft_delete",
                    })
                # For all models: invalidate CoS context
                from apps.ai.readiness_cache import invalidate_cos_context_on_action
                invalidate_cos_context_on_action(_user)
            except Exception:
                pass  # Cache invalidation is best-effort

    def archive(self):
        """Archive the record (hide but preserve)."""
        self.status = "archived"
        self.deleted_at = None
        self.save(update_fields=["status", "deleted_at", "updated_at"])

    def restore(self):
        """Restore a deleted or archived record to active status."""
        self.status = "active"
        self.deleted_at = None
        self.save(update_fields=["status", "deleted_at", "updated_at"])

    @property
    def is_active(self):
        return self.status == "active"

    @property
    def is_archived(self):
        return self.status == "archived"

    @property
    def is_deleted(self):
        return self.status == "deleted"

    @property
    def days_until_permanent_deletion(self):
        """Returns days remaining before permanent deletion, or None if not deleted."""
        if not self.is_deleted or not self.deleted_at:
            return None
        retention_days = settings.WLJ_SETTINGS.get("SOFT_DELETE_RETENTION_DAYS", 30)
        deletion_date = self.deleted_at + timezone.timedelta(days=retention_days)
        remaining = (deletion_date - timezone.now()).days
        return max(0, remaining)


class UserOwnedModel(SoftDeleteModel):
    """
    Abstract model for records that belong to a specific user.

    Combines soft delete with user ownership.
    """

    # Creation source tracking - indicates how the entry was created
    CREATED_VIA_MANUAL = 'manual'
    CREATED_VIA_AI_CAMERA = 'ai_camera'
    CREATED_VIA_IMPORT = 'import'
    CREATED_VIA_API = 'api'
    CREATED_VIA_ROUTINE = 'routine'

    CREATED_VIA_CHOICES = [
        (CREATED_VIA_MANUAL, 'Manual Entry'),
        (CREATED_VIA_AI_CAMERA, 'AI Camera Scan'),
        (CREATED_VIA_IMPORT, 'Data Import'),
        (CREATED_VIA_API, 'API'),
        (CREATED_VIA_ROUTINE, 'Routine Completion'),
    ]

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="%(class)ss",
    )
    created_via = models.CharField(
        max_length=20,
        choices=CREATED_VIA_CHOICES,
        default=CREATED_VIA_MANUAL,
        help_text="How this entry was created",
    )

    class Meta:
        abstract = True

    @property
    def was_created_by_ai(self):
        """Check if this entry was created via AI Camera."""
        return self.created_via == self.CREATED_VIA_AI_CAMERA


class Tag(UserOwnedModel):
    """
    User-defined tags for organizing entries.
    
    Tags can be applied across modules (journal, faith, health, etc.)
    """

    name = models.CharField(max_length=50)
    color = models.CharField(
        max_length=7,
        default="#6b7280",
        help_text="Hex color code for visual distinction",
    )

    class Meta:
        ordering = ["name"]
        unique_together = ["user", "name"]

    def __str__(self):
        return self.name


class Category(models.Model):
    """
    Pre-defined categories for journal entries.
    
    These are system-wide, not user-specific.
    Users can select multiple categories per entry.
    """

    name = models.CharField(max_length=50, unique=True)
    slug = models.SlugField(max_length=50, unique=True)
    description = models.TextField(blank=True)
    icon = models.CharField(
        max_length=50,
        blank=True,
        help_text="Icon filename from static/icons/",
    )
    order = models.PositiveIntegerField(default=0)

    class Meta:
        ordering = ["order", "name"]
        verbose_name_plural = "Categories"

    def __str__(self):
        return self.name

"""
Site Configuration Models

Singleton model for site-wide settings that can be managed through the admin.
"""

from django.db import models
from django.core.cache import cache


class SiteConfiguration(models.Model):
    """
    Singleton model for site-wide configuration.
    
    Only one instance should exist. Use SiteConfiguration.get_solo() to access.
    """
    
    # Branding
    site_name = models.CharField(
        max_length=100,
        default="Whole Life Journey",
        help_text="The name of your site"
    )
    tagline = models.CharField(
        max_length=200,
        default="Your personal life operating system",
        blank=True,
        help_text="A short tagline displayed on the landing page"
    )
    logo = models.ImageField(
        upload_to="site/",
        blank=True,
        null=True,
        help_text="Site logo (recommended size: 200x64 pixels)"
    )
    favicon = models.ImageField(
        upload_to="site/",
        blank=True,
        null=True,
        help_text="Favicon (recommended: 32x32 PNG)"
    )
    
    # Default Settings
    default_theme = models.CharField(
        max_length=50,
        default="minimal",
        help_text="Default theme for new users"
    )
    
    # Feature Toggles
    allow_registration = models.BooleanField(
        default=True,
        help_text="Allow new users to register"
    )
    require_email_verification = models.BooleanField(
        default=False,
        help_text="Require email verification for new accounts"
    )
    
    # Module Defaults
    faith_enabled_by_default = models.BooleanField(
        default=True,
        help_text="Enable Faith module by default for new users"
    )
    
    # Footer & Legal
    footer_text = models.CharField(
        max_length=200,
        default="© 2025 Whole Life Journey. All rights reserved.",
        blank=True
    )
    privacy_policy_url = models.URLField(
        blank=True,
        help_text="Link to privacy policy"
    )
    terms_url = models.URLField(
        blank=True,
        help_text="Link to terms of service"
    )
    
    # Metadata
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        verbose_name = "Site Configuration"
        verbose_name_plural = "Site Configuration"
    
    def __str__(self):
        return "Site Configuration"
    
    def save(self, *args, **kwargs):
        # Ensure only one instance exists
        self.pk = 1
        super().save(*args, **kwargs)
        # Clear cache when saved
        cache.delete('site_configuration')

    @classmethod
    def get_solo(cls):
        """
        Get the single instance of SiteConfiguration.
        Creates one with defaults if it doesn't exist.
        Uses caching for performance.
        If DB is unreachable, returns a default unsaved instance.
        """
        config = cache.get('site_configuration')
        if config is None:
            try:
                config, created = cls.objects.get_or_create(pk=1)
                cache.set('site_configuration', config, 60 * 60)  # Cache for 1 hour
            except Exception:
                # DB connection dead — return an unsaved default instance
                # so callers get safe default values without crashing
                import logging
                logging.getLogger(__name__).warning(
                    "SiteConfiguration.get_solo: DB unavailable, returning defaults"
                )
                return cls()
        return config
    
    @classmethod
    def get_logo_url(cls):
        """Get the logo URL, falling back to static file if not set."""
        config = cls.get_solo()
        if config.logo:
            return config.logo.url
        return None  # Template will fall back to static logo


class Theme(models.Model):
    """
    Theme configuration stored in database.
    
    Allows admins to create and modify themes without code changes.
    """
    
    # Identity
    slug = models.SlugField(
        max_length=50,
        unique=True,
        help_text="Unique identifier (e.g., 'minimal', 'faith')"
    )
    name = models.CharField(
        max_length=100,
        help_text="Display name (e.g., 'Minimal / Life Focus')"
    )
    description = models.CharField(
        max_length=200,
        blank=True,
        help_text="Short description of the theme's feel"
    )
    
    # Colors - Light Mode
    color_primary = models.CharField(
        max_length=7,
        default="#6b7280",
        help_text="Primary color (hex, e.g., #6b7280)"
    )
    color_secondary = models.CharField(
        max_length=7,
        default="#f9fafb",
        help_text="Secondary/background color"
    )
    color_accent = models.CharField(
        max_length=7,
        default="#6366f1",
        help_text="Accent color for buttons, links"
    )
    color_text = models.CharField(
        max_length=7,
        default="#374151",
        help_text="Main text color"
    )
    color_text_muted = models.CharField(
        max_length=7,
        default="#6b7280",
        help_text="Muted/secondary text color"
    )
    color_background = models.CharField(
        max_length=7,
        default="#ffffff",
        help_text="Page background color"
    )
    color_surface = models.CharField(
        max_length=7,
        default="#f3f4f6",
        help_text="Card/surface background color"
    )
    color_border = models.CharField(
        max_length=7,
        default="#e5e7eb",
        help_text="Border color"
    )
    
    # Colors - Dark Mode
    dark_color_primary = models.CharField(
        max_length=7,
        default="#9ca3af",
        help_text="Primary color in dark mode"
    )
    dark_color_secondary = models.CharField(
        max_length=7,
        default="#111827",
        help_text="Secondary color in dark mode"
    )
    dark_color_accent = models.CharField(
        max_length=7,
        default="#818cf8",
        help_text="Accent color in dark mode"
    )
    dark_color_text = models.CharField(
        max_length=7,
        default="#f9fafb",
        help_text="Text color in dark mode"
    )
    dark_color_text_muted = models.CharField(
        max_length=7,
        default="#9ca3af",
        help_text="Muted text in dark mode"
    )
    dark_color_background = models.CharField(
        max_length=7,
        default="#030712",
        help_text="Background in dark mode"
    )
    dark_color_surface = models.CharField(
        max_length=7,
        default="#1f2937",
        help_text="Surface color in dark mode"
    )
    dark_color_border = models.CharField(
        max_length=7,
        default="#374151",
        help_text="Border color in dark mode"
    )
    
    # Status
    is_active = models.BooleanField(
        default=True,
        help_text="Make this theme available to users"
    )
    is_default = models.BooleanField(
        default=False,
        help_text="Use as default theme for new users"
    )
    
    # Ordering
    sort_order = models.PositiveIntegerField(
        default=0,
        help_text="Order in theme selector (lower = first)"
    )
    
    # Metadata
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        ordering = ['sort_order', 'name']
        verbose_name = "Theme"
        verbose_name_plural = "Themes"
    
    def __str__(self):
        return self.name
    
    def save(self, *args, **kwargs):
        # If this is set as default, unset others
        if self.is_default:
            Theme.objects.exclude(pk=self.pk).update(is_default=False)
        super().save(*args, **kwargs)
        # Clear theme cache
        cache.delete('active_themes')
        cache.delete(f'theme_{self.slug}')
    
    @classmethod
    def get_active_themes(cls):
        """Get all active themes, cached."""
        themes = cache.get('active_themes')
        if themes is None:
            themes = list(cls.objects.filter(is_active=True))
            cache.set('active_themes', themes, 60 * 60)
        return themes
    
    @classmethod
    def get_default_theme(cls):
        """Get the default theme."""
        return cls.objects.filter(is_default=True).first()
    
    @classmethod
    def get_by_slug(cls, slug):
        """Get a theme by slug, cached."""
        cache_key = f'theme_{slug}'
        theme = cache.get(cache_key)
        if theme is None:
            theme = cls.objects.filter(slug=slug, is_active=True).first()
            if theme:
                cache.set(cache_key, theme, 60 * 60)
        return theme
    
    def get_css_variables(self, dark_mode=False):
        """Generate CSS custom properties for this theme."""
        if dark_mode:
            return {
                '--color-primary': self.dark_color_primary,
                '--color-secondary': self.dark_color_secondary,
                '--color-accent': self.dark_color_accent,
                '--color-text': self.dark_color_text,
                '--color-text-muted': self.dark_color_text_muted,
                '--color-background': self.dark_color_background,
                '--color-surface': self.dark_color_surface,
                '--color-border': self.dark_color_border,
            }
        return {
            '--color-primary': self.color_primary,
            '--color-secondary': self.color_secondary,
            '--color-accent': self.color_accent,
            '--color-text': self.color_text,
            '--color-text-muted': self.color_text_muted,
            '--color-background': self.color_background,
            '--color-surface': self.color_surface,
            '--color-border': self.color_border,
        }

"""
Dynamic Choice Models

These models allow admins to configure dropdown options
without modifying code.
"""

from django.db import models


class ChoiceCategory(models.Model):
    """
    Categories for grouping choice options.
    
    Examples: mood, milestone_type, prayer_priority, health_metric
    """
    
    slug = models.SlugField(
        max_length=50,
        unique=True,
        help_text="Unique identifier (e.g., 'mood', 'milestone_type')"
    )
    name = models.CharField(
        max_length=100,
        help_text="Display name (e.g., 'Mood', 'Milestone Type')"
    )
    description = models.TextField(
        blank=True,
        help_text="Description of what this category is for"
    )
    
    # Which app/model uses this
    app_label = models.CharField(
        max_length=50,
        blank=True,
        help_text="App that uses this (e.g., 'journal', 'faith', 'health')"
    )
    
    # Is this a system category that shouldn't be deleted?
    is_system = models.BooleanField(
        default=False,
        help_text="System categories cannot be deleted"
    )
    
    created_at = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        ordering = ['name']
        verbose_name = "Choice Category"
        verbose_name_plural = "Choice Categories"
    
    def __str__(self):
        return self.name
    
    def save(self, *args, **kwargs):
        super().save(*args, **kwargs)
        cache.delete(f'choices_{self.slug}')
    
    @classmethod
    def get_choices_for(cls, slug):
        """Get all active choices for a category slug."""
        cache_key = f'choices_{slug}'
        choices = cache.get(cache_key)
        if choices is None:
            try:
                category = cls.objects.get(slug=slug)
                choices = list(
                    category.options.filter(is_active=True)
                    .order_by('sort_order', 'label')
                    .values_list('value', 'label')
                )
                cache.set(cache_key, choices, 60 * 60)  # Cache 1 hour
            except cls.DoesNotExist:
                choices = []
        return choices


class ChoiceOption(models.Model):
    """
    Individual choice options within a category.
    """
    
    category = models.ForeignKey(
        ChoiceCategory,
        on_delete=models.CASCADE,
        related_name='options'
    )
    
    value = models.CharField(
        max_length=50,
        help_text="Value stored in database (e.g., 'happy', 'urgent')"
    )
    label = models.CharField(
        max_length=100,
        help_text="Display label (e.g., 'Happy 😊', 'Urgent')"
    )
    
    # Optional styling
    icon = models.CharField(
        max_length=50,
        blank=True,
        help_text="Emoji or icon class (e.g., '😊', 'fa-smile')"
    )
    color = models.CharField(
        max_length=7,
        blank=True,
        help_text="Color hex code (e.g., '#10b981')"
    )
    
    # Ordering and status
    sort_order = models.PositiveIntegerField(
        default=0,
        help_text="Order in dropdown (lower = first)"
    )
    is_active = models.BooleanField(
        default=True,
        help_text="Show in dropdowns"
    )
    is_default = models.BooleanField(
        default=False,
        help_text="Pre-selected option"
    )
    
    created_at = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        ordering = ['category', 'sort_order', 'label']
        unique_together = ['category', 'value']
        verbose_name = "Choice Option"
        verbose_name_plural = "Choice Options"
    
    def __str__(self):
        return f"{self.category.name}: {self.label}"
    
    def save(self, *args, **kwargs):
        # If this is set as default, unset others in same category
        if self.is_default:
            ChoiceOption.objects.filter(
                category=self.category
            ).exclude(pk=self.pk).update(is_default=False)
        super().save(*args, **kwargs)
        # Clear cache
        cache.delete(f'choices_{self.category.slug}')


# =============================================================================
# Helper functions for getting choices in forms
# =============================================================================

def get_mood_choices():
    """Get mood choices for journal entries."""
    choices = ChoiceCategory.get_choices_for('mood')
    if not choices:
        # Fallback to hardcoded if database is empty
        choices = [
            ('happy', 'Happy 😊'),
            ('grateful', 'Grateful 🙏'),
            ('calm', 'Calm 😌'),
            ('anxious', 'Anxious 😰'),
            ('sad', 'Sad 😢'),
            ('angry', 'Angry 😠'),
            ('tired', 'Tired 😴'),
            ('energetic', 'Energetic ⚡'),
            ('hopeful', 'Hopeful 🌟'),
            ('neutral', 'Neutral 😐'),
        ]
    return choices


def get_milestone_type_choices():
    """Get milestone type choices for faith milestones."""
    choices = ChoiceCategory.get_choices_for('milestone_type')
    if not choices:
        choices = [
            ('salvation', 'Accepted Christ'),
            ('baptism', 'Baptism'),
            ('rededication', 'Rededication'),
            ('answered_prayer', 'Answered Prayer'),
            ('spiritual_insight', 'Spiritual Insight'),
            ('community', 'Church/Community Moment'),
            ('other', 'Other'),
        ]
    return choices


def get_prayer_priority_choices():
    """Get prayer priority choices."""
    choices = ChoiceCategory.get_choices_for('prayer_priority')
    if not choices:
        choices = [
            ('normal', 'Normal'),
            ('urgent', 'Urgent'),
        ]
    return choices


def get_scripture_translation_choices():
    """Get Bible translation choices."""
    choices = ChoiceCategory.get_choices_for('scripture_translation')
    if not choices:
        choices = [
            ('ESV', 'English Standard Version'),
            ('NIV', 'New International Version'),
            ('BSB', 'Berean Standard Bible'),
            ('NKJV', 'New King James Version'),
            ('NLT', 'New Living Translation'),
            ('KJV', 'King James Version'),
        ]
    return choices


# =============================================================================
# TEST RUN HISTORY MODELS
# =============================================================================

class TestRun(models.Model):
    """
    Record of a test run execution.
    
    Stores historical test results for tracking over time.
    """
    
    STATUS_CHOICES = [
        ('passed', 'All Passed'),
        ('failed', 'Some Failed'),
        ('error', 'Has Errors'),
    ]
    
    # Run metadata
    run_at = models.DateTimeField(auto_now_add=True)
    duration_seconds = models.FloatField(default=0, help_text="Total run time in seconds")
    
    # Overall results
    status = models.CharField(max_length=10, choices=STATUS_CHOICES, default='passed')
    total_tests = models.PositiveIntegerField(default=0)
    passed = models.PositiveIntegerField(default=0)
    failed = models.PositiveIntegerField(default=0)
    errors = models.PositiveIntegerField(default=0)
    
    # Apps tested
    apps_tested = models.TextField(help_text="Comma-separated list of apps tested")
    
    # Pass rate
    pass_rate = models.DecimalField(max_digits=5, decimal_places=2, default=0,
                                     help_text="Pass rate as percentage")
    
    # Git info (optional)
    git_branch = models.CharField(max_length=100, blank=True)
    git_commit = models.CharField(max_length=40, blank=True)
    
    class Meta:
        ordering = ['-run_at']
        verbose_name = "Test Run"
        verbose_name_plural = "Test Runs"
    
    def __str__(self):
        return f"Test Run {self.run_at.strftime('%Y-%m-%d %H:%M')} - {self.status}"
    
    @property
    def apps_list(self):
        """Return apps_tested as a list."""
        return [a.strip() for a in self.apps_tested.split(',') if a.strip()]


class TestRunDetail(models.Model):
    """
    Detailed results for each app in a test run.
    """
    
    test_run = models.ForeignKey(TestRun, on_delete=models.CASCADE, related_name='details')
    
    # App info
    app_name = models.CharField(max_length=100)
    
    # Results
    passed = models.PositiveIntegerField(default=0)
    failed = models.PositiveIntegerField(default=0)
    errors = models.PositiveIntegerField(default=0)
    total = models.PositiveIntegerField(default=0)
    
    # Failed/error test names (JSON list)
    failed_tests = models.TextField(blank=True, help_text="JSON list of failed test names")
    error_tests = models.TextField(blank=True, help_text="JSON list of error test names")
    
    # Error details (full traceback)
    error_details = models.TextField(blank=True, help_text="Full error tracebacks")
    
    class Meta:
        ordering = ['app_name']
    
    def __str__(self):
        return f"{self.app_name} - {self.passed}/{self.total} passed"
    
    @property
    def status(self):
        """Get status string for this app."""
        if self.errors > 0:
            return 'error'
        elif self.failed > 0:
            return 'failed'
        return 'passed'


# =============================================================================
# CAMERA SCAN MODELS
# =============================================================================


class CameraScan(UserOwnedModel):
    """
    Raw camera scan output before classification/action.

    General-purpose intake mechanism for camera-based input. Can detect:
    - Food items for nutrition tracking
    - Packaged food with nutrition labels
    - Medicine bottles
    - Receipts, documents, etc.
    """

    # Detected category
    CATEGORY_FOOD = 'food'
    CATEGORY_PACKAGED_FOOD = 'packaged_food'
    CATEGORY_MEDICINE = 'medicine'
    CATEGORY_SUPPLEMENT = 'supplement'
    CATEGORY_RECEIPT = 'receipt'
    CATEGORY_DOCUMENT = 'document'
    CATEGORY_UNKNOWN = 'unknown'

    CATEGORY_CHOICES = [
        (CATEGORY_FOOD, 'Food'),
        (CATEGORY_PACKAGED_FOOD, 'Packaged Food'),
        (CATEGORY_MEDICINE, 'Medicine'),
        (CATEGORY_SUPPLEMENT, 'Supplement'),
        (CATEGORY_RECEIPT, 'Receipt'),
        (CATEGORY_DOCUMENT, 'Document'),
        (CATEGORY_UNKNOWN, 'Unknown'),
    ]

    # Image storage
    image = models.ImageField(
        upload_to='camera_scans/%Y/%m/',
        help_text="Original captured image",
    )

    # AI classification results
    detected_category = models.CharField(
        max_length=20,
        choices=CATEGORY_CHOICES,
        default=CATEGORY_UNKNOWN,
    )
    confidence_score = models.DecimalField(
        max_digits=5,
        decimal_places=4,
        null=True,
        blank=True,
        help_text="AI confidence score (0-1)",
    )
    raw_ai_response = models.JSONField(
        default=dict,
        blank=True,
        help_text="Full AI output for audit and reprocessing",
    )

    # Extracted data
    extracted_text = models.TextField(
        blank=True,
        help_text="OCR results from the image",
    )
    extracted_brand = models.CharField(max_length=200, blank=True)
    extracted_product_name = models.CharField(max_length=200, blank=True)
    extracted_serving_size = models.CharField(max_length=100, blank=True)
    extracted_nutrition_data = models.JSONField(
        default=dict,
        blank=True,
        help_text="Structured nutrition facts extracted from the image",
    )
    extracted_barcode = models.CharField(
        max_length=50,
        blank=True,
        help_text="Detected barcode value",
    )

    # Metadata
    device_info = models.CharField(
        max_length=200,
        blank=True,
        help_text="Device/browser info",
    )
    lighting_quality = models.CharField(
        max_length=20,
        blank=True,
        help_text="AI assessment of image quality (good/fair/poor)",
    )
    scanned_at = models.DateTimeField(default=timezone.now)

    # Processing status
    PROCESSING_STATUS_PENDING = 'pending'
    PROCESSING_STATUS_PROCESSING = 'processing'
    PROCESSING_STATUS_COMPLETED = 'completed'
    PROCESSING_STATUS_FAILED = 'failed'
    PROCESSING_STATUS_DISCARDED = 'discarded'

    PROCESSING_STATUS_CHOICES = [
        (PROCESSING_STATUS_PENDING, 'Pending'),
        (PROCESSING_STATUS_PROCESSING, 'Processing'),
        (PROCESSING_STATUS_COMPLETED, 'Completed'),
        (PROCESSING_STATUS_FAILED, 'Failed'),
        (PROCESSING_STATUS_DISCARDED, 'Discarded'),
    ]
    processing_status = models.CharField(
        max_length=20,
        choices=PROCESSING_STATUS_CHOICES,
        default=PROCESSING_STATUS_PENDING,
    )
    processing_error = models.TextField(
        blank=True,
        help_text="Error message if processing failed",
    )

    # Action tracking - what was done with this scan
    action_taken = models.CharField(
        max_length=50,
        blank=True,
        help_text="Action taken: 'food_logged', 'medicine_added', 'saved', 'discarded'",
    )
    action_reference_type = models.CharField(
        max_length=50,
        blank=True,
        help_text="Model type created: 'health.FoodEntry', 'health.Medicine'",
    )
    action_reference_id = models.PositiveIntegerField(
        null=True,
        blank=True,
        help_text="ID of the created record",
    )

    class Meta:
        ordering = ['-scanned_at']
        verbose_name = "camera scan"
        verbose_name_plural = "camera scans"

    def __str__(self):
        return f"{self.get_detected_category_display()} scan at {self.scanned_at}"

    def mark_processing(self):
        """Mark this scan as currently processing."""
        self.processing_status = self.PROCESSING_STATUS_PROCESSING
        self.save(update_fields=['processing_status', 'updated_at'])

    def mark_completed(self, category, confidence=None, ai_response=None):
        """Mark this scan as successfully processed."""
        self.processing_status = self.PROCESSING_STATUS_COMPLETED
        self.detected_category = category
        if confidence is not None:
            self.confidence_score = confidence
        if ai_response is not None:
            self.raw_ai_response = ai_response
        self.save()

    def mark_failed(self, error_message):
        """Mark this scan as failed processing."""
        self.processing_status = self.PROCESSING_STATUS_FAILED
        self.processing_error = error_message
        self.save(update_fields=['processing_status', 'processing_error', 'updated_at'])

    def mark_discarded(self):
        """Mark this scan as discarded by user."""
        self.processing_status = self.PROCESSING_STATUS_DISCARDED
        self.action_taken = 'discarded'
        self.save(update_fields=['processing_status', 'action_taken', 'updated_at'])

    def record_action(self, action, reference_type=None, reference_id=None):
        """Record what action was taken with this scan."""
        self.action_taken = action
        if reference_type:
            self.action_reference_type = reference_type
        if reference_id:
            self.action_reference_id = reference_id
        self.save(update_fields=['action_taken', 'action_reference_type', 'action_reference_id', 'updated_at'])


# =============================================================================
# RELEASE NOTE / WHAT'S NEW MODELS
# =============================================================================


class ReleaseNote(models.Model):
    """
    A single "What's New" entry shown to users after deployment.

    Each entry represents a feature, fix, or enhancement that should be
    communicated to users. Entries are shown in a popup modal when users
    log in after new entries are published.
    """

    # Entry types for categorization and icons
    TYPE_FEATURE = 'feature'
    TYPE_FIX = 'fix'
    TYPE_ENHANCEMENT = 'enhancement'
    TYPE_SECURITY = 'security'

    TYPE_CHOICES = [
        (TYPE_FEATURE, 'New Feature'),
        (TYPE_FIX, 'Bug Fix'),
        (TYPE_ENHANCEMENT, 'Enhancement'),
        (TYPE_SECURITY, 'Security Update'),
    ]

    # Content
    title = models.CharField(
        max_length=200,
        help_text="Short, descriptive title (e.g., 'AI Camera Scanning')",
    )
    description = models.TextField(
        help_text="Brief description of what's new. Keep it user-friendly.",
    )
    entry_type = models.CharField(
        max_length=20,
        choices=TYPE_CHOICES,
        default=TYPE_FEATURE,
        help_text="Type of release note for categorization and display",
    )

    # Versioning and ordering
    version = models.CharField(
        max_length=20,
        blank=True,
        help_text="Optional version number (e.g., '1.2.0')",
    )
    release_date = models.DateField(
        help_text="Date this was released/deployed",
    )

    # Visibility control
    is_published = models.BooleanField(
        default=True,
        help_text="Only published entries are shown to users",
    )
    is_major = models.BooleanField(
        default=False,
        help_text="Mark as major update for visual emphasis",
    )

    # Optional link to more info
    learn_more_url = models.URLField(
        blank=True,
        help_text="Optional link to documentation or blog post",
    )

    # Metadata — default=timezone.now for loaddata/fixture compatibility.
    # auto_now_add bypasses pre_save when raw=True, leaving NULL on NOT NULL columns.
    created_at = models.DateTimeField(default=timezone.now)
    updated_at = models.DateTimeField(default=timezone.now)

    class Meta:
        ordering = ['-release_date', '-created_at']
        verbose_name = "Release Note"
        verbose_name_plural = "Release Notes"

    def __str__(self):
        return f"{self.title} ({self.release_date})"

    def save(self, *args, **kwargs):
        self.updated_at = timezone.now()
        super().save(*args, **kwargs)

    @classmethod
    def get_published(cls):
        """Get all published release notes, ordered by date descending."""
        return cls.objects.filter(is_published=True).order_by('-release_date', '-created_at')

    @classmethod
    def get_unseen_for_user(cls, user):
        """
        Get release notes the user hasn't seen yet.

        Returns notes published after the user's last view, or all notes
        if the user has never viewed any.
        """
        from apps.users.models import UserPreferences

        # Check if user has opted out of What's New
        try:
            prefs = user.preferences
            if not prefs.show_whats_new:
                return cls.objects.none()
        except UserPreferences.DoesNotExist:
            pass

        # Get user's last seen timestamp
        last_seen = UserReleaseNoteView.objects.filter(user=user).first()

        if last_seen:
            # Show notes the user hasn't seen yet.
            # We use release_date (not created_at) as the primary filter because
            # release notes are often created via data migrations at deployment
            # time, but their logical release_date is when the feature was deployed.
            #
            # Logic: Show notes where:
            # - release_date > last_seen_date (notes from future days), OR
            # - release_date = last_seen_date AND created_at > last_viewed_at
            #   (notes created same day but after viewing)
            from django.db.models import Q
            last_seen_date = last_seen.last_viewed_at.date()
            return cls.get_published().filter(
                Q(release_date__gt=last_seen_date) |
                Q(release_date=last_seen_date, created_at__gt=last_seen.last_viewed_at)
            )
        else:
            # New user - show all published notes (up to a reasonable limit)
            return cls.get_published()[:10]

    def get_icon(self):
        """Return an emoji icon based on entry type."""
        icons = {
            self.TYPE_FEATURE: '✨',
            self.TYPE_FIX: '🔧',
            self.TYPE_ENHANCEMENT: '🚀',
            self.TYPE_SECURITY: '🔒',
        }
        return icons.get(self.entry_type, '📌')


class UserReleaseNoteView(models.Model):
    """
    Track when a user last viewed the What's New popup.

    This is a simple timestamp model - we track when the user last
    dismissed the popup, then show only notes with release_date after
    the dismissal date.
    """

    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='release_note_view',
    )
    last_viewed_at = models.DateTimeField(
        help_text="When the user last dismissed the What's New popup",
    )

    class Meta:
        verbose_name = "User Release Note View"
        verbose_name_plural = "User Release Note Views"

    def __str__(self):
        return f"{self.user.email} - last viewed {self.last_viewed_at}"

    @classmethod
    def mark_viewed(cls, user):
        """Mark that the user has viewed all current release notes.

        last_viewed_at is set to max(now, latest published note's created_at +
        1 microsecond). The clamp protects against fixture timestamp mistakes:
        if a fixture sets a future created_at (e.g. noon UTC) and a user
        dismisses earlier in the UTC day, ReleaseNote.get_unseen_for_user()
        would otherwise re-show the note on every refresh because the
        same-day-late-addition clause (`created_at > last_viewed_at`) keeps
        evaluating True. The clamp guarantees dismissal sticks regardless of
        what the fixture wrote.
        """
        from datetime import timedelta

        from django.db.models import Max

        now = timezone.now()
        latest_created = (
            ReleaseNote.get_published()
            .aggregate(latest=Max("created_at"))["latest"]
        )
        viewed_at = now
        if latest_created and latest_created >= viewed_at:
            viewed_at = latest_created + timedelta(microseconds=1)

        obj, _ = cls.objects.update_or_create(
            user=user,
            defaults={"last_viewed_at": viewed_at},
        )
        return obj


# =============================================================================
# FAVORITES AND RECENT PAGES
# =============================================================================


class FavoritePage(models.Model):
    """
    Track user's favorite pages for quick access.

    Users can mark up to 16 pages as favorites. Favorites appear in the
    Favorites dropdown menu in the navigation.
    """

    MAX_FAVORITES = 16

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='favorite_pages',
    )
    url = models.CharField(
        max_length=500,
        help_text="The URL path of the favorited page (e.g., '/journal/entries/')",
    )
    title = models.CharField(
        max_length=200,
        help_text="Display title for the favorite",
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']
        unique_together = ['user', 'url']
        verbose_name = "Favorite Page"
        verbose_name_plural = "Favorite Pages"

    def __str__(self):
        return f"{self.user.email} - {self.title}"

    @staticmethod
    def normalize_url(url):
        """Normalize URL for consistent matching: strip query params, ensure trailing slash."""
        from urllib.parse import urlparse, urlunparse
        parsed = urlparse(url)
        # Keep only the path, strip query string and fragment
        path = parsed.path
        # Ensure trailing slash
        if path and not path.endswith('/'):
            path += '/'
        return path

    def save(self, *args, **kwargs):
        self.url = self.normalize_url(self.url)
        super().save(*args, **kwargs)

    @classmethod
    def is_favorite(cls, user, url):
        """Check if a URL is favorited by the user."""
        from django.db.models import Q
        normalized_url = cls.normalize_url(url)
        return cls.objects.filter(
            Q(url=normalized_url) | Q(url=url),
            user=user
        ).exists()

    @classmethod
    def toggle(cls, user, url, title):
        """
        Toggle a page as favorite.

        Returns tuple of (is_now_favorite, error_message).
        Error message is set if max favorites reached when trying to add.
        """
        from django.db.models import Q
        normalized_url = cls.normalize_url(url)
        # Match on both normalized and original URL for backward compatibility
        existing = cls.objects.filter(
            Q(url=normalized_url) | Q(url=url),
            user=user
        ).first()
        if existing:
            existing.delete()
            return (False, None)

        # Check if at max favorites
        current_count = cls.objects.filter(user=user).count()
        if current_count >= cls.MAX_FAVORITES:
            return (True, f"Maximum of {cls.MAX_FAVORITES} favorites reached. Remove one to add more.")

        cls.objects.create(user=user, url=normalized_url, title=title)
        return (True, None)

    @classmethod
    def get_favorites_for_user(cls, user, limit=None):
        """Get user's favorite pages."""
        qs = cls.objects.filter(user=user).order_by('-created_at')
        if limit:
            qs = qs[:limit]
        return qs


class PageView(models.Model):
    """
    Track page views for the user.

    Used to populate the "Most Used" section of the Favorites menu
    when there are fewer than 16 favorites. Pages are ranked by
    visit count (most frequently visited first).
    """

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='page_views',
    )
    url = models.CharField(
        max_length=500,
        help_text="The URL path that was viewed",
    )
    title = models.CharField(
        max_length=200,
        help_text="Page title at time of viewing",
    )
    viewed_at = models.DateTimeField(auto_now=True)
    visit_count = models.PositiveIntegerField(
        default=1,
        help_text="Number of times this page has been visited",
    )

    class Meta:
        ordering = ['-visit_count', '-viewed_at']
        verbose_name = "Page View"
        verbose_name_plural = "Page Views"

    def __str__(self):
        return f"{self.user.email} viewed {self.title} ({self.visit_count}x)"

    @classmethod
    def record_view(cls, user, url, title):
        """
        Record a page view, incrementing visit count if exists.

        Each URL only appears once per user. Subsequent visits
        increment the visit_count and update the timestamp.
        """
        from django.db.models import F

        obj, created = cls.objects.get_or_create(
            user=user,
            url=url,
            defaults={'title': title, 'visit_count': 1}
        )
        if not created:
            # Increment visit count and update title
            obj.visit_count = F('visit_count') + 1
            obj.title = title
            obj.save(update_fields=['visit_count', 'title', 'viewed_at'])
            obj.refresh_from_db()
        return obj

    @classmethod
    def get_most_used_for_user(cls, user, limit=10, exclude_urls=None):
        """
        Get user's most frequently visited pages.

        Args:
            user: The user
            limit: Maximum pages to return
            exclude_urls: List of URLs to exclude (e.g., favorited pages)

        Returns pages ordered by visit_count (descending), then by
        viewed_at (descending) as a tiebreaker.
        """
        qs = cls.objects.filter(user=user)
        if exclude_urls:
            qs = qs.exclude(url__in=exclude_urls)
        return qs.order_by('-visit_count', '-viewed_at')[:limit]

    @classmethod
    def get_recent_for_user(cls, user, limit=10, exclude_urls=None):
        """
        Get user's most frequently visited pages.

        DEPRECATED: Use get_most_used_for_user instead.
        This method now returns most used pages for backwards compatibility.
        """
        return cls.get_most_used_for_user(user, limit, exclude_urls)

    @classmethod
    def cleanup_old_views(cls, user, keep_count=50):
        """
        Remove least-used page views to prevent table bloat.

        Keeps only the top `keep_count` most-used views per user.
        """
        views_to_keep = cls.objects.filter(user=user).order_by('-visit_count', '-viewed_at')[:keep_count]
        ids_to_keep = list(views_to_keep.values_list('id', flat=True))
        cls.objects.filter(user=user).exclude(id__in=ids_to_keep).delete()


class APIRequestLog(models.Model):
    """
    Log of API requests for security monitoring and anomaly detection.

    CISO Review 2026-01-12: Added for security requirement
    "API request logging with anomaly detection"

    Features:
    - Records all API requests with timing and response data
    - Tracks patterns for anomaly detection
    - Supports IP-based and key-based analysis
    - Auto-cleanup of old records (30 days default)

    Usage:
    - Created by APIRequestLoggingMiddleware for /api/* endpoints
    - Queried by anomaly detection background job
    - Displayed in admin console security dashboard
    """

    # Request identification
    request_id = models.CharField(
        max_length=36,
        db_index=True,
        help_text="UUID for correlating logs"
    )

    # Endpoint info
    method = models.CharField(
        max_length=10,
        help_text="HTTP method (GET, POST, etc.)"
    )
    path = models.CharField(
        max_length=500,
        db_index=True,
        help_text="API endpoint path"
    )
    query_string = models.TextField(
        blank=True,
        default="",
        help_text="Query parameters (sanitized)"
    )

    # Authentication
    api_key_name = models.CharField(
        max_length=100,
        blank=True,
        default="",
        db_index=True,
        help_text="Name/identifier of API key used (not the key itself)"
    )
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        help_text="Authenticated user (if any)"
    )

    # Client info
    ip_address = models.GenericIPAddressField(
        db_index=True,
        help_text="Client IP address"
    )
    user_agent = models.CharField(
        max_length=500,
        blank=True,
        default="",
        help_text="User agent string"
    )

    # Response info
    status_code = models.PositiveSmallIntegerField(
        db_index=True,
        help_text="HTTP response status code"
    )
    response_time_ms = models.PositiveIntegerField(
        help_text="Response time in milliseconds"
    )

    # Error tracking
    error_message = models.TextField(
        blank=True,
        default="",
        help_text="Error message if request failed"
    )

    # Anomaly detection flags
    is_anomaly = models.BooleanField(
        default=False,
        db_index=True,
        help_text="Flagged as anomalous by detection system"
    )
    anomaly_reason = models.CharField(
        max_length=200,
        blank=True,
        default="",
        help_text="Reason for anomaly flag"
    )
    anomaly_score = models.FloatField(
        default=0.0,
        help_text="Anomaly score (0-1, higher = more anomalous)"
    )

    # Timestamps
    created_at = models.DateTimeField(
        auto_now_add=True,
        db_index=True
    )

    class Meta:
        ordering = ['-created_at']
        verbose_name = "API Request Log"
        verbose_name_plural = "API Request Logs"
        indexes = [
            models.Index(fields=['ip_address', 'created_at']),
            models.Index(fields=['api_key_name', 'created_at']),
            models.Index(fields=['path', 'created_at']),
            models.Index(fields=['status_code', 'created_at']),
            models.Index(fields=['is_anomaly', 'created_at']),
        ]

    def __str__(self):
        return f"{self.method} {self.path} - {self.status_code} ({self.ip_address})"

    @classmethod
    def log_request(cls, request, response, response_time_ms, error_message=""):
        """
        Create a log entry for an API request.

        Args:
            request: Django HttpRequest
            response: Django HttpResponse
            response_time_ms: Response time in milliseconds
            error_message: Error message if request failed

        Returns:
            APIRequestLog instance
        """
        import uuid
        from apps.core.rate_limiting import get_client_ip

        # Get or generate request ID
        request_id = getattr(request, 'request_id', None) or str(uuid.uuid4())

        # Determine API key name (if used)
        api_key_name = ""
        api_key = request.headers.get('X-Claude-API-Key', '')
        if api_key:
            # Don't store the key, just indicate it was used
            api_key_name = "claude-api"

        # Get user if authenticated
        user = None
        if hasattr(request, 'user') and request.user.is_authenticated:
            user = request.user

        # Sanitize query string (remove sensitive params)
        query_string = request.META.get('QUERY_STRING', '')
        sensitive_params = ['key', 'token', 'password', 'secret', 'api_key']
        for param in sensitive_params:
            if param in query_string.lower():
                query_string = '[REDACTED]'
                break

        return cls.objects.create(
            request_id=request_id,
            method=request.method,
            path=request.path,
            query_string=query_string[:500],  # Limit length
            api_key_name=api_key_name,
            user=user,
            ip_address=get_client_ip(request),
            user_agent=request.META.get('HTTP_USER_AGENT', '')[:500],
            status_code=response.status_code,
            response_time_ms=response_time_ms,
            error_message=error_message[:1000] if error_message else "",
        )

    @classmethod
    def get_stats_for_ip(cls, ip_address, hours=1):
        """
        Get request statistics for an IP address.

        Returns dict with:
        - total_requests: Total requests in time window
        - error_rate: Percentage of 4xx/5xx responses
        - avg_response_time: Average response time in ms
        - unique_endpoints: Number of unique endpoints accessed
        """
        from django.db.models import Avg

        cutoff = timezone.now() - timezone.timedelta(hours=hours)
        qs = cls.objects.filter(ip_address=ip_address, created_at__gte=cutoff)

        total = qs.count()
        if total == 0:
            return {
                'total_requests': 0,
                'error_rate': 0.0,
                'avg_response_time': 0,
                'unique_endpoints': 0,
            }

        errors = qs.filter(status_code__gte=400).count()
        avg_time = qs.aggregate(avg=Avg('response_time_ms'))['avg'] or 0
        unique_endpoints = qs.values('path').distinct().count()

        return {
            'total_requests': total,
            'error_rate': (errors / total) * 100,
            'avg_response_time': int(avg_time),
            'unique_endpoints': unique_endpoints,
        }

    @classmethod
    def detect_anomalies(cls, hours=1):
        """
        Detect anomalous API request patterns.

        Checks for:
        1. High request volume from single IP (>100/hour)
        2. High error rate from single IP (>50% errors)
        3. Sequential endpoint probing (many 404s)
        4. Rapid authentication failures (many 401/403s)

        Returns list of anomaly dicts with ip_address, reason, score.
        """
        from django.db.models import Count, Q

        cutoff = timezone.now() - timezone.timedelta(hours=hours)
        anomalies = []

        # 1. High volume IPs (>100 requests/hour)
        high_volume = cls.objects.filter(
            created_at__gte=cutoff
        ).values('ip_address').annotate(
            count=Count('id')
        ).filter(count__gt=100)

        for item in high_volume:
            anomalies.append({
                'ip_address': item['ip_address'],
                'reason': f"High request volume: {item['count']} requests/hour",
                'score': min(1.0, item['count'] / 500),  # Cap at 1.0
                'type': 'high_volume',
            })

        # 2. High error rate IPs (>50% errors with >10 requests)
        ip_error_rates = cls.objects.filter(
            created_at__gte=cutoff
        ).values('ip_address').annotate(
            total=Count('id'),
            errors=Count('id', filter=Q(status_code__gte=400))
        ).filter(total__gt=10)

        for item in ip_error_rates:
            error_rate = item['errors'] / item['total']
            if error_rate > 0.5:
                anomalies.append({
                    'ip_address': item['ip_address'],
                    'reason': f"High error rate: {error_rate*100:.0f}% ({item['errors']}/{item['total']})",
                    'score': error_rate,
                    'type': 'high_error_rate',
                })

        # 3. Sequential 404s (endpoint probing)
        probing_ips = cls.objects.filter(
            created_at__gte=cutoff,
            status_code=404
        ).values('ip_address').annotate(
            count=Count('id')
        ).filter(count__gt=20)

        for item in probing_ips:
            anomalies.append({
                'ip_address': item['ip_address'],
                'reason': f"Possible endpoint probing: {item['count']} 404 responses",
                'score': min(1.0, item['count'] / 50),
                'type': 'endpoint_probing',
            })

        # 4. Auth failures (many 401/403s)
        auth_failures = cls.objects.filter(
            created_at__gte=cutoff,
            status_code__in=[401, 403]
        ).values('ip_address').annotate(
            count=Count('id')
        ).filter(count__gt=10)

        for item in auth_failures:
            anomalies.append({
                'ip_address': item['ip_address'],
                'reason': f"Authentication failures: {item['count']} 401/403 responses",
                'score': min(1.0, item['count'] / 30),
                'type': 'auth_failures',
            })

        return anomalies

    @classmethod
    def cleanup_old_logs(cls, days=30):
        """
        Delete API request logs older than specified days.

        Returns number of deleted records.
        """
        cutoff = timezone.now() - timezone.timedelta(days=days)
        deleted, _ = cls.objects.filter(created_at__lt=cutoff).delete()
        return deleted


# =============================================================================
# IN-APP NOTIFICATION SYSTEM
# =============================================================================

from django.contrib.contenttypes.fields import GenericForeignKey
from django.contrib.contenttypes.models import ContentType


class Notification(TimeStampedModel):
    """
    In-app notification for users.

    Notifications appear in the notification bell dropdown and notification
    center. They can be linked to a source object (prayer request, task, etc.)
    via a generic foreign key.

    Categories match the SMS notification categories for consistency.
    """

    # Category choices - matches SMS categories
    CATEGORY_MEDICINE = 'medicine'
    CATEGORY_MEDICINE_REFILL = 'medicine_refill'
    CATEGORY_TASK = 'task'
    CATEGORY_EVENT = 'event'
    CATEGORY_PRAYER = 'prayer'
    CATEGORY_READING_PLAN = 'reading_plan'
    CATEGORY_FASTING = 'fasting'
    CATEGORY_SIGNIFICANT_EVENT = 'significant_event'
    CATEGORY_MILESTONE = 'milestone'
    CATEGORY_FINANCE = 'finance'
    CATEGORY_JOURNAL = 'journal'
    CATEGORY_SYSTEM = 'system'
    CATEGORY_INTELLIGENCE = 'intelligence'

    CATEGORY_CHOICES = [
        (CATEGORY_MEDICINE, 'Medicine Reminder'),
        (CATEGORY_MEDICINE_REFILL, 'Medicine Refill'),
        (CATEGORY_TASK, 'Task Due'),
        (CATEGORY_EVENT, 'Calendar Event'),
        (CATEGORY_PRAYER, 'Prayer Reminder'),
        (CATEGORY_READING_PLAN, 'Reading Plan'),
        (CATEGORY_FASTING, 'Fasting Reminder'),
        (CATEGORY_SIGNIFICANT_EVENT, 'Significant Event'),
        (CATEGORY_MILESTONE, 'Goal Milestone'),
        (CATEGORY_FINANCE, 'Finance Alert'),
        (CATEGORY_JOURNAL, 'Journal Prompt'),
        (CATEGORY_SYSTEM, 'System'),
        (CATEGORY_INTELLIGENCE, 'Intelligence'),
    ]

    # Map categories to module preference fields
    CATEGORY_MODULE_MAP = {
        CATEGORY_MEDICINE: 'health_enabled',
        CATEGORY_MEDICINE_REFILL: 'health_enabled',
        CATEGORY_TASK: 'life_enabled',
        CATEGORY_EVENT: 'life_enabled',
        CATEGORY_PRAYER: 'faith_enabled',
        CATEGORY_READING_PLAN: 'faith_enabled',
        CATEGORY_FASTING: 'health_enabled',
        CATEGORY_SIGNIFICANT_EVENT: 'life_enabled',
        CATEGORY_MILESTONE: 'purpose_enabled',
        CATEGORY_FINANCE: 'finances_enabled',
        CATEGORY_JOURNAL: 'journal_enabled',
        CATEGORY_SYSTEM: None,  # Always show system notifications
        CATEGORY_INTELLIGENCE: 'ai_enabled',
    }

    # Fields
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='notifications',
        help_text="User this notification is for"
    )

    category = models.CharField(
        max_length=20,
        choices=CATEGORY_CHOICES,
        default=CATEGORY_SYSTEM,
        db_index=True,
        help_text="Type of notification"
    )

    title = models.CharField(
        max_length=200,
        help_text="Short notification title"
    )

    message = models.TextField(
        help_text="Notification message body"
    )

    action_url = models.CharField(
        max_length=500,
        blank=True,
        help_text="URL to navigate to when notification is clicked"
    )

    icon = models.CharField(
        max_length=50,
        blank=True,
        help_text="Icon class or emoji for the notification"
    )

    is_read = models.BooleanField(
        default=False,
        db_index=True,
        help_text="Whether the user has read this notification"
    )

    read_at = models.DateTimeField(
        null=True,
        blank=True,
        help_text="When the notification was marked as read"
    )

    # Generic foreign key to source object (optional)
    content_type = models.ForeignKey(
        ContentType,
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        help_text="Type of the source object"
    )
    object_id = models.PositiveIntegerField(
        null=True,
        blank=True,
        help_text="ID of the source object"
    )
    source_object = GenericForeignKey('content_type', 'object_id')

    # For scheduled notifications (e.g., daily reminders)
    scheduled_for = models.DateTimeField(
        null=True,
        blank=True,
        db_index=True,
        help_text="When this notification should be shown (null = immediate)"
    )

    # Email tracking
    email_sent = models.BooleanField(
        default=False,
        help_text="Whether an email was sent for this notification"
    )
    email_sent_at = models.DateTimeField(
        null=True,
        blank=True,
        help_text="When the email was sent"
    )

    class Meta:
        ordering = ['-created_at']
        verbose_name = "Notification"
        verbose_name_plural = "Notifications"
        indexes = [
            models.Index(fields=['user', 'is_read', '-created_at']),
            models.Index(fields=['user', 'category', '-created_at']),
            models.Index(fields=['scheduled_for', 'is_read']),
        ]

    def __str__(self):
        return f"{self.user.email}: {self.title}"

    def mark_read(self):
        """Mark this notification as read."""
        if not self.is_read:
            self.is_read = True
            self.read_at = timezone.now()
            self.save(update_fields=['is_read', 'read_at', 'updated_at'])
            # Invalidate the notification count cache
            from apps.core.context_processors import invalidate_notification_count_cache
            invalidate_notification_count_cache(self.user_id)

    def mark_email_sent(self):
        """Mark that an email was sent for this notification."""
        self.email_sent = True
        self.email_sent_at = timezone.now()
        self.save(update_fields=['email_sent', 'email_sent_at', 'updated_at'])

    @classmethod
    def get_unread_for_user(cls, user, limit=None):
        """Get unread notifications for a user."""
        qs = cls.objects.filter(
            user=user,
            is_read=False
        ).filter(
            models.Q(scheduled_for__isnull=True) |
            models.Q(scheduled_for__lte=timezone.now())
        ).order_by('-created_at')

        if limit:
            qs = qs[:limit]
        return qs

    @classmethod
    def get_unread_count(cls, user):
        """Get count of unread notifications for a user."""
        return cls.objects.filter(
            user=user,
            is_read=False
        ).filter(
            models.Q(scheduled_for__isnull=True) |
            models.Q(scheduled_for__lte=timezone.now())
        ).count()

    @classmethod
    def mark_all_read(cls, user):
        """Mark all notifications as read for a user."""
        now = timezone.now()
        count = cls.objects.filter(
            user=user,
            is_read=False
        ).update(is_read=True, read_at=now, updated_at=now)
        # Invalidate the notification count cache
        if count > 0:
            from apps.core.context_processors import invalidate_notification_count_cache
            invalidate_notification_count_cache(user.id)
        return count

    @classmethod
    def get_pending_email_notifications(cls, user):
        """Get notifications that need to be sent via email."""
        return cls.objects.filter(
            user=user,
            email_sent=False,
            is_read=False
        ).filter(
            models.Q(scheduled_for__isnull=True) |
            models.Q(scheduled_for__lte=timezone.now())
        ).order_by('-created_at')

    @classmethod
    def cleanup_old_notifications(cls, days=90):
        """Delete read notifications older than specified days."""
        cutoff = timezone.now() - timezone.timedelta(days=days)
        deleted, _ = cls.objects.filter(
            is_read=True,
            created_at__lt=cutoff
        ).delete()
        return deleted

    def get_icon(self):
        """Return an icon for this notification based on category."""
        icons = {
            self.CATEGORY_MEDICINE: '💊',
            self.CATEGORY_MEDICINE_REFILL: '💊',
            self.CATEGORY_TASK: '✅',
            self.CATEGORY_EVENT: '📅',
            self.CATEGORY_PRAYER: '🙏',
            self.CATEGORY_READING_PLAN: '📖',
            self.CATEGORY_FASTING: '🍽️',
            self.CATEGORY_SIGNIFICANT_EVENT: '🎂',
            self.CATEGORY_MILESTONE: '🎯',
            self.CATEGORY_FINANCE: '💰',
            self.CATEGORY_JOURNAL: '📝',
            self.CATEGORY_SYSTEM: '🔔',
        }
        return self.icon or icons.get(self.category, '🔔')


class UserDailyActivity(models.Model):
    """
    Tracks the first and last interaction time per user per day.

    Updated by PageViewTrackingMiddleware on every page view.
    Used to compute UserActivityPattern (typical day start/end times).
    One row per user per calendar day — lightweight and bounded.
    """

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='daily_activities',
    )
    date = models.DateField(
        help_text="The calendar date of activity (in user's timezone)",
    )
    first_seen = models.TimeField(
        help_text="Earliest interaction time on this date",
    )
    last_seen = models.TimeField(
        help_text="Latest interaction time on this date",
    )
    interaction_count = models.PositiveIntegerField(
        default=1,
        help_text="Number of page views on this date",
    )

    class Meta:
        unique_together = ['user', 'date']
        ordering = ['-date']
        verbose_name = "User Daily Activity"
        verbose_name_plural = "User Daily Activities"

    def __str__(self):
        return f"{self.user.email} on {self.date}: {self.first_seen}-{self.last_seen}"

    @classmethod
    def record_activity(cls, user, current_time):
        """
        Record a user interaction. Creates or updates the daily record.

        Args:
            user: The authenticated user
            current_time: Timezone-aware datetime of the interaction
        """
        from django.db.models import F

        activity_date = current_time.date()
        time_of_day = current_time.time()

        obj, created = cls.objects.get_or_create(
            user=user,
            date=activity_date,
            defaults={
                'first_seen': time_of_day,
                'last_seen': time_of_day,
                'interaction_count': 1,
            }
        )
        if not created:
            update_fields = ['interaction_count']
            obj.interaction_count = F('interaction_count') + 1

            if time_of_day < obj.first_seen:
                obj.first_seen = time_of_day
                update_fields.append('first_seen')
            if time_of_day > obj.last_seen:
                obj.last_seen = time_of_day
                update_fields.append('last_seen')

            obj.save(update_fields=update_fields)

    @classmethod
    def cleanup_old_records(cls, days_to_keep=90):
        """Remove activity records older than retention period."""
        from datetime import timedelta
        from django.utils import timezone
        cutoff = timezone.now().date() - timedelta(days=days_to_keep)
        deleted_count, _ = cls.objects.filter(date__lt=cutoff).delete()
        return deleted_count


class UserActivityPattern(models.Model):
    """
    Computed behavioral pattern for a user based on their daily activity.

    Recalculated periodically (e.g., nightly) from UserDailyActivity records.
    Used by the AI insight system to personalize time-of-day messaging.
    """

    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='activity_pattern',
    )
    typical_start_hour = models.FloatField(
        default=8.0,
        help_text="Average hour the user starts their day (e.g., 6.5 = 6:30am)",
    )
    typical_end_hour = models.FloatField(
        default=22.0,
        help_text="Average hour the user ends their day (e.g., 22.5 = 10:30pm)",
    )
    earliest_start_hour = models.FloatField(
        default=8.0,
        help_text="Earliest recorded day start (10th percentile)",
    )
    sample_days = models.PositiveIntegerField(
        default=0,
        help_text="Number of days of data used to compute this pattern",
    )
    last_computed = models.DateTimeField(
        auto_now=True,
        help_text="When this pattern was last recalculated",
    )

    # Minimum days of data before we trust the pattern
    MIN_SAMPLE_DAYS = 7

    class Meta:
        verbose_name = "User Activity Pattern"
        verbose_name_plural = "User Activity Patterns"

    def __str__(self):
        return (
            f"{self.user.email}: typically "
            f"{self._format_hour(self.typical_start_hour)}-"
            f"{self._format_hour(self.typical_end_hour)} "
            f"({self.sample_days} days)"
        )

    @staticmethod
    def _format_hour(hour_float):
        """Convert float hour (e.g., 6.5) to readable string (e.g., '6:30am')."""
        h = int(hour_float)
        m = int((hour_float - h) * 60)
        period = 'am' if h < 12 else 'pm'
        display_h = h if h <= 12 else h - 12
        if display_h == 0:
            display_h = 12
        if m == 0:
            return f"{display_h}{period}"
        return f"{display_h}:{m:02d}{period}"

    @property
    def is_reliable(self):
        """Whether we have enough data to trust this pattern."""
        return self.sample_days >= self.MIN_SAMPLE_DAYS

    def get_early_morning_threshold(self):
        """
        Return the hour before which the user's day hasn't really started.

        If we have reliable data, use 1 hour before their typical start.
        Otherwise fall back to the static 8am default.
        """
        if not self.is_reliable:
            return 8.0
        # Their "early morning" is before their typical start time
        # Use the earlier of: 1 hour before typical OR their earliest recorded
        return min(self.typical_start_hour, self.earliest_start_hour)

    @classmethod
    def compute_for_user(cls, user, lookback_days=30):
        """
        Compute or update the activity pattern for a user.

        Uses UserDailyActivity records from the past `lookback_days` days.
        """
        from datetime import timedelta
        from django.utils import timezone

        cutoff = timezone.now().date() - timedelta(days=lookback_days)
        activities = UserDailyActivity.objects.filter(
            user=user,
            date__gte=cutoff,
        ).values_list('first_seen', 'last_seen')

        if not activities:
            return None

        start_hours = []
        end_hours = []
        for first_seen, last_seen in activities:
            start_hours.append(first_seen.hour + first_seen.minute / 60.0)
            end_hours.append(last_seen.hour + last_seen.minute / 60.0)

        start_hours.sort()
        end_hours.sort()

        sample_days = len(start_hours)
        typical_start = sum(start_hours) / sample_days
        typical_end = sum(end_hours) / sample_days

        # 10th percentile for earliest start (accounts for occasional very early days)
        p10_index = max(0, int(sample_days * 0.1))
        earliest_start = start_hours[p10_index]

        pattern, _ = cls.objects.update_or_create(
            user=user,
            defaults={
                'typical_start_hour': round(typical_start, 2),
                'typical_end_hour': round(typical_end, 2),
                'earliest_start_hour': round(earliest_start, 2),
                'sample_days': sample_days,
            },
        )
        return pattern


# Import ai_memory models so Django discovers them for migrations
from apps.core.ai_memory.models import (  # noqa: E402, F401
    ClarificationLog,
    ContextSnapshot,
    LearnedMapping,
)

# Import ai_insights models so Django discovers them for migrations
from apps.core.ai_insights.models import Insight  # noqa: E402, F401

# Import ai_predictions models so Django discovers them for migrations
from apps.core.ai_predictions.models import Prediction  # noqa: E402, F401

# Import ai_state models so Django discovers them for migrations
from apps.core.ai_state.models import UserState  # noqa: E402, F401

# Import ai_semantics models so Django discovers them for migrations
from apps.core.ai_semantics.semantic_models import SemanticDecisionLog  # noqa: E402, F401

# Import ai_guidance models so Django discovers them for migrations
from apps.core.ai_guidance.models import GuidanceItem  # noqa: E402, F401

# Import ai_briefing models so Django discovers them for migrations
from apps.core.ai_briefing.models import DailyBriefing  # noqa: E402, F401

# Import ai_guidance_learning models so Django discovers them for migrations
from apps.core.ai_guidance_learning.learning_models import (  # noqa: E402, F401
    GuidanceLearningEvent,
    GuidanceLearningProfile,
)

# Import ai_scheduler models so Django discovers them for migrations
from apps.core.ai_scheduler.scheduler_models import (  # noqa: E402, F401
    ScheduledIntelligenceTask,
    SchedulerLock,
)

# Import ai_weekly_report models so Django discovers them for migrations
from apps.core.ai_weekly_report.models import (  # noqa: E402, F401
    WeeklyIntelligenceReport,
)

# Import ai_explain models so Django discovers them for migrations
from apps.core.ai_explain.models import (  # noqa: E402, F401
    ExplainRecord,
)
from apps.core.ai_delivery.models import (  # noqa: E402, F401
    DeliveredNotification,
)

# Import ai_quality models so Django discovers them for migrations
from apps.core.ai_quality.quality_models import (  # noqa: E402, F401
    QualityMetricAggregate,
    QualitySuppressionRecord,
)

# Import ai_observability models so Django discovers them for migrations
from apps.core.ai_observability.models import (  # noqa: E402, F401
    IntelligenceMetricsSnapshot,
)

# Import blueprint models so Django discovers them for migrations
from apps.core.blueprint.models import (  # noqa: E402, F401
    ArchitecturePlan,
    DriftEvent,
    DriftScore,
    InterventionLog,
    NonNegotiable,
    PersonalOperatingBlueprint,
    ScheduledBlock,
)

# Phase 4 CoS — Feedback loop models
from apps.core.ai_feedback.models import (  # noqa: E402, F401
    BriefingEngagement,
    BriefingEngagementProfile,
    InsightEngagement,
    InsightEngagementProfile,
    InterventionEffectivenessProfile,
    PredictionAccuracyProfile,
    PredictionOutcome,
)

# Phase 4 CoS — Conversational learning models
from apps.core.ai_learning.models import (  # noqa: E402, F401
    LearningExtraction,
    UserLearnedProfile,
)

# Phase 5 — Governance onboarding models
from apps.core.ai_governance.models import (  # noqa: E402, F401
    GovernanceAlignmentSession,
    GovernanceProfile,
)

# Import ai_arbitration models so Django discovers them for migrations
from apps.core.ai_arbitration.models import (  # noqa: E402, F401
    ArbitrationDecisionLog,
    DailyCapacityLog,
    ScenarioHistory,
    WeightAdjustment,
)

# CDCE — Cross-Domain Correlation Engine models
from apps.core.ai_cross_domain.models import DomainCorrelation  # noqa: E402, F401

# Phase 10 — Schedule drift detection models
from apps.core.drift.models import (  # noqa: E402, F401
    DriftSignal,
    ExecutionLog,
)

from apps.core.ai_config import AIThresholdConfig  # noqa: E402, F401

# Phase 4 Signal — Feedback loop model
from apps.core.signals.models import SignalFeedback  # noqa: E402, F401
