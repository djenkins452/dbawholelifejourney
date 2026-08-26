# ==============================================================================
# File: apps/finance/services/sync_service.py
# Project: Whole Life Journey - Django 5.x Personal Wellness/Journaling App
# Description: Transaction sync service for bank integrations
# Owner: Danny Jenkins (admin@wholelifejourney.com)
# Created: 2026-01-03
# Last Updated: 2026-01-03
# ==============================================================================
"""
Transaction Sync Service

Handles syncing transactions from Plaid to WLJ:
- Full initial sync after connection
- Incremental sync using cursor-based pagination
- Account creation and balance updates
- Transaction mapping and categorization

See docs/wlj_bank_integration_architecture.md for architecture details.
"""

import logging
from decimal import Decimal

from django.utils import timezone

logger = logging.getLogger(__name__)


class TransactionSyncService:
    """
    Syncs transactions from Plaid to WLJ database.

    Usage:
        service = TransactionSyncService(bank_connection)
        result = service.sync()
    """

    #: Bounded so one runaway pagination cannot hold a worker forever. Whatever is left
    #: arrives on the next run — the cursor makes that safe.
    MAX_SYNC_PAGES = 50
    #: Plaid asks us to restart pagination when the account mutates mid-flight. Bounded
    #: so a constantly-changing account cannot loop indefinitely.
    MAX_SYNC_RESTARTS = 3

    # Map Plaid account types to WLJ account types
    ACCOUNT_TYPE_MAP = {
        ('depository', 'checking'): 'checking',
        ('depository', 'savings'): 'savings',
        ('depository', 'money market'): 'savings',
        ('depository', 'cd'): 'savings',
        ('credit', 'credit card'): 'credit_card',
        ('loan', 'mortgage'): 'mortgage',
        ('loan', 'student'): 'student_loan',
        ('loan', 'auto'): 'loan',
        ('loan', 'personal'): 'loan',
        ('investment', '401k'): 'investment',
        ('investment', 'ira'): 'investment',
        ('investment', 'brokerage'): 'investment',
        ('investment', 'mutual fund'): 'investment',
    }

    def __init__(self, bank_connection):
        """
        Initialize sync service.

        Args:
            bank_connection: BankConnection model instance
        """
        self.bank_connection = bank_connection
        self.user = bank_connection.user
        # Per-sync caches so a batch costs one lookup, not one per transaction.
        self._category_map = None
        self._liability_names = None

    def sync(self) -> dict:
        """
        Perform a full transaction sync.

        Returns:
            dict with 'added', 'modified', 'removed', 'accounts_synced'
        """
        from apps.finance.services.plaid_service import get_plaid_service

        plaid = get_plaid_service()
        access_token = self.bank_connection.get_access_token()

        if not access_token:
            logger.error(f"No access token for connection {self.bank_connection.id}")
            return {'error': 'No access token available'}

        result = {
            'added': 0,
            'modified': 0,
            'removed': 0,
            'accounts_synced': 0,
        }

        try:
            # First, sync accounts
            accounts_data = plaid.get_accounts(access_token)
            result['accounts_synced'] = self._sync_accounts(accounts_data)

            # Transactions, paginated. The cursor we START from is the last one we
            # durably persisted; a mid-pagination failure therefore replays from a known
            # good position rather than skipping a page.
            start_cursor = self.bank_connection.last_sync_cursor or ''
            cursor = start_cursor
            page = 0
            pages_processed = 0
            update_status = ''
            restarts = 0

            while True:
                page += 1
                if page > self.MAX_SYNC_PAGES:
                    logger.warning("Sync page cap reached for connection %s; the rest "
                                   "will arrive on the next run",
                                   self.bank_connection.pk)
                    break
                try:
                    sync_result = plaid.sync_transactions(access_token, cursor)
                except Exception as exc:
                    if self._is_mutation_during_pagination(exc) and \
                            restarts < self.MAX_SYNC_RESTARTS:
                        # The account changed underneath us mid-pagination. Plaid's
                        # contract is to START OVER from the last durable cursor —
                        # continuing would silently skip whatever moved.
                        restarts += 1
                        cursor = start_cursor
                        page = 0
                        result['added'] = result['modified'] = result['removed'] = 0
                        logger.info("Sync restarted after a mutation during pagination "
                                    "(connection %s, restart %s)",
                                    self.bank_connection.pk, restarts)
                        continue
                    raise

                for txn_data in sync_result['added']:
                    if self._create_or_update_transaction(txn_data):
                        result['added'] += 1
                for txn_data in sync_result['modified']:
                    if self._create_or_update_transaction(txn_data, is_update=True):
                        result['modified'] += 1
                for txn_id in sync_result['removed']:
                    if self._remove_transaction(txn_id):
                        result['removed'] += 1

                pages_processed += 1
                update_status = sync_result.get('update_status') or update_status
                cursor = sync_result.get('next_cursor') or ''
                if not sync_result.get('has_more'):
                    break

            # An empty first response with no cursor is Plaid saying "still preparing" —
            # a normal, expected state for a brand-new Item, not a failure. Persisting an
            # empty cursor would also be meaningless, so we simply wait for the webhook.
            preparing = (not cursor and not start_cursor
                         and result['added'] == 0 and result['modified'] == 0)
            result['preparing'] = preparing

            # Persist the cursor ONLY at the true pagination boundary — after every page
            # has been applied. Saving mid-flight would advance past data we never stored.
            if cursor:
                self.bank_connection.update_sync_cursor(
                    cursor, transactions_added=result['added'])

            # Record coverage from the PROVIDER'S OWN statement in the sync response.
            # Previously this could only ever be learned from a webhook, so a single
            # undelivered (or, as on 2026-08-26, wrongly rejected) webhook left the
            # connection permanently reporting "historical import still running" while
            # holding the complete history. Every sync now re-states the truth.
            self.bank_connection.record_update_status(update_status)

            if preparing:
                self.bank_connection.mark_preparing()
            else:
                self.bank_connection.mark_active()

            self._log_sync_event(True, {k: v for k, v in result.items()
                                        if k != 'error'})

            logger.info(
                "Sync complete for connection %s: added=%s modified=%s removed=%s "
                "pages=%s restarts=%s preparing=%s",
                self.bank_connection.pk, result['added'], result['modified'],
                result['removed'], pages_processed, restarts, preparing,
            )

        except Exception as e:
            from apps.finance.services.provider_diagnostics import (
                safe_provider_diagnostics,
            )

            diagnostics = safe_provider_diagnostics(e)
            # Full detail — including SDK validation text — stays in the protected log.
            logger.error("Sync failed for connection %s: %s",
                         self.bank_connection.pk, diagnostics, exc_info=True)
            self._log_sync_event(False, {k: v for k, v in diagnostics.items()
                                         if k != 'exception'})

            error_code = (diagnostics.get('error_code') or '').upper()
            if error_code in ('ITEM_LOGIN_REQUIRED', 'INVALID_ACCESS_TOKEN'):
                # The only genuinely actionable state: the user must re-authenticate.
                self.bank_connection.mark_reauth_required()
                result['error'] = 'reauth_required'
            else:
                # Everything else is OUR problem, not the user's. The connection stays
                # usable and simply reports that it is still working — a raw SDK
                # validation string is not something a person can act on.
                self.bank_connection.mark_preparing()
                result['error'] = 'sync_incomplete'
            result['error_code'] = error_code or 'UNKNOWN'

        return result

    @staticmethod
    def _is_mutation_during_pagination(exc) -> bool:
        """Plaid signalling that the account changed while we were paging through it."""
        from apps.finance.services.provider_diagnostics import safe_provider_diagnostics

        diagnostics = safe_provider_diagnostics(exc)
        return diagnostics.get("error_code") == "TRANSACTIONS_SYNC_MUTATION_DURING_PAGINATION"

    def _sync_accounts(self, accounts_data: list) -> int:
        """
        Sync accounts from Plaid to WLJ.

        Creates new FinancialAccount records or updates existing ones.

        Args:
            accounts_data: List of account dicts from Plaid

        Returns:
            Number of accounts synced
        """
        from apps.finance.models import FinancialAccount

        synced = 0

        for acct_data in accounts_data:
            plaid_account_id = acct_data['id']

            # Try to find existing account
            account = FinancialAccount.objects.filter(
                user=self.user,
                plaid_account_id=plaid_account_id
            ).first()

            if account:
                # Update existing account
                self._update_account(account, acct_data)
            else:
                # Create new account
                account = self._create_account(acct_data)

            synced += 1

        return synced

    def _create_account(self, acct_data: dict):
        """Create a new FinancialAccount from Plaid data."""
        from apps.finance.models import FinancialAccount

        # Map Plaid type/subtype to WLJ account type
        plaid_type = acct_data.get('type') or ''
        plaid_subtype = acct_data.get('subtype') or ''
        wlj_type = self.ACCOUNT_TYPE_MAP.get(
            (plaid_type, plaid_subtype),
            'other_asset' if plaid_type not in ['credit', 'loan'] else 'other_liability'
        )

        # Determine balance
        balance = acct_data.get('balance_current', 0) or 0

        # Create account name
        name = acct_data.get('official_name') or acct_data.get('name') or 'Unnamed Account'
        mask = acct_data.get('mask') or ''
        if mask:
            name = f"{name} (...{mask})"

        account = FinancialAccount.objects.create(
            user=self.user,
            name=name,
            account_type=wlj_type,
            institution=self.bank_connection.institution_name,
            current_balance=Decimal(str(balance)),
            balance_updated_at=timezone.now(),
            currency=acct_data.get('currency') or 'USD',
            account_number_last4=mask,
            bank_connection=self.bank_connection,
            plaid_account_id=acct_data['id'],
            is_synced=True,
            last_balance_sync=timezone.now(),
        )

        logger.info(f"Created account: {account.name}")
        return account

    def _update_account(self, account, acct_data: dict):
        """Update an existing FinancialAccount with Plaid data."""
        balance = acct_data.get('balance_current', 0) or 0

        account.current_balance = Decimal(str(balance))
        account.balance_updated_at = timezone.now()
        account.last_balance_sync = timezone.now()
        account.save(update_fields=[
            'current_balance', 'balance_updated_at', 'last_balance_sync', 'updated_at'
        ])

        logger.debug(f"Updated account balance: {account.name} = {balance}")

    def _create_or_update_transaction(self, txn_data: dict, is_update: bool = False) -> bool:
        """
        Create or update a transaction from Plaid data.

        Args:
            txn_data: Transaction data dict from Plaid
            is_update: Whether this is an update to existing transaction

        Returns:
            True if transaction was created/updated
        """
        from apps.finance.models import FinancialAccount, Transaction

        plaid_txn_id = txn_data['transaction_id']
        plaid_account_id = txn_data['account_id']

        # Find the WLJ account
        account = FinancialAccount.objects.filter(
            user=self.user,
            plaid_account_id=plaid_account_id
        ).first()

        if not account:
            logger.warning(f"No account found for Plaid account {plaid_account_id}")
            return False

        pending_id = (txn_data.get('pending_transaction_id') or '').strip()

        # Pending -> posted. Plaid sends the POSTED transaction as a NEW id carrying
        # `pending_transaction_id`. Matching only on transaction_id would leave the
        # pending row behind, so the same purchase would be counted twice — and any
        # attribution the user had already made would be stranded on the ghost.
        existing = Transaction.objects.filter(
            user=self.user, plaid_transaction_id=plaid_txn_id
        ).first()
        promoted_from_pending = False
        if existing is None and pending_id:
            existing = Transaction.objects.filter(
                user=self.user, plaid_transaction_id=pending_id
            ).first()
            promoted_from_pending = existing is not None

        # Plaid amounts: positive = money out, negative = money in
        # WLJ amounts: positive = money in, negative = money out
        plaid_amount = txn_data['amount']
        wlj_amount = Decimal(str(-plaid_amount))

        description = txn_data.get('merchant_name') or txn_data.get('name', 'Unknown')
        is_pending = bool(txn_data.get('pending', False))

        provenance = {
            'provider_category': txn_data.get('category') or [],
            'provider_category_primary': (txn_data.get('pfc_primary') or '')[:64],
            'provider_category_detailed': (txn_data.get('pfc_detailed') or '')[:128],
            'provider_category_confidence': (txn_data.get('pfc_confidence') or '')[:16],
            'provider_payment_channel': (txn_data.get('payment_channel') or '')[:24],
            'provider_transaction_code': (txn_data.get('transaction_code') or '')[:32],
            'provider_merchant_name': (txn_data.get('merchant_name') or '')[:200],
            'provider_counterparties': txn_data.get('counterparties') or [],
            'provider_pending_transaction_id': pending_id[:100],
            'provider_authorized_date': txn_data.get('authorized_date'),
        }

        if existing:
            existing.amount = wlj_amount
            existing.description = description
            existing.date = txn_data['date']
            existing.plaid_pending = is_pending
            existing.is_cleared = not is_pending
            if promoted_from_pending:
                # The posted row REPLACES the pending one in place, so the user's
                # attribution, category choice, and transfer decision all survive.
                existing.plaid_transaction_id = plaid_txn_id
            for field, value in provenance.items():
                setattr(existing, field, value)
            # A user's own category choice is never overwritten by the provider.
            self._apply_provider_category(existing)
            existing.save()
            self._classify(existing)
            return True

        transaction = Transaction.objects.create(
            user=self.user,
            account=account,
            date=txn_data['date'],
            amount=wlj_amount,
            description=description,
            # `.get(key, '')` returns None when the key EXISTS and is null, which Plaid
            # does routinely for transactions with no resolved merchant. `payee` is
            # non-null, so the default must be applied to the VALUE, not the key.
            payee=(txn_data.get('merchant_name') or ''),
            plaid_transaction_id=plaid_txn_id,
            plaid_pending=is_pending,
            is_cleared=not is_pending,
            **provenance,
        )
        self._apply_provider_category(transaction)
        transaction.save(update_fields=['category', 'category_source', 'updated_at'])
        self._classify(transaction)
        return True

    def _apply_provider_category(self, transaction):
        """Map the provider's classification onto a WLJ category. Deterministic.

        Never overwrites a category the USER chose, and never guesses: an unmapped or
        low-confidence classification leaves the category unset, which is honest.
        The provider's own value is retained either way.
        """
        from apps.finance.models import Transaction
        from apps.finance.services.category_taxonomy import (
            map_provider_category,
            system_category_map,
        )

        if transaction.category_source == Transaction.CATEGORY_SOURCE_USER:
            return transaction

        name = map_provider_category(
            transaction.provider_category_primary,
            transaction.provider_category_detailed,
            transaction.provider_category_confidence,
        )
        if not name:
            return transaction

        if self._category_map is None:
            self._category_map = system_category_map()
        category = self._category_map.get(name)
        if category is None:
            return transaction

        transaction.category = category
        transaction.category_source = Transaction.CATEGORY_SOURCE_PROVIDER
        return transaction

    def _classify(self, transaction):
        """Assess transfer state from provider facts. One liability lookup per sync."""
        from apps.finance.services.transfer_detection import (
            classify,
            liability_account_names,
        )

        if self._liability_names is None:
            self._liability_names = liability_account_names(self.user)
        classify(transaction, liability_names=self._liability_names)

    def _remove_transaction(self, plaid_txn_id: str) -> bool:
        """
        Soft-delete a transaction that was removed from Plaid.

        Args:
            plaid_txn_id: Plaid transaction ID

        Returns:
            True if transaction was removed
        """
        from apps.finance.models import Transaction

        txn = Transaction.objects.filter(
            user=self.user,
            plaid_transaction_id=plaid_txn_id
        ).first()

        if txn:
            txn.soft_delete()
            logger.debug(f"Soft-deleted transaction: {plaid_txn_id}")
            return True

        return False

    def _log_sync_event(self, success: bool, details: dict):
        """Log sync event for audit trail."""
        from apps.finance.models import BankIntegrationLog

        BankIntegrationLog.objects.create(
            user=self.user,
            bank_connection=self.bank_connection,
            action=BankIntegrationLog.ACTION_SYNC,
            success=success,
            details=details,
        )


def sync_all_connections(user=None):
    """
    Sync all active bank connections.

    Args:
        user: Optional user to limit sync to

    Returns:
        dict with results per connection
    """
    from apps.finance.models import BankConnection

    queryset = BankConnection.objects.filter(
        connection_status=BankConnection.STATUS_ACTIVE
    )

    if user:
        queryset = queryset.filter(user=user)

    results = {}

    for connection in queryset:
        service = TransactionSyncService(connection)
        results[connection.id] = service.sync()

    return results
