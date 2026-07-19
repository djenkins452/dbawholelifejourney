"""
Configuration Governance — deterministic evaluation + secret-safety contract.

Covers the Phase-14 scenarios that apply to the report-only foundation: required
present/missing/empty, non-required, cross-service consistency, optional missing,
unknown verification, the exact production incident (Cloudinary on worker/beat),
recovery, and the non-negotiable that NO secret value ever appears in a manifest.
"""
from datetime import timedelta

from django.test import SimpleTestCase
from django.utils import timezone

from apps.core.config_governance import contract as C
from apps.core.config_governance import evaluator as E
from apps.core.config_governance import manifest as M


def _manifest(service, overrides=None, when=None):
    """Build a manifest with every contract var 'present', minus overrides."""
    presence = {v.name: M.PRESENT for v in C.CONTRACT}
    presence.update(overrides or {})
    return {
        "service": service,
        "environment": "production",
        "commit": "abc123",
        "presence": presence,
        "published_at": (when or timezone.now()).isoformat(),
    }


def _all_healthy():
    return {s: _manifest(s) for s in (C.SERVICE_WEB, C.SERVICE_WORKER, C.SERVICE_BEAT)}


class EvaluatorTest(SimpleTestCase):
    def test_all_required_present_is_healthy(self):
        r = E.evaluate(_all_healthy())
        self.assertEqual(r["status"], E.HEALTHY)
        self.assertEqual(r["counts"]["total"], 0)

    def test_missing_critical_required_is_critical(self):
        mans = _all_healthy()
        mans[C.SERVICE_WORKER]["presence"]["DATABASE_URL"] = M.ABSENT
        r = E.evaluate(mans)
        self.assertEqual(r["status"], E.CRITICAL)
        self.assertTrue(any(f["variable"] == "DATABASE_URL" for f in r["findings"]))

    def test_empty_required_counts_as_missing(self):
        mans = _all_healthy()
        mans[C.SERVICE_WEB]["presence"]["SECRET_KEY"] = M.EMPTY
        r = E.evaluate(mans)
        self.assertEqual(r["status"], E.CRITICAL)

    def test_service_not_requiring_var_no_finding(self):
        # CLAUDE_API_KEY is required only on web; absent on worker must NOT flag.
        mans = _all_healthy()
        mans[C.SERVICE_WORKER]["presence"]["CLAUDE_API_KEY"] = M.ABSENT
        r = E.evaluate(mans)
        self.assertFalse(any(
            f.get("variable") == "CLAUDE_API_KEY" and "Background Worker" in (f.get("services") or [])
            for f in r["findings"]
        ))

    def test_optional_empty_valid_missing_is_ok(self):
        # CLAUDE_API_KEY is empty_valid — empty on web is acceptable.
        mans = _all_healthy()
        mans[C.SERVICE_WEB]["presence"]["CLAUDE_API_KEY"] = M.EMPTY
        r = E.evaluate(mans)
        self.assertFalse(any(f.get("variable") == "CLAUDE_API_KEY" for f in r["findings"]))

    def test_degraded_when_only_non_critical_missing(self):
        mans = _all_healthy()
        mans[C.SERVICE_WORKER]["presence"]["OPENAI_API_KEY"] = M.ABSENT  # degraded sev
        r = E.evaluate(mans)
        self.assertEqual(r["status"], E.DEGRADED)

    def test_unverified_service_is_unknown_never_healthy(self):
        mans = {C.SERVICE_WEB: _manifest(C.SERVICE_WEB)}  # worker + beat absent
        r = E.evaluate(mans)
        self.assertEqual(r["status"], E.UNKNOWN)
        self.assertIn("Background Worker", r["unverified_services"])
        self.assertNotEqual(r["status"], E.HEALTHY)

    def test_stale_manifest_is_not_trusted(self):
        old = timezone.now() - timedelta(seconds=M.FRESH_WINDOW_SECONDS + 60)
        mans = _all_healthy()
        mans[C.SERVICE_BEAT] = _manifest(C.SERVICE_BEAT, when=old)
        r = E.evaluate(mans)
        self.assertEqual(r["status"], E.UNKNOWN)
        self.assertIn("Scheduler", r["unverified_services"])

    def test_production_incident_cloudinary_on_worker_and_beat(self):
        """The exact incident: Cloudinary present on Web, absent on Worker+Beat."""
        mans = _all_healthy()
        for var in ("CLOUDINARY_CLOUD_NAME", "CLOUDINARY_API_KEY", "CLOUDINARY_API_SECRET"):
            mans[C.SERVICE_WORKER]["presence"][var] = M.ABSENT
            mans[C.SERVICE_BEAT]["presence"][var] = M.ABSENT
        r = E.evaluate(mans)
        self.assertEqual(r["status"], E.CRITICAL)
        self.assertEqual(set(r["affected_services"]), {"Background Worker", "Scheduler"})
        # Durable-media capability named in customer language, no jargon leak.
        caps = " ".join(r["affected_capabilities"]).lower()
        self.assertIn("media", caps)
        # Inconsistency finding present (web has it, worker/beat don't).
        self.assertTrue(any(f["code"] == "inconsistent_across_services" for f in r["findings"]))

    def test_recovery_after_config_restored(self):
        mans = _all_healthy()
        for var in ("CLOUDINARY_CLOUD_NAME", "CLOUDINARY_API_KEY", "CLOUDINARY_API_SECRET"):
            mans[C.SERVICE_WORKER]["presence"][var] = M.ABSENT
        self.assertEqual(E.evaluate(mans)["status"], E.CRITICAL)
        # Config becomes available → healthy again.
        for var in ("CLOUDINARY_CLOUD_NAME", "CLOUDINARY_API_KEY", "CLOUDINARY_API_SECRET"):
            mans[C.SERVICE_WORKER]["presence"][var] = M.PRESENT
        self.assertEqual(E.evaluate(mans)["status"], E.HEALTHY)


class SecretSafetyTest(SimpleTestCase):
    def test_manifest_never_contains_values_only_presence_tokens(self):
        import os
        os.environ["SECRET_KEY"] = "super-secret-should-never-appear"
        try:
            m = M.build_local_manifest("web")
            blob = str(m)
            self.assertNotIn("super-secret-should-never-appear", blob)
            # Every presence value is one of the three safe tokens.
            self.assertTrue(set(m["presence"].values()) <= {M.PRESENT, M.EMPTY, M.ABSENT})
        finally:
            os.environ.pop("SECRET_KEY", None)

    def test_findings_carry_no_values(self):
        mans = _all_healthy()
        mans[C.SERVICE_WORKER]["presence"]["CLOUDINARY_API_SECRET"] = M.ABSENT
        r = E.evaluate(mans)
        # Findings reference the NAME + presence, never a value field.
        for f in r["findings"]:
            self.assertNotIn("value", f)


class ContractIntegrityTest(SimpleTestCase):
    def test_contract_names_unique_and_well_formed(self):
        names = [v.name for v in C.CONTRACT]
        self.assertEqual(len(names), len(set(names)), "duplicate variable in contract")
        for v in C.CONTRACT:
            self.assertIn(v.severity, (C.SEV_CRITICAL, C.SEV_DEGRADED, C.SEV_ADVISORY))
            self.assertTrue(v.required_services, f"{v.name} has no required services")
            self.assertTrue(v.remediation, f"{v.name} missing remediation")

    def test_hardcoded_settings_not_in_contract(self):
        # ALLOWED_HOSTS / CSRF_TRUSTED_ORIGINS are hardcoded, not env vars.
        names = C.contract_variable_names()
        self.assertNotIn("ALLOWED_HOSTS", names)
        self.assertNotIn("CSRF_TRUSTED_ORIGINS", names)
