"""Offline behavior checks for the optional document OCR module."""

import json
import importlib.util
import os
import sys
import tempfile
import types
import unittest
from pathlib import Path
from unittest.mock import patch

try:
    from PIL import Image
except ImportError:
    Image = None

from src import document_ocr


class FakeTesseract:
    class Output:
        DICT = "dict"

    def __init__(self):
        self.calls = 0
        self.pytesseract = self
        self.tesseract_cmd = "tesseract"

    def image_to_string(self, image, *, config, lang):
        raise AssertionError("OCR should run only once per page")

    def image_to_data(self, image, *, config, lang, output_type):
        self.calls += 1
        return {
            "text": ["", "Page", str(self.calls), "revenue", "123"],
            "conf": ["-1", "80.5", "99", "bad", "89.75"],
            "block_num": [1, 1, 1, 1, 1],
            "par_num": [1, 1, 1, 1, 1],
            "line_num": [1, 1, 1, 1, 1],
            "left": [0, 10, 55, 70, 150],
            "width": [0, 40, 10, 75, 30],
        }

    def get_tesseract_version(self):
        return "fake-1"


@unittest.skipUnless(Image is not None, "optional Pillow dependency is not installed")
class DocumentOCRTests(unittest.TestCase):
    def _hybrid(self, bounds, **options):
        header = "Schedule of mortgage loans and property collateral as of year end."
        class TextPage:
            def get_text_bounded(self): return header
            def close(self): pass
        class Obj:
            def get_bounds(self): return bounds
        class Bitmap:
            def to_pil(self): return Image.new("RGB", (100, 100), "white")
            def close(self): pass
        class Page:
            def get_textpage(self): return TextPage()
            def get_size(self): return (100, 100)
            def get_objects(self, filter): return iter([Obj()])
            def render(self, **kwargs): return Bitmap()
            def close(self): pass
        class PDF:
            def __init__(self, source): pass
            def __len__(self): return 1
            def __getitem__(self, index): return Page()
            def close(self): pass
        fake = FakeTesseract()
        module = types.SimpleNamespace(PdfDocument=PDF, raw=types.SimpleNamespace(FPDF_PAGEOBJ_IMAGE=3),
                                       PYPDFIUM_INFO="wrapper-1", PDFIUM_INFO="renderer-2")
        with tempfile.TemporaryDirectory() as tmp:
            source = Path(tmp) / "hybrid.pdf"
            source.write_bytes(b"fake")
            with patch.dict(sys.modules, {"pypdfium2": module}), patch.object(document_ocr, "_load_tesseract", return_value=fake):
                result = document_ocr.extract_document(source, **options)
        return result, fake

    def test_large_image_table_under_native_header_is_ocred(self):
        result, fake = self._hybrid((0, 0, 100, 80))
        self.assertEqual(fake.calls, 1)
        self.assertIn("Schedule of mortgage", result.text)
        self.assertIn("revenue", result.text)
        self.assertIn("native_and_ocr_text_overlap_possible", result.pages[0].quality_flags)
        self.assertIn("substantial_image_coverage", result.pages[0].quality_flags)
        self.assertIn("unverified_table_or_reading_order", result.pages[0].quality_flags)
        self.assertEqual(result.settings["engine_versions"]["pdfium"], "renderer-2")
        self.assertEqual(result.pages[0].words[0]["left"], 10)
        self.assertEqual(result.pages[0].words[0]["confidence"], 80.5)

    def test_small_logo_uses_native_text(self):
        result, fake = self._hybrid((0, 0, 10, 10))
        self.assertEqual(fake.calls, 0)
        self.assertEqual(result.pages[0].method, "native_pdf_text")

    def test_force_ocr_and_segmentation_override(self):
        result, fake = self._hybrid((0, 0, 10, 10), force_ocr=True, psm=11)
        self.assertEqual(fake.calls, 1)
        self.assertIn("--psm 11", result.settings["tesseract_config"])
        self.assertTrue(result.settings["force_ocr"])
        self.assertEqual(result.settings["extraction_revision"], document_ocr.EXTRACTION_REVISION)

    def test_low_confidence_and_empty_ocr_require_review_and_close_images(self):
        class LowTesseract(FakeTesseract):
            def image_to_data(self, image, **kwargs):
                self.prepared = image
                return {"text": ["loan"], "conf": ["22"], "left": [1], "top": [2],
                        "width": [3], "height": [4]}
        with tempfile.TemporaryDirectory() as tmp:
            source = Path(tmp) / "scan.png"
            Image.new("RGB", (20, 20), "white").save(source)
            fake = LowTesseract()
            with patch.object(document_ocr, "_load_tesseract", return_value=fake):
                result = document_ocr.extract_document(source)
            self.assertIn("low_ocr_confidence", result.pages[0].quality_flags)
            self.assertEqual(result.pages[0].words[0]["top"], 2)
            self.assertEqual(result.pages[0].words[0]["height"], 4)
            with self.assertRaises(ValueError):
                fake.prepared.getpixel((0, 0))
            with patch.object(document_ocr, "_load_tesseract", return_value=FakeTesseract()) as loader:
                loader.return_value.image_to_data = lambda *args, **kwargs: {"text": [], "conf": []}
                empty = document_ocr.extract_document(source)
            self.assertIn("empty_text", empty.pages[0].quality_flags)

    def test_nonempty_ocr_without_confidence_requires_review(self):
        with tempfile.TemporaryDirectory() as tmp:
            source = Path(tmp) / "scan.png"
            Image.new("RGB", (20, 20), "white").save(source)
            fake = FakeTesseract()
            fake.image_to_data = lambda *args, **kwargs: {"text": ["Loan"], "conf": ["bad"]}
            with patch.object(document_ocr, "_load_tesseract", return_value=fake):
                result = document_ocr.extract_document(source)
            self.assertIn("ocr_confidence_unavailable", result.pages[0].quality_flags)

    def test_mixed_pdf_uses_native_text_then_ocrs_only_scanned_page(self):
        rendered = []

        class TextPage:
            def __init__(self, text):
                self.text = text

            def get_text_bounded(self):
                return self.text

            def close(self):
                pass

        class Bitmap:
            def to_pil(self):
                return Image.new("RGB", (20, 20), "white")

            def close(self):
                pass

        class Page:
            def __init__(self, number):
                self.number = number

            def get_textpage(self):
                return TextPage("Cash provided by operating activities was $123 million. " if self.number == 0 else "")

            def get_size(self):
                return (612, 792)

            def render(self, *, scale):
                rendered.append(self.number)
                return Bitmap()

            def close(self):
                pass

        class PDF:
            def __init__(self, source):
                pass

            def __len__(self):
                return 2

            def __getitem__(self, number):
                return Page(number)

            def close(self):
                pass

        with tempfile.TemporaryDirectory() as tmp:
            source = Path(tmp) / "filing.pdf"
            source.write_bytes(b"fake PDF")
            fake = FakeTesseract()
            with patch.dict(sys.modules, {"pypdfium2": types.SimpleNamespace(PdfDocument=PDF)}), \
                 patch.object(document_ocr, "_load_tesseract", return_value=fake):
                result = document_ocr.extract_document(source)
        self.assertEqual(fake.calls, 1)
        self.assertEqual(rendered, [1])
        self.assertEqual([page.method for page in result.pages], ["native_pdf_text", "tesseract_ocr"])
        self.assertIn("Cash provided", result.pages[0].text)

    def test_native_pdf_does_not_load_tesseract(self):
        class TextPage:
            def get_text_bounded(self):
                return "A sufficiently long digital text page with financial details."

            def close(self):
                pass

        class Page:
            def get_textpage(self):
                return TextPage()

            def close(self):
                pass

        class PDF:
            def __init__(self, source):
                pass

            def __len__(self):
                return 1

            def __getitem__(self, number):
                return Page()

            def close(self):
                pass

        with tempfile.TemporaryDirectory() as tmp:
            source = Path(tmp) / "digital.pdf"
            source.write_bytes(b"fake PDF")
            with patch.dict(sys.modules, {"pypdfium2": types.SimpleNamespace(PdfDocument=PDF)}), \
                 patch.object(document_ocr, "_load_tesseract", side_effect=AssertionError("OCR invoked")):
                result = document_ocr.extract_document(source)
        self.assertEqual(result.engine, "pdfium")
        self.assertEqual(result.pages[0].method, "native_pdf_text")

    def test_multipage_tiff_preserves_pages_and_source_hash(self):
        with tempfile.TemporaryDirectory() as tmp:
            source = Path(tmp) / "filing.tiff"
            Image.new("RGB", (24, 24), "white").save(
                source, save_all=True, append_images=[Image.new("RGB", (24, 24), "white")]
            )
            fake = FakeTesseract()
            with patch.object(document_ocr, "_load_tesseract", return_value=fake):
                result = document_ocr.extract_document(source, preprocess=False)
            self.assertEqual(result.page_count, 2)
            self.assertEqual([page.text for page in result.pages],
                             ["Page 1 revenue 123\n", "Page 2 revenue 123\n"])
            self.assertIn("\f", result.text)
            self.assertAlmostEqual(result.pages[0].confidence, 89.75)
            self.assertEqual(fake.calls, 2)
            self.assertEqual(len(result.sha256), 64)
            self.assertEqual(result.source_path, str(source.resolve()))

    def test_json_output_contains_text_and_provenance(self):
        with tempfile.TemporaryDirectory() as tmp:
            source = Path(tmp) / "scan.png"
            output = Path(tmp) / "result.json"
            Image.new("RGB", (20, 20), "white").save(source)
            with patch.object(document_ocr, "_load_tesseract", return_value=FakeTesseract()):
                result = document_ocr.extract_document(source)
            document_ocr.write_json(result, output)
            saved = json.loads(output.read_text(encoding="utf-8"))
            self.assertEqual(saved["page_count"], 1)
            self.assertEqual(saved["pages"][0]["text"], "Page 1 revenue 123\n")
            self.assertEqual(saved["sha256"], result.sha256)
            self.assertEqual(saved["settings"]["language"], "eng")
            self.assertEqual(saved["settings"]["preprocess"], True)
            self.assertEqual(saved["engine_version"], "fake-1")

    def test_unsupported_file_fails_before_ocr(self):
        with tempfile.TemporaryDirectory() as tmp:
            source = Path(tmp) / "notes.txt"
            source.write_text("hello", encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "Unsupported document type"):
                document_ocr.extract_document(source)

    @unittest.skipUnless(importlib.util.find_spec("pypdfium2"),
                         "optional pypdfium2 dependency is not installed")
    def test_scanned_pdf_renders_each_page(self):
        with tempfile.TemporaryDirectory() as tmp:
            source = Path(tmp) / "filing.pdf"
            Image.new("RGB", (24, 24), "white").save(
                source, save_all=True, append_images=[Image.new("RGB", (24, 24), "white")]
            )
            fake = FakeTesseract()
            with patch.object(document_ocr, "_load_tesseract", return_value=fake):
                result = document_ocr.extract_document(source)
            self.assertEqual(result.page_count, 2)
            self.assertEqual(fake.calls, 2)

    def test_missing_tesseract_has_actionable_error(self):
        with tempfile.TemporaryDirectory() as tmp:
            source = Path(tmp) / "scan.png"
            Image.new("RGB", (20, 20), "white").save(source)
            with patch.object(document_ocr, "_load_tesseract", side_effect=RuntimeError("Install Tesseract OCR")):
                with self.assertRaisesRegex(RuntimeError, "Install Tesseract OCR"):
                    document_ocr.extract_document(source)

    def test_finds_tesseract_in_windows_user_install(self):
        with tempfile.TemporaryDirectory() as tmp:
            executable = Path(tmp) / "Programs" / "Tesseract-OCR" / "tesseract.exe"
            executable.parent.mkdir(parents=True)
            executable.touch()
            with patch.dict(os.environ, {"LOCALAPPDATA": tmp}):
                self.assertEqual(document_ocr._find_tesseract(), str(executable))

    def test_pdf_render_scale_is_capped_before_bitmap_allocation(self):
        scales = []

        class Bitmap:
            def to_pil(self):
                return Image.new("RGB", (10, 10), "white")

            def close(self):
                pass

        class Page:
            def get_size(self):
                return (2000, 1000)

            def render(self, *, scale):
                scales.append(scale)
                return Bitmap()

            def close(self):
                pass

        class PDF:
            def __init__(self, source):
                pass

            def __len__(self):
                return 1

            def __getitem__(self, number):
                return Page()

            def close(self):
                pass

        with patch.dict(sys.modules, {"pypdfium2": types.SimpleNamespace(PdfDocument=PDF)}):
            self.assertEqual(len(list(document_ocr._page_images(Path("scan.pdf"), 2000))), 1)
        self.assertEqual(scales, [2.0])

    def test_text_preserves_large_gaps_between_table_columns(self):
        data = {
            "text": ["Revenue", "12345"],
            "block_num": [1, 1],
            "par_num": [1, 1],
            "line_num": [1, 1],
            "left": [10, 300],
            "width": [100, 80],
        }
        self.assertRegex(document_ocr._text_from_data(data), r"Revenue {3,}12345")


if __name__ == "__main__":
    unittest.main()
