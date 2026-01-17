"""
Gmail Integration Service

Handles OAuth 2.0 authentication and email fetching from Gmail API.
Follows patterns from google_calendar.py in this directory.
"""

import base64
import logging
from datetime import timedelta
from email.utils import parsedate_to_datetime

from django.conf import settings
from django.utils import timezone

logger = logging.getLogger(__name__)


# Check for required dependencies
try:
    from google.oauth2.credentials import Credentials
    from google_auth_oauthlib.flow import Flow
    from googleapiclient.discovery import build
    from googleapiclient.errors import HttpError
    GOOGLE_AVAILABLE = True
except ImportError:
    GOOGLE_AVAILABLE = False
    logger.warning(
        "Gmail integration not available. Install: "
        "pip install google-auth google-auth-oauthlib google-api-python-client"
    )


class GmailService:
    """
    Service for Gmail OAuth and email fetching.

    Provides OAuth 2.0 flow handling and methods to fetch emails
    from the user's primary inbox (excluding Promotions, Social, etc.).
    """

    SCOPES = ['https://www.googleapis.com/auth/gmail.readonly']

    def __init__(self):
        if not GOOGLE_AVAILABLE:
            raise ImportError(
                "Gmail integration requires: "
                "pip install google-auth google-auth-oauthlib google-api-python-client"
            )

        self.client_id = getattr(settings, 'GMAIL_CLIENT_ID', None)
        self.client_secret = getattr(settings, 'GMAIL_CLIENT_SECRET', None)
        self.redirect_uri = getattr(settings, 'GMAIL_REDIRECT_URI', None)

        logger.info(f"Gmail OAuth - Redirect URI: {self.redirect_uri}")

        if not all([self.client_id, self.client_secret, self.redirect_uri]):
            logger.error(
                f"Gmail not configured - "
                f"client_id: {'set' if self.client_id else 'missing'}, "
                f"client_secret: {'set' if self.client_secret else 'missing'}, "
                f"redirect_uri: {'set' if self.redirect_uri else 'missing'}"
            )
            raise ValueError(
                "Gmail settings not configured. Add GMAIL_CLIENT_ID, "
                "GMAIL_CLIENT_SECRET, and GMAIL_REDIRECT_URI to settings."
            )

    def get_authorization_url(self, state=None):
        """
        Get the OAuth2 authorization URL.

        Args:
            state: Optional state parameter for CSRF protection.

        Returns:
            Tuple of (authorization_url, state)
        """
        flow = Flow.from_client_config(
            {
                "web": {
                    "client_id": self.client_id,
                    "client_secret": self.client_secret,
                    "auth_uri": "https://accounts.google.com/o/oauth2/auth",
                    "token_uri": "https://oauth2.googleapis.com/token",
                    "redirect_uris": [self.redirect_uri],
                }
            },
            scopes=self.SCOPES,
        )
        flow.redirect_uri = self.redirect_uri

        authorization_url, state = flow.authorization_url(
            access_type='offline',
            include_granted_scopes='true',
            state=state,
            prompt='consent',
        )

        return authorization_url, state

    def exchange_code_for_credentials(self, code):
        """
        Exchange authorization code for credentials.

        Args:
            code: Authorization code from OAuth callback.

        Returns:
            Dict with token, refresh_token, expiry, etc.
        """
        flow = Flow.from_client_config(
            {
                "web": {
                    "client_id": self.client_id,
                    "client_secret": self.client_secret,
                    "auth_uri": "https://accounts.google.com/o/oauth2/auth",
                    "token_uri": "https://oauth2.googleapis.com/token",
                    "redirect_uris": [self.redirect_uri],
                }
            },
            scopes=self.SCOPES,
        )
        flow.redirect_uri = self.redirect_uri
        flow.fetch_token(code=code)

        credentials = flow.credentials
        return {
            'token': credentials.token,
            'refresh_token': credentials.refresh_token,
            'token_uri': credentials.token_uri,
            'client_id': credentials.client_id,
            'client_secret': credentials.client_secret,
            'scopes': list(credentials.scopes),
            'expiry': credentials.expiry.isoformat() if credentials.expiry else None,
        }

    def get_gmail_service(self, credentials_dict):
        """
        Get a Gmail API service object.

        Args:
            credentials_dict: Dict with token, refresh_token, etc.

        Returns:
            Gmail API service object.
        """
        credentials = Credentials(
            token=credentials_dict['token'],
            refresh_token=credentials_dict.get('refresh_token'),
            token_uri=credentials_dict.get('token_uri', 'https://oauth2.googleapis.com/token'),
            client_id=credentials_dict.get('client_id', self.client_id),
            client_secret=credentials_dict.get('client_secret', self.client_secret),
            scopes=credentials_dict.get('scopes', self.SCOPES),
        )

        return build('gmail', 'v1', credentials=credentials)

    def refresh_credentials(self, credentials_dict):
        """
        Refresh an expired access token using the refresh token.

        Args:
            credentials_dict: Dict with token, refresh_token, etc.

        Returns:
            Updated credentials dict or None if refresh fails.
        """
        try:
            from google.auth.transport.requests import Request

            credentials = Credentials(
                token=credentials_dict['token'],
                refresh_token=credentials_dict.get('refresh_token'),
                token_uri=credentials_dict.get('token_uri', 'https://oauth2.googleapis.com/token'),
                client_id=credentials_dict.get('client_id', self.client_id),
                client_secret=credentials_dict.get('client_secret', self.client_secret),
                scopes=credentials_dict.get('scopes', self.SCOPES),
            )

            # Refresh the token
            credentials.refresh(Request())

            return {
                'token': credentials.token,
                'refresh_token': credentials.refresh_token or credentials_dict.get('refresh_token'),
                'token_uri': credentials.token_uri,
                'client_id': credentials.client_id,
                'client_secret': credentials.client_secret,
                'scopes': list(credentials.scopes) if credentials.scopes else credentials_dict.get('scopes', []),
                'expiry': credentials.expiry.isoformat() if credentials.expiry else None,
            }
        except Exception as e:
            logger.error(f"Error refreshing Gmail credentials: {e}")
            return None

    def get_primary_inbox_emails(
        self,
        credentials_dict,
        max_results=20,
        days_back=3
    ):
        """
        Fetch emails from primary inbox only.

        Filters out Promotions, Social, Updates, Forums tabs.
        Only returns emails from the last N days.

        Args:
            credentials_dict: Dict with token, refresh_token, etc.
            max_results: Maximum number of emails to fetch.
            days_back: Only fetch emails from the last N days.

        Returns:
            List of email dicts with: id, subject, sender, date, snippet, body
        """
        service = self.get_gmail_service(credentials_dict)

        # Calculate date filter
        since_date = (timezone.now() - timedelta(days=days_back)).strftime('%Y/%m/%d')

        # Query for primary inbox only (excludes promotions, social, updates, forums)
        query = f'category:primary after:{since_date}'

        try:
            # List messages matching query
            results = service.users().messages().list(
                userId='me',
                q=query,
                maxResults=max_results
            ).execute()

            messages = results.get('messages', [])
            logger.info(f"Gmail: Found {len(messages)} messages in primary inbox")

            emails = []
            for msg in messages:
                try:
                    # Get full message details
                    full_msg = service.users().messages().get(
                        userId='me',
                        id=msg['id'],
                        format='full'
                    ).execute()

                    emails.append(self._parse_email(full_msg))
                except HttpError as e:
                    logger.warning(f"Error fetching message {msg['id']}: {e}")
                    continue

            return emails

        except HttpError as e:
            logger.error(f"Gmail API error: {e}")
            return []

    def _parse_email(self, gmail_message):
        """
        Parse Gmail API message into usable format.

        Args:
            gmail_message: Raw message from Gmail API.

        Returns:
            Dict with id, thread_id, subject, sender, date, snippet, body.
        """
        headers = {
            h['name'].lower(): h['value']
            for h in gmail_message['payload'].get('headers', [])
        }

        # Extract body
        body = self._extract_body(gmail_message['payload'])

        # Parse date
        date_str = headers.get('date', '')
        parsed_date = None
        if date_str:
            try:
                parsed_date = parsedate_to_datetime(date_str)
            except Exception:
                pass

        return {
            'id': gmail_message['id'],
            'thread_id': gmail_message['threadId'],
            'subject': headers.get('subject', '(No Subject)'),
            'sender': headers.get('from', ''),
            'date': date_str,
            'date_parsed': parsed_date,
            'snippet': gmail_message.get('snippet', ''),
            'body': body,
        }

    def _extract_body(self, payload):
        """
        Extract plain text body from email payload.

        Handles both single-part and multipart messages.

        Args:
            payload: Email payload from Gmail API.

        Returns:
            Plain text body content.
        """
        # Handle multipart messages
        if 'parts' in payload:
            for part in payload['parts']:
                # Prefer plain text
                if part.get('mimeType') == 'text/plain':
                    data = part.get('body', {}).get('data', '')
                    if data:
                        try:
                            return base64.urlsafe_b64decode(data).decode('utf-8')
                        except Exception:
                            pass

                # Recursively check nested parts
                if 'parts' in part:
                    nested_body = self._extract_body(part)
                    if nested_body:
                        return nested_body

            # Fall back to HTML if no plain text found
            for part in payload['parts']:
                if part.get('mimeType') == 'text/html':
                    data = part.get('body', {}).get('data', '')
                    if data:
                        try:
                            html = base64.urlsafe_b64decode(data).decode('utf-8')
                            # Strip HTML tags for basic text extraction
                            import re
                            text = re.sub(r'<[^>]+>', ' ', html)
                            text = re.sub(r'\s+', ' ', text).strip()
                            return text
                        except Exception:
                            pass

        # Handle single-part messages
        body_data = payload.get('body', {}).get('data')
        if body_data:
            try:
                return base64.urlsafe_b64decode(body_data).decode('utf-8')
            except Exception:
                pass

        return ''
