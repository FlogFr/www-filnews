"""`runserver` that compiles SCSS on start and whenever a .scss file changes."""

import threading
import time

from django.contrib.staticfiles.management.commands.runserver import (
    Command as StaticfilesRunserver,
)
from sass import CompileError

from filnews.assets import SCSS_DIR, compile_scss

POLL_SECONDS = 1.0


def _scss_signature() -> dict[str, int]:
    return {str(p): p.stat().st_mtime_ns for p in SCSS_DIR.rglob("*.scss")}


class Command(StaticfilesRunserver):
    help = "Run the development server (serves static files and compiles SCSS)."

    def inner_run(self, *args, **options):
        # Static files are served even with DEBUG off: this server is local only.
        options["insecure_serving"] = True
        self._compile()
        threading.Thread(target=self._watch_scss, daemon=True).start()
        super().inner_run(*args, **options)

    def _compile(self) -> None:
        try:
            compile_scss()
        except CompileError as exc:
            self.stderr.write(f"SCSS error:\n{exc}")

    def _watch_scss(self) -> None:
        signature = _scss_signature()
        while True:
            time.sleep(POLL_SECONDS)
            current = _scss_signature()
            if current != signature:
                signature = current
                self._compile()
                self.stdout.write("SCSS recompiled.")
