"""
Capture Storage Utilities - S3 presigned URL generation for audio files.

This module provides functions for generating presigned URLs for uploading
and downloading audio files to/from S3-compatible storage.

Audio files are stored temporarily (default 7 days) and automatically
deleted via S3 lifecycle policy.
"""

import logging
import uuid
from datetime import timedelta
from typing import Optional

from django.conf import settings
from django.utils import timezone

logger = logging.getLogger(__name__)


class CaptureStorageError(Exception):
    """Exception raised for storage-related errors."""
    pass


class CaptureStorageNotConfiguredError(CaptureStorageError):
    """Exception raised when S3 storage is not configured."""
    pass


def _get_s3_client():
    """
    Get a boto3 S3 client configured with capture storage settings.

    Returns:
        boto3.client: Configured S3 client

    Raises:
        CaptureStorageNotConfiguredError: If required settings are missing
    """
    # Check required settings
    if not settings.CAPTURE_AUDIO_BUCKET:
        raise CaptureStorageNotConfiguredError(
            "CAPTURE_AUDIO_BUCKET is not configured. "
            "Set the environment variable to enable audio storage."
        )

    if not settings.CAPTURE_AWS_ACCESS_KEY_ID or not settings.CAPTURE_AWS_SECRET_ACCESS_KEY:
        raise CaptureStorageNotConfiguredError(
            "AWS credentials not configured. "
            "Set CAPTURE_AWS_ACCESS_KEY_ID and CAPTURE_AWS_SECRET_ACCESS_KEY."
        )

    try:
        import boto3
        from botocore.config import Config
    except ImportError:
        raise CaptureStorageError(
            "boto3 is not installed. Run: pip install boto3"
        )

    # Configure client
    client_kwargs = {
        'aws_access_key_id': settings.CAPTURE_AWS_ACCESS_KEY_ID,
        'aws_secret_access_key': settings.CAPTURE_AWS_SECRET_ACCESS_KEY,
        'region_name': settings.CAPTURE_AWS_REGION,
        'config': Config(signature_version='s3v4'),
    }

    # Add custom endpoint URL if configured (for S3-compatible services)
    if settings.CAPTURE_S3_ENDPOINT_URL:
        client_kwargs['endpoint_url'] = settings.CAPTURE_S3_ENDPOINT_URL

    return boto3.client('s3', **client_kwargs)


def generate_upload_presigned_url(
    user_id: str,
    content_type: str = 'audio/webm',
    filename: Optional[str] = None,
) -> dict:
    """
    Generate a presigned URL for uploading an audio file to S3.

    The generated URL allows direct upload from the browser to S3,
    bypassing the Django server for better performance.

    Args:
        user_id: The user's ID (used in the S3 key path)
        content_type: MIME type of the audio file (default: audio/webm)
        filename: Optional original filename (used for extension)

    Returns:
        dict: Contains:
            - url: The presigned upload URL
            - key: The S3 object key
            - expires_at: When the upload URL expires
            - audio_expires_at: When the audio file will be deleted

    Raises:
        CaptureStorageNotConfiguredError: If storage is not configured
        CaptureStorageError: If URL generation fails
    """
    client = _get_s3_client()

    # Generate unique key with user ID prefix for organization
    # Format: captures/{user_id}/{uuid}.{ext}
    file_id = uuid.uuid4()
    extension = _get_extension_from_content_type(content_type)
    if filename and '.' in filename:
        extension = filename.rsplit('.', 1)[1].lower()

    key = f"captures/{user_id}/{file_id}.{extension}"

    # Calculate expiration times
    upload_expires_at = timezone.now() + timedelta(
        seconds=settings.CAPTURE_PRESIGNED_URL_EXPIRATION
    )
    audio_expires_at = timezone.now() + timedelta(
        days=settings.CAPTURE_AUDIO_RETENTION_DAYS
    )

    try:
        url = client.generate_presigned_url(
            'put_object',
            Params={
                'Bucket': settings.CAPTURE_AUDIO_BUCKET,
                'Key': key,
                'ContentType': content_type,
            },
            ExpiresIn=settings.CAPTURE_PRESIGNED_URL_EXPIRATION,
        )
    except Exception as e:
        logger.error(f"Failed to generate upload presigned URL: {e}")
        raise CaptureStorageError(f"Failed to generate upload URL: {e}")

    logger.info(f"Generated upload URL for user {user_id}, key: {key}")

    return {
        'url': url,
        'key': key,
        'expires_at': upload_expires_at,
        'audio_expires_at': audio_expires_at,
    }


def generate_download_presigned_url(
    key: str,
    expiration_seconds: Optional[int] = None,
) -> dict:
    """
    Generate a presigned URL for downloading an audio file from S3.

    Args:
        key: The S3 object key
        expiration_seconds: URL expiration in seconds (default: from settings)

    Returns:
        dict: Contains:
            - url: The presigned download URL
            - expires_at: When the URL expires

    Raises:
        CaptureStorageNotConfiguredError: If storage is not configured
        CaptureStorageError: If URL generation fails
    """
    client = _get_s3_client()

    if expiration_seconds is None:
        expiration_seconds = settings.CAPTURE_PRESIGNED_URL_EXPIRATION

    expires_at = timezone.now() + timedelta(seconds=expiration_seconds)

    try:
        url = client.generate_presigned_url(
            'get_object',
            Params={
                'Bucket': settings.CAPTURE_AUDIO_BUCKET,
                'Key': key,
            },
            ExpiresIn=expiration_seconds,
        )
    except Exception as e:
        logger.error(f"Failed to generate download presigned URL for key {key}: {e}")
        raise CaptureStorageError(f"Failed to generate download URL: {e}")

    return {
        'url': url,
        'expires_at': expires_at,
    }


def delete_audio_file(key: str) -> bool:
    """
    Delete an audio file from S3.

    This is typically not needed as files are auto-deleted by lifecycle policy,
    but can be used for immediate cleanup (e.g., user deletes capture).

    Args:
        key: The S3 object key

    Returns:
        bool: True if deletion was successful

    Raises:
        CaptureStorageNotConfiguredError: If storage is not configured
        CaptureStorageError: If deletion fails
    """
    client = _get_s3_client()

    try:
        client.delete_object(
            Bucket=settings.CAPTURE_AUDIO_BUCKET,
            Key=key,
        )
        logger.info(f"Deleted audio file: {key}")
        return True
    except Exception as e:
        logger.error(f"Failed to delete audio file {key}: {e}")
        raise CaptureStorageError(f"Failed to delete audio file: {e}")


def is_storage_configured() -> bool:
    """
    Check if S3 storage is properly configured.

    Returns:
        bool: True if all required settings are present
    """
    return bool(
        settings.CAPTURE_AUDIO_BUCKET
        and settings.CAPTURE_AWS_ACCESS_KEY_ID
        and settings.CAPTURE_AWS_SECRET_ACCESS_KEY
    )


def _get_extension_from_content_type(content_type: str) -> str:
    """
    Get file extension from MIME content type.

    Args:
        content_type: MIME type string

    Returns:
        str: File extension without dot
    """
    # Strip codec parameters (e.g., "audio/webm;codecs=opus" → "audio/webm")
    base_type = content_type.split(';')[0].strip()
    content_type_map = {
        'audio/webm': 'webm',
        'audio/ogg': 'ogg',
        'audio/mp3': 'mp3',
        'audio/mpeg': 'mp3',
        'audio/mp4': 'm4a',
        'audio/x-m4a': 'm4a',
        'audio/wav': 'wav',
        'audio/x-wav': 'wav',
        'audio/flac': 'flac',
        'audio/aac': 'aac',
        'audio/x-caf': 'caf',
        'audio/3gpp': '3gp',
        'audio/3gpp2': '3g2',
        'video/mp4': 'm4a',
    }
    return content_type_map.get(base_type, 'webm')
