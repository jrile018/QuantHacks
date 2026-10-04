"""Optional OCR for scanned financial documents.

The OCR layer returns text and provenance only. Financial-statement extraction
and validation belong in a separate parser that consumes this output.
"""

from __future__ import annotations

import argparse
import hashlib
import itertools
import json
import os
import shutil
import statistics
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Iterator


IMAGE_SUFFIXES = {".tif", ".tiff", ".png", ".jpg", ".jpeg", ".bmp", ".webp"}
SUPPORTED_SUFFIXES = IMAGE_SUFFIXES | {".pdf"}
TESSERACT_CONFIG = "--oem 3 --psm 6 -c preserve_interword_spaces=1"
MAX_OCR_DIMENSION = 4000
EXTRACTION_REVISION = "2"


@dataclass(frozen=True)
class OCRPage:
    number: int
    text: str
    confidence: float | None
    method: str = "tesseract_ocr"
    quality_flags: list[str] = field(default_factory=list)
    words: list[dict] = field(default_factory=list)
    native_text: str | None = None


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


def _native_pdf_texts(source: Path, *, diagnostics: list | None = None, force_ocr: bool = False) -> list[str | None]:
    """Return useful embedded text, or None for pages requiring OCR."""
    try:
        import pypdfium2 as pdfium
    except ImportError as exc:
        raise RuntimeError("PDF extraction requires pypdfium2: pip install -r requirements-ocr.txt") from exc
    pdf = pdfium.PdfDocument(source)
    texts = []
    try:
        for index in range(len(pdf)):
            page = pdf[index]
            try:
                textpage = page.get_textpage()
                try:
                    value = textpage.get_text_bounded()
                finally:
                    textpage.close()
                alnum = sum(char.isalnum() for char in value)
                coverage = None
                if hasattr(page, "get_objects") and hasattr(page, "get_size"):
                    width, height = page.get_size()
                    if width > 0 and height > 0:
                        areas = []
                        for obj in page.get_objects(filter=[pdfium.raw.FPDF_PAGEOBJ_IMAGE]):
                            left, bottom, right, top = obj.get_bounds()
                            areas.append(max(0, min(width, right) - max(0, left)) *
                                         max(0, min(height, top) - max(0, bottom)))
                        # Conservative diagnostic: overlapping images may overestimate coverage.
                        coverage = min(1.0, sum(areas) / (width * height))
                hybrid = coverage is not None and coverage >= 0.3 and alnum <= 300
                if diagnostics is not None:
                    size = page.get_size() if hasattr(page, "get_size") else None
                    diagnostics.append({"native_text": value, "image_coverage": coverage,
                                        "page_size_points": size, "hybrid": hybrid})
                texts.append(value if alnum >= 40 and not hybrid and not force_ocr else None)
            finally:
                page.close()
    finally:
        pdf.close()
    return texts


def _page_images(source: Path, dpi: int, page_numbers: set[int] | None = None) -> Iterator:
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
                if page_numbers is not None and number + 1 not in page_numbers:
                    continue
                page = pdf[number]
                try:
                    page_size = page.get_size()
                    if min(page_size) <= 0:
                        raise ValueError(f"PDF page {number + 1} has invalid dimensions")
                    scale = min(dpi / 72, MAX_OCR_DIMENSION / max(page_size))
                    bitmap = page.render(scale=scale)
                    try:
                        shared = bitmap.to_pil()
                        converted = None
                        try:
                            converted = shared.convert("RGB")
                            independent = converted.copy()
                        finally:
                            if converted is not None and converted is not shared:
                                converted.close()
                            shared.close()
                        yield independent
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
            converted = image.convert("RGB")
            try:
                independent = converted.copy()
            finally:
                if converted is not image:
                    converted.close()
            yield independent


def _prepare_image(image, preprocess: bool):
    Image, ImageOps = _pillow()
    if max(image.size) > MAX_OCR_DIMENSION:
        image.thumbnail((MAX_OCR_DIMENSION, MAX_OCR_DIMENSION), Image.Resampling.LANCZOS)
    if preprocess:
        gray = ImageOps.grayscale(image)
        try:
            image = ImageOps.autocontrast(gray)
        finally:
            gray.close()
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
    force_ocr: bool = False,
    psm: int = 6,
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

    if psm not in (3, 6, 11):
        raise ValueError("psm must be 3, 6, or 11")
    config = f"--oem 3 --psm {psm} -c preserve_interword_spaces=1"
    source_hash = _sha256(source)
    diagnostics = []
    native_texts = _native_pdf_texts(source, diagnostics=diagnostics, force_ocr=force_ocr) if source.suffix.lower() == ".pdf" else []
    versions = {}
    if native_texts:
        import pypdfium2 as pdfium
        for key, attribute in (("pypdfium2", "PYPDFIUM_INFO"), ("pdfium", "PDFIUM_INFO")):
            value = getattr(pdfium, attribute, None)
            if value is not None:
                versions[key] = str(value)
    renderer_pages = []
    pages: list[OCRPage] = []
    needed = {i for i, value in enumerate(native_texts, 1) if value is None}
    pytesseract = None
    if not native_texts or needed:
        pytesseract = _load_tesseract()
        command = tesseract_cmd or _find_tesseract()
        if command:
            pytesseract.pytesseract.tesseract_cmd = command
    images = iter(())
    try:
        images = iter(_page_images(source, dpi, needed if native_texts else None)) if pytesseract else iter(())
        for number in range(1, len(native_texts) + 1) if native_texts else itertools.count(1):
            if native_texts and native_texts[number - 1] is not None:
                flags = ["native_text_completeness_unverified"]
                coverage = diagnostics[number - 1]["image_coverage"]
                if coverage is not None and coverage >= 0.3:
                    flags.append("substantial_image_coverage")
                pages.append(OCRPage(number, native_texts[number - 1], None, "native_pdf_text",
                                     flags, native_text=native_texts[number - 1]))
                continue
            try:
                image = next(images)
            except StopIteration:
                if native_texts:
                    raise ValueError(f"PDF page {number} could not be rendered")
                break
            prepared = None
            try:
                prepared = _prepare_image(image, preprocess)
                size = diagnostics[number - 1].get("page_size_points") if diagnostics else None
                scale = min(dpi / 72, MAX_OCR_DIMENSION / max(size)) if size and min(size) > 0 else None
                renderer_pages.append({"page": number, "scale": scale, "effective_dpi": scale * 72 if scale else None, "image_width": image.width,
                                       "image_height": image.height,
                                       "ocr_width": prepared.width, "ocr_height": prepared.height})
                data = pytesseract.image_to_data(
                    prepared, config=config, lang=lang,
                    output_type=pytesseract.Output.DICT,
                )
                text = _text_from_data(data)
                confidence = _confidence(data)
                flags = ["unverified_table_or_reading_order"]
                if confidence is None and text.strip():
                    flags.append("ocr_confidence_unavailable")
                if confidence is not None and confidence < 70:
                    flags.append("low_ocr_confidence")
                if not text.strip():
                    flags.append("empty_text")
                native = diagnostics[number - 1]["native_text"] if diagnostics else None
                if diagnostics and (diagnostics[number - 1]["image_coverage"] or 0) >= 0.3:
                    flags.append("substantial_image_coverage")
                if native and native.strip():
                    flags.append("native_and_ocr_text_overlap_possible")
                    text = native.rstrip() + "\n\n" + text
                words = []
                for index, raw in enumerate(data.get("text", [])):
                    if raw is None or not str(raw).strip():
                        continue
                    word = {"text": str(raw).strip()}
                    for key in ("left", "top", "width", "height", "conf"):
                        values = data.get(key, [])
                        value = values[index] if index < len(values) else None
                        if key == "conf":
                            try:
                                value = float(value)
                                if not 0 <= value <= 100: value = None
                            except (TypeError, ValueError):
                                value = None
                        word["confidence" if key == "conf" else key] = value
                    words.append(word)
                pages.append(OCRPage(number, text, confidence, quality_flags=flags,
                                     words=words, native_text=native))
            finally:
                if prepared is not None and prepared is not image:
                    prepared.close()
                image.close()
    except Exception as exc:
        if exc.__class__.__name__ == "TesseractNotFoundError":
            raise RuntimeError(
                "Install Tesseract OCR and add tesseract.exe to PATH, or pass --tesseract-cmd"
            ) from exc
        raise

    finally:
        if pytesseract and hasattr(images, "close"):
            images.close()

    if not pages:
        raise ValueError(f"Document contains no pages: {source}")
    if _sha256(source) != source_hash:
        raise RuntimeError(f"Document changed during OCR: {source}")
    if pytesseract:
        versions["tesseract"] = str(pytesseract.get_tesseract_version())
    return OCRDocument(
        source_path=str(source),
        sha256=source_hash,
        engine="mixed" if native_texts and needed and len(needed) < len(native_texts) else
               "pdfium" if native_texts and not needed else "tesseract",
        engine_version=versions.get("tesseract", versions.get("pdfium", "")),
        settings={"language": lang, "dpi": dpi, "preprocess": preprocess,
                  "tesseract_config": config, "psm": psm, "force_ocr": force_ocr,
                  "extraction_revision": EXTRACTION_REVISION, "engine_versions": versions,
                  "renderer": {"max_dimension": MAX_OCR_DIMENSION, "scale_policy": "min(dpi/72, max_dimension/max(page_size))", "pages": renderer_pages},
                  "pdf_page_diagnostics": diagnostics},
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
    parser.add_argument("--force-ocr", action="store_true", help="OCR pages even when embedded text exists")
    parser.add_argument("--psm", type=int, choices=(3, 6, 11), default=6, help="Tesseract page segmentation mode")
    parser.add_argument("--lang", default="eng", help="installed Tesseract language code")
    parser.add_argument("--tesseract-cmd", help="full path to tesseract.exe when absent from PATH")
    args = parser.parse_args(argv)
    output = args.output or Path("data/processed/ocr") / f"{args.input.name}.json"
    result = extract_document(args.input, preprocess=not args.no_preprocess,
                              dpi=args.dpi, lang=args.lang,
                              tesseract_cmd=args.tesseract_cmd, force_ocr=args.force_ocr, psm=args.psm)
    write_json(result, output)
    print(f"Saved {result.page_count} page(s) to {output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
