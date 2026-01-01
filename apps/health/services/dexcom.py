# ==============================================================================
# File: apps/health/services/dexcom.py
# Project: Whole Life Journey - Django 5.x Personal Wellness/Journaling App
# Description: Dexcom CGM OAuth and data sync service
# Owner: Danny Jenkins (dannyjenkins71@gmail.com)
# Created: 2025-12-31
# Last Updated: 2025-12-31
# ==============================================================================
"""
Dexcom CGM Integration Service

Handles OAuth 2.0 authentication and glucose data sync with Dexcom API.
Follows patterns from Google Calendar integration in apps/life/services/.
"""

import logging
import secrets
from datetime import datetime, timedelta
from decimal import Decimal
from typing import Optional

import requests
from django.conf import settings
from django.db import transaction
from django.utils import timezone

logger = logging.getLogger(__name__)


class DexcomService:
    """
    Service for Dexcom OAuth 2.0 authentication.

    Handles authorization URL generation, token exchange, and token refresh.
    """

    # API endpoints - use sandbox for development
    SANDBOX_BASE_URL = "https://sandbox-api.dexcom.com"
    PRODUCTION_BASE_URL = "https://api.dexcom.com"

    # OAuth endpoints (v3)
    OAUTH_AUTHORIZE_PATH = "/v2/oauth2/login"
    OAUTH_TOKEN_PATH = "/v2/oauth2/token"

    # Data endpoints (v3)
    EGV_PATH = "/v3/users/self/egvs"

    def __init__(self):
        self.client_id = getattr(settings, 'DEXCOM_CLIENT_ID', '')
        self.client_secret = getattr(settings, 'DEXCOM_CLIENT_SECRET', '')
        self.redirect_uri = getattr(settings, 'DEXCOM_REDIRECT_URI', '')
        self.use_sandbox = getattr(settings, 'DEXCOM_USE_SANDBOX', True)

        self.base_url = self.SANDBOX_BASE_URL if self.use_sandbox else self.PRODUCTION_BASE_URL

    @property
    def is_configured(self):
        """Check if Dexcom integration is properly configured."""
        return bool(self.client_id and self.client_secret and self.redirect_uri)

    def get_authorization_url(self, state: Optional[str] = None) -> tuple:
        """
        Generate the OAuth2 authorization URL for Dexcom.

        Args:
            state: Optional state parameter for CSRF protection

        Returns:
            tuple: (authorization_url, state)
        """
        if not self.is_configured:
            raise ValueError(
                "Dexcom integration not configured. "
                "Set DEXCOM_CLIENT_ID, DEXCOM_CLIENT_SECRET, and DEXCOM_REDIRECT_URI."
            )

        if state is None:
            state = secrets.token_urlsafe(32)

        # Build authorization URL
        auth_url = f"{self.base_url}{self.OAUTH_AUTHORIZE_PATH}"
        params = {
            'client_id': self.client_id,
            'redirect_uri': self.redirect_uri,
            'response_type': 'code',
            'scope': 'offline_access',
            'state': state,
        }

        # Build query string
        query_string = '&'.join(f"{k}={v}" for k, v in params.items())
        full_url = f"{auth_url}?{query_string}"

        return full_url, state

    def exchange_code_for_credentials(self, code: str) -> dict:
        """
        Exchange authorization code for access/refresh tokens.

        Args:
            code: Authorization code from callback

        Returns:
            dict: Credentials including access_token, refresh_token, expires_in
        """
        token_url = f"{self.base_url}{self.OAUTH_TOKEN_PATH}"

        data = {
            'client_id': self.client_id,
            'client_secret': self.client_secret,
            'code': code,
            'grant_type': 'authorization_code',
            'redirect_uri': self.redirect_uri,
        }

        headers = {
            'Content-Type': 'application/x-www-form-urlencoded',
        }

        try:
            response = requests.post(token_url, data=data, headers=headers, timeout=30)
            response.raise_for_status()
            token_data = response.json()

            # Calculate token expiry
            expires_in = token_data.get('expires_in', 7200)  # Default 2 hours
            token_expiry = timezone.now() + timedelta(seconds=expires_in)

            return {
                'access_token': token_data.get('access_token', ''),
                'refresh_token': token_data.get('refresh_token', ''),
                'token_expiry': token_expiry,
                'expires_in': expires_in,
            }
        except requests.exceptions.RequestException as e:
            logger.error(f"Dexcom token exchange failed: {e}")
            raise ValueError(f"Failed to exchange authorization code: {e}")

    def refresh_access_token(self, refresh_token: str) -> dict:
        """
        Refresh an expired access token.

        Args:
            refresh_token: Current refresh token

        Returns:
            dict: New credentials
        """
        token_url = f"{self.base_url}{self.OAUTH_TOKEN_PATH}"

        data = {
            'client_id': self.client_id,
            'client_secret': self.client_secret,
            'refresh_token': refresh_token,
            'grant_type': 'refresh_token',
        }

        headers = {
            'Content-Type': 'application/x-www-form-urlencoded',
        }

        try:
            response = requests.post(token_url, data=data, headers=headers, timeout=30)
            response.raise_for_status()
            token_data = response.json()

            expires_in = token_data.get('expires_in', 7200)
            token_expiry = timezone.now() + timedelta(seconds=expires_in)

            return {
                'access_token': token_data.get('access_token', ''),
                'refresh_token': token_data.get('refresh_token', ''),
                'token_expiry': token_expiry,
            }
        except requests.exceptions.RequestException as e:
            logger.error(f"Dexcom token refresh failed: {e}")
            raise ValueError(f"Failed to refresh token: {e}")

    def get_glucose_readings(
        self,
        access_token: str,
        start_date: datetime,
        end_date: datetime
    ) -> list:
        """
        Fetch estimated glucose values from Dexcom API.

        Args:
            access_token: Valid access token
            start_date: Start of date range
            end_date: End of date range

        Returns:
            list: List of EGV records
        """
        egv_url = f"{self.base_url}{self.EGV_PATH}"

        # Format dates as ISO 8601
        start_str = start_date.strftime('%Y-%m-%dT%H:%M:%S')
        end_str = end_date.strftime('%Y-%m-%dT%H:%M:%S')

        params = {
            'startDate': start_str,
            'endDate': end_str,
        }

        headers = {
            'Authorization': f'Bearer {access_token}',
        }

        try:
            response = requests.get(
                egv_url,
                params=params,
                headers=headers,
                timeout=30
            )
            response.raise_for_status()
            data = response.json()

            return data.get('records', [])
        except requests.exceptions.RequestException as e:
            logger.error(f"Dexcom glucose fetch failed: {e}")
            raise ValueError(f"Failed to fetch glucose readings: {e}")


class DexcomSyncService:
    """
    Service for syncing Dexcom glucose data to GlucoseEntry models.
    """

    def __init__(self, user):
        self.user = user
        self.dexcom_service = DexcomService()

    def get_credential(self):
        """Get user's Dexcom credential if exists."""
        from apps.health.models import DexcomCredential
        try:
            return self.user.dexcom_credential
        except DexcomCredential.DoesNotExist:
            return None

    def ensure_valid_token(self, credential) -> bool:
        """
        Ensure the access token is valid, refreshing if needed.

        Returns:
            bool: True if token is valid
        """
        if not credential.is_token_expired:
            return True

        if not credential.refresh_token:
            logger.warning(f"No refresh token for user {self.user.email}")
            return False

        try:
            new_creds = self.dexcom_service.refresh_access_token(
                credential.refresh_token
            )
            credential.update_from_credentials(new_creds)
            return True
        except ValueError as e:
            logger.error(f"Token refresh failed for {self.user.email}: {e}")
            credential.record_sync(
                success=False,
                message=f"Token refresh failed: {e}"
            )
            return False

    def dexcom_record_to_glucose_entry(self, record: dict) -> dict:
        """
        Convert a Dexcom EGV record to GlucoseEntry field values.

        Args:
            record: Dexcom EGV record dict

        Returns:
            dict: Fields for GlucoseEntry
        """
        # Parse the display time (local device time)
        display_time = record.get('displayTime', '')
        if display_time:
            # Handle ISO format with potential timezone
            try:
                recorded_at = datetime.fromisoformat(
                    display_time.replace('Z', '+00:00')
                )
                if timezone.is_naive(recorded_at):
                    recorded_at = timezone.make_aware(recorded_at)
            except ValueError:
                recorded_at = timezone.now()
        else:
            recorded_at = timezone.now()

        # Get glucose value (Dexcom reports in mg/dL)
        value = record.get('value', 0)

        # Handle edge cases: 39 = "LOW", 401 = "HIGH"
        if value <= 39:
            value = 39  # Dexcom shows "LOW" for readings below 40
        elif value >= 401:
            value = 401  # Dexcom shows "HIGH" for readings above 400

        return {
            'value': Decimal(str(value)),
            'unit': 'mg/dL',
            'context': 'cgm',
            'recorded_at': recorded_at,
            'source': 'dexcom',
            'dexcom_record_id': record.get('recordId', ''),
            'trend': record.get('trend', ''),
            'trend_rate': Decimal(str(record.get('trendRate', 0))) if record.get('trendRate') else None,
            'display_device': record.get('displayDevice', ''),
        }

    def sync_from_dexcom(self, days: int = 7) -> tuple:
        """
        Sync glucose readings from Dexcom.

        Args:
            days: Number of days of history to sync

        Returns:
            tuple: (created_count, updated_count, error_message)
        """
        from apps.health.models import GlucoseEntry

        credential = self.get_credential()
        if not credential:
            return 0, 0, "Dexcom not connected"

        if not self.ensure_valid_token(credential):
            return 0, 0, "Token expired and refresh failed"

        # Calculate date range
        end_date = timezone.now()
        start_date = end_date - timedelta(days=days)

        try:
            records = self.dexcom_service.get_glucose_readings(
                credential.access_token,
                start_date,
                end_date
            )
        except ValueError as e:
            credential.record_sync(success=False, message=str(e))
            return 0, 0, str(e)

        created_count = 0
        updated_count = 0

        with transaction.atomic():
            for record in records:
                entry_data = self.dexcom_record_to_glucose_entry(record)
                record_id = entry_data.pop('dexcom_record_id')

                if not record_id:
                    continue

                # Check if record already exists
                existing = GlucoseEntry.objects.filter(
                    user=self.user,
                    dexcom_record_id=record_id
                ).first()

                if existing:
                    # Update existing record
                    for key, value in entry_data.items():
                        setattr(existing, key, value)
                    existing.dexcom_record_id = record_id
                    existing.save()
                    updated_count += 1
                else:
                    # Create new record
                    GlucoseEntry.objects.create(
                        user=self.user,
                        dexcom_record_id=record_id,
                        **entry_data
                    )
                    created_count += 1

        # Record sync result
        credential.record_sync(
            success=True,
            message=f"Synced {created_count} new, {updated_count} updated",
            count=created_count + updated_count
        )

        return created_count, updated_count, None

    def get_latest_readings(self, hours: int = 3) -> list:
        """
        Get latest glucose readings from Dexcom (for real-time display).

        Args:
            hours: Number of hours of data to fetch

        Returns:
            list: Raw Dexcom records
        """
        credential = self.get_credential()
        if not credential or not self.ensure_valid_token(credential):
            return []

        end_date = timezone.now()
        start_date = end_date - timedelta(hours=hours)

        try:
            return self.dexcom_service.get_glucose_readings(
                credential.access_token,
                start_date,
                end_date
            )
        except ValueError:
            return []

    def disconnect(self):
        """
        Disconnect Dexcom integration for user.

        Removes stored credentials but keeps synced glucose data.
        """
        credential = self.get_credential()
        if credential:
            credential.delete()
            logger.info(f"Dexcom disconnected for user {self.user.email}")
