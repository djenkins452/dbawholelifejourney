# ==============================================================================
# File: apps/finance/services/plaid_service.py
# Project: Whole Life Journey - Django 5.x Personal Wellness/Journaling App
# Description: Plaid API client for bank connectivity
# Owner: Danny Jenkins (dannyjenkins71@gmail.com)
# Created: 2026-01-03
# Last Updated: 2026-01-03
# ==============================================================================
"""
Plaid Service

Provides a high-level interface for Plaid API operations:
- Link token creation for Plaid Link UI
- Access token exchange
- Transaction sync with cursor-based pagination
- Account information retrieval
- Connection management (disconnect, reauth)

See docs/wlj_bank_integration_architecture.md for architecture details.

Environment Variables:
    PLAID_CLIENT_ID - Plaid API client ID
    PLAID_SECRET - Plaid API secret key
    PLAID_ENV - Environment: sandbox, development, or production
    PLAID_WEBHOOK_URL - Webhook endpoint URL (optional)
"""

import logging
from datetime import date, timedelta
from decimal import Decimal
from typing import Optional

from django.conf import settings
from django.utils import timezone

logger = logging.getLogger(__name__)


class PlaidNotConfiguredError(Exception):
    """Raised when Plaid credentials are not configured."""
    pass


class PlaidService:
    """
    High-level Plaid API client for WLJ bank integration.

    Usage:
        service = PlaidService()
        link_token = service.create_link_token(user, request)
    """

    def __init__(self):
        """Initialize the Plaid client."""
        self.client_id = getattr(settings, 'PLAID_CLIENT_ID', None)
        self.secret = getattr(settings, 'PLAID_SECRET', None)
        self.environment = getattr(settings, 'PLAID_ENV', 'sandbox')
        self.webhook_url = getattr(settings, 'PLAID_WEBHOOK_URL', None)

        self._client = None

    @property
    def is_configured(self) -> bool:
        """Check if Plaid is properly configured."""
        return bool(self.client_id and self.secret)

    @property
    def client(self):
        """
        Get the Plaid API client, creating it if needed.

        Returns:
            Plaid API client instance

        Raises:
            PlaidNotConfiguredError: If Plaid credentials not set
        """
        if not self.is_configured:
            raise PlaidNotConfiguredError(
                "Plaid is not configured. Set PLAID_CLIENT_ID and PLAID_SECRET."
            )

        if self._client is None:
            try:
                import plaid
                from plaid.api import plaid_api
                from plaid.model.products import Products
                from plaid.model.country_code import CountryCode

                # Map environment string to Plaid environment
                env_map = {
                    'sandbox': plaid.Environment.Sandbox,
                    'development': plaid.Environment.Development,
                    'production': plaid.Environment.Production,
                }
                plaid_env = env_map.get(self.environment, plaid.Environment.Sandbox)

                configuration = plaid.Configuration(
                    host=plaid_env,
                    api_key={
                        'clientId': self.client_id,
                        'secret': self.secret,
                    }
                )
                api_client = plaid.ApiClient(configuration)
                self._client = plaid_api.PlaidApi(api_client)
            except ImportError:
                raise PlaidNotConfiguredError(
                    "plaid-python package not installed. Run: pip install plaid-python"
                )

        return self._client

    def create_link_token(self, user, request=None) -> dict:
        """
        Create a Plaid Link token for initiating bank connection.

        Args:
            user: The Django user object
            request: Optional Django request for redirect URI

        Returns:
            dict with 'link_token' and 'expiration'

        Raises:
            PlaidNotConfiguredError: If Plaid not configured
            Exception: If API call fails
        """
        from plaid.model.link_token_create_request import LinkTokenCreateRequest
        from plaid.model.link_token_create_request_user import LinkTokenCreateRequestUser
        from plaid.model.products import Products
        from plaid.model.country_code import CountryCode

        link_request = LinkTokenCreateRequest(
            user=LinkTokenCreateRequestUser(
                client_user_id=str(user.id),
            ),
            client_name='Whole Life Journey',
            products=[Products('transactions')],
            country_codes=[CountryCode('US')],
            language='en',
        )

        # Add webhook URL if configured
        if self.webhook_url:
            link_request.webhook = self.webhook_url

        # Add redirect URI for OAuth banks (optional)
        redirect_uri = getattr(settings, 'PLAID_REDIRECT_URI', None)
        if redirect_uri:
            link_request.redirect_uri = redirect_uri

        response = self.client.link_token_create(link_request)

        return {
            'link_token': response.link_token,
            'expiration': response.expiration,
        }

    def create_link_token_for_update(self, user, access_token: str) -> dict:
        """
        Create a Link token for re-authentication (update mode).

        Args:
            user: The Django user object
            access_token: The existing access token that needs reauth

        Returns:
            dict with 'link_token' and 'expiration'
        """
        from plaid.model.link_token_create_request import LinkTokenCreateRequest
        from plaid.model.link_token_create_request_user import LinkTokenCreateRequestUser
        from plaid.model.country_code import CountryCode

        link_request = LinkTokenCreateRequest(
            user=LinkTokenCreateRequestUser(
                client_user_id=str(user.id),
            ),
            client_name='Whole Life Journey',
            country_codes=[CountryCode('US')],
            language='en',
            access_token=access_token,  # This enables update mode
        )

        response = self.client.link_token_create(link_request)

        return {
            'link_token': response.link_token,
            'expiration': response.expiration,
        }

    def exchange_public_token(self, public_token: str) -> dict:
        """
        Exchange a public token for an access token.

        Called after user completes Plaid Link flow.

        Args:
            public_token: The public_token from Plaid Link

        Returns:
            dict with 'access_token' and 'item_id'
        """
        from plaid.model.item_public_token_exchange_request import ItemPublicTokenExchangeRequest

        request = ItemPublicTokenExchangeRequest(
            public_token=public_token
        )
        response = self.client.item_public_token_exchange(request)

        return {
            'access_token': response.access_token,
            'item_id': response.item_id,
        }

    def get_institution(self, institution_id: str) -> dict:
        """
        Get institution details (name, logo, etc.).

        Args:
            institution_id: Plaid institution ID

        Returns:
            dict with 'name', 'logo', 'primary_color', 'url'
        """
        from plaid.model.institutions_get_by_id_request import InstitutionsGetByIdRequest
        from plaid.model.country_code import CountryCode

        request = InstitutionsGetByIdRequest(
            institution_id=institution_id,
            country_codes=[CountryCode('US')],
        )
        response = self.client.institutions_get_by_id(request)
        institution = response.institution

        return {
            'name': institution.name,
            'logo': institution.logo if hasattr(institution, 'logo') else None,
            'primary_color': institution.primary_color if hasattr(institution, 'primary_color') else None,
            'url': institution.url if hasattr(institution, 'url') else None,
        }

    def get_accounts(self, access_token: str) -> list:
        """
        Get all accounts for an access token.

        Args:
            access_token: Plaid access token

        Returns:
            List of account dicts with 'id', 'name', 'type', 'subtype', 'mask', 'balance'
        """
        from plaid.model.accounts_get_request import AccountsGetRequest

        request = AccountsGetRequest(access_token=access_token)
        response = self.client.accounts_get(request)

        accounts = []
        for account in response.accounts:
            accounts.append({
                'id': account.account_id,
                'name': account.name,
                'official_name': account.official_name,
                'type': account.type.value if account.type else None,
                'subtype': account.subtype.value if account.subtype else None,
                'mask': account.mask,
                'balance_available': float(account.balances.available) if account.balances.available else None,
                'balance_current': float(account.balances.current) if account.balances.current else None,
                'balance_limit': float(account.balances.limit) if account.balances.limit else None,
                'currency': account.balances.iso_currency_code,
            })

        return accounts

    def sync_transactions(self, access_token: str, cursor: str = '') -> dict:
        """
        Sync transactions using cursor-based pagination.

        Args:
            access_token: Plaid access token
            cursor: Optional sync cursor for incremental updates

        Returns:
            dict with 'added', 'modified', 'removed', 'next_cursor', 'has_more'
        """
        from plaid.model.transactions_sync_request import TransactionsSyncRequest

        request = TransactionsSyncRequest(
            access_token=access_token,
            cursor=cursor if cursor else None,
        )
        response = self.client.transactions_sync(request)

        # Convert transactions to dicts
        added = []
        for txn in response.added:
            added.append(self._transaction_to_dict(txn))

        modified = []
        for txn in response.modified:
            modified.append(self._transaction_to_dict(txn))

        removed = [r.transaction_id for r in response.removed]

        return {
            'added': added,
            'modified': modified,
            'removed': removed,
            'next_cursor': response.next_cursor,
            'has_more': response.has_more,
        }

    def _transaction_to_dict(self, txn) -> dict:
        """Convert a Plaid transaction object to a dict."""
        return {
            'transaction_id': txn.transaction_id,
            'account_id': txn.account_id,
            'amount': float(txn.amount),  # Plaid: positive=debit, negative=credit
            'date': txn.date,
            'name': txn.name,
            'merchant_name': txn.merchant_name,
            'pending': txn.pending,
            'category': txn.category,
            'category_id': txn.category_id,
            'payment_channel': txn.payment_channel.value if txn.payment_channel else None,
            'location': {
                'city': txn.location.city if txn.location else None,
                'region': txn.location.region if txn.location else None,
            } if txn.location else None,
        }

    def remove_item(self, access_token: str) -> bool:
        """
        Remove a Plaid Item (disconnect bank).

        Revokes the access token and removes Plaid's connection.

        Args:
            access_token: Plaid access token to revoke

        Returns:
            True if successful
        """
        from plaid.model.item_remove_request import ItemRemoveRequest

        request = ItemRemoveRequest(access_token=access_token)
        self.client.item_remove(request)

        logger.info("Plaid item removed successfully")
        return True

    def get_item(self, access_token: str) -> dict:
        """
        Get Item (connection) details.

        Args:
            access_token: Plaid access token

        Returns:
            dict with 'item_id', 'institution_id', 'error'
        """
        from plaid.model.item_get_request import ItemGetRequest

        request = ItemGetRequest(access_token=access_token)
        response = self.client.item_get(request)
        item = response.item

        return {
            'item_id': item.item_id,
            'institution_id': item.institution_id,
            'error': response.status.to_dict() if response.status else None,
        }


# Singleton instance for convenience
_plaid_service = None


def get_plaid_service() -> PlaidService:
    """Get the global PlaidService instance."""
    global _plaid_service
    if _plaid_service is None:
        _plaid_service = PlaidService()
    return _plaid_service
