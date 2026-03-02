"""
Scan signals — Auto-trigger comprehensive vision analysis on image uploads.

Connects to post_save signals on models with image fields to automatically
analyze uploaded images and persist results for CoS context.
"""

import logging

from django.db.models.signals import post_save
from django.dispatch import receiver

logger = logging.getLogger(__name__)


def _trigger_analysis(instance, image_field_name, source_type, get_user):
    """
    Common handler: read image field, call comprehensive vision service.

    Args:
        instance: The saved model instance.
        image_field_name: Name of the ImageField/FileField attribute.
        source_type: ImageAnalysis.SOURCE_CHOICES value.
        get_user: Callable that returns the user from the instance.
    """
    field = getattr(instance, image_field_name, None)
    if not field or not field.name:
        return

    try:
        from apps.scan.services.image_utils import file_is_analyzable_image, image_field_to_base64
        if not file_is_analyzable_image(field):
            return

        user = get_user(instance)

        # Check scan consent
        from apps.scan.models import ScanConsent
        if not ScanConsent.objects.filter(user=user).exists():
            return

        # Check for existing analysis (avoid re-analyzing on every save)
        from apps.scan.models import ImageAnalysis
        from apps.scan.services.image_utils import compute_image_hash

        base64_data, mime_type = image_field_to_base64(field)
        if not base64_data:
            return

        image_hash = compute_image_hash(base64_data)
        if ImageAnalysis.objects.filter(user=user, image_hash=image_hash, status='completed').exists():
            return

        from apps.scan.services.comprehensive_vision import comprehensive_vision_service
        comprehensive_vision_service.analyze(
            image_base64=base64_data,
            mime_type=mime_type,
            user=user,
            source_type=source_type,
            source_object=instance,
        )
    except Exception as e:
        logger.warning("Auto vision analysis failed for %s %s: %s",
                        source_type, instance.pk, e)


@receiver(post_save, sender='life.InventoryPhoto')
def analyze_inventory_photo(sender, instance, created, **kwargs):
    """Analyze new inventory photos."""
    if created:
        _trigger_analysis(instance, 'image', 'inventory',
                          lambda i: i.item.user)


@receiver(post_save, sender='life.Pet')
def analyze_pet_photo(sender, instance, **kwargs):
    """Analyze pet photo when set."""
    _trigger_analysis(instance, 'photo', 'pet',
                      lambda i: i.user)


@receiver(post_save, sender='life.Recipe')
def analyze_recipe_image(sender, instance, **kwargs):
    """Analyze recipe image when set."""
    _trigger_analysis(instance, 'image', 'recipe',
                      lambda i: i.user)


@receiver(post_save, sender='life.Document')
def analyze_document_image(sender, instance, created, **kwargs):
    """Analyze document file if it's an image."""
    if created:
        _trigger_analysis(instance, 'file', 'document',
                          lambda i: i.user)


@receiver(post_save, sender='notes.NoteImage')
def analyze_note_image(sender, instance, created, **kwargs):
    """Analyze new note images."""
    if created:
        _trigger_analysis(instance, 'image', 'note',
                          lambda i: i.note.user)
