from django.apps import AppConfig


class AiConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'apps.ai'
    verbose_name = 'AI Services'

    def ready(self):
        """Import signal handlers when app is ready."""
        from . import signals  # noqa: F401
        self._log_cos_model_alignment()

    @staticmethod
    def _log_cos_model_alignment():
        """One-line startup visibility in production deploy logs: the resolved
        conversational model for BOTH CoS paths. After aligning the General lane to
        COS_MODEL, the General lane and Tool loop resolve identically — the model
        divergence that made 'Give me John 3:16' work but 'What is Metformin used
        for?' fail. Best-effort; never blocks boot."""
        try:
            import logging
            from django.conf import settings
            cos = getattr(settings, "COS_MODEL", None)
            openai_m = getattr(settings, "OPENAI_MODEL", None)
            resolved = cos or openai_m  # both paths now do `COS_MODEL or self.model`
            logging.getLogger("apps.ai").info(
                "COS_MODEL_ALIGNMENT COS_MODEL=%s OPENAI_MODEL=%s "
                "general_lane_model=%s tool_loop_model=%s aligned=%s",
                cos, openai_m, resolved, resolved, True,
            )
        except Exception:
            pass
