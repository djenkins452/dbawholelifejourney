"""
Core Models - Base models inherited by other apps.

These abstract models provide common functionality:
- Timestamps (created_at, updated_at)
- Soft delete with 30-day retention
- User ownership
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

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="%(class)ss",
    )

    class Meta:
        abstract = True


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
        """
        config = cache.get('site_configuration')
        if config is None:
            config, created = cls.objects.get_or_create(pk=1)
            cache.set('site_configuration', config, 60 * 60)  # Cache for 1 hour
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
from django.core.cache import cache


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
