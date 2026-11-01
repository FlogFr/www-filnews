"""Thumbnail generation: cover-crop to 16:9 and encode as WebP."""

from __future__ import annotations

import io
from pathlib import Path

from PIL import Image, ImageOps

THUMBNAIL_SIZE = (640, 360)
WEBP_QUALITY = 78


def make_thumbnail(image_bytes: bytes, destination: Path) -> None:
    with Image.open(io.BytesIO(image_bytes)) as image:
        image = ImageOps.exif_transpose(image)
        if image.mode not in ("RGB", "RGBA"):
            image = image.convert("RGBA" if "transparency" in image.info else "RGB")
        thumbnail = ImageOps.fit(image, THUMBNAIL_SIZE, Image.Resampling.LANCZOS)
        destination.parent.mkdir(parents=True, exist_ok=True)
        thumbnail.save(destination, "WEBP", quality=WEBP_QUALITY, method=6)
