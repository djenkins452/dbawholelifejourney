"""
User Models - Custom user and preferences.

The User model uses email for authentication (no username).
UserPreferences stores all personalization settings.
TermsAcceptance tracks which version of terms the user accepted.
"""

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

    AI_COACHING_STYLE_CHOICES = [
        ('gentle', 'Gentle Guide'),
        ('supportive', 'Supportive Partner'),
        ('direct', 'Direct Coach'),
]

    TIMEZONE_CHOICES = [
        ("US/Eastern", "US/Eastern"),
        ("US/Central", "US/Central"),
        ("US/Mountain", "US/Mountain"),
        ("US/Pacific", "US/Pacific"),
    ]

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
    
    # AI Features
    ai_enabled = models.BooleanField(
        default=False,
        help_text="Enable AI-powered insights and reflections",
    )

    ai_coaching_style = models.CharField(
    max_length=20,
    choices=AI_COACHING_STYLE_CHOICES,
    default='supportive',
    help_text='AI personality style for insights and feedback',
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

    # Onboarding status
    has_completed_onboarding = models.BooleanField(default=False)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "user preferences"
        verbose_name_plural = "user preferences"

    def __str__(self):
        return f"Preferences for {self.user.email}"


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
