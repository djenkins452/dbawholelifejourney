from django.apps import AppConfig


class MealsConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.meals"
    verbose_name = "Meal Intelligence"

    def ready(self):
        # Wire Recipe write-boundary enrichment (Foundation 2).
        from apps.meals import signals  # noqa: F401
