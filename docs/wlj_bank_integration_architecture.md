# ==============================================================================
# File: docs/wlj_bank_integration_architecture.md
# Project: Whole Life Journey - Django 5.x Personal Wellness/Journaling App
# Description: Bank Integration Architecture for Secure Financial Connections
# Owner: Danny Jenkins (dannyjenkins71@gmail.com)
# Created: 2026-01-03
# Last Updated: 2026-01-03
# ==============================================================================

# Bank Integration Architecture

## 1. Executive Summary

This document defines the architecture for enabling users to securely connect their financial institutions to WLJ for automatic transaction synchronization. The design prioritizes:

1. **Security** - Encrypted credential storage, no direct bank login capture
2. **Compliance** - Alignment with PCI-DSS, Open Banking standards
3. **User Control** - Easy connection and disconnection
4. **Reliability** - Graceful failure handling and sync scheduling

---

## 2. Financial Data Aggregator Strategy

### 2.1 Aggregator Selection

WLJ will use **Plaid** as the primary financial data aggregator.

| Criteria | Plaid | Alternatives Considered |
|----------|-------|------------------------|
| **Coverage** | 12,000+ institutions | Yodlee (similar), MX (banking-focused) |
| **Security** | SOC 2 Type II, bank-level encryption | All meet standards |
| **Pricing** | Per-connection model | Varies |
| **Developer Experience** | Excellent docs, Link UI | Varies |
| **Open Banking Ready** | Yes (OAuth-first for supported banks) | Varies |

### 2.2 Why Plaid?

1. **No Credential Handling** - Plaid Link UI handles all bank login flows
2. **Token-Based Access** - WLJ only stores access tokens, never bank passwords
3. **Wide Coverage** - Supports major US banks and credit unions
4. **OAuth Support** - Modern banks use OAuth (no screen scraping)
5. **Proven Track Record** - Used by major fintech apps

### 2.3 Integration Architecture

```
┌─────────────────────────────────────────────────────────────────────────┐
│                          User's Browser                                  │
├─────────────────────────────────────────────────────────────────────────┤
│  1. User clicks "Connect Bank"                                          │
│  2. Plaid Link UI opens (embedded iframe/popup)                         │
│  3. User authenticates directly with their bank                         │
│  4. Plaid returns public_token to browser                               │
│  5. Browser sends public_token to WLJ backend                           │
└─────────────────────────────────────────────────────────────────────────┘
                                    │
                                    ▼
┌─────────────────────────────────────────────────────────────────────────┐
│                          WLJ Backend                                     │
├─────────────────────────────────────────────────────────────────────────┤
│  6. Exchange public_token for access_token via Plaid API                │
│  7. Encrypt access_token before database storage                        │
│  8. Create BankConnection record                                        │
│  9. Fetch initial transactions                                          │
│  10. Store transactions in WLJ database                                 │
└─────────────────────────────────────────────────────────────────────────┘
                                    │
                                    ▼
┌─────────────────────────────────────────────────────────────────────────┐
│                          Plaid API                                       │
├─────────────────────────────────────────────────────────────────────────┤
│  - Handles bank authentication                                          │
│  - Provides account and transaction data                                │
│  - Sends webhooks for updates                                           │
└─────────────────────────────────────────────────────────────────────────┘
```

---

## 3. Token Storage and Refresh Mechanisms

### 3.1 Credential Model

```python
# apps/finance/models.py

class BankConnection(UserOwnedModel):
    """
    Stores Plaid access tokens and connection metadata.
    Follows pattern from GoogleCalendarCredential.
    """

    # Plaid identifiers
    item_id = models.CharField(
        max_length=100,
        help_text="Plaid Item ID (unique per institution connection)"
    )
    access_token = models.TextField(
        help_text="Encrypted Plaid access token"
    )

    # Institution info
    institution_id = models.CharField(
        max_length=50,
        help_text="Plaid institution ID"
    )
    institution_name = models.CharField(
        max_length=200,
        help_text="Display name of the institution"
    )
    institution_logo = models.URLField(
        blank=True,
        help_text="URL to institution logo (from Plaid)"
    )

    # Connection status
    STATUS_ACTIVE = 'active'
    STATUS_PENDING = 'pending'
    STATUS_ERROR = 'error'
    STATUS_DISCONNECTED = 'disconnected'

    STATUS_CHOICES = [
        (STATUS_ACTIVE, 'Active'),
        (STATUS_PENDING, 'Pending Initial Sync'),
        (STATUS_ERROR, 'Requires Attention'),
        (STATUS_DISCONNECTED, 'Disconnected'),
    ]

    connection_status = models.CharField(
        max_length=20,
        choices=STATUS_CHOICES,
        default=STATUS_PENDING
    )

    # Error tracking
    error_code = models.CharField(
        max_length=50,
        blank=True,
        help_text="Plaid error code if connection has issues"
    )
    error_message = models.TextField(
        blank=True,
        help_text="Human-readable error message"
    )
    requires_reauth = models.BooleanField(
        default=False,
        help_text="User needs to re-authenticate with bank"
    )

    # Sync tracking
    last_sync_at = models.DateTimeField(
        null=True,
        blank=True,
        help_text="Last successful transaction sync"
    )
    last_sync_cursor = models.CharField(
        max_length=500,
        blank=True,
        help_text="Plaid sync cursor for incremental updates"
    )
    transactions_synced = models.PositiveIntegerField(
        default=0,
        help_text="Total transactions synced from this connection"
    )

    # Consent and audit
    consent_given_at = models.DateTimeField(
        auto_now_add=True,
        help_text="When user authorized this connection"
    )
    consent_ip_address = models.GenericIPAddressField(
        null=True,
        blank=True,
        help_text="IP address when consent was given"
    )

    class Meta:
        ordering = ['-created_at']
        verbose_name = "Bank Connection"
        verbose_name_plural = "Bank Connections"
        unique_together = ['user', 'item_id']
        indexes = [
            models.Index(fields=['user', 'connection_status']),
            models.Index(fields=['item_id']),
        ]

    def __str__(self):
        return f"{self.institution_name} ({self.get_connection_status_display()})"
```

### 3.2 Encryption Strategy

**CRITICAL:** Access tokens MUST be encrypted at rest.

```python
# Using django-fernet-fields or custom encryption

from cryptography.fernet import Fernet
from django.conf import settings

def encrypt_token(plaintext: str) -> str:
    """Encrypt a token for database storage."""
    fernet = Fernet(settings.BANK_TOKEN_ENCRYPTION_KEY.encode())
    return fernet.encrypt(plaintext.encode()).decode()

def decrypt_token(ciphertext: str) -> str:
    """Decrypt a token retrieved from database."""
    fernet = Fernet(settings.BANK_TOKEN_ENCRYPTION_KEY.encode())
    return fernet.decrypt(ciphertext.encode()).decode()
```

**Environment Variables Required:**
- `BANK_TOKEN_ENCRYPTION_KEY` - 32-byte Fernet key (base64 encoded)
- `PLAID_CLIENT_ID` - Plaid API client ID
- `PLAID_SECRET` - Plaid API secret (sandbox/development/production)
- `PLAID_ENV` - Environment: sandbox, development, or production

### 3.3 Token Lifecycle

Plaid access tokens are **permanent** and do not expire. However, they can become invalid due to:

| Scenario | Detection | Resolution |
|----------|-----------|------------|
| User changes bank password | Webhook `ITEM_LOGIN_REQUIRED` | Trigger re-auth via Link |
| Bank requires MFA update | Webhook `ITEM_LOGIN_REQUIRED` | Trigger re-auth via Link |
| User disconnects via bank | Webhook `PENDING_EXPIRATION` | Notify user, remove connection |
| WLJ system deletes connection | User-initiated | Revoke token via Plaid API |

### 3.4 Token Revocation

When a user disconnects a bank:

```python
def disconnect_bank(bank_connection: BankConnection):
    """
    Securely disconnect a bank and revoke access.
    """
    # 1. Revoke the token with Plaid
    plaid_client.item_remove(bank_connection.decrypt_access_token())

    # 2. Clear the encrypted token
    bank_connection.access_token = ''
    bank_connection.connection_status = 'disconnected'
    bank_connection.save()

    # 3. Optionally: Keep or delete synced transactions based on user preference
```

---

## 4. Sync Schedules and Failure Handling

### 4.1 Sync Strategy

| Sync Type | Trigger | Frequency |
|-----------|---------|-----------|
| **Initial Sync** | After successful connection | Once |
| **Webhook Sync** | Plaid sends transaction update | Real-time |
| **Scheduled Sync** | Cron/APScheduler job | Every 4 hours |
| **Manual Sync** | User clicks "Refresh" | On-demand |

### 4.2 Webhook Integration

Plaid sends webhooks to notify of new transactions and status changes.

**Webhook Endpoint:** `/finance/webhooks/plaid/`

**Webhook Types to Handle:**

| Webhook Type | Code | Action |
|--------------|------|--------|
| `TRANSACTIONS` | `SYNC_UPDATES_AVAILABLE` | Trigger incremental sync |
| `TRANSACTIONS` | `INITIAL_UPDATE` | Initial sync complete |
| `TRANSACTIONS` | `HISTORICAL_UPDATE` | Historical data ready |
| `ITEM` | `ERROR` | Mark connection as error |
| `ITEM` | `LOGIN_REQUIRED` | Set `requires_reauth = True` |
| `ITEM` | `PENDING_EXPIRATION` | Notify user, prompt reauth |

**Webhook Security:**
- Verify `Plaid-Verification` header signature
- Only process webhooks from Plaid IPs (optional)
- Idempotent processing (handle duplicate webhooks)

### 4.3 Incremental Sync with Cursor

Plaid uses cursor-based pagination for efficient syncs:

```python
def sync_transactions(bank_connection: BankConnection):
    """
    Incrementally sync transactions using cursor.
    """
    cursor = bank_connection.last_sync_cursor
    has_more = True
    added = 0
    modified = 0
    removed = 0

    while has_more:
        response = plaid_client.transactions_sync(
            access_token=bank_connection.decrypt_access_token(),
            cursor=cursor
        )

        # Process added transactions
        for txn in response.added:
            create_or_update_transaction(bank_connection, txn)
            added += 1

        # Process modified transactions
        for txn in response.modified:
            create_or_update_transaction(bank_connection, txn)
            modified += 1

        # Process removed transactions
        for txn_id in response.removed:
            soft_delete_transaction(txn_id)
            removed += 1

        cursor = response.next_cursor
        has_more = response.has_more

    # Save the cursor for next sync
    bank_connection.last_sync_cursor = cursor
    bank_connection.last_sync_at = timezone.now()
    bank_connection.transactions_synced += added
    bank_connection.save()

    return {'added': added, 'modified': modified, 'removed': removed}
```

### 4.4 Failure Handling

| Failure Type | Response | User Communication |
|--------------|----------|-------------------|
| **Network timeout** | Retry with exponential backoff (3 attempts) | Silent retry |
| **Rate limit (429)** | Back off, schedule retry in 5 minutes | Silent retry |
| **Auth error (ITEM_LOGIN_REQUIRED)** | Set `requires_reauth`, stop syncing | "Please reconnect your bank" |
| **Institution unavailable** | Log, retry in 1 hour | Silent retry, notify if persistent |
| **Internal error (500)** | Log, alert admin, retry | "Sync temporarily unavailable" |
| **Invalid cursor** | Clear cursor, do full sync | Silent recovery |

### 4.5 Scheduled Sync Job

```python
# apps/finance/management/commands/sync_bank_connections.py

class Command(BaseCommand):
    def handle(self, *args, **options):
        # Get all active connections due for sync
        stale_connections = BankConnection.objects.filter(
            connection_status='active',
            last_sync_at__lt=timezone.now() - timedelta(hours=4)
        )

        for connection in stale_connections:
            try:
                sync_transactions(connection)
            except PlaidError as e:
                handle_plaid_error(connection, e)
```

---

## 5. User Connection and Disconnection Flow

### 5.1 Connection Flow (User Perspective)

```
1. User navigates to Finance > Settings > Connected Accounts
2. User clicks "Connect a Bank"
3. Plaid Link UI opens (WLJ is in background)
4. User searches for their bank
5. User authenticates with bank (username, password, MFA)
6. Plaid Link returns success
7. WLJ shows "Connected!" message
8. Initial sync begins in background
9. Transactions appear within 30 seconds
```

### 5.2 Connection Flow (Technical)

```
Browser                    WLJ Backend                 Plaid API
   │                            │                          │
   │─── GET /finance/connect ──▶│                          │
   │◀── Plaid Link token ───────│◀── create_link_token ────│
   │                            │                          │
   │ (User completes Plaid Link flow)                      │
   │                            │                          │
   │─── POST public_token ─────▶│                          │
   │                            │─── item/public_token/    │
   │                            │    exchange ────────────▶│
   │                            │◀── access_token ─────────│
   │                            │                          │
   │                            │ (Encrypt & store token)  │
   │                            │                          │
   │◀── Success, redirect ──────│                          │
   │                            │                          │
   │                            │─── transactions/sync ───▶│
   │                            │◀── transactions ─────────│
```

### 5.3 Link Token Configuration

```python
def create_link_token(user, request):
    """
    Create a Plaid Link token for the user.
    """
    return plaid_client.link_token_create({
        'user': {
            'client_user_id': str(user.id),
        },
        'client_name': 'Whole Life Journey',
        'products': ['transactions'],
        'country_codes': ['US'],
        'language': 'en',
        'webhook': settings.PLAID_WEBHOOK_URL,
        'redirect_uri': settings.PLAID_REDIRECT_URI,  # For OAuth banks
    })
```

### 5.4 Disconnection Flow

```
1. User navigates to Finance > Settings > Connected Accounts
2. User clicks "Disconnect" on a bank
3. Confirmation dialog: "This will stop syncing. Your existing transactions will be kept."
4. User confirms
5. WLJ revokes the Plaid access token
6. Connection status set to "Disconnected"
7. User sees confirmation message
```

### 5.5 Re-authentication Flow

When a bank requires re-authentication:

```
1. User sees banner: "Your Chase account needs attention"
2. User clicks "Fix Connection"
3. Plaid Link opens in "update" mode
4. User re-authenticates with bank
5. Connection status returns to "Active"
6. Sync resumes automatically
```

---

## 6. Account Mapping

### 6.1 Plaid Accounts to WLJ Accounts

Each Plaid "account" maps to a `FinancialAccount` in WLJ:

```python
# apps/finance/models.py

class FinancialAccount(UserOwnedModel):
    # Existing fields...

    # Plaid integration fields
    plaid_account_id = models.CharField(
        max_length=100,
        blank=True,
        help_text="Plaid account ID for synced accounts"
    )
    bank_connection = models.ForeignKey(
        'BankConnection',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='accounts',
        help_text="Link to bank connection if synced"
    )
    is_synced = models.BooleanField(
        default=False,
        help_text="Whether this account syncs with a bank"
    )
    last_balance_sync = models.DateTimeField(
        null=True,
        blank=True,
        help_text="Last time balance was synced from bank"
    )
```

### 6.2 Account Type Mapping

| Plaid Type | Plaid Subtype | WLJ Account Type |
|------------|---------------|------------------|
| depository | checking | checking |
| depository | savings | savings |
| depository | money market | savings |
| credit | credit card | credit_card |
| loan | mortgage | mortgage |
| loan | student | student_loan |
| loan | auto | loan |
| investment | 401k, ira, etc. | investment |

---

## 7. Security Considerations

### 7.1 Data Protection

| Data | Storage | Protection |
|------|---------|------------|
| Access tokens | Database | AES-256 encryption (Fernet) |
| Transaction data | Database | Standard DB security |
| User credentials | Never stored | Handled by Plaid Link |
| Webhook payloads | Logged (redacted) | Signature verification |

### 7.2 Access Control

- Only the account owner can view/manage their bank connections
- Admin cannot view access tokens (encrypted)
- No staff access to financial data without explicit permission

### 7.3 Audit Logging

Log all bank integration events:

```python
class BankIntegrationLog(UserOwnedModel):
    ACTION_CONNECT = 'connect'
    ACTION_DISCONNECT = 'disconnect'
    ACTION_SYNC = 'sync'
    ACTION_ERROR = 'error'
    ACTION_REAUTH = 'reauth'

    bank_connection = models.ForeignKey(BankConnection, on_delete=models.CASCADE)
    action = models.CharField(max_length=20)
    success = models.BooleanField()
    details = models.JSONField(default=dict)
    ip_address = models.GenericIPAddressField(null=True)
    timestamp = models.DateTimeField(auto_now_add=True)
```

### 7.4 Compliance Notes

| Standard | Requirement | WLJ Approach |
|----------|-------------|--------------|
| PCI-DSS | Never store card numbers | Plaid handles all card data |
| Open Banking | Use OAuth where available | Plaid uses OAuth-first |
| GDPR/CCPA | User can delete data | Disconnect + optional deletion |
| SOC 2 | Audit trail | BankIntegrationLog |

---

## 8. Environment Variables

### 8.1 Required Configuration

```bash
# Plaid API Configuration
PLAID_CLIENT_ID=your_client_id
PLAID_SECRET=your_secret_key
PLAID_ENV=sandbox  # sandbox, development, or production

# Encryption
BANK_TOKEN_ENCRYPTION_KEY=your_32_byte_base64_fernet_key

# Webhooks
PLAID_WEBHOOK_URL=https://wholelifejourney.com/finance/webhooks/plaid/

# OAuth Redirect (for OAuth-enabled banks)
PLAID_REDIRECT_URI=https://wholelifejourney.com/finance/plaid/oauth/
```

### 8.2 Sandbox vs Production

| Environment | Purpose | Data |
|-------------|---------|------|
| Sandbox | Development/testing | Fake institutions, fake data |
| Development | Integration testing | Limited real banks |
| Production | Live users | Full access |

---

## 9. Implementation Phases

### Phase 1: Foundation (This Task)
- [x] Architecture document (this file)
- [ ] BankConnection model
- [ ] Encryption utilities
- [ ] Environment configuration

### Phase 2: Core Integration
- [ ] Plaid client service
- [ ] Link token generation
- [ ] Token exchange endpoint
- [ ] Initial sync implementation

### Phase 3: Reliability
- [ ] Webhook handler
- [ ] Incremental sync with cursor
- [ ] Error handling and retry logic
- [ ] Re-authentication flow

### Phase 4: User Experience
- [ ] Connection management UI
- [ ] Sync status indicators
- [ ] Error messaging
- [ ] Account mapping UI

### Phase 5: Operations
- [ ] Monitoring and alerting
- [ ] Audit logging
- [ ] Admin tools
- [ ] Documentation for users

---

## 10. Dependencies

### Python Packages

```
plaid-python>=14.0.0
cryptography>=42.0.0
```

### Third-Party Services

| Service | Purpose | Pricing |
|---------|---------|---------|
| Plaid | Bank connectivity | Per-connection fee |

---

## Appendix A: Related Documents

- `docs/wlj_ai_finance_rules.md` - AI interpretation rules for financial data
- `docs/wlj_security_review.md` - Security review findings
- `docs/wlj_third_party_services.md` - Third-party service inventory
- `apps/finance/models.py` - Finance data models

---

## Appendix B: Revision History

| Date | Version | Changes |
|------|---------|---------|
| 2026-01-03 | 1.0 | Initial architecture document |

---

*This document is part of the WLJ Finance Module - Phase 8*
