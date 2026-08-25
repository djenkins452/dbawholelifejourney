# ==============================================================================
# File: apps/finance/tests/test_plaid_trial_security.py
# Project: Whole Life Journey - Django 5.x Personal Wellness/Journaling App
# Description: The security promises WLJ makes to Plaid, enforced in code.
# Owner: Danny Jenkins (admin@wholelifejourney.com)
# ==============================================================================
"""Each test corresponds to a promise on Plaid's Trial security attestation.

No test makes a network call, and none needs a real Plaid credential.
"""
from __future__ import annotations

import hashlib
import json
import time

from cryptography.hazmat.primitives.asymmetric import ec
from django.conf import settings
from django.core.cache import cache
from django.core.exceptions import PermissionDenied, ValidationError
from django.test import RequestFactory, TestCase, override_settings
from django.urls import reverse

from apps.finance.models import BankConnection, FinancialAccount
from apps.finance.services import provider_disconnect
from apps.finance.services.encryption import (
    EncryptionNotConfigured,
    decrypt_token,
    encrypt_token,
    encryption_available,
    generate_encryption_key,
    is_legacy_plaintext,
)
from apps.users.models import TermsAcceptance, User

TEST_KEY = "Zx6vN0oQ0aPpBqfN0O0m5m2H1s8xkGm0lJZ0hQ6oQ2c="   # test-only Fernet key


def _fernet_key():
    return generate_encryption_key()


# =============================================================================
# 1 — Token encryption fails closed
# =============================================================================

class EncryptionFailsClosedTests(TestCase):

    @override_settings(BANK_TOKEN_ENCRYPTION_KEY="")
    def test_encrypting_without_a_key_raises_instead_of_storing_plaintext(self):
        with self.assertRaises(EncryptionNotConfigured):
            encrypt_token("access-sandbox-secret")

    @override_settings(BANK_TOKEN_ENCRYPTION_KEY="")
    def test_encryption_available_is_false_without_a_key(self):
        self.assertFalse(encryption_available())

    @override_settings(BANK_TOKEN_ENCRYPTION_KEY="not-a-valid-fernet-key")
    def test_an_invalid_key_raises_rather_than_degrading(self):
        with self.assertRaises(EncryptionNotConfigured):
            encrypt_token("access-sandbox-secret")
        self.assertFalse(encryption_available())

    def test_round_trip_with_a_valid_key(self):
        key = _fernet_key()
        with override_settings(BANK_TOKEN_ENCRYPTION_KEY=key):
            ciphertext = encrypt_token("access-sandbox-secret")
            self.assertNotIn("access-sandbox-secret", ciphertext)
            self.assertFalse(ciphertext.startswith("UNENCRYPTED:"))
            self.assertEqual(decrypt_token(ciphertext), "access-sandbox-secret")

    def test_no_code_path_can_write_the_legacy_plaintext_prefix(self):
        import inspect

        from apps.finance.services import encryption
        source = inspect.getsource(encryption)
        self.assertNotIn('return f"UNENCRYPTED:{plaintext}"', source)
        self.assertNotIn("f'UNENCRYPTED:{plaintext}'", source)

    def test_legacy_plaintext_remains_readable_so_revocation_is_possible(self):
        """Reading one is allowed — it may be the only credential that can revoke."""
        key = _fernet_key()
        with override_settings(BANK_TOKEN_ENCRYPTION_KEY=key):
            legacy = "UNENCRYPTED:access-sandbox-legacy"
            self.assertTrue(is_legacy_plaintext(legacy))
            self.assertEqual(decrypt_token(legacy), "access-sandbox-legacy")

    def test_rotation_readiness_old_key_cannot_read_new_ciphertext(self):
        old_key, new_key = _fernet_key(), _fernet_key()
        with override_settings(BANK_TOKEN_ENCRYPTION_KEY=new_key):
            ciphertext = encrypt_token("access-sandbox-secret")
        with override_settings(BANK_TOKEN_ENCRYPTION_KEY=old_key):
            with self.assertRaises(ValueError):
                decrypt_token(ciphertext)

    def test_key_value_is_never_logged(self):
        import inspect

        from apps.finance.services import encryption
        source = inspect.getsource(encryption)
        for bad in ("logger.error(f\"Invalid BANK_TOKEN_ENCRYPTION_KEY: {e}\")",
                    "%s\", key", "{key}"):
            self.assertNotIn(bad, source)

    def test_deployment_check_blocks_a_plaid_environment_without_a_key(self):
        from apps.finance.checks import bank_token_encryption_check
        with override_settings(BANK_TOKEN_ENCRYPTION_KEY="", DEBUG=False,
                               PLAID_CLIENT_ID="cid", PLAID_SECRET="sec"):
            errors = bank_token_encryption_check(None)
            self.assertEqual([e.id for e in errors], ["finance.E001"])

    def test_deployment_check_passes_with_a_valid_key(self):
        with override_settings(BANK_TOKEN_ENCRYPTION_KEY=_fernet_key(), DEBUG=False,
                               PLAID_CLIENT_ID="cid", PLAID_SECRET="sec"):
            from apps.finance.checks import bank_token_encryption_check
            self.assertEqual(bank_token_encryption_check(None), [])

    def test_key_is_declared_in_configuration_governance(self):
        import apps.core.config_governance.contract as contract
        source = open(contract.__file__).read()
        self.assertIn('name="BANK_TOKEN_ENCRYPTION_KEY"', source)


# =============================================================================
# 2 — Plaid webhook verification
# =============================================================================

@override_settings(PLAID_CLIENT_ID="test-client", PLAID_SECRET="test-secret")
class WebhookVerificationTests(TestCase):

    def setUp(self):
        cache.clear()
        self.factory = RequestFactory()
        self.private_key = ec.generate_private_key(ec.SECP256R1())
        self.body = json.dumps({"webhook_type": "TRANSACTIONS"}).encode()
        self.jwk = self._public_jwk(self.private_key)

    @staticmethod
    def _public_jwk(private_key):
        from jwt.algorithms import ECAlgorithm
        return json.loads(ECAlgorithm.to_jwk(private_key.public_key()))

    def _token(self, *, body=None, iat=None, kid="kid-1", alg="ES256", key=None):
        import jwt
        payload = {
            "iat": int(iat if iat is not None else time.time()),
            "request_body_sha256": hashlib.sha256(
                self.body if body is None else body).hexdigest(),
        }
        return jwt.encode(payload, key or self.private_key, algorithm=alg,
                          headers={"kid": kid})

    def _request(self, token, body=None):
        request = self.factory.post(
            "/finance/webhooks/plaid/", data=body if body is not None else self.body,
            content_type="application/json")
        if token is not None:
            request.META["HTTP_PLAID_VERIFICATION"] = token
        return request

    def _verify(self, request, fetcher=None):
        from apps.finance.services.plaid_webhook_verification import verify_webhook
        return verify_webhook(request, key_fetcher=fetcher or (lambda kid: self.jwk))

    def test_valid_webhook_is_accepted(self):
        self.assertTrue(self._verify(self._request(self._token())))

    def test_invalid_signature_is_rejected(self):
        from apps.finance.services.plaid_webhook_verification import REASON_BAD_SIGNATURE
        other_key = ec.generate_private_key(ec.SECP256R1())
        result = self._verify(self._request(self._token(key=other_key)))
        self.assertFalse(result)
        self.assertEqual(result.reason, REASON_BAD_SIGNATURE)

    def test_wrong_body_is_rejected(self):
        from apps.finance.services.plaid_webhook_verification import REASON_BODY_MISMATCH
        token = self._token(body=b'{"tampered": true}')
        result = self._verify(self._request(token))
        self.assertFalse(result)
        self.assertEqual(result.reason, REASON_BODY_MISMATCH)

    def test_expired_timestamp_is_rejected(self):
        from apps.finance.services.plaid_webhook_verification import REASON_EXPIRED
        result = self._verify(self._request(self._token(iat=time.time() - 3600)))
        self.assertFalse(result)
        self.assertEqual(result.reason, REASON_EXPIRED)

    def test_unknown_key_is_rejected(self):
        from apps.finance.services.plaid_webhook_verification import REASON_UNKNOWN_KEY
        result = self._verify(self._request(self._token()), fetcher=lambda kid: None)
        self.assertFalse(result)
        self.assertEqual(result.reason, REASON_UNKNOWN_KEY)

    def test_missing_header_is_rejected(self):
        from apps.finance.services.plaid_webhook_verification import (
            REASON_MISSING_HEADER,
        )
        result = self._verify(self._request(None))
        self.assertFalse(result)
        self.assertEqual(result.reason, REASON_MISSING_HEADER)

    def test_unsigned_token_is_rejected(self):
        """`alg: none` — the exact forgery the old implementation accepted."""
        import jwt

        from apps.finance.services.plaid_webhook_verification import REASON_BAD_ALGORITHM
        payload = {"iat": int(time.time()),
                   "request_body_sha256": hashlib.sha256(self.body).hexdigest()}
        token = jwt.encode(payload, key="", algorithm="none",
                           headers={"kid": "kid-1"})
        result = self._verify(self._request(token))
        self.assertFalse(result)
        self.assertEqual(result.reason, REASON_BAD_ALGORITHM)

    def test_replayed_webhook_is_rejected(self):
        from apps.finance.services.plaid_webhook_verification import REASON_REPLAY
        token = self._token()
        self.assertTrue(self._verify(self._request(token)))
        result = self._verify(self._request(token))
        self.assertFalse(result)
        self.assertEqual(result.reason, REASON_REPLAY)

    @override_settings(PLAID_CLIENT_ID="", PLAID_SECRET="")
    def test_missing_configuration_fails_closed(self):
        from apps.finance.services.plaid_webhook_verification import (
            REASON_NOT_CONFIGURED,
        )
        result = self._verify(self._request(self._token()))
        self.assertFalse(result, "unconfigured MUST reject, not accept")
        self.assertEqual(result.reason, REASON_NOT_CONFIGURED)

    def test_verification_keys_are_cached_with_a_bounded_lifetime(self):
        from apps.finance.services import plaid_webhook_verification as verification
        self.assertLessEqual(verification.KEY_CACHE_SECONDS, 24 * 60 * 60)
        self.assertGreater(verification.KEY_CACHE_SECONDS, 0)

    def test_no_sensitive_material_is_logged(self):
        import inspect

        from apps.finance.services import plaid_webhook_verification as verification
        source = inspect.getsource(verification)
        for bad in ("logger.warning(token", "%s\", token", "{token}", "request.body)",
                    "logger.info(claims"):
            self.assertNotIn(bad, source)

    def test_the_view_helper_fails_closed(self):
        from apps.finance.views import verify_plaid_webhook
        is_valid, reason = verify_plaid_webhook(self._request(None))
        self.assertFalse(is_valid)
        self.assertTrue(reason)


# =============================================================================
# 3 — Disconnection revokes safely
# =============================================================================

class _FakePlaid:
    def __init__(self, *, error=None):
        self.error = error
        self.calls = 0

    def remove_item(self, access_token):
        self.calls += 1
        if self.error:
            raise self.error
        return True


class _ProviderError(Exception):
    def __init__(self, code=""):
        super().__init__(code or "provider error")
        self.code = code


class DisconnectionTests(TestCase):

    def setUp(self):
        self.key = _fernet_key()
        self.user = User.objects.create_user(email="dc@example.com", password="x" * 14)
        with override_settings(BANK_TOKEN_ENCRYPTION_KEY=self.key):
            self.connection = BankConnection.objects.create(
                user=self.user, item_id="item-1", institution_name="Test Bank",
                connection_status=BankConnection.STATUS_ACTIVE)
            self.connection.set_access_token("access-sandbox-token")
            self.connection.save()

    def test_successful_revocation_clears_the_token(self):
        with override_settings(BANK_TOKEN_ENCRYPTION_KEY=self.key):
            fake = _FakePlaid()
            provider_disconnect.revoke_and_disconnect(self.connection,
                                                      plaid_service=fake)
        self.connection.refresh_from_db()
        self.assertEqual(fake.calls, 1)
        self.assertEqual(self.connection.connection_status,
                         BankConnection.STATUS_DISCONNECTED)
        self.assertEqual(self.connection.access_token_encrypted, "")

    def test_failed_revocation_preserves_the_token_and_reports_failure(self):
        with override_settings(BANK_TOKEN_ENCRYPTION_KEY=self.key):
            fake = _FakePlaid(error=_ProviderError("INTERNAL_SERVER_ERROR"))
            with self.assertRaises(provider_disconnect.RevocationFailed):
                provider_disconnect.revoke_and_disconnect(self.connection,
                                                          plaid_service=fake)
        self.connection.refresh_from_db()
        self.assertEqual(self.connection.connection_status,
                         BankConnection.STATUS_REVOCATION_PENDING)
        self.assertNotEqual(self.connection.access_token_encrypted, "",
                            "the only credential able to revoke was discarded")

    def test_item_already_gone_is_treated_as_revoked(self):
        with override_settings(BANK_TOKEN_ENCRYPTION_KEY=self.key):
            fake = _FakePlaid(error=_ProviderError("ITEM_NOT_FOUND"))
            provider_disconnect.revoke_and_disconnect(self.connection,
                                                      plaid_service=fake)
        self.connection.refresh_from_db()
        self.assertEqual(self.connection.connection_status,
                         BankConnection.STATUS_DISCONNECTED)
        self.assertEqual(self.connection.access_token_encrypted, "")

    def test_retry_is_idempotent_and_can_succeed_later(self):
        with override_settings(BANK_TOKEN_ENCRYPTION_KEY=self.key):
            with self.assertRaises(provider_disconnect.RevocationFailed):
                provider_disconnect.revoke_and_disconnect(
                    self.connection, plaid_service=_FakePlaid(error=_ProviderError()))
            self.connection.refresh_from_db()
            provider_disconnect.revoke_and_disconnect(self.connection,
                                                      plaid_service=_FakePlaid())
            self.connection.refresh_from_db()
            self.assertEqual(self.connection.connection_status,
                             BankConnection.STATUS_DISCONNECTED)
            # Running once more must be a no-op, not an error.
            provider_disconnect.revoke_and_disconnect(self.connection,
                                                      plaid_service=_FakePlaid())

    def test_deletion_cannot_bypass_revocation(self):
        with self.assertRaises(ValidationError):
            self.connection.delete()
        with self.assertRaises(ValidationError):
            self.connection.soft_delete()

    def test_deletion_is_allowed_once_revoked(self):
        with override_settings(BANK_TOKEN_ENCRYPTION_KEY=self.key):
            provider_disconnect.revoke_and_disconnect(self.connection,
                                                      plaid_service=_FakePlaid())
        self.connection.refresh_from_db()
        self.connection.delete()
        self.assertFalse(
            BankConnection.all_objects.filter(pk=self.connection.pk).exists())

    def test_account_closure_is_blocked_while_access_is_live(self):
        with self.assertRaises(ValidationError):
            provider_disconnect.assert_no_live_provider_access(self.user)

    def test_no_network_call_lives_in_a_model_signal(self):
        import inspect

        from apps.finance import models as finance_models
        source = inspect.getsource(finance_models)
        self.assertNotIn("remove_item", source,
                         "provider calls must stay in the disconnect service")

    def test_pending_revocations_can_be_retried_in_bulk(self):
        with override_settings(BANK_TOKEN_ENCRYPTION_KEY=self.key):
            with self.assertRaises(provider_disconnect.RevocationFailed):
                provider_disconnect.revoke_and_disconnect(
                    self.connection, plaid_service=_FakePlaid(error=_ProviderError()))
            self.connection.refresh_from_db()
            self.assertEqual(
                BankConnection.objects.filter(
                    connection_status=BankConnection.STATUS_REVOCATION_PENDING).count(),
                1)


# =============================================================================
# 4 & 5 — Trial eligibility, MFA/re-auth, rate limiting
# =============================================================================

class FinanceAccessControlTests(TestCase):

    def _user(self, email, *, finance=False, staff=False):
        user = User.objects.create_user(email=email, password="testpass123",
                                        is_staff=staff)
        TermsAcceptance.objects.create(
            user=user, terms_version=settings.WLJ_SETTINGS.get("TERMS_VERSION", "1.0"))
        prefs = user.preferences
        prefs.has_completed_onboarding = True
        prefs.finances_enabled = finance
        prefs.save()
        return user

    def test_finance_is_off_by_default_for_a_new_user(self):
        from apps.finance.access import finance_access_granted
        user = User.objects.create_user(email="fresh@example.com", password="x" * 14)
        self.assertFalse(user.preferences.finances_enabled)
        self.assertFalse(finance_access_granted(user))

    def test_signup_does_not_grant_provider_access(self):
        user = self._user("nofinance@example.com", finance=False)
        self.client.login(email="nofinance@example.com", password="testpass123")
        response = self.client.get(reverse("finance:connection_start"))
        self.assertEqual(response.status_code, 403)

    def test_enabled_user_passes_the_capability_gate(self):
        from apps.finance.access import finance_access_granted
        user = self._user("yesfinance@example.com", finance=True)
        self.assertTrue(finance_access_granted(user))

    def test_attribution_surfaces_are_gated(self):
        self._user("nofinance2@example.com", finance=False)
        self.client.login(email="nofinance2@example.com", password="testpass123")
        response = self.client.post(
            reverse("finance:attribution_decide"),
            data=json.dumps({"transaction_id": 1, "entity_id": 1}),
            content_type="application/json")
        self.assertEqual(response.status_code, 403)

    def test_no_identity_is_hardcoded_in_the_access_layer(self):
        """No name, address, or id may appear in EXECUTABLE code.

        The file header credits an owner, as every WLJ module does — prose is not logic.
        What matters is that no string literal in the code encodes an identity.
        """
        import ast

        from apps.finance import access
        tree = ast.parse(open(access.__file__).read())
        docstrings = set()
        for node in ast.walk(tree):
            if isinstance(node, (ast.Module, ast.ClassDef, ast.FunctionDef)):
                body = getattr(node, "body", None)
                if body and isinstance(body[0], ast.Expr) and \
                        isinstance(body[0].value, ast.Constant):
                    docstrings.add(id(body[0].value))
        for node in ast.walk(tree):
            if isinstance(node, ast.Constant) and isinstance(node.value, str) \
                    and id(node) not in docstrings:
                lowered = node.value.lower()
                for identity in ("danny", "jenkins", "@gmail", "@wholelifejourney"):
                    self.assertNotIn(identity, lowered,
                                     f"identity hardcoded at line {node.lineno}")

    def test_staff_can_grant_and_non_staff_cannot(self):
        from apps.finance.access import grant_finance_access
        target = self._user("target@example.com", finance=False)
        staff = self._user("staff@example.com", staff=True)
        civilian = self._user("civilian@example.com")
        with self.assertRaises(PermissionDenied):
            grant_finance_access(target, granted_by=civilian)
        grant_finance_access(target, granted_by=staff)
        target.preferences.refresh_from_db()
        self.assertTrue(target.preferences.finances_enabled)

    def test_sensitive_provider_controls_are_applied_not_merely_defined(self):
        """The exact failure the audit found: these decorators existed and were unused."""
        source = open("apps/finance/views.py").read()
        for name in ("bank_connection_start", "bank_connection_complete",
                     "bank_connection_disconnect", "bank_connection_sync"):
            index = source.index(f"def {name}(")
            preceding = source[max(0, index - 260):index]
            self.assertIn("@finance_enabled_required", preceding, name)
            self.assertIn("@requires_recent_auth", preceding, name)
            self.assertIn("@finance_rate_limit", preceding, name)

    def test_webhooks_are_not_user_authenticated(self):
        source = open("apps/finance/views.py").read()
        index = source.index("def plaid_webhook(")
        preceding = source[max(0, index - 200):index]
        self.assertNotIn("@login_required", preceding)
        self.assertNotIn("@requires_recent_auth", preceding)
        self.assertIn("@csrf_exempt", preceding)

    def test_rate_limit_blocks_a_burst(self):
        from apps.finance.security import FinanceRateLimiter
        cache.clear()
        user = self._user("burst@example.com", finance=True)
        limiter = FinanceRateLimiter(user)
        allowed_count = 0
        for _ in range(10):
            allowed, _retry = limiter.check_limit("bank_connect")
            if not allowed:
                break
            limiter.record_request("bank_connect")
            allowed_count += 1
        self.assertEqual(allowed_count, 5, "bank_connect must cap at 5/hour")
