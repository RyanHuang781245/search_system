from django.apps import AppConfig


class SearchConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.search"

    def ready(self):
        try:
            from .mongo import ensure_indexes

            ensure_indexes()
        except Exception:
            # Avoid blocking startup when MongoDB is unavailable.
            pass
