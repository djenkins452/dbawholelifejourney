"""Email service for audio expiration reminders."""

import logging

from django.conf import settings
from django.core.mail import EmailMessage
from django.template.loader import render_to_string
from django.utils.html import strip_tags

from apps.core.utils import user_log_id

logger = logging.getLogger(__name__)

DEFAULT_FROM_EMAIL = getattr(settings, 'DEFAULT_FROM_EMAIL', 'admin@wholelifejourney.com')


def send_expiration_reminder_email(capture_entry):
    """
    Send an audio expiration reminder email for a capture entry.

    Args:
        capture_entry: CaptureEntry model instance with audio expiring soon

    Returns:
        dict with 'success' boolean and 'error' message if failed
    """
    user = capture_entry.user
    title = capture_entry.title or 'Untitled Recording'

    # Calculate days remaining
    if capture_entry.audio_expires_at:
        from django.utils import timezone
        days_remaining = (capture_entry.audio_expires_at - timezone.now()).days
        days_remaining = max(0, days_remaining)
        expires_date = capture_entry.audio_expires_at.strftime('%B %d, %Y')
    else:
        days_remaining = 2
        expires_date = 'Soon'

    # Format duration
    formatted_duration = None
    if capture_entry.duration_seconds:
        minutes = capture_entry.duration_seconds // 60
        seconds = capture_entry.duration_seconds % 60
        formatted_duration = f"{minutes}:{seconds:02d}"

    # Build download URL
    download_url = f"https://wholelifejourney.com/capture/{capture_entry.id}/"

    # Prepare context for email template
    context = {
        'title': title,
        'days_remaining': days_remaining,
        'expires_date': expires_date,
        'formatted_duration': formatted_duration,
        'created_date': capture_entry.created_at.strftime('%B %d, %Y'),
        'download_url': download_url,
        'entry': capture_entry,
    }

    # Render email content
    html_content = render_to_string('capture/email/expiration_reminder.html', context)
    strip_tags(html_content)

    # Build subject
    subject = f"Audio Expiring Soon: {title}"

    try:
        # Create and send email
        email = EmailMessage(
            subject=subject,
            body=html_content,
            from_email=DEFAULT_FROM_EMAIL,
            to=[user.email],
        )
        email.content_subtype = 'html'

        email.send(fail_silently=False)

        logger.info(
            f"Expiration reminder email sent for entry {capture_entry.id} "
            f"to {user_log_id(user)}"
        )

        return {'success': True}

    except Exception as e:
        logger.exception(
            f"Failed to send expiration reminder email for entry {capture_entry.id}: {e}"
        )
        return {
            'success': False,
            'error': f'Failed to send email: {str(e)}'
        }
