import unittest
from src.document_transcript import normalize_ocr
from src.document_evidence import build_evidence


class EvidenceTests(unittest.TestCase):
    def test_decimal_item_and_page_mapping(self):
        transcript = normalize_ocr({'pages': [{'number': 1, 'text': 'Item 2.02 Results of Operations\nRevenue was $3.25 million. We did not change guidance.'}, {'number': 2, 'text': 'Loss was -2.50 million.'}]}, 'doc')
        evidence = build_evidence(transcript)
        self.assertTrue(any(row['quoted_text'] == 'Revenue was $3.25 million.' for row in evidence))
        for row in evidence:
            self.assertEqual(transcript['normalized_text'][row['char_start']:row['char_end']], row['quoted_text'])
            self.assertEqual(row['sec_item'], '2.02')
            self.assertEqual(row['text_sha256'], transcript['text_sha256'])
        self.assertEqual(evidence[-1]['page_number'], 2)

    def test_hash_tampering_rejected(self):
        transcript = normalize_ocr({'text': 'Original.'}, 'doc')
        transcript['normalized_text'] = 'Changed.'
        with self.assertRaises(ValueError):
            build_evidence(transcript)

    def test_section_ids_are_document_specific(self):
        one = build_evidence(normalize_ocr({'text': 'Item 2.02 Results\nRevenue rose.'}, 'one'))
        two = build_evidence(normalize_ocr({'text': 'Item 2.02 Results\nRevenue rose.'}, 'two'))
        self.assertNotEqual(one[-1]['section_id'], two[-1]['section_id'])
