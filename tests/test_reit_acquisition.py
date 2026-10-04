import hashlib
from pathlib import Path
import tempfile
import unittest

try:
    from src.reit_acquisition import FetchBroker, AcquisitionBlocked, CacheCorrupt, RunState
except ImportError:
    FetchBroker = None


class AcquisitionTests(unittest.TestCase):
    def setUp(self):
        self.assertIsNotNone(FetchBroker, 'Durable acquisition broker not implemented')
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.now = [100.0]
        self.calls = []

    def broker(self, response=None):
        def transport(url, headers):
            self.calls.append((self.now[0], url, headers))
            return response or {'status': 200, 'body': b'{"ok":true}', 'content_type': 'application/json', 'final_url': url}
        return FetchBroker(self.root, contact_email='john.p.riley00@gmail.com', transport=transport,
                           clock=lambda: self.now[0], sleep=lambda seconds: self.now.__setitem__(0, self.now[0]+seconds))

    def test_cache_resumes_and_detects_mutation(self):
        broker = self.broker()
        url = 'https://data.sec.gov/submissions/CIK0001500217.json'
        first = broker.fetch(url)
        second = self.broker().fetch(url)
        self.assertEqual(first['sha256'], second['sha256'])
        self.assertEqual(len(self.calls), 1)
        Path(first['path']).write_bytes(b'changed')
        with self.assertRaises(CacheCorrupt):
            broker.fetch(url)
        self.assertEqual(len(self.calls), 1)

    def test_two_instances_share_sec_rate_and_contact(self):
        self.broker().fetch('https://data.sec.gov/submissions/a.json')
        self.broker().fetch('https://www.sec.gov/Archives/b.htm')
        self.broker().fetch('https://www.reit.com/c.html')
        self.assertGreaterEqual(self.calls[1][0]-self.calls[0][0], .5)
        self.assertGreaterEqual(self.calls[2][0]-self.calls[1][0], .5)
        self.assertIn('john.p.riley00@gmail.com', self.calls[0][2]['User-Agent'])

    def test_block_is_durable_and_prevents_repeat_traffic(self):
        broker = self.broker({'status': 429, 'body': b'try later', 'content_type': 'text/plain'})
        with self.assertRaises(AcquisitionBlocked):
            broker.fetch('https://www.sec.gov/Archives/a.htm')
        with self.assertRaises(AcquisitionBlocked):
            self.broker().fetch('https://data.sec.gov/submissions/a.json')
        self.assertEqual(len(self.calls), 1)

    def test_unapproved_redirect_and_url_are_rejected(self):
        broker = self.broker({'status': 200, 'body': b'x', 'content_type': 'text/plain', 'final_url': 'https://evil.invalid/x'})
        with self.assertRaises(ValueError):
            broker.fetch('https://data.sec.gov/x')
        with self.assertRaises(ValueError):
            broker.fetch('http://data.sec.gov/x')
        with self.assertRaises(ValueError):
            broker.fetch('https://data.sec.gov.evil.invalid/x')

    def test_import_is_hash_checked_and_not_a_network_receipt(self):
        source = self.root/'pilot.htm'
        source.write_bytes(b'pilot')
        digest = hashlib.sha256(b'pilot').hexdigest()
        broker = self.broker()
        row = broker.import_cached('https://www.sec.gov/Archives/pilot.htm', source, digest)
        self.assertEqual(row['receipt']['kind'], 'retained_cache_import')
        self.assertIsNone(row['receipt']['status'])
        with self.assertRaises(CacheCorrupt):
            broker.import_cached('https://www.sec.gov/Archives/other.htm', source, '0'*64)
        self.assertEqual(self.calls, [])

    def test_queue_lease_resume_idempotence_and_changed_payload(self):
        queue = RunState(self.root/'run.sqlite', clock=lambda: self.now[0])
        queue.enqueue('1', {'url': 'a'})
        queue.enqueue('1', {'url': 'a'})
        with self.assertRaises(ValueError):
            queue.enqueue('1', {'url': 'b'})
        task = queue.claim('ownerA', lease_seconds=10)
        self.assertIsNone(queue.claim('ownerB'))
        self.now[0] += 11
        task2 = queue.claim('ownerB')
        self.assertEqual(task['task_id'], task2['task_id'])
        with self.assertRaises(ValueError):
            queue.finish('1', 'ownerA', {'done': True})
        queue.finish('1', 'ownerB', {'done': True})
        self.assertIsNone(queue.claim('ownerA'))
        self.assertEqual(queue.summary()['counts']['complete'], 1)

    def test_fourth_expired_attempt_becomes_terminal(self):
        queue=RunState(self.root/'run.sqlite',clock=lambda:self.now[0])
        queue.enqueue('x',{})
        for attempt in range(4):
            self.assertIsNotNone(queue.claim('owner',lease_seconds=1))
            self.now[0]+=2
        self.assertIsNone(queue.claim('owner'))
        self.assertEqual(queue.summary()['counts'].get('failed'),1)

    def test_sidecar_failure_cannot_erase_http_block(self):
        broker=self.broker({'status':403,'body':b'denied','content_type':'text/plain'})
        def fail(receipt):
            raise OSError('disk full')
        broker._receipt=fail
        with self.assertRaises(OSError):
            broker.fetch('https://www.sec.gov/Archives/a.htm')
        with self.assertRaises(AcquisitionBlocked):
            self.broker().fetch('https://data.sec.gov/submissions/a.json')
        self.assertEqual(len(self.calls),1)


if __name__ == '__main__':
    unittest.main()
