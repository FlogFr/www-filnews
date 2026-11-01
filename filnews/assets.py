"""Front-end asset pipeline: SCSS -> CSS (libsass, no Node.js needed)."""

from pathlib import Path

import sass
from django.conf import settings

SCSS_DIR = settings.PROJECT_DIR / "static" / "scss"
CSS_FILE = settings.PROJECT_DIR / "static" / "css" / "main.css"


def compile_scss(output: Path = CSS_FILE, compressed: bool = False) -> Path:
    css = sass.compile(
        filename=str(SCSS_DIR / "main.scss"),
        output_style="compressed" if compressed else "expanded",
    )
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(css, encoding="utf-8")
    return output
