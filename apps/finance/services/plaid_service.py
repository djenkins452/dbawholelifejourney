# ==============================================================================
# File: apps/finance/services/plaid_service.py
# Project: Whole Life Journey - Django 5.x Personal Wellness/Journaling App
# Description: Plaid API client for bank connectivity
# Owner: Danny Jenkins (admin@wholelifejourney.com)
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
    PLAID_ENV - Environment: sandbox or production ('development' was retired by Plaid)
    PLAID_WEBHOOK_URL - Webhook endpoint URL (optional)
"""

import logging

from django.conf import settings

logger = logging.getLogger(__name__)


#: Environment name -> SDK attribute. Plaid removed `Development` (2024); only these
#: two remain. Resolution is by attribute NAME so a future SDK change surfaces as a clear
#: configuration error instead of an AttributeError raised while building a dict.
PLAID_ENVIRONMENT_ATTRS = {
    'sandbox': 'Sandbox',
    'production': 'Production',
}
#: Retired environments, kept so a stale config gets a truthful message.
RETIRED_PLAID_ENVIRONMENTS = {'development'}


class PlaidEnvironmentError(Exception):
    """The configured PLAID_ENV cannot be resolved against the installed SDK."""


def _resolve_plaid_host(environment):
    """Map `PLAID_ENV` to an SDK host, failing with an explanation rather than a crash.

    The NAME is validated before the SDK is imported, so a stale configuration reports
    itself even in an environment where plaid-python is not installed.
    """
    name = (environment or '').strip().lower()
    if name in RETIRED_PLAID_ENVIRONMENTS:
        raise PlaidEnvironmentError(
            f"PLAID_ENV='{name}' refers to an environment Plaid has retired. "
            "Use 'sandbox' or 'production'."
        )
    attr = PLAID_ENVIRONMENT_ATTRS.get(name)
    if attr is None:
        raise PlaidEnvironmentError(
            f"PLAID_ENV='{environment}' is not a supported environment. "
            f"Expected one of: {', '.join(sorted(PLAID_ENVIRONMENT_ATTRS))}."
        )

    import plaid

    host = getattr(plaid.Environment, attr, None)
    if host is None:
        available = [a for a in dir(plaid.Environment) if not a.startswith('_')]
        raise PlaidEnvironmentError(
            f"The installed Plaid SDK does not provide the '{attr}' environment "
            f"(available: {', '.join(available)}). Upgrade or pin plaid-python."
        )
    return host


#: Days of transaction history requested when an Item is CREATED. 730 is the provider
#: maximum; the default is 90, far too little to reason about a year over year.
#:
#: PLAID'S INVARIANT (https://plaid.com/docs/api/products/transactions/): once the
#: Transactions product has been initialized on an Item, `days_requested` HAS NO EFFECT.
#: The window is decided once, at Item creation, and cannot be increased afterwards — not
#: by syncing, not by Link update mode. Getting a longer window for an existing Item means
#: removing that Item and creating a new one, which is destructive and externally revokes
#: access. See docs/WLJ_FINANCE_HISTORY_RECREATE_RUNBOOK.md.
TRANSACTION_HISTORY_DAYS_REQUESTED = 730


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

                # Map environment string to Plaid environment
                # Resolve the host by NAME, never by attribute access on a literal dict.
                # Plaid retired the `Development` environment and removed it from the
                # SDK (43.x exposes only Sandbox and Production). The previous dict
                # evaluated `plaid.Environment.Development` while being BUILT, so it
                # raised AttributeError on every call regardless of which environment
                # was configured — Link could not start in sandbox OR production.
                plaid_env = _resolve_plaid_host(self.environment)

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

        # Ask for as much history as the provider will give. Omitting this silently
        # accepts the provider's DEFAULT (90 days), which is why the first connection
        # returned only ~3 months.
        #
        # This is the ONLY moment the window can be set. Once Transactions is initialized
        # on the Item, `days_requested` has no effect anywhere — so an omission here is
        # permanent for the life of that Item.
        try:
            from plaid.model.link_token_transactions import LinkTokenTransactions
            link_request.transactions = LinkTokenTransactions(
                days_requested=TRANSACTION_HISTORY_DAYS_REQUESTED)
        except ImportError:                      # pragma: no cover - older SDKs
            logger.warning("SDK does not support days_requested; the provider default "
                           "history window will apply.")

        # Add webhook URL if configured
        if self.webhook_url:
            link_request.webhook = self.webhook_url

        # OAuth redirect URI — sent ONLY when explicitly configured.
        #
        # Plaid rejects the whole request when this is present but not registered in the
        # developer dashboard, so sending a speculative value breaks every connection
        # attempt including non-OAuth ones. Absent is safe: non-OAuth institutions work
        # normally and OAuth ones simply are not offered.
        redirect_uri = (getattr(settings, 'PLAID_REDIRECT_URI', '') or '').strip()
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

        # DELIBERATELY no `days_requested` here.
        #
        # Update mode REPAIRS an Item — expired credentials, a new MFA challenge, added
        # accounts. It does NOT widen transaction history: once Transactions is
        # initialized, `days_requested` has no effect
        # (https://plaid.com/docs/transactions/troubleshooting/). Plaid will happily
        # ACCEPT a token carrying it, which is exactly the trap — an accepted token
        # proves the request was well-formed, never that a backfill will happen. Sending
        # it here would encode a promise the provider does not make.
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

        # OMIT `cursor` entirely on the first call — do not pass None.
        #
        # plaid-python validates the TYPE of every optional field that is present, so an
        # explicit `cursor=None` fails client-side before the request is ever sent
        # ("Required value type is str and passed type was NoneType"). Since the first
        # sync of any connection has no cursor, that made the FIRST sync of every
        # connection impossible. Never substitute a placeholder cursor either: Plaid
        # treats the cursor as an opaque position, and a fake one loses history.
        kwargs = {'access_token': access_token}
        if cursor:
            kwargs['cursor'] = cursor
        request = TransactionsSyncRequest(**kwargs)
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
        """Convert a Plaid transaction to a dict, PRESERVING its classification.

        The provider's own categorisation, transaction code, payment channel,
        counterparties, and — critically — `pending_transaction_id` are carried through.
        They are what make normalization, pending→posted matching, transfer detection,
        refunds and auditability possible. Previously they were fetched and dropped.

        Deliberately NOT carried: account/routing numbers, tokens, raw payloads, or
        anything else a WLJ user never needs and a log should never hold.
        """
        pfc = getattr(txn, 'personal_finance_category', None)

        def _enum(value):
            return value.value if hasattr(value, 'value') else value

        counterparties = []
        for party in (getattr(txn, 'counterparties', None) or [])[:5]:
            name = getattr(party, 'name', None)
            if name:
                counterparties.append({
                    'name': str(name)[:120],
                    'type': str(_enum(getattr(party, 'type', '')) or '')[:40],
                })

        return {
            'transaction_id': txn.transaction_id,
            'account_id': txn.account_id,
            'amount': float(txn.amount),  # Plaid: positive=debit, negative=credit
            'date': txn.date,
            'name': txn.name,
            'merchant_name': txn.merchant_name,
            'pending': txn.pending,
            # -- provenance kept verbatim --------------------------------------
            'category': list(txn.category or []) if txn.category else [],
            'category_id': txn.category_id,
            'pfc_primary': str(getattr(pfc, 'primary', '') or ''),
            'pfc_detailed': str(getattr(pfc, 'detailed', '') or ''),
            'pfc_confidence': str(_enum(getattr(pfc, 'confidence_level', '')) or ''),
            'payment_channel': _enum(txn.payment_channel) if txn.payment_channel else None,
            'transaction_code': str(_enum(getattr(txn, 'transaction_code', '')) or ''),
            'pending_transaction_id': getattr(txn, 'pending_transaction_id', None) or '',
            'authorized_date': getattr(txn, 'authorized_date', None),
            'counterparties': counterparties,
            'location': {
                'city': txn.location.city if txn.location else None,
                'region': txn.location.region if txn.location else None,
            } if txn.location else None,
        }

    def get_webhook_verification_key(self, key_id: str):
        """Fetch Plaid's public JWK for a webhook `kid`.

        Returned as a plain dict so the verifier stays SDK-agnostic and testable without
        a network call. Never logs the key id in full or the key material.
        """
        from plaid.model.webhook_verification_key_get_request import (
            WebhookVerificationKeyGetRequest,
        )

        request = WebhookVerificationKeyGetRequest(key_id=key_id)
        response = self.client.webhook_verification_key_get(request)
        key = response.get("key") if hasattr(response, "get") else response.key
        if key is None:
            return None
        return key.to_dict() if hasattr(key, "to_dict") else dict(key)

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
