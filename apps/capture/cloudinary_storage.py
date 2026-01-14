"""
Capture Cloudinary Storage - Audio file storage using Cloudinary.

This module provides functions for uploading and managing audio files
using Cloudinary's video/audio upload capabilities.

Audio files are stored with a 7-day retention tag for manual cleanup.
"""

import logging
import uuid
from datetime import timedelta
from typing import Optional

from django.conf import settings
from django.utils import timezone

logger = logging.getLogger(__name__)


class CloudinaryStorageError(Exception):
    """Exception raised for Cloudinary storage errors."""
    pass


class CloudinaryNotConfiguredError(CloudinaryStorageError):
    """Exception raised when Cloudinary is not configured."""
    pass


def is_cloudinary_configured() -> bool:
    """
    Check if Cloudinary is properly configured.

    Returns:
        bool: True if Cloudinary credentials are present
    """
    try:
        import cloudinary
        config = cloudinary.config()
        return bool(config.cloud_name and config.api_key and config.api_secret)
    except ImportError:
        return False


def upload_audio(
    file_data,
    user_id: str,
    filename: Optional[str] = None,
    content_type: str = 'audio/webm',
) -> dict:
    """
    Upload an audio file to Cloudinary.

    Args:
        file_data: File-like object or bytes containing audio data
        user_id: User ID for organizing uploads
        filename: Optional original filename
        content_type: MIME type of the audio

    Returns:
        dict: Contains:
            - url: Public URL for the audio file
            - public_id: Cloudinary public ID for deletion
            - audio_expires_at: When the audio should be considered expired

    Raises:
        CloudinaryNotConfiguredError: If Cloudinary is not configured
        CloudinaryStorageError: If upload fails
    """
    if not is_cloudinary_configured():
        raise CloudinaryNotConfiguredError(
            "Cloudinary is not configured. "
            "Set CLOUDINARY_CLOUD_NAME, CLOUDINARY_API_KEY, and CLOUDINARY_API_SECRET."
        )

    try:
        import cloudinary.uploader
    except ImportError:
        raise CloudinaryStorageError("cloudinary package is not installed")

    # Generate unique public_id
    file_id = uuid.uuid4()
    public_id = f"captures/{user_id}/{file_id}"

    # Calculate expiration (for tracking, not enforced by Cloudinary)
    audio_expires_at = timezone.now() + timedelta(
        days=getattr(settings, 'CAPTURE_AUDIO_RETENTION_DAYS', 7)
    )

    try:
        # Upload as video resource_type (handles audio files)
        result = cloudinary.uploader.upload(
            file_data,
            resource_type="video",  # Cloudinary uses 'video' for audio too
            public_id=public_id,
            folder="",  # public_id already includes folder
            tags=["capture_audio", f"user_{user_id}"],
            context=f"user_id={user_id}|expires_at={audio_expires_at.isoformat()}",
        )

        logger.info(f"Uploaded audio to Cloudinary: {public_id}")

        return {
            'url': result['secure_url'],
            'public_id': result['public_id'],
            'audio_expires_at': audio_expires_at,
            'duration_seconds': int(result.get('duration', 0)),
        }

    except Exception as e:
        logger.error(f"Failed to upload audio to Cloudinary: {e}")
        raise CloudinaryStorageError(f"Failed to upload audio: {e}")


def delete_audio(public_id: str) -> bool:
    """
    Delete an audio file from Cloudinary.

    Args:
        public_id: Cloudinary public ID

    Returns:
        bool: True if deletion was successful

    Raises:
        CloudinaryStorageError: If deletion fails
    """
    if not is_cloudinary_configured():
        logger.warning("Cloudinary not configured, skipping delete")
        return False

    try:
        import cloudinary.uploader
    except ImportError:
        raise CloudinaryStorageError("cloudinary package is not installed")

    try:
        result = cloudinary.uploader.destroy(
            public_id,
            resource_type="video",
        )
        success = result.get('result') == 'ok'
        if success:
            logger.info(f"Deleted audio from Cloudinary: {public_id}")
        else:
            logger.warning(f"Cloudinary delete returned: {result}")
        return success

    except Exception as e:
        logger.error(f"Failed to delete audio from Cloudinary: {e}")
        raise CloudinaryStorageError(f"Failed to delete audio: {e}")


def get_audio_url(public_id: str) -> str:
    """
    Get the URL for an audio file.

    Args:
        public_id: Cloudinary public ID

    Returns:
        str: Public URL for the audio file
    """
    try:
        import cloudinary
        return cloudinary.CloudinaryVideo(public_id).build_url(secure=True)
    except Exception as e:
        logger.error(f"Failed to get audio URL: {e}")
        raise CloudinaryStorageError(f"Failed to get audio URL: {e}")
