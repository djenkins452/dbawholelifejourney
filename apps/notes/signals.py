"""
Django signals for Notes search index consistency.

Keeps tags_text, attachments_text, search_vector, and embeddings in sync when:
- Tags are added/removed from a note (m2m_changed)
- NoteAttachments are created/deleted (post_save/post_delete)
- Attached entities are renamed (pre_save/post_save via registry)
- Note content fields change (post_save → embedding refresh)
"""

import logging

from django.contrib.contenttypes.models import ContentType
from django.db.models.signals import m2m_changed, post_delete, post_save, pre_save
from django.dispatch import receiver

from .models import Note, NoteAttachment

logger = logging.getLogger(__name__)


def _enqueue_note_embedding(note_id):
    """Enqueue the OpenAI-backed embedding refresh off the request thread.

    Embedding generation calls the OpenAI API; a note save is NOT a path the
    user should wait on an LLM for. Fire-and-forget via safe_enqueue (runs
    inline under EAGER/tests, async in prod, skipped if the broker is down —
    the next content edit re-enqueues).
    """
    if not note_id:
        return
    from apps.core.celery_utils import safe_enqueue
    from .tasks import deferred_update_note_embedding
    safe_enqueue(deferred_update_note_embedding, note_id)


# ---------------------------------------------------------------------------
# Note tag/attachment signals (Phase 3)
# ---------------------------------------------------------------------------


# Cache for old Note content field values keyed by note pk
_old_note_content = {}

# Fields that, when changed, trigger an embedding refresh
_EMBEDDING_CONTENT_FIELDS = ("title", "body")


@receiver(pre_save, sender=Note)
def note_pre_save_capture(sender, instance, **kwargs):
    """Capture old title/body before save for embedding change detection."""
    if not instance.pk:
        return
    try:
        old_values = (
            Note.objects.filter(pk=instance.pk)
            .values_list(*_EMBEDDING_CONTENT_FIELDS)
            .first()
        )
        if old_values is not None:
            _old_note_content[instance.pk] = dict(
                zip(_EMBEDDING_CONTENT_FIELDS, old_values)
            )
    except Exception:
        pass


@receiver(post_save, sender=Note)
def note_post_save_embedding(sender, instance, created, **kwargs):
    """Trigger embedding update when Note content fields change."""
    # Skip if this save was triggered by update_fields that don't affect content
    update_fields = kwargs.get("update_fields")
    if update_fields is not None:
        content_fields = {"title", "body", "tags_text", "attachments_text"}
        if not content_fields.intersection(set(update_fields)):
            return

    needs_embedding = False

    if created:
        needs_embedding = True
    else:
        old_values = _old_note_content.pop(instance.pk, None)
        if old_values is not None:
            for field_name, old_value in old_values.items():
                new_value = getattr(instance, field_name, None)
                if old_value != new_value:
                    needs_embedding = True
                    break

    if needs_embedding:
        _enqueue_note_embedding(instance.pk)


@receiver(m2m_changed, sender=Note.tags.through)
def note_tags_changed(sender, instance, action, **kwargs):
    """Rebuild tags_text, refresh search_vector, and update embedding when tags change."""
    if action in ("post_add", "post_remove", "post_clear"):
        instance.refresh_search_index(rebuild_tags=True)
        # Tags changed → refresh embedding too (deferred; the worker reads the
        # freshly-persisted tags_text when it rebuilds the embedding text).
        _enqueue_note_embedding(instance.pk)


@receiver(post_save, sender=NoteAttachment)
def attachment_created(sender, instance, created, **kwargs):
    """Rebuild attachments_text and update embedding when a NoteAttachment is created."""
    if created:
        instance.note.refresh_search_index(rebuild_attachments=True)
        _enqueue_note_embedding(instance.note_id)


@receiver(post_delete, sender=NoteAttachment)
def attachment_deleted(sender, instance, **kwargs):
    """Rebuild attachments_text and update embedding when a NoteAttachment is deleted."""
    try:
        # note may have been cascade-deleted; check it still exists
        note = Note.objects.get(pk=instance.note_id)
        note.refresh_search_index(rebuild_attachments=True)
        _enqueue_note_embedding(note.pk)
    except Note.DoesNotExist:
        pass


# ---------------------------------------------------------------------------
# Entity rename signals (Phase 4B.1 Layer 2, refactored Phase 4B.2)
#
# Registry-driven rename detection. Models and their display fields are
# defined in index_registry.NOTE_INDEX_REGISTRY — adding a new model
# there automatically wires up rename signals.
# ---------------------------------------------------------------------------

# Cache for old field values keyed by (model_label, pk)
_old_field_values = {}


def _get_registry_model_classes():
    """Lazily import models from the registry and return {model_class: config} mapping."""
    from django.apps import apps

    from .index_registry import NOTE_INDEX_REGISTRY

    result = {}
    for model_path, config in NOTE_INDEX_REGISTRY.items():
        app_label, model_name = model_path.split(".")
        try:
            model_class = apps.get_model(app_label, model_name)
            result[model_class] = config
        except LookupError:
            pass
    return result


def _entity_pre_save(sender, instance, **kwargs):
    """Capture old display field values before save for rename detection."""
    if not instance.pk:
        return  # new instance, no rename possible
    model_classes = _get_registry_model_classes()
    config = model_classes.get(sender)
    if not config:
        return
    try:
        display_fields = config["display_fields"]
        old_values = (
            sender.objects.filter(pk=instance.pk)
            .values_list(*display_fields)
            .first()
        )
        if old_values is not None:
            label = f"{sender._meta.app_label}.{sender._meta.model_name}"
            _old_field_values[(label, instance.pk)] = dict(
                zip(display_fields, old_values)
            )
    except Exception:
        pass


def _entity_post_save(sender, instance, created, **kwargs):
    """If any display field changed, refresh notes attached to this entity."""
    if created:
        return  # new instance, no rename
    model_classes = _get_registry_model_classes()
    config = model_classes.get(sender)
    if not config:
        return

    label = f"{sender._meta.app_label}.{sender._meta.model_name}"
    key = (label, instance.pk)
    old_values = _old_field_values.pop(key, None)
    if old_values is None:
        return

    # Check if any display field actually changed
    changed = False
    for field_name, old_value in old_values.items():
        new_value = getattr(instance, field_name, None)
        if old_value != new_value:
            changed = True
            logger.info(
                "Entity rename detected: %s #%s field '%s': '%s' -> '%s'. Refreshing notes.",
                label, instance.pk, field_name, old_value, new_value,
            )
            break

    if not changed:
        return

    # Display field changed — refresh notes attached to this entity
    from .services import refresh_notes_for_entity

    refresh_notes_for_entity(
        content_type_str=label,
        object_id=instance.pk,
    )


def connect_rename_signals():
    """Connect pre_save/post_save signals for rename detection from registry."""
    for model_class in _get_registry_model_classes():
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
