"""Write results to JSON / CSV / XLSX safely."""

from __future__ import annotations

import csv
import io
import json
import time
from collections.abc import Callable
from pathlib import Path

import requests
from openpyxl import Workbook
from openpyxl.drawing.image import Image as XLImage
from PIL import Image as PILImage

from .security import MAX_IMAGE_BYTES, SecurityError, safe_filename, safe_get, sanitize_cell

Log = Callable[[str], None]
COLUMNS = ("name", "price", "url", "image_url")
THUMB = 100
PILImage.MAX_IMAGE_PIXELS = 25_000_000  # decompression-bomb guard (Pillow raises above 2x this)


def output_path(out_dir: Path, site: str, keyword: str, ext: str) -> Path:
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    stamp = time.strftime("%Y%m%d_%H%M%S")
    path = (out_dir / f"{safe_filename(site)}_{safe_filename(keyword)}_{stamp}.{ext}").resolve()
    if path.parent != out_dir.resolve():
        raise SecurityError("Output path escapes the output directory.")
    return path


def fetch_thumbnail(url: str, *, allow_private: bool = False) -> bytes:
    """Download an image safely and re-encode it as a small PNG (strips metadata,
    rejects anything Pillow cannot decode)."""
    body, _ = safe_get(url, max_bytes=MAX_IMAGE_BYTES, allow_private=allow_private, accept_prefix="image/")
    img = PILImage.open(io.BytesIO(body))
    img.verify()
    img = PILImage.open(io.BytesIO(body)).convert("RGB")
    img.thumbnail((THUMB * 2, THUMB * 2))
    out = io.BytesIO()
    img.save(out, format="PNG")
    return out.getvalue()


def export_json(rows: list[dict], path: Path) -> None:
    path.write_text(json.dumps(rows, indent=2, ensure_ascii=False), encoding="utf-8")


def export_csv(rows: list[dict], path: Path) -> None:
    with path.open("w", newline="", encoding="utf-8-sig") as fh:
        writer = csv.writer(fh)
        writer.writerow(COLUMNS)
        for row in rows:
            writer.writerow([sanitize_cell(row.get(c, "N/A")) for c in COLUMNS])


def export_xlsx(
    rows: list[dict],
    path: Path,
    *,
    images: bool = True,
    max_images: int = 50,
    allow_private: bool = False,
    log: Log = print,
) -> None:
    wb = Workbook()
    ws = wb.active
    ws.title = "Products"
    ws.append(["Name", "Price", "URL", "Image"])
    ws.column_dimensions["A"].width = 50
    ws.column_dimensions["B"].width = 16
    ws.column_dimensions["C"].width = 60
    ws.column_dimensions["D"].width = 18
    embedded = 0
    for r, row in enumerate(rows, start=2):
        for c, key in enumerate(("name", "price", "url"), start=1):
            ws.cell(row=r, column=c, value=sanitize_cell(row.get(key, "N/A")))
        img_url = row.get("image_url")
        if images and embedded < max_images and isinstance(img_url, str) and img_url.startswith("http"):
            try:
                png = fetch_thumbnail(img_url, allow_private=allow_private)
                xl = XLImage(io.BytesIO(png))
                xl.width = xl.height = THUMB
                ws.add_image(xl, f"D{r}")
                ws.row_dimensions[r].height = 80
                embedded += 1
            except (
                SecurityError,
                requests.RequestException,
                OSError,
                ValueError,
                SyntaxError,
                PILImage.DecompressionBombError,
            ) as exc:  # SyntaxError: Pillow's corrupt-file error
                log(f"Image skipped for row {r}: {exc}")
    wb.save(path)


def export_all(
    rows: list[dict],
    out_dir: Path,
    site: str,
    keyword: str,
    *,
    formats=("json", "csv", "xlsx"),
    images: bool = True,
    max_images: int = 50,
    allow_private: bool = False,
    log: Log = print,
) -> list[Path]:
    written = []
    for fmt in formats:
        path = output_path(out_dir, site, keyword, fmt)
        if fmt == "json":
            export_json(rows, path)
        elif fmt == "csv":
            export_csv(rows, path)
        elif fmt == "xlsx":
            export_xlsx(
                rows, path, images=images, max_images=max_images, allow_private=allow_private, log=log
            )
        else:
            raise ValueError(f"Unknown format '{fmt}'")
        log(f"Saved {path}")
        written.append(path)
    return written
