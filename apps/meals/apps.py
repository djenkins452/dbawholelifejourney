from django.apps import AppConfig


class MealsConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.meals"
    verbose_name = "Meal Intelligence"

    def ready(self):
        pass
