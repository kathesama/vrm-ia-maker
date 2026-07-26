from __future__ import annotations

import argparse
import base64
import json
import re
from io import BytesIO
from pathlib import Path

from PIL import Image

DEFAULT_PACKAGE = (
    Path(__file__).resolve().parents[1]
    / "packages"
    / "juana-pixel-runtime"
    / "v2"
)
THUMBNAIL_SIZE = (384, 576)
THUMBNAIL_PATTERN = re.compile(
    r"      const thumbnails = \{.*?\}\n      const scenarios =",
    flags=re.DOTALL,
)


def _thumbnail_data_url(path: Path) -> str:
    with Image.open(path) as source:
        thumbnail = source.convert("RGBA")
        thumbnail.thumbnail(THUMBNAIL_SIZE, Image.Resampling.NEAREST)
        encoded = BytesIO()
        thumbnail.save(encoded, format="WEBP", lossless=True, method=6)
    payload = base64.b64encode(encoded.getvalue()).decode("ascii")
    return f"data:image/webp;base64,{payload}"


def build_gallery(package: Path) -> Path:
    runtime = package / "runtime"
    gallery = package / "gallery.html"
    seal = json.loads((runtime / "bundle-seal.json").read_text(encoding="utf-8"))
    png_paths = sorted(
        relative_path
        for relative_path in seal["files"]
        if relative_path.endswith(".png")
    )
    thumbnails = {
        f"runtime/{relative_path}": _thumbnail_data_url(runtime / relative_path)
        for relative_path in png_paths
    }
    payload = json.dumps(thumbnails, indent=2, sort_keys=True)
    indented_payload = payload.replace("\n", "\n      ")
    declaration = (
        f"      const thumbnails = {indented_payload}\n      const scenarios ="
    )

    html = gallery.read_text(encoding="utf-8")
    if THUMBNAIL_PATTERN.search(html):
        html = THUMBNAIL_PATTERN.sub(declaration, html, count=1)
    else:
        marker = "      const scenarios ="
        if marker not in html:
            raise ValueError(f"Gallery marker not found in {gallery}")
        html = html.replace(marker, declaration, 1)

    source_assignment = "          image.src = source"
    embedded_assignment = "          image.src = thumbnails[source]"
    if embedded_assignment not in html:
        if source_assignment not in html:
            raise ValueError(f"Image source assignment not found in {gallery}")
        html = html.replace(source_assignment, embedded_assignment, 1)

    temporary = gallery.with_suffix(".html.tmp")
    temporary.write_text(html, encoding="utf-8", newline="\n")
    temporary.replace(gallery)
    return gallery


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Embed self-contained WebP thumbnails in the pixel runtime gallery."
    )
    parser.add_argument(
        "--package",
        type=Path,
        default=DEFAULT_PACKAGE,
        help="Pixel runtime package directory containing gallery.html and runtime/.",
    )
    args = parser.parse_args()
    print(build_gallery(args.package.resolve()))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
