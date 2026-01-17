# ==============================================================================
# File: apps/admin_console/services/email_intake.py
# Project: Whole Life Journey - Django 5.x Personal Wellness/Journaling App
# Description: Email intake service for creating AdminTasks from emails
# Owner: Danny Jenkins (admin@wholelifejourney.com)
# Created: 2026-01-16
# ==============================================================================
"""
Email Intake Service

Polls IMAP mailbox for emails in the "INBOX/Automate" folder and creates AdminTasks.

Workflow:
1. Connect to IMAP mailbox (mail.privateemail.com)
2. Check "INBOX/Automate" folder for any emails
3. For each email found:
   - Parse subject, sender, body (and forwarded content if present)
   - Create AdminTask to review/work the email
   - Send confirmation reply with task details
   - Move email to "INBOX/New Requests" folder
4. Done

Environment Variables Required:
- EMAIL_INTAKE_HOST: IMAP server (mail.privateemail.com)
- EMAIL_INTAKE_PORT: IMAP port (993)
- EMAIL_INTAKE_USER: Email address (admin@wholelifejourney.com)
- EMAIL_INTAKE_PASSWORD: Email password
"""

import email
import imaplib
import logging
import re
from dataclasses import dataclass
from datetime import datetime
from email.header import decode_header
from email.utils import parseaddr, parsedate_to_datetime
from typing import Optional

from django.conf import settings
from django.core.mail import send_mail
from django.utils import timezone

logger = logging.getLogger(__name__)


@dataclass
class ParsedEmail:
    """Parsed email data from IMAP."""
    message_id: str
    subject: str
    sender: str
    sender_name: str
    date: Optional[datetime]
    body_text: str
    body_html: str
    uid: str  # IMAP UID for moving/deleting


class EmailIntakeError(Exception):
    """Base exception for email intake errors."""
    pass


class EmailConnectionError(EmailIntakeError):
    """Error connecting to IMAP server."""
    pass


class EmailProcessingError(EmailIntakeError):
    """Error processing an email."""
    pass


def get_email_settings():
    """Get email intake settings from Django settings/environment."""
    host = getattr(settings, 'EMAIL_INTAKE_HOST', None)
    port = getattr(settings, 'EMAIL_INTAKE_PORT', 993)
    user = getattr(settings, 'EMAIL_INTAKE_USER', None)
    password = getattr(settings, 'EMAIL_INTAKE_PASSWORD', None)

    # Validate required settings
    missing = []
    if not host:
        missing.append('EMAIL_INTAKE_HOST')
    if not user:
        missing.append('EMAIL_INTAKE_USER')
    if not password:
        missing.append('EMAIL_INTAKE_PASSWORD')

    if missing:
        raise EmailIntakeError(f"Missing required email settings: {', '.join(missing)}")

    return {
        'host': host,
        'port': int(port),
        'user': user,
        'password': password,
    }


def decode_mime_header(header_value: str) -> str:
    """Decode MIME encoded header value (e.g., =?UTF-8?Q?...?=)."""
    if not header_value:
        return ''

    decoded_parts = []
    for part, charset in decode_header(header_value):
        if isinstance(part, bytes):
            decoded_parts.append(part.decode(charset or 'utf-8', errors='replace'))
        else:
            decoded_parts.append(part)
    return ''.join(decoded_parts)


def extract_email_body(msg: email.message.Message) -> tuple[str, str]:
    """
    Extract text and HTML body from email message.

    Returns:
        Tuple of (text_body, html_body)
    """
    text_body = ''
    html_body = ''

    if msg.is_multipart():
        for part in msg.walk():
            content_type = part.get_content_type()
            content_disposition = str(part.get('Content-Disposition', ''))

            # Skip attachments
            if 'attachment' in content_disposition:
                continue

            try:
                payload = part.get_payload(decode=True)
                if payload is None:
                    continue

                charset = part.get_content_charset() or 'utf-8'
                decoded = payload.decode(charset, errors='replace')

                if content_type == 'text/plain':
                    text_body = decoded
                elif content_type == 'text/html':
                    html_body = decoded
            except Exception as e:
                logger.warning(f"Error decoding email part: {e}")
                continue
    else:
        # Not multipart - single body
        try:
            payload = msg.get_payload(decode=True)
            if payload:
                charset = msg.get_content_charset() or 'utf-8'
                content = payload.decode(charset, errors='replace')
                if msg.get_content_type() == 'text/html':
                    html_body = content
                else:
                    text_body = content
        except Exception as e:
            logger.warning(f"Error decoding email body: {e}")

    return text_body, html_body


def parse_email_message(uid: str, raw_email: bytes) -> ParsedEmail:
    """
    Parse raw email bytes into ParsedEmail dataclass.

    Args:
        uid: IMAP UID of the message
        raw_email: Raw email bytes from IMAP FETCH

    Returns:
        ParsedEmail with extracted data
    """
    msg = email.message_from_bytes(raw_email)

    # Parse headers
    subject = decode_mime_header(msg.get('Subject', '(No Subject)'))
    from_header = msg.get('From', '')
    sender_name, sender_email = parseaddr(from_header)
    sender_name = decode_mime_header(sender_name) or sender_email
    message_id = msg.get('Message-ID', '')

    # Parse date
    date_str = msg.get('Date')
    msg_date = None
    if date_str:
        try:
            msg_date = parsedate_to_datetime(date_str)
        except Exception:
            pass

    # Extract body
    text_body, html_body = extract_email_body(msg)

    return ParsedEmail(
        message_id=message_id,
        subject=subject,
        sender=sender_email,
        sender_name=sender_name,
        date=msg_date,
        body_text=text_body,
        body_html=html_body,
        uid=uid,
    )


def connect_imap():
    """
    Connect to IMAP server and login.

    Returns:
        imaplib.IMAP4_SSL connection object
    """
    config = get_email_settings()

    try:
        imap = imaplib.IMAP4_SSL(config['host'], config['port'])
        imap.login(config['user'], config['password'])
        return imap
    except imaplib.IMAP4.error as e:
        raise EmailConnectionError(f"IMAP login failed: {e}")
    except Exception as e:
        raise EmailConnectionError(f"IMAP connection failed: {e}")


def fetch_emails_from_folder(imap, folder_name: str = 'INBOX/Automate') -> list[ParsedEmail]:
    """
    Fetch all emails from a folder.

    Args:
        imap: IMAP connection
        folder_name: Folder to fetch from (default: INBOX/Automate)

    Returns:
        List of ParsedEmail objects
    """
    emails = []

    # Select folder
    status, data = imap.select(f'"{folder_name}"')
    if status != 'OK':
        logger.warning(f"Could not select folder '{folder_name}': {data}")
        return emails

    # Search for all messages
    status, data = imap.uid('search', None, 'ALL')
    if status != 'OK':
        logger.warning(f"Search failed in folder '{folder_name}': {data}")
        return emails

    uids = data[0].split()
    if not uids:
        logger.info(f"No emails found in '{folder_name}' folder")
        return emails

    logger.info(f"Found {len(uids)} email(s) in '{folder_name}' folder")

    for uid in uids:
        uid_str = uid.decode('utf-8')
        try:
            status, data = imap.uid('fetch', uid, '(RFC822)')
            if status != 'OK':
                logger.warning(f"Failed to fetch email UID {uid_str}")
                continue

            raw_email = data[0][1]
            parsed = parse_email_message(uid_str, raw_email)
            emails.append(parsed)
            logger.debug(f"Parsed email: {parsed.subject} from {parsed.sender}")

        except Exception as e:
            logger.error(f"Error processing email UID {uid_str}: {e}")
            continue

    return emails


def move_email_to_folder(imap, uid: str, destination_folder: str = 'New Requests'):
    """
    Move an email from current folder to destination folder.

    Args:
        imap: IMAP connection
        uid: UID of the email to move
        destination_folder: Target folder name
    """
    try:
        # Copy to destination
        status, data = imap.uid('copy', uid, f'"{destination_folder}"')
        if status != 'OK':
            raise EmailProcessingError(f"Failed to copy email to '{destination_folder}': {data}")

        # Mark as deleted in source
        status, data = imap.uid('store', uid, '+FLAGS', '(\\Deleted)')
        if status != 'OK':
            logger.warning(f"Failed to mark email as deleted: {data}")

        # Expunge to actually delete
        imap.expunge()

        logger.info(f"Moved email UID {uid} to '{destination_folder}'")

    except Exception as e:
        raise EmailProcessingError(f"Failed to move email: {e}")


def create_task_from_email(parsed_email: ParsedEmail):
    """
    Create an AdminTask from a parsed email.

    Args:
        parsed_email: ParsedEmail object

    Returns:
        AdminTask instance
    """
    from apps.admin_console.models import AdminProject, AdminProjectPhase, AdminTask

    # Get or create a project for email intake tasks
    project, _ = AdminProject.objects.get_or_create(
        name='Email Intake',
        defaults={
            'description': 'Tasks created from emails moved to the Automate folder',
            'status': 'open',
            'priority': 5,
        }
    )

    # Get or create a phase for email tasks
    phase, _ = AdminProjectPhase.objects.get_or_create(
        phase_number=999,  # Special phase for email intake
        defaults={
            'name': 'Email Requests',
            'objective': 'Process and complete tasks from email requests',
            'status': 'in_progress',
        }
    )

    # Truncate body for objective (first 500 chars)
    body_preview = parsed_email.body_text[:500] if parsed_email.body_text else '(No text body)'
    if len(parsed_email.body_text) > 500:
        body_preview += '...'

    # Clean up body for task description
    clean_body = re.sub(r'\s+', ' ', parsed_email.body_text).strip()
    if len(clean_body) > 2000:
        clean_body = clean_body[:2000] + '...'

    # Build task description in Executable Task Standard format
    description = {
        'objective': f"Review and process email: {parsed_email.subject}",
        'inputs': [
            f"From: {parsed_email.sender_name} <{parsed_email.sender}>",
            f"Date: {parsed_email.date.isoformat() if parsed_email.date else 'Unknown'}",
            f"Email body preview: {body_preview}",
        ],
        'actions': [
            "Read and understand the email content and context",
            "Determine what action is needed (feature request, bug report, question, etc.)",
            "If it requires code changes, create appropriate sub-tasks",
            "If it requires a response, draft and send a reply",
            "Document any decisions or outcomes",
        ],
        'output': "Email request processed with appropriate action taken and documented",
    }

    # Create the task
    task = AdminTask.objects.create(
        title=f"Email: {parsed_email.subject[:150]}",
        description=description,
        category='business',
        priority=3,
        status='ready',
        effort='M',
        phase=phase,
        project=project,
        created_by='claude',
    )

    logger.info(f"Created AdminTask #{task.pk}: {task.title}")
    return task


def should_skip_confirmation(sender: str) -> bool:
    """
    Check if we should skip sending a confirmation email to this sender.

    Automated/system addresses will never receive our confirmations,
    so sending to them just creates bounce notifications.

    Args:
        sender: Email address of the original sender

    Returns:
        True if we should skip sending confirmation
    """
    if not sender:
        return True

    sender_lower = sender.lower()

    # Extract the local part (before @)
    local_part = sender_lower.split('@')[0] if '@' in sender_lower else sender_lower

    # System/automated address prefixes that won't receive replies
    skip_prefixes = [
        'noreply',
        'no-reply',
        'no_reply',
        'donotreply',
        'do-not-reply',
        'do_not_reply',
        'postmaster',
        'mailer-daemon',
        'mailerdaemon',
        'bounce',
        'bounces',
        'notification',
        'notifications',
        'alert',
        'alerts',
        'newsletter',
        'news',
        'marketing',
        'promo',
        'info',  # Often automated
        'support',  # Often ticketing systems
        'helpdesk',
        'system',
        'automated',
        'auto',
    ]

    for prefix in skip_prefixes:
        if local_part.startswith(prefix):
            return True

    return False


def send_confirmation_email(parsed_email: ParsedEmail, task):
    """
    Send confirmation email that task was created.

    Args:
        parsed_email: Original email that was processed
        task: Created AdminTask
    """
    # Skip confirmation for automated/system addresses that won't receive it
    if should_skip_confirmation(parsed_email.sender):
        logger.info(
            f"Skipping confirmation email for task #{task.pk} - "
            f"sender '{parsed_email.sender}' appears to be automated/system address"
        )
        return

    config = get_email_settings()

    # Sanitize subject - remove newlines which are invalid in email headers
    clean_subject = parsed_email.subject.replace('\r\n', ' ').replace('\n', ' ').replace('\r', ' ')
    subject = f"[WLJ Task #{task.pk}] Task created: {clean_subject[:80]}"

    body = f"""Your email has been received and converted to a task in Whole Life Journey.

Task Details:
- Task ID: #{task.pk}
- Title: {task.title}
- Status: {task.get_status_display()}
- Priority: {task.priority}

Original Email:
- Subject: {parsed_email.subject}
- From: {parsed_email.sender}
- Date: {parsed_email.date.strftime('%Y-%m-%d %H:%M') if parsed_email.date else 'Unknown'}

The task has been added to the queue and will be processed during the next work session.

---
This is an automated message from Whole Life Journey.
"""

    try:
        send_mail(
            subject=subject,
            message=body,
            from_email=config['user'],
            recipient_list=[parsed_email.sender],
            fail_silently=False,
        )
        logger.info(f"Sent confirmation email for task #{task.pk} to {parsed_email.sender}")
    except Exception as e:
        logger.error(f"Failed to send confirmation email: {e}")
        # Don't raise - task creation succeeded, email confirmation is optional


def process_email_intake(dry_run: bool = False):
    """
    Main entry point for email intake processing.

    Connects to IMAP, processes all emails in "Automate" folder,
    creates tasks, and moves emails to "New Requests" folder.

    Args:
        dry_run: If True, don't create tasks or move emails (for testing)

    Returns:
        Dict with processing results
    """
    results = {
        'processed': 0,
        'errors': 0,
        'tasks_created': [],
        'error_messages': [],
    }

    imap = None
    try:
        # Connect to IMAP
        logger.info("Connecting to IMAP server...")
        imap = connect_imap()

        # Fetch emails from Automate folder
        emails = fetch_emails_from_folder(imap, 'INBOX/Automate')

        if not emails:
            logger.info("No emails to process")
            return results

        # Process each email
        for parsed_email in emails:
            try:
                logger.info(f"Processing: {parsed_email.subject}")

                if dry_run:
                    logger.info(f"[DRY RUN] Would create task for: {parsed_email.subject}")
                    results['processed'] += 1
                    continue

                # Create task
                task = create_task_from_email(parsed_email)
                results['tasks_created'].append({
                    'id': task.pk,
                    'title': task.title,
                    'email_subject': parsed_email.subject,
                })

                # Send confirmation
                send_confirmation_email(parsed_email, task)

                # Move email to New Requests folder
                # Need to re-select Automate folder since we may have been in a different state
                imap.select('"INBOX/Automate"')
                move_email_to_folder(imap, parsed_email.uid, 'INBOX/New Requests')

                results['processed'] += 1

            except Exception as e:
                logger.error(f"Error processing email '{parsed_email.subject}': {e}")
                results['errors'] += 1
                results['error_messages'].append(f"{parsed_email.subject}: {str(e)}")

        return results

    except EmailIntakeError as e:
        logger.error(f"Email intake error: {e}")
        results['errors'] += 1
        results['error_messages'].append(str(e))
        return results

    finally:
        if imap:
            try:
                imap.close()
                imap.logout()
            except Exception:
                pass
