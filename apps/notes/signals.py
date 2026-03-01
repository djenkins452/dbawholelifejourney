"""
Django signals for Notes search index consistency.

Keeps tags_text, attachments_text, and search_vector in sync when:
- Tags are added/removed from a note (m2m_changed)
- NoteAttachments are created/deleted (post_save/post_delete)
"""

import logging

from django.db.models.signals import m2m_changed, post_delete, post_save
from django.dispatch import receiver

from .models import Note, NoteAttachment

logger = logging.getLogger(__name__)


@receiver(m2m_changed, sender=Note.tags.through)
def note_tags_changed(sender, instance, action, **kwargs):
    """Rebuild tags_text and refresh search_vector when tags change."""
    if action in ("post_add", "post_remove", "post_clear"):
        instance.refresh_search_index(rebuild_tags=True)


@receiver(post_save, sender=NoteAttachment)
def attachment_created(sender, instance, created, **kwargs):
    """Rebuild attachments_text when a NoteAttachment is created."""
    if created:
        instance.note.refresh_search_index(rebuild_attachments=True)


@receiver(post_delete, sender=NoteAttachment)
def attachment_deleted(sender, instance, **kwargs):
    """Rebuild attachments_text when a NoteAttachment is deleted."""
    try:
        # note may have been cascade-deleted; check it still exists
        note = Note.objects.get(pk=instance.note_id)
        note.refresh_search_index(rebuild_attachments=True)
    except Note.DoesNotExist:
        pass
