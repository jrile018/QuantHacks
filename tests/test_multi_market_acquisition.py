"""Budget and persistent single-submission safeguards; no paid network calls."""
import json
import tempfile
import unittest
from unittest.mock import patch
from datetime import datetime,timezone
import contextlib
import io
from pathlib import Path
from scripts.multi_market import acquire_pilot as acquisition

class AcquisitionTests(unittest.TestCase):
    def test_frozen_scopes_exclude_split_futures_and_samples(self):
        scopes = acquisition.frozen_scopes()
        self.assertEqual(len(scopes),7)
        futures = [s for s in scopes if s['dataset']=='GLBX.MDP3']
        self.assertEqual(len(futures),4)
        for s in futures:
            self.assertEqual(set(s['symbols'].split(',')), {'ES.v.0','MES.v.0','ZN.v.0','CL.v.0','GC.v.0'})
        self.assertTrue(all(s['end']=='2026-01-01' for s in scopes))

    def test_invalid_quotes_never_authorize_purchase(self):
        for bad in [-1,float('nan'),float('inf'),None]:
            with self.subTest(bad=bad), self.assertRaises(ValueError):
                acquisition.check_budget({'budget_ceiling_usd':250,'purchases':[]}, [bad], [])

    def test_unresolved_quotes_and_reservations_count_against_cap(self):
        ledger={'budget_ceiling_usd':250,'purchases':[{'quoted_cost_usd':245,'status':'processing'}]}
        with self.assertRaises(ValueError):
            acquisition.check_budget(ledger,[4],[{'quoted_cost_usd':2}])
        with self.assertRaises(ValueError):
            acquisition.check_budget({'budget_ceiling_usd':250,'purchases':[]},[10.01],[])
        with self.assertRaises(ValueError):
            acquisition.check_budget(ledger,[3],[{'quoted_cost_usd':2}])
        self.assertEqual(acquisition.check_budget(ledger,[2.99],[{'quoted_cost_usd':2}]),249.99)

    def test_invalid_ledger_cost_fails_closed(self):
        with self.assertRaises(ValueError):
            acquisition.check_budget({'budget_ceiling_usd':250,'purchases':[{'actual_cost_usd':float('nan')}]},[1],[])

    def test_overlap_detects_split_futures_and_canonical_dates(self):
        scope=acquisition.frozen_scopes()[0]
        existing={**scope,'symbols':'MES.v.0,ES.v.0','start':'2024-01-01T00:00:00.000000000Z'}
        with self.assertRaises(ValueError):
            acquisition.ensure_disjoint([scope],[existing])
        with self.assertRaises(ValueError):
            acquisition.ensure_disjoint([scope,scope],[])

    def test_unknown_submission_persisted_and_cannot_be_retried(self):
        with tempfile.TemporaryDirectory() as folder:
            evidence=Path(folder)/'request.json'
            def disconnect(_):
                raise TimeoutError('uncertain response')
            with self.assertRaisesRegex(RuntimeError,'unknown'):
                acquisition.submit_once(acquisition.frozen_scopes()[0],1,evidence,disconnect)
            self.assertEqual(json.loads(evidence.read_text())['status'],'unknown')
            def unexpected(_):
                self.fail('second paid call must never occur')
            with self.assertRaisesRegex(RuntimeError,'already'):
                acquisition.submit_once(acquisition.frozen_scopes()[0],1,evidence,unexpected)

    def test_single_submit_rejects_cost_above_pilot_cap(self):
        with tempfile.TemporaryDirectory() as folder:
            evidence=Path(folder)/'request.json'
            def external(_):
                return {'id':'must-not-purchase','state':'queued'}
            with self.assertRaises(ValueError):
                acquisition.submit_once(acquisition.frozen_scopes()[0],10.01,evidence,external)
            self.assertFalse(evidence.exists())

    def test_actual_completed_cost_blocks_next_post(self):
        # First quote6, remaining six quotes0.5: initialpilot9. Actualfirst8
        # arrives only through provider refresh: pilotexposure11 muststop.
        class Provider:
            def __init__(self):
                self.submitted=[]
            def get(self,method,scope):
                if method=='metadata.get_cost':
                    return 6 if scope['schema']=='statistics' else .5
                return 100
            def submit(self,scope):
                job={**scope,'id':'job-'+str(len(self.submitted)), 'state':'queued','cost_usd':None}
                self.submitted.append(job)
                return job
            def jobs(self):
                return [dict(j,state='done',cost_usd=8 if i==0 else .5) for i,j in enumerate(self.submitted)]
        provider=Provider()
        with tempfile.TemporaryDirectory() as folder:
            project=Path(folder)
            evidence=project/'data/raw/databento/multi-market-pilot'
            ledger=project/'data/raw/databento/acquisition_ledger.json'
            ledger.parent.mkdir(parents=True)
            ledger.write_text(json.dumps({'budget_ceiling_usd':250,'purchases':[]}))
            with patch.object(acquisition,'PROJECT',project), patch.object(acquisition,'EVIDENCE',evidence), patch.object(acquisition,'HTTP',return_value=provider), contextlib.redirect_stdout(io.StringIO()):
                with self.assertRaisesRegex(ValueError,'Pilot'):
                    acquisition.run(submit=True)
            self.assertEqual(len(provider.submitted),1)

    def test_provider_retained_purchase_before_current_day_prevents_duplicate(self):
        prior={**acquisition.frozen_scopes()[0],'id':'older-job','state':'done','ts_received':'2026-09-30T10:00:00Z'}
        client=acquisition.HTTP.__new__(acquisition.HTTP)
        def metadata(method,params):
            cutoff=datetime.fromisoformat(params.get('since','1970-01-01T00:00:00Z').replace('Z','+00:00'))
            return [prior] if cutoff<datetime(2026,9,30,10,tzinfo=timezone.utc) else []
        client.get=metadata
        with self.assertRaisesRegex(ValueError,'Duplicate'):
            acquisition.ensure_disjoint([acquisition.frozen_scopes()[0]],client.jobs())

    def test_merged_reservation_counts_larger_actual_once(self):
        for ledger_row in [
            {'job_id':'same-job','scope_sha256':'same-scope','quoted_cost_usd':2},
            {'job_id':'same-job','scope_sha256':'same-scope','actual_cost_usd':4,'quoted_cost_usd':2},
            {'scope_sha256':'same-scope','quoted_cost_usd':2},
        ]:
            with self.subTest(ledger_row=ledger_row):
                ledger={'budget_ceiling_usd':250,'purchases':[ledger_row]}
                local={'job_id':'same-job','scope_sha256':'same-scope','actual_cost_usd':4,'quoted_cost_usd':2}
                self.assertEqual(acquisition.check_budget(ledger,[1],[local]),5)

    def test_reconciliation_preserves_existing_rows_and_is_idempotent(self):
        with tempfile.TemporaryDirectory() as folder:
            ledger=Path(folder)/'ledger.json'
            original={'job_id':'old','quoted_cost_usd':2,'actual_cost_usd':3,'status':'done','keep':'original'}
            ledger.write_text(json.dumps({'budget_ceiling_usd':250,'purchases':[original]}))
            scope=acquisition.frozen_scopes()[0]
            record={'job_id':'new','request':scope,'scope_sha256':acquisition.scope_hash(scope),
                'quoted_cost_usd':1,'actual_cost_usd':1.5,'status':'done','job':{'cost_usd':1.5}}
            reconcile=getattr(acquisition,'reconcile_ledger',lambda *args:None)
            reconcile(ledger,[record])
            reconcile(ledger,[record])
            result=json.loads(ledger.read_text())
            self.assertEqual(result['purchases'][0],original)
            self.assertEqual(len(result['purchases']),2)
            self.assertEqual(result['actual_plus_quoted_usd'],4.5)
            self.assertEqual(result['purchases'][1]['request'],scope)

    def test_reconciliation_aborts_when_another_writer_changes_ledger(self):
        with tempfile.TemporaryDirectory() as folder:
            ledger=Path(folder)/'ledger.json'
            ledger.write_text(json.dumps({'budget_ceiling_usd':250,'purchases':[]}))
            external={'budget_ceiling_usd':250,'purchases':[],'concurrent_marker':'must-survive'}
            real_write=acquisition.write_json
            def race(path,payload,*args,**kwargs):
                ledger.write_text(json.dumps(external))
                return real_write(path,payload,*args,**kwargs)
            with patch.object(acquisition,'write_json',side_effect=race):
                with self.assertRaisesRegex(RuntimeError,'concurrent'):
                    getattr(acquisition,'reconcile_ledger',lambda *args:None)(ledger,[])
            self.assertEqual(json.loads(ledger.read_text()),external)

    def test_success_persists_job_id_without_account_credentials(self):
        with tempfile.TemporaryDirectory() as folder:
            evidence=Path(folder)/'request.json'
            result=acquisition.submit_once(acquisition.frozen_scopes()[0],.1,evidence,
                lambda _: {'id':'GLBX-test','state':'queued','api_key':'secret','user_id':'private','cost_usd':None})
            stored=json.loads(evidence.read_text())
            self.assertEqual(result['job_id'], 'GLBX-test')
            self.assertEqual(stored['job_id'], 'GLBX-test')
            self.assertNotIn('secret', evidence.read_text())
            self.assertNotIn('private', evidence.read_text())

if __name__=='__main__':
    unittest.main()
