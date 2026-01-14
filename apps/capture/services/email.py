"""Email service for sharing capture entries."""

import logging

from django.conf import settings
from django.core.mail import EmailMessage
from django.core.validators import validate_email
from django.core.exceptions import ValidationError
from django.template.loader import render_to_string
from django.utils.html import strip_tags

from .pdf import generate_pdf, get_pdf_filename

logger = logging.getLogger(__name__)

DEFAULT_FROM_EMAIL = getattr(settings, 'DEFAULT_FROM_EMAIL', 'admin@wholelifejourney.com')


def send_capture_email(capture_entry, recipient_email, sender_user, message=None):
    """
    Send a capture entry summary via email with PDF attachment.

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

    # Generate PDF attachment
    try:
        pdf_bytes = generate_pdf(capture_entry)
        pdf_filename = get_pdf_filename(capture_entry)
    except ImportError as e:
        logger.error(f"PDF generation failed - WeasyPrint not installed: {e}")
        return {
            'success': False,
            'error': 'PDF generation is not available'
        }
    except Exception as e:
        logger.exception(f"PDF generation failed for entry {capture_entry.id}: {e}")
        return {
            'success': False,
            'error': 'Failed to generate PDF'
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

        # Attach PDF
        email.attach(pdf_filename, pdf_bytes, 'application/pdf')

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
