"""
Whole Life Journey - Notes Models

Project: Whole Life Journey
Path: apps/notes/models.py
Purpose: Unified notes system with entity attachment support
"""

from django.contrib.contenttypes.fields import GenericForeignKey
from django.contrib.contenttypes.models import ContentType
from django.contrib.postgres.indexes import GinIndex
from django.contrib.postgres.search import SearchVector, SearchVectorField
from django.db import models
from django.urls import reverse

from apps.core.models import Tag, UserOwnedModel


class Note(UserOwnedModel):
    """
    A general-purpose note that can stand alone or be attached to any WLJ entity.

    Notes support tags (reusing core.Tag), color coding, pinning, and
    optional attachment to any model via NoteAttachment.

    Inherits from UserOwnedModel:
        user, status, deleted_at, created_at, updated_at, created_via
    """

    COLOR_CHOICES = [
        ("default", "Default"),
        ("red", "Red"),
        ("orange", "Orange"),
        ("yellow", "Yellow"),
        ("green", "Green"),
        ("blue", "Blue"),
        ("purple", "Purple"),
        ("pink", "Pink"),
    ]

    title = models.CharField(
        max_length=200,
        blank=True,
        help_text="Optional title. If blank, derived from body preview.",
    )
    body = models.TextField(
        help_text="Note content.",
    )
    tags = models.ManyToManyField(
        Tag,
        blank=True,
        related_name="notes",
    )
    color = models.CharField(
        max_length=10,
        choices=COLOR_CHOICES,
        default="default",
        help_text="Visual color code for the note card.",
    )
    is_pinned = models.BooleanField(
        default=False,
        db_index=True,
        help_text="Pinned notes appear first in the list.",
    )
    word_count = models.PositiveIntegerField(default=0, editable=False)
    search_vector = SearchVectorField(null=True, editable=False)

    class Meta:
        ordering = ["-is_pinned", "-updated_at"]
        verbose_name = "note"
        verbose_name_plural = "notes"
        indexes = [
            models.Index(
                fields=["user", "status", "-is_pinned", "-updated_at"],
                name="notes_user_status_pin_updated",
            ),
            models.Index(
                fields=["user", "color"],
                name="notes_user_color",
            ),
            GinIndex(
                fields=["search_vector"],
                name="notes_search_vector_gin",
            ),
        ]

    def __str__(self):
        return self.display_title

    def save(self, *args, **kwargs):
        if self.body:
            self.word_count = len(self.body.split())
        else:
            self.word_count = 0
        super().save(*args, **kwargs)
        # Update search vector after save (separate UPDATE to avoid recursion)
        self._update_search_vector()

    def _update_search_vector(self):
        """Rebuild the search_vector from title (A) and body (B)."""
        Note.objects.filter(pk=self.pk).update(
            search_vector=(
                SearchVector("title", weight="A")
                + SearchVector("body", weight="B")
            )
        )

    def get_absolute_url(self):
        return reverse("notes:note_detail", kwargs={"pk": self.pk})

    @property
    def body_preview(self):
        """First 100 characters for list views and auto-title."""
        if not self.body:
            return "Empty note"
        if len(self.body) <= 100:
            return self.body
        return self.body[:100].rsplit(" ", 1)[0] + "..."

    @property
    def display_title(self):
        """Title if set, otherwise body preview."""
        return self.title if self.title else self.body_preview

    @property
    def attachment_count(self):
        """Number of entities this note is attached to."""
        return self.attachments.count()


class NoteAttachment(models.Model):
    """
    Links a Note to any WLJ entity via GenericForeignKey.

    A note can be attached to multiple entities.
    An entity can have multiple notes attached to it.
    This is a many-to-many relationship via GFK.

    Uses the same pattern as CosReflection in apps/cos/models.py.
    """

    note = models.ForeignKey(
        Note,
        on_delete=models.CASCADE,
        related_name="attachments",
    )
    content_type = models.ForeignKey(
        ContentType,
        on_delete=models.CASCADE,
        help_text="Type of the attached entity.",
    )
    object_id = models.PositiveIntegerField(
        help_text="ID of the attached entity.",
    )
    attached_entity = GenericForeignKey("content_type", "object_id")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]
        unique_together = ["note", "content_type", "object_id"]
        indexes = [
            models.Index(
                fields=["content_type", "object_id"],
                name="noteattach_entity",
            ),
            models.Index(
                fields=["note", "content_type"],
                name="noteattach_note_ct",
            ),
        ]

    def __str__(self):
        return f"Note {self.note_id} -> {self.content_type}:{self.object_id}"
