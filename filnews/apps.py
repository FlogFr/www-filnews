from django.apps import AppConfig


class FilNewsConfig(AppConfig):
    name = "filnews"
    verbose_name = "FilNews"

    def ready(self) -> None:
        # Load the JSON database once at bootstrap.
        from .store import get_store

        get_store()
