"""Hash-checked collection cache and a single durable HTTP broker per pipeline."""
from contextlib import contextmanager
from datetime import datetime, timezone
from hashlib import sha256
import json
from pathlib import Path
import sqlite3
import time
from urllib.error import HTTPError
from urllib.parse import urlsplit
from urllib.request import Request, build_opener, HTTPRedirectHandler
from uuid import uuid4


class AcquisitionBlocked(RuntimeError):
    pass


class CacheCorrupt(RuntimeError):
    pass


@contextmanager
def transaction(path):
    db = sqlite3.connect(path, timeout=90)
    db.row_factory = sqlite3.Row
    try:
        db.execute('PRAGMA busy_timeout=90000')
        db.execute('BEGIN IMMEDIATE')
        yield db
        db.commit()
    except BaseException:
        db.rollback()
        raise
    finally:
        db.close()


def stamp(value):
    return datetime.fromtimestamp(value, timezone.utc).isoformat()


class FetchBroker:
    """Shared SQLite lock spans the HTTP call, so concurrent clients cannot burst.

    All clients in this REIT pipeline must use the same root. This cannot limit
    unrelated processes elsewhere. 403/429 stops further traffic to the group;
    cached bytes remain usable. Imports are never relabeled as live receipts.
    """
    def __init__(self, root, *, contact_email, rate=2, allowed_hosts=None,
                 transport=None, clock=time.time, sleep=time.sleep):
        if not contact_email or '@' not in contact_email:
            raise ValueError('SEC contact email is required')
        if not 0 < rate <= 2:
            raise ValueError('REIT pipeline rate must be no more than 2 requests/s')
        self.root = Path(root).resolve()
        self.root.mkdir(parents=True, exist_ok=True)
        (self.root/'objects').mkdir(exist_ok=True)
        (self.root/'receipts').mkdir(exist_ok=True)
        self.db = self.root/'broker.sqlite'
        self.contact = contact_email
        self.rate, self.clock, self.sleep = rate, clock, sleep
        self.hosts = set(allowed_hosts or ['www.sec.gov', 'data.sec.gov', 'www.reit.com', 'reit.com'])
        self.transport = transport or self._http
        with transaction(self.db) as db:
            db.execute('CREATE TABLE IF NOT EXISTS groups (name TEXT PRIMARY KEY,last_start REAL,blocked TEXT)')
            db.execute('CREATE TABLE IF NOT EXISTS cache (url TEXT PRIMARY KEY,sha256 TEXT NOT NULL,receipt TEXT NOT NULL)')
            db.execute('CREATE TABLE IF NOT EXISTS receipts (receipt_id TEXT PRIMARY KEY,payload TEXT NOT NULL)')

    def _check_url(self, url):
        parsed = urlsplit(url)
        if parsed.scheme != 'https' or parsed.hostname not in self.hosts or parsed.username or parsed.password or parsed.port not in (None, 443):
            raise ValueError('URL must use an approved HTTPS host without credentials')
        return parsed

    def _http(self, url, headers):
        owner = self
        class SafeRedirect(HTTPRedirectHandler):
            def redirect_request(self, req, fp, code, msg, hdrs, newurl):
                owner._check_url(newurl)
                raise ValueError('Redirect requires a separate broker request and receipt: '+newurl)
        try:
            response = build_opener(SafeRedirect()).open(Request(url, headers=headers), timeout=40)
        except HTTPError as exc:
            response = exc
        with response:
            body = response.read(50*1024*1024+1)
            if len(body) > 50*1024*1024:
                raise ValueError('Document exceeds the 50 MiB acquisition limit')
            return {'status': response.code, 'body': body,
                    'content_type': response.headers.get('Content-Type'), 'final_url': response.geturl()}

    def _object(self, digest):
        return self.root/'objects'/digest

    def _store(self, body):
        digest = sha256(body).hexdigest()
        path = self._object(digest)
        if path.exists():
            if sha256(path.read_bytes()).hexdigest() != digest:
                raise CacheCorrupt('Content-addressed object was modified')
        else:
            temporary = path.with_name(digest+'.'+uuid4().hex+'.tmp')
            temporary.write_bytes(body)
            temporary.replace(path)
        return digest, path

    def _receipt(self, receipt):
        path = self.root/'receipts'/(receipt['receipt_id']+'.json')
        path.write_text(json.dumps(receipt, indent=2, allow_nan=False), encoding='utf-8')
        return receipt

    def _result(self, url, digest, receipt, *, cached):
        path = self._object(digest)
        if not path.exists() or sha256(path.read_bytes()).hexdigest() != digest:
            raise CacheCorrupt('Cached source is missing or has a different SHA256')
        return {'url': url, 'path': str(path), 'sha256': digest, 'cached': cached, 'receipt': receipt}

    def import_cached(self, url, path, expected_sha256, *, content_type=None):
        self._check_url(url)
        body = Path(path).read_bytes()
        if sha256(body).hexdigest() != expected_sha256:
            raise CacheCorrupt('Retained source hash does not match its manifest')
        with transaction(self.db) as db:
            old = db.execute('SELECT * FROM cache WHERE url=?', (url,)).fetchone()
            if old:
                if old['sha256'] != expected_sha256:
                    raise CacheCorrupt('Import conflicts with the current cached source version')
                return self._result(url, old['sha256'], json.loads(old['receipt']), cached=True)
            digest, _ = self._store(body)
            receipt = self._receipt({'receipt_id': uuid4().hex, 'kind': 'retained_cache_import',
                      'url': url, 'status': None, 'source_sha256': digest, 'content_type': content_type,
                      'imported_at': stamp(self.clock()), 'retrieved_at': None, 'publicly_available': None})
            db.execute('INSERT INTO cache VALUES (?,?,?)', (url, digest, json.dumps(receipt)))
            return self._result(url, digest, receipt, cached=True)

    def fetch(self, url, *, force=False, validator=None):
        parsed = self._check_url(url)
        group = 'pipeline'
        error = None
        result = None
        with transaction(self.db) as db:
            old = db.execute('SELECT * FROM cache WHERE url=?', (url,)).fetchone()
            if old:
                old_result = self._result(url, old['sha256'], json.loads(old['receipt']), cached=True)
                if not force:
                    if validator:
                        validator(Path(old_result['path']).read_bytes())
                    return old_result
            state = db.execute('SELECT * FROM groups WHERE name=?', (group,)).fetchone()
            if state and state['blocked']:
                raise AcquisitionBlocked(state['blocked'])
            if state and state['last_start'] is not None:
                self.sleep(max(0, state['last_start']+1/self.rate-self.clock()))
            started = self.clock()
            db.execute('INSERT INTO groups VALUES (?,?,NULL) ON CONFLICT(name) DO UPDATE SET last_start=excluded.last_start', (group, started))
            receipt = {'receipt_id': uuid4().hex, 'kind': 'http', 'url': url,
                       'started_at': stamp(started), 'retrieved_at': None, 'status': None,
                       'source_sha256': None, 'publicly_available': False}
            try:
                response = self.transport(url, {'User-Agent': 'QuantHaxs REIT research '+self.contact,
                                                  'Accept-Encoding': 'identity', 'Accept': '*/*'})
                final = response.get('final_url') or url
                self._check_url(final)
                receipt.update(status=response['status'], content_type=response.get('content_type'),
                               final_url=final, retrieved_at=stamp(self.clock()))
                body = response['body']
                receipt['response_sha256'] = sha256(body).hexdigest()
                if response['status'] in (403, 429):
                    message = 'Acquisition stopped after HTTP '+str(response['status'])+' for '+group
                    db.execute('UPDATE groups SET blocked=? WHERE name=?', (message, group))
                    error = AcquisitionBlocked(message)
                elif response['status'] != 200:
                    error = RuntimeError('HTTP '+str(response['status'])+' for '+url)
                else:
                    if validator:
                        validator(body)
                    digest, _ = self._store(body)
                    receipt.update(source_sha256=digest, publicly_available=True)
                    db.execute('INSERT INTO cache VALUES (?,?,?) ON CONFLICT(url) DO UPDATE SET sha256=excluded.sha256,receipt=excluded.receipt',
                               (url, digest, json.dumps(receipt)))
                    result = self._result(url, digest, receipt, cached=False)
            except Exception as exc:
                error = exc
                receipt['error'] = type(exc).__name__+': '+str(exc)
            db.execute('INSERT INTO receipts VALUES (?,?)',(receipt['receipt_id'],json.dumps(receipt)))
        # Fallible sidecar output cannot roll back an access block or rate state.
        self._receipt(receipt)
        if error:
            raise error
        return result

    def receipts(self):
        with transaction(self.db) as db:
            rows=[json.loads(r[0]) for r in db.execute('SELECT payload FROM receipts ORDER BY receipt_id')]
        known={r['receipt_id'] for r in rows}
        rows.extend(json.loads(p.read_text(encoding='utf-8')) for p in sorted((self.root/'receipts').glob('*.json')) if p.stem not in known)
        return rows


class RunState:
    """Persistent work claims; expired leases resume without duplicating completions."""
    def __init__(self, path, *, clock=time.time):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.clock = clock
        with transaction(self.path) as db:
            db.execute('CREATE TABLE IF NOT EXISTS tasks (task_id TEXT PRIMARY KEY,payload TEXT NOT NULL,status TEXT NOT NULL,owner TEXT,lease_until REAL,attempts INTEGER NOT NULL,result TEXT,error TEXT,retry_at REAL NOT NULL)')

    def enqueue(self, task_id, payload):
        encoded = json.dumps(payload, sort_keys=True, allow_nan=False)
        with transaction(self.path) as db:
            old = db.execute('SELECT payload FROM tasks WHERE task_id=?', (task_id,)).fetchone()
            if old and old['payload'] != encoded:
                raise ValueError('Task ID cannot be reused for a different payload')
            db.execute('INSERT OR IGNORE INTO tasks VALUES (?,?,?,NULL,NULL,0,NULL,NULL,0)', (task_id, encoded, 'pending'))

    def claim(self, owner, *, lease_seconds=120):
        with transaction(self.path) as db:
            now = self.clock()
            db.execute("UPDATE tasks SET status='failed',owner=NULL,lease_until=NULL,error=COALESCE(error,'Retry limit exhausted after expired lease') WHERE attempts>=4 AND (status='retry' OR (status='running' AND lease_until<?))",(now,))
            row = db.execute("SELECT * FROM tasks WHERE ((status IN ('pending','retry') AND retry_at<=?) OR (status='running' AND lease_until<?)) AND attempts<4 ORDER BY task_id LIMIT 1", (now, now)).fetchone()
            if not row:
                return None
            db.execute("UPDATE tasks SET status='running',owner=?,lease_until=?,attempts=attempts+1 WHERE task_id=?", (owner, now+lease_seconds, row['task_id']))
            return dict(db.execute('SELECT * FROM tasks WHERE task_id=?', (row['task_id'],)).fetchone()) | {'payload': json.loads(row['payload'])}

    def _finish(self, task_id, owner, status, result, error, retry_at):
        with transaction(self.path) as db:
            row = db.execute('SELECT * FROM tasks WHERE task_id=?', (task_id,)).fetchone()
            if not row or row['status'] != 'running' or row['owner'] != owner or row['lease_until'] < self.clock():
                raise ValueError('Task lease is not owned or has expired')
            db.execute('UPDATE tasks SET status=?,result=?,error=?,retry_at=?,owner=NULL,lease_until=NULL WHERE task_id=?',
                       (status, json.dumps(result, allow_nan=False) if result is not None else None, error, retry_at, task_id))

    def finish(self, task_id, owner, result):
        self._finish(task_id, owner, 'complete', result, None, 0)

    def fail(self, task_id, owner, error, *, blocked=False, retry_seconds=60):
        self._finish(task_id, owner, 'blocked' if blocked else 'retry', None, str(error), self.clock()+retry_seconds)

    def summary(self):
        with transaction(self.path) as db:
            rows = [dict(r) for r in db.execute('SELECT * FROM tasks ORDER BY task_id')]
        counts = {}
        for row in rows:
            counts[row['status']] = counts.get(row['status'], 0)+1
        return {'counts': counts, 'tasks': rows}
