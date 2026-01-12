# Key Rotation Schedule

**Created:** 2026-01-12 (CISO Review)
**Last Updated:** 2026-01-12
**Owner:** Danny Jenkins (admin@wholelifejourney.com)

## Overview

This document outlines the encryption key rotation schedule and procedures for Whole Life Journey. All encryption keys must be rotated on a regular schedule or immediately if compromise is suspected.

---

## Encryption Keys Inventory

| Key Name | Purpose | Storage Location | Rotation Frequency |
|----------|---------|------------------|-------------------|
| `BANK_TOKEN_ENCRYPTION_KEY` | Encrypt Plaid bank tokens | Railway env vars | Annual or on compromise |
| `OAUTH_TOKEN_ENCRYPTION_KEY` | Encrypt OAuth tokens (Google, Dexcom) | Railway env vars | Annual or on compromise |
| `SECRET_KEY` | Django session/CSRF signing | Railway env vars | Annual or on compromise |

---

## Standard Rotation Schedule

### Annual Rotation (January)

1. **BANK_TOKEN_ENCRYPTION_KEY** - First week of January
2. **OAUTH_TOKEN_ENCRYPTION_KEY** - First week of January
3. **SECRET_KEY** - First week of January (will invalidate all sessions)

### Emergency Rotation Triggers

Immediately rotate ALL keys if any of the following occur:

- Suspected key compromise or data breach
- Employee with key access leaves the company
- Security audit finding
- Any unauthorized access detected
- Key accidentally exposed in logs/error messages

---

## Rotation Procedures

### BANK_TOKEN_ENCRYPTION_KEY Rotation

Location: `apps/finance/services/encryption.py`

```bash
# 1. Generate new key
python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"

# 2. Save OLD key for decryption (create BANK_TOKEN_OLD_KEY env var)
# This allows reading existing tokens during migration

# 3. Update BANK_TOKEN_ENCRYPTION_KEY in Railway with new key

# 4. Run migration script to re-encrypt all tokens:
python manage.py shell
>>> from apps.finance.models import BankConnection
>>> from apps.finance.services.encryption import encrypt_bank_token, decrypt_bank_token_with_old_key
>>> for conn in BankConnection.objects.filter(encrypted_access_token__isnull=False):
...     old_token = decrypt_bank_token_with_old_key(conn.encrypted_access_token)
...     conn.encrypted_access_token = encrypt_bank_token(old_token)
...     conn.save()

# 5. Verify migration by testing one connection

# 6. Remove BANK_TOKEN_OLD_KEY from Railway after 7 days
```

### OAUTH_TOKEN_ENCRYPTION_KEY Rotation

Location: `apps/core/encryption.py`

```bash
# 1. Generate new key
python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"

# 2. Save OLD key for decryption (create OAUTH_TOKEN_OLD_KEY env var)

# 3. Update OAUTH_TOKEN_ENCRYPTION_KEY in Railway with new key

# 4. Run migration script:
python manage.py shell
>>> from apps.life.models import GoogleCalendarCredential
>>> from apps.health.models import DexcomCredential
>>> from apps.core.encryption import encrypt_oauth_token, decrypt_oauth_token_with_old_key
>>> # Re-encrypt Google Calendar tokens
>>> for cred in GoogleCalendarCredential.objects.all():
...     if cred.access_token:
...         old_token = decrypt_oauth_token_with_old_key(cred.access_token)
...         cred.access_token = encrypt_oauth_token(old_token)
...     if cred.refresh_token:
...         old_token = decrypt_oauth_token_with_old_key(cred.refresh_token)
...         cred.refresh_token = encrypt_oauth_token(old_token)
...     if cred.client_secret:
...         old_secret = decrypt_oauth_token_with_old_key(cred.client_secret)
...         cred.client_secret = encrypt_oauth_token(old_secret)
...     cred.save()
>>> # Re-encrypt Dexcom tokens
>>> for cred in DexcomCredential.objects.all():
...     if cred.access_token:
...         old_token = decrypt_oauth_token_with_old_key(cred.access_token)
...         cred.access_token = encrypt_oauth_token(old_token)
...     if cred.refresh_token:
...         old_token = decrypt_oauth_token_with_old_key(cred.refresh_token)
...         cred.refresh_token = encrypt_oauth_token(old_token)
...     cred.save()

# 5. Verify by testing OAuth connections

# 6. Remove OAUTH_TOKEN_OLD_KEY after 7 days
```

### SECRET_KEY Rotation

**WARNING:** Rotating SECRET_KEY will:
- Invalidate ALL user sessions (force re-login)
- Invalidate password reset tokens
- Invalidate CSRF tokens

```bash
# 1. Generate new key
python -c "from django.core.management.utils import get_random_secret_key; print(get_random_secret_key())"

# 2. Update SECRET_KEY in Railway

# 3. Deploy - all users will be logged out

# 4. Notify users if planned (not for emergency rotations)
```

---

## Verification Checklist

After any key rotation:

- [ ] Test bank account sync (BANK_TOKEN_ENCRYPTION_KEY)
- [ ] Test Google Calendar sync (OAUTH_TOKEN_ENCRYPTION_KEY)
- [ ] Test Dexcom sync (OAUTH_TOKEN_ENCRYPTION_KEY)
- [ ] Test user login/logout (SECRET_KEY)
- [ ] Test password reset flow (SECRET_KEY)
- [ ] Monitor error logs for 24 hours
- [ ] Remove OLD_KEY environment variables after 7 days

---

## Audit Log

| Date | Key Rotated | Reason | Performed By |
|------|-------------|--------|--------------|
| 2026-01-12 | Initial setup | CISO Review | Claude/Danny |

---

## Emergency Contact

If key compromise is suspected:

1. **Immediately** rotate affected key(s)
2. Notify admin@wholelifejourney.com
3. Review audit logs for unauthorized access
4. Document incident in this file

---

## Related Documentation

- `apps/finance/services/encryption.py` - Bank token encryption
- `apps/core/encryption.py` - OAuth token encryption
- `docs/wlj_claude_changelog.md` - Change history
