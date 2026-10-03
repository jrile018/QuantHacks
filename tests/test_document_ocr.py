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
