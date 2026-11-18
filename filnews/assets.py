"""Front-end asset pipeline: SCSS -> CSS (libsass, no Node.js needed)."""

from pathlib import Path

import sass
from django.conf import settings

SCSS_DIR = settings.PROJECT_DIR / "static" / "scss"
CSS_DIR = settings.PROJECT_DIR / "static" / "css"
# Entry points (partials start with "_"): the site stylesheet, and the one
# js/sender.js injects into Sender's form iframes.
ENTRY_POINTS = {
    "main.scss": "main.css",
    "sender-frame.scss": "sender-frame.css",
}


def compile_scss(output_dir: Path = CSS_DIR, compressed: bool = False) -> list[Path]:
    output_dir.mkdir(parents=True, exist_ok=True)
    outputs = []
    for source, target in ENTRY_POINTS.items():
        css = sass.compile(
            filename=str(SCSS_DIR / source),
            output_style="compressed" if compressed else "expanded",
        )
        output = output_dir / target
        output.write_text(css, encoding="utf-8")
        outputs.append(output)
    return outputs
