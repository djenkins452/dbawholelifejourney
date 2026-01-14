"""Email service for sharing capture entries."""

import logging

from django.conf import settings
from django.core.mail import EmailMessage
from django.core.validators import validate_email
from django.core.exceptions import ValidationError
from django.template.loader import render_to_string
from django.utils.html import strip_tags

from .docx_generator import generate_docx, get_docx_filename

logger = logging.getLogger(__name__)

DEFAULT_FROM_EMAIL = getattr(settings, 'DEFAULT_FROM_EMAIL', 'admin@wholelifejourney.com')


def send_capture_email(capture_entry, recipient_email, sender_user, message=None):
    """
    Send a capture entry summary via email with Word document attachment.

    Args:
        capture_entry: CaptureEntry model instance
        recipient_email: Email address to send to
        sender_user: User sending the email (for display name)
        message: Optional personal message from sender

    Returns:
        dict with 'success' boolean and 'error' message if failed

    Raises:
        ValidationError: If recipient email is invalid
    """
    # Validate recipient email
    try:
        validate_email(recipient_email)
    except ValidationError:
        return {
            'success': False,
            'error': 'Invalid email address'
        }

    # Generate Word document attachment
    try:
        docx_bytes = generate_docx(capture_entry)
        docx_filename = get_docx_filename(capture_entry)
    except Exception as e:
        logger.exception(f"Document generation failed for entry {capture_entry.id}: {e}")
        return {
            'success': False,
            'error': 'Failed to generate document'
        }

    # Build email content
    sender_name = sender_user.get_full_name() or sender_user.email.split('@')[0]
    title = capture_entry.title or 'Capture Recording'

    subject = f"Summary from {sender_name}'s WLJ Capture: {title}"

    # Prepare context for email template
    context = {
        'sender_name': sender_name,
        'title': title,
        'message': message,
        'entry': capture_entry,
    }

    # Render email content
    html_content = render_to_string('capture/email/share_capture.html', context)
    text_content = strip_tags(html_content)

    try:
        # Create email with attachment
        email = EmailMessage(
            subject=subject,
            body=text_content,
            from_email=DEFAULT_FROM_EMAIL,
            to=[recipient_email],
            reply_to=[sender_user.email],
        )

        # Attach Word document
        content_type = 'application/vnd.openxmlformats-officedocument.wordprocessingml.document'
        email.attach(docx_filename, docx_bytes, content_type)

        # Attach HTML version
        email.content_subtype = 'html'
        email.body = html_content

        # Send email
        email.send(fail_silently=False)

        logger.info(
            f"Capture email sent for entry {capture_entry.id} "
            f"from {sender_user.email} to {recipient_email}"
        )

        return {'success': True}

    except Exception as e:
        logger.exception(
            f"Failed to send capture email for entry {capture_entry.id}: {e}"
        )
        return {
            'success': False,
            'error': 'Failed to send email. Please try again.'
        }


def send_processing_complete_email(capture_entry):
    """
    Send an email notification when delayed processing completes.

    This is sent when processing takes longer than expected (timeout scenario)
    and the user was told "we will email you when ready".

    Args:
        capture_entry: CaptureEntry model instance that just completed processing

    Returns:
        dict with 'success' boolean and 'error' message if failed
    """
    from django.urls import reverse
    from django.utils import timezone

    user = capture_entry.user

    # Don't send if already sent
    if capture_entry.completion_email_sent_at:
        logger.info(f"Completion email already sent for entry {capture_entry.id}")
        return {'success': True, 'already_sent': True}

    # Build email content
    title = capture_entry.title or 'Your Recording'

    subject = f"Your WLJ Capture is Ready: {title}"

    # Build detail URL
    try:
        detail_url = settings.SITE_URL + reverse('capture:detail', kwargs={'pk': capture_entry.id})
    except Exception:
        detail_url = f"https://wholelifejourney.com/capture/{capture_entry.id}/"

    # Prepare context for email template
    context = {
        'user': user,
        'title': title,
        'entry': capture_entry,
        'detail_url': detail_url,
    }

    # Render email content
    html_content = render_to_string('capture/email/processing_complete.html', context)
    text_content = strip_tags(html_content)

    try:
        # Create and send email
        email = EmailMessage(
            subject=subject,
            body=text_content,
            from_email=DEFAULT_FROM_EMAIL,
            to=[user.email],
        )

        # Attach HTML version
        email.content_subtype = 'html'
        email.body = html_content

        # Send email
        email.send(fail_silently=False)

        # Mark as sent
        capture_entry.completion_email_sent_at = timezone.now()
        capture_entry.save(update_fields=['completion_email_sent_at'])

        logger.info(f"Processing complete email sent for entry {capture_entry.id} to {user.email}")

        return {'success': True}

    except Exception as e:
        logger.exception(f"Failed to send processing complete email for entry {capture_entry.id}: {e}")
        return {
            'success': False,
            'error': 'Failed to send email notification.'
        }
