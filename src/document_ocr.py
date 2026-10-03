"""Optional OCR for scanned financial documents.

The OCR layer returns text and provenance only. Financial-statement extraction
and validation belong in a separate parser that consumes this output.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import statistics
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Iterator


IMAGE_SUFFIXES = {".tif", ".tiff", ".png", ".jpg", ".jpeg", ".bmp", ".webp"}
SUPPORTED_SUFFIXES = IMAGE_SUFFIXES | {".pdf"}
TESSERACT_CONFIG = "--oem 3 --psm 6 -c preserve_interword_spaces=1"
MAX_OCR_DIMENSION = 4000


@dataclass(frozen=True)
class OCRPage:
    number: int
    text: str
    confidence: float | None


@dataclass(frozen=True)
class OCRDocument:
    source_path: str
    sha256: str
    engine: str
    engine_version: str
    settings: dict
    page_count: int
    text: str
    pages: list[OCRPage]


def _load_tesseract():
    try:
        import pytesseract
    except ImportError as exc:
        raise RuntimeError(
            "Install OCR Python dependencies with: pip install -r requirements-ocr.txt"
        ) from exc
    return pytesseract


def _pillow():
    try:
        from PIL import Image, ImageOps
    except ImportError as exc:
        raise RuntimeError(
            "Install OCR Python dependencies with: pip install -r requirements-ocr.txt"
        ) from exc
    return Image, ImageOps


def _page_images(source: Path, dpi: int) -> Iterator:
    """Yield independent RGB pages from an image or rasterized PDF."""
    Image, _ = _pillow()
    if source.suffix.lower() == ".pdf":
        try:
            import pypdfium2 as pdfium
        except ImportError as exc:
            raise RuntimeError(
                "PDF OCR requires pypdfium2: pip install -r requirements-ocr.txt"
            ) from exc
        pdf = pdfium.PdfDocument(source)
        try:
            for number in range(len(pdf)):
                page = pdf[number]
                try:
                    page_size = page.get_size()
                    if min(page_size) <= 0:
                        raise ValueError(f"PDF page {number + 1} has invalid dimensions")
                    scale = min(dpi / 72, MAX_OCR_DIMENSION / max(page_size))
                    bitmap = page.render(scale=scale)
                    try:
                        yield bitmap.to_pil().convert("RGB").copy()
                    finally:
                        bitmap.close()
                finally:
                    page.close()
        finally:
            pdf.close()
        return

    with Image.open(source) as image:
        for number in range(getattr(image, "n_frames", 1)):
            image.seek(number)
            yield image.convert("RGB").copy()


def _prepare_image(image, preprocess: bool):
    Image, ImageOps = _pillow()
    if max(image.size) > MAX_OCR_DIMENSION:
        image.thumbnail((MAX_OCR_DIMENSION, MAX_OCR_DIMENSION), Image.Resampling.LANCZOS)
    if preprocess:
        image = ImageOps.autocontrast(ImageOps.grayscale(image))
    return image


def _confidence(data: dict) -> float | None:
    values = []
    for raw in data.get("conf", []):
        try:
            value = float(raw)
        except (TypeError, ValueError):
            continue
        if 0 <= value <= 100:
            values.append(value)
    return round(sum(values) / len(values), 2) if values else None


def _text_from_data(data: dict) -> str:
    """Rebuild plain-text lines from Tesseract's word-level result."""
    def render_line(entries: list[tuple[str, int | None, int | None]]) -> str:
        widths = [width / len(word) for word, _, width in entries if width and word]
        char_width = statistics.median(widths) if widths else None
        rendered = entries[0][0]
        previous_left, previous_width = entries[0][1:]
        for word, left, width in entries[1:]:
            spaces = 1
            if (char_width and left is not None and previous_left is not None
                    and previous_width is not None):
                gap = max(0, left - previous_left - previous_width)
                spaces = max(1, min(80, round(gap / char_width)))
            rendered += " " * spaces + word
            previous_left, previous_width = left, width
        return rendered

    lines = []
    current_key = None
    entries = []
    lefts, widths = data.get("left", []), data.get("width", [])
    for index, raw in enumerate(data.get("text", [])):
        word = str(raw).strip() if raw is not None else ""
        if not word:
            continue
        key = tuple(data.get(name, [0] * len(data["text"]))[index]
                    for name in ("block_num", "par_num", "line_num"))
        if current_key is not None and key != current_key:
            lines.append(render_line(entries))
            entries = []
        current_key = key
        left = lefts[index] if index < len(lefts) else None
        width = widths[index] if index < len(widths) else None
        entries.append((word, left, width))
    if entries:
        lines.append(render_line(entries))
    return "\n".join(lines) + ("\n" if lines else "")


def _sha256(source: Path) -> str:
    digest = hashlib.sha256()
    with source.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _find_tesseract() -> str | None:
    """Find a Windows user/system install or an executable on PATH."""
    roots = (
        (os.environ.get("LOCALAPPDATA"), ("Programs", "Tesseract-OCR")),
        (os.environ.get("ProgramFiles"), ("Tesseract-OCR",)),
        (os.environ.get("ProgramFiles(x86)"), ("Tesseract-OCR",)),
    )
    for root, parts in roots:
        if not root:
            continue
        candidate = Path(root).joinpath(*parts, "tesseract.exe")
        try:
            if candidate.is_file():
                return str(candidate)
        except PermissionError:
            continue
    return shutil.which("tesseract")


def extract_document(
    path: str | Path,
    *,
    preprocess: bool = True,
    dpi: int = 300,
    lang: str = "eng",
    tesseract_cmd: str | None = None,
) -> OCRDocument:
    """Read all pages of a scan and return raw OCR text with provenance.

    Confidence is Tesseract's mean word confidence on a 0–100 scale, or None
    when no word confidence is available. It is not a field-accuracy score.
    """
    source = Path(path).resolve()
    if not source.is_file():
        raise FileNotFoundError(f"Document does not exist: {source}")
    if source.suffix.lower() not in SUPPORTED_SUFFIXES:
        raise ValueError(f"Unsupported document type: {source.suffix or '(none)'}")
    if dpi <= 0:
        raise ValueError("dpi must be positive")

    pytesseract = _load_tesseract()
    command = tesseract_cmd or _find_tesseract()
    if command:
        pytesseract.pytesseract.tesseract_cmd = command

    pages = []
    source_hash = _sha256(source)
    try:
        for number, image in enumerate(_page_images(source, dpi), start=1):
            prepared = _prepare_image(image, preprocess)
            data = pytesseract.image_to_data(
                prepared, config=TESSERACT_CONFIG, lang=lang,
                output_type=pytesseract.Output.DICT,
            )
            pages.append(OCRPage(number, _text_from_data(data), _confidence(data)))
    except Exception as exc:
        if exc.__class__.__name__ == "TesseractNotFoundError":
            raise RuntimeError(
                "Install Tesseract OCR and add tesseract.exe to PATH, or pass --tesseract-cmd"
            ) from exc
        raise

    if not pages:
        raise ValueError(f"Document contains no pages: {source}")
    if _sha256(source) != source_hash:
        raise RuntimeError(f"Document changed during OCR: {source}")
    return OCRDocument(
        source_path=str(source),
        sha256=source_hash,
        engine="tesseract",
        engine_version=str(pytesseract.get_tesseract_version()),
        settings={"language": lang, "dpi": dpi, "preprocess": preprocess,
                  "tesseract_config": TESSERACT_CONFIG},
        page_count=len(pages),
        text="\n\f\n".join(page.text for page in pages),
        pages=pages,
    )


def write_json(result: OCRDocument, path: str | Path) -> Path:
    """Save OCR output as UTF-8 JSON and return its location."""
    output = Path(path)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(asdict(result), indent=2, ensure_ascii=False) + "\n",
                      encoding="utf-8")
    return output


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="OCR a scanned PDF or image into JSON")
    parser.add_argument("input", type=Path, help="PDF, TIFF, PNG, JPEG, BMP, or WebP file")
    parser.add_argument("--output", type=Path, help="output JSON path")
    parser.add_argument("--no-preprocess", action="store_true", help="skip grayscale and contrast")
    parser.add_argument("--dpi", type=int, default=300, help="PDF rendering resolution")
    parser.add_argument("--lang", default="eng", help="installed Tesseract language code")
    parser.add_argument("--tesseract-cmd", help="full path to tesseract.exe when absent from PATH")
    args = parser.parse_args(argv)
    output = args.output or Path("data/processed/ocr") / f"{args.input.name}.json"
    result = extract_document(args.input, preprocess=not args.no_preprocess,
                              dpi=args.dpi, lang=args.lang,
                              tesseract_cmd=args.tesseract_cmd)
    write_json(result, output)
    print(f"Saved {result.page_count} page(s) to {output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
