"""
DNE — APNs Push Notification Sender.

Wraps the apns2 library for sending push notifications via Apple's
HTTP/2 APNs service using token-based (JWT) authentication.

Configuration (environment variables):
    APNS_TEAM_ID — Apple Developer Team ID
    APNS_KEY_ID — APNs auth key identifier
    APNS_AUTH_KEY — .p8 key file contents (multi-line)
    APNS_BUNDLE_ID — App bundle identifier (default: com.wholelifejourney.app)
    APNS_USE_SANDBOX — Use sandbox APNs (default: same as DEBUG)
"""

import logging

from django.conf import settings as django_settings

logger = logging.getLogger(__name__)

# Module-level client cache (avoid re-creating on every push)
_apns_client = None


def _get_client():
    """Get or create a cached APNs client. Returns None if not configured."""
    global _apns_client
    if _apns_client is not None:
        return _apns_client

    try:
        from apns2.client import APNsClient
        from apns2.credentials import TokenCredentials
    except ImportError:
        logger.warning("DNE: apns2 library not installed")
        return None

    auth_key = getattr(django_settings, "APNS_AUTH_KEY", "")
    key_id = getattr(django_settings, "APNS_KEY_ID", "")
    team_id = getattr(django_settings, "APNS_TEAM_ID", "")

    if not all([auth_key, key_id, team_id]):
        logger.debug("DNE: APNs not configured (missing credentials)")
        return None

    # Handle escaped newlines in environment variables
    if "\\n" in auth_key and "\n" not in auth_key:
        auth_key = auth_key.replace("\\n", "\n")

    try:
        token_credentials = TokenCredentials(
            auth_key_p8=auth_key,
            auth_key_id=key_id,
            team_id=team_id,
        )

        use_sandbox = getattr(django_settings, "APNS_USE_SANDBOX", True)
        _apns_client = APNsClient(
            credentials=token_credentials,
            use_sandbox=use_sandbox,
        )
        return _apns_client

    except Exception as e:
        logger.error(f"DNE: Failed to create APNs client: {e}")
        return None


def send_push_notification(push_token, title, body, action_url="", sound="default"):
    """
    Send a single push notification via APNs.

    Args:
        push_token: Hex-encoded APNs device token.
        title: Notification title.
        body: Notification body text.
        action_url: Deep-link URL path (e.g., '/guidance/inbox/').
        sound: Alert sound name (default: 'default').

    Returns:
        True on success, False on failure.
    """
    try:
        from apns2.payload import Payload
    except ImportError:
        logger.warning("DNE: apns2 library not installed — push skipped")
        return False

    client = _get_client()
    if client is None:
        return False

    bundle_id = getattr(
        django_settings, "APNS_BUNDLE_ID", "com.wholelifejourney.app"
    )

    custom_data = {}
    if action_url:
        custom_data["action_url"] = action_url

    payload = Payload(
        alert={"title": title, "body": body[:200]},
        sound=sound,
        badge=1,
        custom=custom_data,
    )

    try:
        from apns2.client import NotificationPriority

        response = client.send_notification(
            token_hex=push_token,
            notification=payload,
            topic=bundle_id,
            priority=NotificationPriority.Delayed,  # Save battery
        )

        if response.is_successful:
            logger.debug(f"DNE: APNs push sent to token {push_token[:8]}...")
            return True
        else:
            logger.warning(
                f"DNE: APNs error: {response.description} "
                f"for token {push_token[:8]}..."
            )
            return False

    except Exception as e:
        logger.error(f"DNE: APNs send failed: {e}")
        return False


def reset_client():
    """Reset the cached APNs client (for testing or credential rotation)."""
    global _apns_client
    _apns_client = None
