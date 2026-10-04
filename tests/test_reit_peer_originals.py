import unittest
import copy
from hashlib import sha256
import tempfile
from pathlib import Path
from scripts.collect_reit_peer_originals import validate_binding, NativeText, collect, save


class PeerOriginalTests(unittest.TestCase):
    def row(self):
        return {'cik':'0001500217','accession':'0001500217-26-000032','primary_document':'aat-20260326.htm','source_url':'https://www.sec.gov/Archives/edgar/data/1500217/000150021726000032/aat-20260326.htm','form':'8-K'}
    def test_exact_binding(self):
        row=self.row()
        self.assertEqual(validate_binding(row)[1],row['cik'])
        row['source_url']=row['source_url'].replace('/1500217/','/1053507/')
        with self.assertRaises(ValueError): validate_binding(row)
    def test_no_query_or_filename_substitution(self):
        row=self.row()
        row['source_url']+='?download=1'
        with self.assertRaises(ValueError): validate_binding(row)
        row=self.row()
        row['primary_document']='../exhibit.htm'
        with self.assertRaises(ValueError): validate_binding(row)
    def test_native_quote_text(self):
        parser=NativeText()
        parser.feed('<html><p>Loan &amp; maturity</p><script>hidden()</script></html>')
        self.assertIn('Loan & maturity',''.join(parser.parts))
        self.assertNotIn('hidden',''.join(parser.parts))

    def stage(self, output, rows):
        acquisitions = {}
        for row in rows:
            raw = b'<html><p>Retained original quote</p></html>'
            path = output/'raw'/row['cik']/row['accession']/row['primary_document']
            path.parent.mkdir(parents=True,exist_ok=True)
            path.write_bytes(raw)
            digest = sha256(raw).hexdigest()
            receipt = {'kind':'http','receipt_id':row['accession'],'url':row['source_url'],'final_url':row['source_url'],'status':200,'source_sha256':digest,'response_sha256':digest,'publicly_available':True,'started_at':'2026-10-04T01:00:00Z','retrieved_at':'2026-10-04T01:00:01Z'}
            acquisitions[row['source_url']]={'url':row['source_url'],'path':path.relative_to(output).as_posix(),'sha256':digest,'receipt':receipt}
        save(output/'request_manifest.json',{'requests':rows,'schema_failures':[]})
        save(output/'acquired.json',acquisitions)
        save(output/'broker_receipts.json',{'receipts':[a['receipt'] for a in acquisitions.values()]})
        return acquisitions

    def test_offline_rejects_escape_and_forged_evidence(self):
        variants = ['escape','absolute','url','receipt_url','final_url','hash','response_hash','status','timestamp','forged_import','ledger_missing']
        for variant in variants:
            with self.subTest(variant=variant), tempfile.TemporaryDirectory() as directory:
                output=Path(directory)/'export'
                row=self.row()
                acquired=self.stage(output,[row])
                source=acquired[row['source_url']]
                if variant in {'escape','absolute'}:
                    escaped=Path(directory)/'escaped.htm'
                    escaped.write_bytes((output/source['path']).read_bytes())
                    source['path']='../escaped.htm' if variant=='escape' else str(escaped.resolve())
                elif variant=='url': source['url']='https://www.sec.gov/other.htm'
                elif variant=='receipt_url': source['receipt']['url']='https://www.sec.gov/other.htm'
                elif variant=='final_url': source['receipt']['final_url']='https://www.sec.gov/other.htm'
                elif variant=='hash': source['sha256']='0'*64
                elif variant=='response_hash': source['receipt']['response_sha256']='0'*64
                elif variant=='status': source['receipt']['status']=403
                elif variant=='timestamp': source['receipt']['retrieved_at']='2026-10-03T01:00:00Z'
                elif variant=='forged_import': source['receipt'].update(kind='retained_cache_import',status=None,retrieved_at=None,publicly_available=None,imported_at='2026-10-04T01:00:01Z')
                save(output/'acquired.json',acquired)
                save(output/'broker_receipts.json',{'receipts':[] if variant=='ledger_missing' else [source['receipt']]})
                manifest=collect(output,None,offline=True)
                self.assertEqual(manifest['documents'],[])
                self.assertEqual(len(manifest['failures']),1)

    def test_retained_import_requires_bound_primary_and_keeps_import_kind(self):
        with tempfile.TemporaryDirectory() as directory:
            output=Path(directory)
            row=self.row()
            acquired=self.stage(output,[row])
            source=acquired[row['source_url']]
            row['retained']={**row,'url':row['source_url'],'sha256':source['sha256'],'primaryDocument':row['primary_document'],'document_role':'primary'}
            source['receipt']={'receipt_id':'retained-fixture','kind':'retained_cache_import','url':row['source_url'],'source_sha256':source['sha256'],'status':None,'retrieved_at':None,'publicly_available':None,'imported_at':'2026-10-04T01:00:01Z'}
            save(output/'request_manifest.json',{'requests':[row],'schema_failures':[]})
            save(output/'acquired.json',acquired)
            save(output/'broker_receipts.json',{'receipts':[source['receipt']]})
            manifest=collect(output,None,offline=True)
            self.assertEqual(manifest['counts'],{'complete':1})
            self.assertEqual(manifest['documents'][0]['acquisition_evidence_kind'],'retained_cache_import')
            self.assertIsNone(manifest['documents'][0]['receipt']['retrieved_at'])

    def test_shrinking_queue_excludes_obsolete_documents_and_failures(self):
        with tempfile.TemporaryDirectory() as directory:
            output=Path(directory)
            rows=[self.row()]
            for number in (33,34):
                row=self.row()
                row['accession']=f'0001500217-26-0000{number}'
                row['source_url']=row['source_url'].replace('000150021726000032',row['accession'].replace('-',''))
                rows.append(row)
            acquired=self.stage(output,rows)
            acquired[rows[-1]['source_url']]['error']='fixture unavailable'
            save(output/'acquired.json',acquired)
            initial=collect(output,None,offline=True)
            self.assertEqual(len(initial['documents']),2)
            self.assertEqual(len(initial['failures']),1)
            save(output/'request_manifest.json',{'requests':rows[:1],'schema_failures':[]})
            final=collect(output,None,offline=True)
            self.assertEqual(len(final['documents']),1)
            self.assertEqual(final['failures'],[])
            self.assertEqual(final['counts'],{'complete':1})

    def test_completed_result_rejects_same_url_new_valid_source_version(self):
        with tempfile.TemporaryDirectory() as directory:
            output=Path(directory)
            row=self.row()
            acquired=self.stage(output,[row])
            initial=collect(output,None,offline=True)
            old_hash=initial['documents'][0]['sha256']
            source=acquired[row['source_url']]
            replacement=b'<html><p>A distinct subsequently retained quote</p></html>'
            (output/source['path']).write_bytes(replacement)
            new_hash=sha256(replacement).hexdigest()
            source['sha256']=new_hash
            source['receipt'].update(receipt_id='new-version-http',source_sha256=new_hash,response_sha256=new_hash,started_at='2026-10-04T02:00:00Z',retrieved_at='2026-10-04T02:00:01Z')
            save(output/'acquired.json',acquired)
            save(output/'broker_receipts.json',{'receipts':[source['receipt']]})
            final=collect(output,None,offline=True)
            self.assertEqual(final['documents'],[])
            self.assertEqual(final['counts'],{'blocked':1})
            self.assertIn('source version',final['failures'][0]['error'].lower())
            from src.reit_acquisition import RunState
            retained_result=RunState(output/'tasks.sqlite').summary()['tasks'][0]['result']
            import json
            self.assertEqual(json.loads(retained_result)['sha256'],old_hash)


if __name__ == '__main__': unittest.main()
