from hashlib import sha256
from pathlib import Path
import tempfile
import unittest
from scripts import collect_reit_history as runner
from src.reit_acquisition import RunState, CacheCorrupt


class RunnerTests(unittest.TestCase):
    def test_document_separates_filing_metadata_size_from_raw_bytes(self):
        with tempfile.TemporaryDirectory() as tmp:
            raw=Path(tmp)/'original.htm'
            body=b'<html><p>Native source</p></html>'
            raw.write_bytes(body)
            metadata_sources=[{'url':'https://data.sec.gov/submissions/CIK0000000001.json','source_sha256':'a'*64}]
            filing={'cik':'0000000001','accession':'0000000001-26-000001','primaryDocument':'annual.htm','url':'https://www.sec.gov/Archives/edgar/data/1/000000000126000001/annual.htm','filing_date':'2026-01-01','size':50392915,'metadata_sources':metadata_sources}
            value={'filing':filing,'path':str(raw),'sha256':sha256(body).hexdigest(),'receipt':{'retrieved_at':'2026-10-04T01:00:00Z'}}
            result=runner.store_document(value,Path(tmp)/'collection')
            self.assertEqual(result['filing_metadata_size'],50392915)
            self.assertEqual(result['source_byte_count'],len(body))
            self.assertNotIn('size',result)
            self.assertEqual(result['metadata_sources'],metadata_sources)
            self.assertEqual(filing['size'],50392915)

    def test_completed_raw_task_cannot_bypass_mutation_check(self):
        with tempfile.TemporaryDirectory() as tmp:
            path=Path(tmp)/'raw'
            path.write_bytes(b'original')
            queue=RunState(Path(tmp)/'state.sqlite')
            queue.enqueue('a',{})
            queue.claim('owner')
            queue.finish('a','owner',{'path':str(path),'sha256':sha256(b'original').hexdigest()})
            path.write_bytes(b'changed')
            with self.assertRaises(CacheCorrupt):
                runner.retained_results(queue)

    def test_latest_annual_uses_selected_metadata_only(self):
        self.assertTrue(hasattr(runner,'annual_tasks'),'Annual selection helper missing')
        good={'cik':'0000000001','form':'10-K','filing_date':'2025-02-01','accession':'old','url':'https://www.sec.gov/old.htm'}
        bad=dict(good,filing_date='2026-02-01',accession='bad',url='https://www.sec.gov/bad.htm')
        tasks=runner.annual_tasks({'selected':[good],'filings':[good,bad]},['0000000001'])
        self.assertEqual(tasks[0]['url'],good['url'])

    def test_retained_cik_seeds_preserve_current_mapping_without_name_guess(self):
        self.assertTrue(hasattr(runner,'retained_candidates'))
        with tempfile.TemporaryDirectory() as tmp:
            raw=Path(tmp)/'filing.htm'
            raw.write_bytes(b'Example retained annual report')
            doc={'cik':'1','url':'https://www.sec.gov/Archives/edgar/data/1/x/a.htm',
                 'source_path':str(raw),'sha256':sha256(raw.read_bytes()).hexdigest()}
            exchange=[{'cik':'0000000001','ticker':'EXM','name':'EXAMPLE CORP /MA/','exchange':'NYSE'}]
            rows=runner.retained_candidates([doc],exchange)
            self.assertEqual(rows[0]['cik'],'0000000001')
            self.assertEqual(rows[0]['discovery_status'],'candidate_only')
            self.assertEqual(rows[0]['source_sha256'],doc['sha256'])
            raw.write_bytes(b'changed')
            with self.assertRaises(CacheCorrupt):
                runner.retained_candidates([doc],exchange)

    def test_exhibit_override_does_not_inherit_primary_content_identity(self):
        self.assertTrue(hasattr(runner,'exhibit_document'))
        primary={'cik':'1','filename':'annual.htm','url':'https://www.sec.gov/annual.htm',
                 'document_role':'primary','source_path':'old','text_path':'old-text',
                 'sha256':'a'*64,'text_sha256':'b'*64}
        exhibit=dict(primary,filename='credit.htm',url='https://www.sec.gov/credit.htm',document_role='exhibit')
        result=runner.exhibit_document(primary,exhibit)
        self.assertEqual(result['filename'],'credit.htm')
        self.assertEqual(result['document_role'],'exhibit')
        self.assertFalse(set(result)&{'source_path','text_path','sha256','text_sha256'})


if __name__=='__main__':
    unittest.main()
