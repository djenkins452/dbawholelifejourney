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
