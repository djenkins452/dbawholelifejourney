"""
Whole Life Journey — CoS Documentation Sync

Project: Whole Life Journey
Path: apps/core/ai_docs/cos_doc_sync.py
Purpose: Synchronize generated CoS documentation to admin guide models

Description:
    Takes the output of generate_cos_admin_guide() and writes it to
    AdminGuideSection and AdminGuideArticle models. Handles create,
    update, and cleanup of stale articles.

    Also provides a management command hook and startup check.

Public API:
    - sync_cos_admin_guide() -> dict
      Full sync: generate + write to DB.
    - needs_sync() -> bool
      Check if the current checksum differs from last sync.

Copyright:
    (c) Whole Life Journey. All rights reserved.
"""

import logging

from django.utils import timezone

from .cos_doc_generator import generate_cos_admin_guide, _compute_dependency_checksum

logger = logging.getLogger(__name__)

# Key used to track the last sync checksum in DataLoadConfig
SYNC_CONFIG_NAME = "cos_doc_sync_checksum"


def _get_last_synced_checksum():
    """
    Retrieve the checksum from the last successful sync.

    Uses DataLoadConfig.description to store the checksum string.

    Returns:
        str or None — last synced checksum.
    """
    try:
        from apps.admin_console.models import DataLoadConfig
        config = DataLoadConfig.objects.filter(
            loader_name=SYNC_CONFIG_NAME,
        ).first()
        if config and config.is_loaded:
            return config.description  # Checksum stored in description
    except Exception:
        pass
    return None


def _store_synced_checksum(checksum, articles_created=0, articles_updated=0):
    """
    Store the checksum after a successful sync.

    Uses DataLoadConfig to track the sync state so it's visible
    in the admin console Data Loaders page.
    """
    try:
        from apps.admin_console.models import DataLoadConfig
        config, _ = DataLoadConfig.objects.update_or_create(
            loader_name=SYNC_CONFIG_NAME,
            defaults={
                'display_name': 'CoS Documentation Sync',
                'loader_type': 'command',
                'description': checksum,
            },
        )
        config.mark_loaded(
            loaded_by='cos_doc_sync',
            records_created=articles_created,
            records_updated=articles_updated,
        )
    except Exception as e:
        logger.warning("Could not store sync checksum: %s", e)


def needs_sync():
    """
    Check if the CoS documentation needs to be re-synced.

    Compares the current dependency checksum to the last synced value.

    Returns:
        bool — True if a sync is needed.
    """
    current = _compute_dependency_checksum()
    last = _get_last_synced_checksum()
    return current != last


def sync_cos_admin_guide(force=False):
    """
    Generate CoS documentation and sync to admin guide models.

    Creates or updates the CoS section and all articles.
    Removes articles that are no longer in the generated set.

    Args:
        force: If True, sync even if checksum hasn't changed.

    Returns:
        dict with keys:
            - synced: bool — whether sync was performed
            - reason: str — why sync was/wasn't performed
            - articles_created: int
            - articles_updated: int
            - articles_removed: int
            - checksum: str
            - validation: dict
    """
    if not force and not needs_sync():
        return {
            'synced': False,
            'reason': 'Checksum unchanged — documentation is current',
            'articles_created': 0,
            'articles_updated': 0,
            'articles_removed': 0,
            'checksum': _compute_dependency_checksum(),
            'validation': {'is_valid': True, 'errors': []},
        }

    # Generate the guide
    guide = generate_cos_admin_guide()

    # Import models
    try:
        from apps.admin_console.models import AdminGuideSection, AdminGuideArticle
    except ImportError as e:
        logger.error("Cannot import admin guide models: %s", e)
        return {
            'synced': False,
            'reason': f'Import error: {e}',
            'articles_created': 0,
            'articles_updated': 0,
            'articles_removed': 0,
            'checksum': guide['checksum'],
            'validation': guide['validation'],
        }

    section_data = guide['section']
    articles_data = guide['articles']

    # Create or update section
    section, created = AdminGuideSection.objects.update_or_create(
        section_key=section_data['section_key'],
        defaults={
            'title': section_data['title'],
            'icon': section_data['icon'],
            'description': section_data['description'],
            'order': 90,  # High order — appears near end of guide sidebar
            'is_active': True,
        },
    )

    if created:
        logger.info("Created admin guide section: %s", section.section_key)

    # Track article slugs for cleanup
    generated_slugs = set()
    articles_created = 0
    articles_updated = 0

    for article_data in articles_data:
        slug = article_data['slug']
        generated_slugs.add(slug)

        article, art_created = AdminGuideArticle.objects.update_or_create(
            section=section,
            slug=slug,
            defaults={
                'title': article_data['title'],
                'content': article_data['content'],
                'order': article_data['order'],
                'is_editable': False,  # Auto-generated — not editable
                'is_active': True,
            },
        )

        if art_created:
            articles_created += 1
        else:
            articles_updated += 1

    # Remove stale articles (in this section only)
    stale = AdminGuideArticle.objects.filter(
        section=section,
    ).exclude(slug__in=generated_slugs)
    articles_removed = stale.count()
    stale.delete()

    # Store checksum
    _store_synced_checksum(
        guide['checksum'],
        articles_created=articles_created,
        articles_updated=articles_updated,
    )

    logger.info(
        "CoS admin guide synced: %d created, %d updated, %d removed, "
        "checksum=%s",
        articles_created, articles_updated, articles_removed,
        guide['checksum'],
    )

    return {
        'synced': True,
        'reason': 'Sync completed successfully',
        'articles_created': articles_created,
        'articles_updated': articles_updated,
        'articles_removed': articles_removed,
        'checksum': guide['checksum'],
        'validation': guide['validation'],
    }
