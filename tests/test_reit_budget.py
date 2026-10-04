from concurrent.futures import ThreadPoolExecutor
from decimal import Decimal
import importlib
from pathlib import Path
import tempfile
import unittest


class BudgetTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        try:
            self.module = importlib.import_module('src.reit_budget')
        except ModuleNotFoundError:
            self.module = None

    def ledger(self, external='0'):
        self.assertIsNotNone(self.module, 'Durable Databento budget guard is not implemented')
        return self.module.BudgetLedger(Path(self.tmp.name)/'budget.sqlite', external_spend=external)

    def test_boundary_and_duplicate_reservation(self):
        ledger=self.ledger('23.14')
        a=ledger.reserve('a', {'schema':'cbbo-1s'}, '2', buffer_factor='1')
        b=ledger.reserve('a', {'schema':'cbbo-1s'}, '2', buffer_factor='1')
        self.assertEqual(a['request_id'], b['request_id'])
        self.assertEqual(Decimal(ledger.summary()['committed_usd']),Decimal('25.15'))
        with self.assertRaises(self.module.BudgetExceeded):
            ledger.reserve('overspend', {}, '225', buffer_factor='1')

    def test_unknown_submission_keeps_reservation(self):
        ledger=self.ledger()
        ledger.reserve('r', {}, '5', buffer_factor='1')
        ledger.mark_submitting('r')
        ledger.mark_unknown('r','timeout')
        with self.assertRaises(ValueError):
            ledger.release('r')
        self.assertEqual(ledger.summary()['orders'][0]['status'],'unknown_held')
        ledger.mark_submitted('r','JOB-1')
        ledger.settle('r','4.75')
        self.assertEqual(Decimal(ledger.summary()['committed_usd']),Decimal('4.75'))

    def test_changed_payload_cannot_reuse_id(self):
        ledger=self.ledger()
        ledger.reserve('r', {'symbol':'AMT'}, '1')
        with self.assertRaises(ValueError):
            ledger.reserve('r', {'symbol':'AGNC'}, '1')

    def test_concurrent_requests_respect_cap(self):
        ledger=self.ledger('240')
        def reserve(n):
            try:
                ledger.reserve(str(n),{'symbol':str(n)},'3',buffer_factor='1')
                return True
            except self.module.BudgetExceeded:
                return False
        with ThreadPoolExecutor(max_workers=6) as pool:
            accepted=list(pool.map(reserve,range(10)))
        self.assertEqual(sum(accepted),3)
        self.assertLess(Decimal(ledger.summary()['committed_usd']),Decimal('250'))

    def test_invalid_cost_or_cap_rejected(self):
        ledger=self.ledger()
        for value in ('-1','NaN','Infinity'):
            with self.assertRaises(ValueError):
                ledger.reserve(value,{},value)
        with self.assertRaises(ValueError):
            self.module.BudgetLedger(Path(self.tmp.name)/'bad.sqlite',cap='250')

    def test_legacy_pending_actual_null_preserves_quote(self):
        import json
        self.ledger()
        path=Path(self.tmp.name)/'legacy.json'
        path.write_text(json.dumps({'purchases':[{'job_id':'a','actual_cost_usd':None,'quoted_cost_usd':5}]}))
        self.assertEqual(self.module.legacy_spend(path),Decimal(5))

    def test_external_spend_change_blocks_submission_atomically(self):
        ledger=self.ledger()
        ledger.reserve('r',{},20)
        ledger.refresh_external(240)
        with self.assertRaises(self.module.BudgetExceeded):
            ledger.mark_submitting('r')
        self.assertEqual(ledger.summary()['orders'][0]['status'],'reserved')

    def test_new_request_id_cannot_duplicate_unknown_payload(self):
        ledger=self.ledger()
        ledger.reserve('old',{'symbols':'AMT'},1)
        ledger.mark_submitting('old')
        ledger.mark_unknown('old','timeout')
        with self.assertRaises(ValueError):
            ledger.reserve('new',{'symbols':'AMT'},1)

    def test_provider_job_can_only_bind_once(self):
        ledger=self.ledger()
        ledger.reserve('first',{'symbols':'AMT'},1)
        ledger.mark_submitting('first')
        ledger.mark_submitted('first','job-one')
        ledger.reserve('second',{'symbols':'AAT'},1)
        ledger.mark_submitting('second')
        with self.assertRaises(ValueError):
            ledger.mark_submitted('second','job-one')


if __name__=='__main__':
    unittest.main()
