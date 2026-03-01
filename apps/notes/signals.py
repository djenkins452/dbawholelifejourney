"""
Django signals for Notes search index consistency.

Keeps tags_text, attachments_text, and search_vector in sync when:
- Tags are added/removed from a note (m2m_changed)
- NoteAttachments are created/deleted (post_save/post_delete)
- Attached entities are renamed (pre_save/post_save on whitelisted models)
"""

import logging

from django.contrib.contenttypes.models import ContentType
from django.db.models.signals import m2m_changed, post_delete, post_save, pre_save
from django.dispatch import receiver

from .models import Note, NoteAttachment

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Note tag/attachment signals (Phase 3)
# ---------------------------------------------------------------------------


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


# ---------------------------------------------------------------------------
# Entity rename signals (Phase 4B.1 Layer 2)
#
# Detects title/name changes on whitelisted attachable models and refreshes
# the notes' attachments_text + search_vector automatically.
#
# Models covered: Task, Project, LifeGoal, HabitGoal, JournalEntry
# (BibleStudyNote and CalendarEvent omitted — low rename frequency)
# ---------------------------------------------------------------------------

# Map of model path -> title field name for rename detection
_RENAME_MODELS = {
    "life.Task": "title",
    "life.Project": "title",
    "purpose.LifeGoal": "title",
    "purpose.HabitGoal": "name",
    "journal.JournalEntry": "title",
}

# Cache for old titles keyed by (model_label, pk)
_old_titles = {}


def _get_rename_model_classes():
    """Lazily import and return {model_class: title_field} mapping."""
    from django.apps import apps

    result = {}
    for model_path, field in _RENAME_MODELS.items():
        app_label, model_name = model_path.split(".")
        try:
            model_class = apps.get_model(app_label, model_name)
            result[model_class] = field
        except LookupError:
            pass
    return result


def _entity_pre_save(sender, instance, **kwargs):
    """Capture the old title before save for rename detection."""
    if not instance.pk:
        return  # new instance, no rename possible
    model_classes = _get_rename_model_classes()
    field_name = model_classes.get(sender)
    if not field_name:
        return
    try:
        old = sender.objects.filter(pk=instance.pk).values_list(field_name, flat=True).first()
        if old is not None:
            label = f"{sender._meta.app_label}.{sender._meta.model_name}"
            _old_titles[(label, instance.pk)] = old
    except Exception:
        pass


def _entity_post_save(sender, instance, created, **kwargs):
    """If the title changed, refresh notes attached to this entity."""
    if created:
        return  # new instance, no rename
    model_classes = _get_rename_model_classes()
    field_name = model_classes.get(sender)
    if not field_name:
        return

    label = f"{sender._meta.app_label}.{sender._meta.model_name}"
    key = (label, instance.pk)
    old_title = _old_titles.pop(key, None)
    if old_title is None:
        return

    new_title = getattr(instance, field_name, None)
    if old_title == new_title:
        return  # no rename

    # Title changed — refresh notes attached to this entity
    from .services import refresh_notes_for_entity

    logger.info(
        "Entity rename detected: %s #%s '%s' -> '%s'. Refreshing notes.",
        label, instance.pk, old_title, new_title,
    )
    refresh_notes_for_entity(
        content_type_str=label,
        object_id=instance.pk,
    )


def connect_rename_signals():
    """Connect pre_save/post_save signals for rename detection on whitelisted models."""
    for model_class in _get_rename_model_classes():
        pre_save.connect(
            _entity_pre_save,
            sender=model_class,
            dispatch_uid=f"notes_rename_pre_{model_class._meta.label_lower}",
        )
        post_save.connect(
            _entity_post_save,
            sender=model_class,
            dispatch_uid=f"notes_rename_post_{model_class._meta.label_lower}",
        )


# Connect on module import (called from apps.py ready())
connect_rename_signals()
