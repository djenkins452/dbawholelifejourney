"""
Whole Life Journey - Notes Utilities

Project: Whole Life Journey
Path: apps/notes/utils.py
Purpose: Attachable model whitelist and resolution helpers
"""

from django.contrib.contenttypes.models import ContentType
from django.db.models import Q


# Whitelist of models that notes can be attached to.
# Format: "app_label.model" (lowercase).
ATTACHABLE_MODELS = {
    "life.project",
    "life.task",
    "purpose.lifegoal",
    "purpose.habitgoal",
    "journal.journalentry",
    "calendar_engine.calendarevent",
    "faith.biblestudynote",
}


def get_attachable_content_types():
    """Return ContentType queryset for models that support note attachments."""
    q = Q()
    for label in ATTACHABLE_MODELS:
        app_label, model = label.split(".")
        q |= Q(app_label=app_label, model=model)
    return ContentType.objects.filter(q)


def resolve_attachment_target(content_type_id, object_id, user):
    """
    Validate and resolve an attachment target.

    Returns (content_type, target_object) or raises ValueError.
    Ensures the target model is in the whitelist and belongs to the user.
    """
    ct = ContentType.objects.get(pk=content_type_id)
    model_label = f"{ct.app_label}.{ct.model}"
    if model_label not in ATTACHABLE_MODELS:
        raise ValueError(f"Model {model_label} is not attachable.")

    model_class = ct.model_class()
    try:
        obj = model_class.objects.filter(user=user).get(pk=object_id)
    except model_class.DoesNotExist:
        raise ValueError(f"{ct.name} #{object_id} not found.")
    return ct, obj


def get_entity_display_name(attachment):
    """
    Return a human-readable display name for an attachment's target entity.

    Uses priority: display_title > title > name > str(obj).
    Falls back gracefully if the entity has been deleted.
    """
    try:
        entity = attachment.attached_entity
        if entity is None:
            return f"Deleted {attachment.content_type.name}"
        return (
            getattr(entity, "display_title", None)
            or getattr(entity, "title", None)
            or getattr(entity, "name", None)
            or str(entity)
        )
    except Exception:
        return f"Deleted {attachment.content_type.name}"
