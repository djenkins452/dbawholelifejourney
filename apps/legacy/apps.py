from django.apps import AppConfig


class LegacyConfig(AppConfig):
    """
    Legacy — the Personal Legacy Operating System.

    A PRESERVATION-class WLJ domain (see docs/WLJ_LEGACY_DOMAIN_ARCHITECTURE.md).
    Legacy is built as a fully standalone product with NO assistant (Beth)
    integration; the assistant becomes a Legacy consumer only in a later phase.
    """

    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.legacy"
    verbose_name = "Legacy"

    def ready(self):
        # Register the Layer-1 DomainTruth provider so get_domain_truth("legacy") resolves.
        # Import is best-effort: never block app startup on it.
        try:
            from apps.legacy.services import legacy_domain_truth  # noqa: F401
        except Exception:  # pragma: no cover - defensive; truth is non-critical to boot
            import logging
            logging.getLogger(__name__).warning(
                "legacy: failed to register DomainTruth provider", exc_info=True
            )
