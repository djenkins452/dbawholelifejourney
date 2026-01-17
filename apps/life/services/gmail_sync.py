"""
Gmail Sync Service

Orchestrates Gmail inbox scanning for individual users or all users.
Called by views (manual scan) and cron endpoint (scheduled scan).
"""

import logging

from django.utils import timezone

logger = logging.getLogger(__name__)


class GmailSyncService:
    """
    Orchestrate Gmail inbox scanning.

    Coordinates between GmailService (fetching emails) and
    EmailProcessingService (AI extraction and task creation).
    """

    def scan_user_inbox(self, user) -> dict:
        """
        Scan a single user's Gmail inbox for action items.

        Args:
            user: Django User instance.

        Returns:
            Dict with: emails_scanned, tasks_created, errors
        """
        from apps.life.models import GmailCredential
        from apps.life.services.gmail import GmailService
        from apps.life.services.email_processor import EmailProcessingService

        # Get user's Gmail credentials
        try:
            credential = user.gmail_credential
        except GmailCredential.DoesNotExist:
            logger.info(f"No Gmail credential for user {user.email}")
            return {
                'emails_scanned': 0,
                'tasks_created': 0,
                'error': 'not_connected'
            }

        # Check if scanning is enabled
        if not credential.scan_enabled:
            logger.info(f"Gmail scanning disabled for user {user.email}")
            return {
                'emails_scanned': 0,
                'tasks_created': 0,
                'error': 'disabled'
            }

        # Check for decryption errors (key rotation)
        if credential.has_decryption_error():
            logger.error(f"Gmail decryption error for user {user.email}")
            self._record_scan_error(credential, "decryption_error")
            return {
                'emails_scanned': 0,
                'tasks_created': 0,
                'error': 'decryption_error'
            }

        # Initialize Gmail service
        try:
            gmail_service = GmailService()
        except (ImportError, ValueError) as e:
            logger.error(f"Gmail service initialization failed: {e}")
            self._record_scan_error(credential, f"service_init_error: {str(e)[:100]}")
            return {
                'emails_scanned': 0,
                'tasks_created': 0,
                'error': 'service_unavailable'
            }

        # Refresh token if needed
        if credential.is_token_expired:
            logger.info(f"Refreshing Gmail token for user {user.email}")
            try:
                new_creds = gmail_service.refresh_credentials(
                    credential.get_credentials_dict()
                )
                if new_creds:
                    credential.update_from_credentials(new_creds)
                else:
                    logger.error(f"Token refresh returned None for user {user.email}")
                    self._record_scan_error(credential, "token_refresh_failed")
                    return {
                        'emails_scanned': 0,
                        'tasks_created': 0,
                        'error': 'token_expired'
                    }
            except Exception as e:
                logger.error(f"Token refresh error for user {user.email}: {e}")
                self._record_scan_error(credential, f"refresh_error: {str(e)[:100]}")
                return {
                    'emails_scanned': 0,
                    'tasks_created': 0,
                    'error': 'token_refresh_failed'
                }

        # Fetch emails from primary inbox
        logger.info(
            f"Fetching Gmail for user {user.email} "
            f"(max={credential.max_emails_per_scan}, days={credential.days_to_look_back})"
        )

        try:
            emails = gmail_service.get_primary_inbox_emails(
                credential.get_credentials_dict(),
                max_results=credential.max_emails_per_scan,
                days_back=credential.days_to_look_back,
            )
        except Exception as e:
            logger.error(f"Gmail fetch error for user {user.email}: {e}")
            self._record_scan_error(credential, f"fetch_error: {str(e)[:100]}")
            return {
                'emails_scanned': 0,
                'tasks_created': 0,
                'error': 'fetch_failed'
            }

        if not emails:
            logger.info(f"No new emails found for user {user.email}")
            self._record_scan_success(credential, 0, 0)
            return {
                'emails_scanned': 0,
                'tasks_created': 0
            }

        # Process emails with AI
        processor = EmailProcessingService(user)
        total_tasks = 0
        errors = []

        for email in emails:
            try:
                result = processor.process_email(email)
                total_tasks += result.get('tasks_created', 0)

                if result.get('reason') and 'error' in result.get('reason', ''):
                    errors.append(f"{email.get('subject', 'Unknown')[:50]}: {result['reason']}")

            except Exception as e:
                logger.error(f"Error processing email {email.get('id')}: {e}")
                errors.append(f"{email.get('subject', 'Unknown')[:50]}: {str(e)[:50]}")

        # Record scan result
        self._record_scan_success(credential, len(emails), total_tasks, errors)

        logger.info(
            f"Gmail scan complete for user {user.email}: "
            f"scanned={len(emails)}, tasks={total_tasks}, errors={len(errors)}"
        )

        return {
            'emails_scanned': len(emails),
            'tasks_created': total_tasks,
            'errors': errors if errors else None,
        }

    def scan_all_users(self) -> dict:
        """
        Scan all users with Gmail connected and enabled.

        Called by cron endpoint for scheduled processing.

        Returns:
            Dict with: users_processed, tasks_created, errors
        """
        from apps.life.models import GmailCredential

        credentials = GmailCredential.objects.filter(
            scan_enabled=True
        ).select_related('user')

        total_users = 0
        total_tasks = 0
        errors = []

        logger.info(f"Starting Gmail scan for {credentials.count()} users")

        for credential in credentials:
            try:
                result = self.scan_user_inbox(credential.user)
                total_users += 1
                total_tasks += result.get('tasks_created', 0)

                if result.get('error'):
                    errors.append(f"{credential.user.email}: {result['error']}")
                elif result.get('errors'):
                    for err in result['errors']:
                        errors.append(f"{credential.user.email}: {err}")

            except Exception as e:
                logger.error(f"Error scanning user {credential.user.email}: {e}")
                errors.append(f"{credential.user.email}: {str(e)[:100]}")

        logger.info(
            f"Gmail scan complete: users={total_users}, tasks={total_tasks}, errors={len(errors)}"
        )

        return {
            'users_processed': total_users,
            'tasks_created': total_tasks,
            'errors': errors if errors else None,
        }

    def _record_scan_success(self, credential, scanned: int, created: int, errors=None):
        """Record successful scan result."""
        message = f"Scanned {scanned} emails, created {created} tasks"
        if errors:
            message += f" ({len(errors)} errors)"

        credential.record_scan(
            success=True,
            message=message,
            tasks_created=created,
            errors=errors
        )

    def _record_scan_error(self, credential, error: str):
        """Record scan error."""
        credential.record_scan(
            success=False,
            message=error,
            tasks_created=0,
            errors=[error]
        )
