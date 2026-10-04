import hashlib
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from urllib.error import HTTPError
from src.document_manifest import inventory_from_submission, validate_sec_url, SecFetcher, SECBlocked

ROW = {'cik':'0000001234','accession':'0000001234-26-000001','form':'8-K','acceptance_datetime':'2026-01-01T10:00:00Z'}
URL = 'https://www.sec.gov/Archives/edgar/data/1234/000000123426000001/main.htm'
PAYLOAD = b'<DOCUMENT>\n<TYPE>8-K\n<FILENAME>main.htm\n<TEXT><html>Item 2.02 Results of Operations. Exhibit 99.1</html></TEXT>\n</DOCUMENT>\n<DOCUMENT>\n<TYPE>EX-99.1\n<FILENAME>release.htm\n<TEXT><html>Quarterly earnings results: revenue increased 10 percent.</html></TEXT>\n</DOCUMENT>'

class ManifestTests(unittest.TestCase):
    def test_preserves_primary_release_and_hash(self):
        docs = inventory_from_submission(ROW, PAYLOAD)
        self.assertEqual([d['document_role'] for d in docs], ['primary_filing','earnings_release'])
        self.assertEqual(docs[0]['sec_items'], ['2.02'])
        self.assertEqual(docs[1]['source_sha256'], hashlib.sha256(docs[1]['content_bytes']).hexdigest())
        self.assertIsNone(docs[0]['public_at_utc'])
    def test_missing_documents_and_unknown_exhibit(self):
        docs = inventory_from_submission(ROW, b'<DOCUMENT>\n<TYPE>EX-99.1\n<FILENAME>x.htm\n<TEXT>Slide deck</TEXT>\n</DOCUMENT>')
        self.assertEqual(docs[0]['document_role'], 'unclassified')
        self.assertTrue(any(d['inventory_status']=='missing_primary' for d in docs))
        docs = inventory_from_submission(ROW, PAYLOAD.split(b'<DOCUMENT>',2)[0] + PAYLOAD[:PAYLOAD.index(b'\n<DOCUMENT>')])
        self.assertTrue(any(d['inventory_status']=='missing_exhibit' for d in docs))
    def test_amendment_and_duplicate_links(self):
        docs = inventory_from_submission(dict(ROW, form='8-K/A', amends_accession='0000001234-25-000001'), PAYLOAD.replace(b'<TYPE>8-K', b'<TYPE>8-K/A'))
        self.assertEqual(docs[0]['accession'], ROW['accession'])
        self.assertIn('0000001234-25-000001', docs[0]['event_group_id'])
    def test_url_identity_and_traversal(self):
        self.assertEqual(validate_sec_url(URL, ROW['cik'], ROW['accession']), URL)
        validate_sec_url('https://www.sec.gov/Archives/edgar/data/1234/0000001234-26-000001.txt', ROW['cik'], ROW['accession'])
        for url in [URL.replace('https:', 'http:'), URL.replace('1234/', '9999/'), URL.replace('main.htm','%2e%2e/x'), URL.replace('www.sec.gov','www.sec.gov.evil.com')]:
            with self.assertRaises(ValueError): validate_sec_url(url, ROW['cik'], ROW['accession'])
    def test_fetch_cache_and_blocks(self):
        class Response:
            headers = {'Content-Type':'text/html'}
            def __enter__(self): return self
            def __exit__(self,*args): pass
            def geturl(self): return URL
            def read(self): return b'original'
        with tempfile.TemporaryDirectory() as tmp:
            fetcher=SecFetcher(tmp,'private@example.com')
            with patch('src.document_manifest.urlopen', return_value=Response()) as request:
                first=fetcher.fetch(URL,ROW['cik'],ROW['accession'])
                second=fetcher.fetch(URL,ROW['cik'],ROW['accession'])
                self.assertEqual(request.call_count,1)
            self.assertEqual(first,second)
            self.assertEqual(Path(first['path']).read_bytes(), b'original')
            self.assertNotIn('private@example.com', ''.join(p.read_text() for p in Path(tmp).glob('*.json')))
            Path(first['path']).write_bytes(b'corrupt')
            with self.assertRaises(ValueError): fetcher.fetch(URL,ROW['cik'],ROW['accession'])
        with tempfile.TemporaryDirectory() as tmp:
            with patch('src.document_manifest.urlopen', side_effect=HTTPError(URL,429,'blocked',{},None)):
                with self.assertRaises(SECBlocked): SecFetcher(tmp,'private@example.com').fetch(URL,ROW['cik'],ROW['accession'])

if __name__=='__main__': unittest.main()

class FetchSafetyTests(unittest.TestCase):
    def test_redirect_rejected_before_request(self):
        from src.document_manifest import _ArchiveRedirect
        from urllib.request import Request
        redirect = _ArchiveRedirect(ROW['cik'], ROW['accession'])
        with self.assertRaises(ValueError):
            redirect.redirect_request(Request(URL), None, 302, 'Found', {}, 'https://evil.com/data')
    def test_fetch_stays_blocked(self):
        with tempfile.TemporaryDirectory() as tmp:
            fetcher = SecFetcher(tmp, 'private@example.com')
            with patch('src.document_manifest.urlopen', side_effect=HTTPError(URL,403,'blocked',{},None)) as transport:
                for _ in range(2):
                    with self.assertRaises(SECBlocked): fetcher.fetch(URL, ROW['cik'], ROW['accession'])
                self.assertEqual(transport.call_count, 1)
    def test_strict_identity(self):
        for cik, accession in [('1/2', ROW['accession']), (ROW['cik'], '000000123426000001')]:
            with self.assertRaises(ValueError): validate_sec_url(URL, cik, accession)

class ReviewRegressionTests(unittest.TestCase):
    def test_formatted_exhibit_reference_and_raw_pdf_exact_bytes(self):
        primary = PAYLOAD[:PAYLOAD.index(b'\n<DOCUMENT>')].replace(b'Exhibit 99.1', b'<b>Exhibit</b>&nbsp;99.1')
        docs = inventory_from_submission(ROW, primary)
        self.assertTrue(any(d['inventory_status'] == 'missing_exhibit' for d in docs))
        pdf = b'%PDF-1.4\n%%EOF\n'
        for body in (pdf, b'<PDF>' + pdf + b'</PDF>'):
            payload = b'<DOCUMENT>\n<TYPE>EX-99.1\n<FILENAME>x.pdf\n<TEXT>' + body + b'</TEXT>\n</DOCUMENT>'
            self.assertEqual(inventory_from_submission(ROW, payload)[0]['content_bytes'], pdf)
    def test_entities_and_distinct_missing_exhibits(self):
        payload = PAYLOAD[:PAYLOAD.index(b'\n<DOCUMENT>')].replace(b'Item 2.02', b'Item&nbsp;2.02').replace(b'Exhibit 99.1', b'Exhibit&nbsp;99.1 Exhibit 99.2')
        docs = inventory_from_submission(ROW, payload)
        self.assertEqual(docs[0]['sec_items'], ['2.02'])
        self.assertIsNone(docs[0]['public_at_evidence'])
        missing = [d for d in docs if d['inventory_status']=='missing_exhibit']
        self.assertEqual(len({d['document_id'] for d in missing}), 2)
    def test_header_identity_checked(self):
        header = b'<SEC-DOCUMENT>0000001234-26-000001.txt\nACCESSION NUMBER: 0000001234-26-000001\nFILER:\n COMPANY DATA:\n  CENTRAL INDEX KEY: 0000001234\n'
        docs = inventory_from_submission(ROW, header + PAYLOAD)
        self.assertEqual(docs[0]['identity_status'], 'verified')
        for bad in [header.replace(b'KEY: 0000001234', b'KEY: 0000009999'), header.replace(b'26-000001', b'26-000002')]:
            with self.assertRaises(ValueError): inventory_from_submission(ROW, bad + PAYLOAD)
        self.assertEqual(inventory_from_submission(ROW, PAYLOAD)[0]['identity_status'], 'unverified')
    def test_pdf_uuencode_and_unsupported(self):
        import binascii
        pdf = b'%PDF-1.4\n1 0 obj\n<<>>\nendobj\n%%EOF\n'
        encoded = b'begin 644 exhibit.pdf\n' + binascii.b2a_uu(pdf) + b'`\nend\n'
        payload = b'<DOCUMENT>\n<TYPE>EX-99.1\n<FILENAME>exhibit.pdf\n<TEXT><PDF>\n' + encoded + b'</PDF></TEXT>\n</DOCUMENT>'
        doc = inventory_from_submission(ROW, payload)[0]
        self.assertEqual(doc['content_bytes'], pdf)
        self.assertEqual(doc['source_sha256'], hashlib.sha256(pdf).hexdigest())
        self.assertEqual(doc['source_encoding'], 'sec_uuencode')
        self.assertEqual(doc['content_type'], 'application/pdf')
        bad = inventory_from_submission(ROW, payload.replace(encoded, b'garbage'))[0]
        self.assertEqual(bad['inventory_status'], 'encoded_binary_unsupported')
        self.assertIsNone(bad['content_bytes'])
