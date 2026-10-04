"""Durable, conservative reservations for the authorized Databento spend."""
from __future__ import annotations

from contextlib import contextmanager
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation, ROUND_CEILING
from hashlib import sha256
import json
from pathlib import Path
import sqlite3


class BudgetExceeded(ValueError):
    pass


def _money(value) -> Decimal:
    try:
        number=Decimal(str(value))
    except InvalidOperation as exc:
        raise ValueError('Invalid dollar amount') from exc
    if not number.is_finite() or number < 0:
        raise ValueError('Dollar amounts must be finite and nonnegative')
    return number


def _cents(value) -> int:
    return int((_money(value)*100).to_integral_value(rounding=ROUND_CEILING))


def _usd(cents: int) -> str:
    return str((Decimal(cents)/100).quantize(Decimal('.01')))


def legacy_spend(path: Path) -> Decimal:
    """Account for recorded actuals or outstanding quotes, never infer credits."""
    if not path.exists():
        return Decimal(0)
    payload=json.loads(path.read_text(encoding='utf-8-sig'))
    purchases=payload.get('purchases')
    if not isinstance(purchases,list):
        raise ValueError('Malformed legacy acquisition ledger')
    total=Decimal(0)
    jobs={}
    for item in purchases:
        if not isinstance(item,dict):
            raise ValueError('Malformed legacy purchase')
        amount=item.get('actual_cost_usd')
        if amount is None:
            amount=item.get('quoted_cost_usd')
        if amount is None:
            raise ValueError('Unpriced legacy purchase must be reconciled before buying')
        amount=_money(amount)
        if item.get('job_id'):
            jobs[item['job_id']]=max(jobs.get(item['job_id'],Decimal(0)),amount)
        else:
            total+=amount
    total+=sum(jobs.values(),Decimal(0))
    declared=payload.get('actual_plus_quoted_usd')
    return max(total,_money(declared)) if declared is not None else total


class BudgetLedger:
    """Single SQLite reservation ledger; unknown submissions hold their money.

    This limits this application's submissions, not unrelated account activity.
    Costs are conservatively rounded upward; external spend uses a high-water
    mark and is refreshed by callers before an order. Quotes are not invoices.
    """
    def __init__(self,path: Path,*,cap='249.99',external_spend='0'):
        self.path=Path(path)
        self.cap=_cents(cap)
        if not 0 < self.cap < 25000:
            raise ValueError('Authorized ceiling must be strictly below $250')
        self.path.parent.mkdir(parents=True,exist_ok=True)
        with self._transaction() as db:
            db.execute('CREATE TABLE IF NOT EXISTS metadata (name TEXT PRIMARY KEY,value INTEGER NOT NULL)')
            db.execute('CREATE TABLE IF NOT EXISTS orders (request_id TEXT PRIMARY KEY,payload TEXT NOT NULL,fingerprint TEXT NOT NULL,quoted_cents INTEGER NOT NULL,reserved_cents INTEGER NOT NULL,actual_cents INTEGER,status TEXT NOT NULL,job_id TEXT,note TEXT,created_at TEXT NOT NULL,updated_at TEXT NOT NULL)')
            previous=db.execute("SELECT value FROM metadata WHERE name='cap'").fetchone()
            if previous and previous[0]!=self.cap:
                raise ValueError('Cannot change an existing authorization ceiling')
            db.execute("INSERT OR IGNORE INTO metadata VALUES ('cap',?)",(self.cap,))
            db.execute("INSERT OR IGNORE INTO metadata VALUES ('external',0)")
            self._external(db,_cents(external_spend))

    @contextmanager
    def _transaction(self):
        db=sqlite3.connect(self.path,timeout=30)
        db.row_factory=sqlite3.Row
        try:
            db.execute('PRAGMA busy_timeout=30000')
            db.execute('BEGIN IMMEDIATE')
            yield db
            db.commit()
        except BaseException:
            db.rollback()
            raise
        finally:
            db.close()

    @staticmethod
    def _external(db,value):
        db.execute("UPDATE metadata SET value=MAX(value,?) WHERE name='external'",(value,))

    def refresh_external(self,value):
        with self._transaction() as db:
            self._external(db,_cents(value))

    @staticmethod
    def _committed(db):
        external=db.execute("SELECT value FROM metadata WHERE name='external'").fetchone()[0]
        own=db.execute("SELECT COALESCE(SUM(CASE WHEN status='settled' THEN actual_cents ELSE reserved_cents END),0) FROM orders WHERE status!='released'").fetchone()[0]
        return external+own

    @staticmethod
    def _order(row):
        item=dict(row)
        item['payload']=json.loads(item['payload'])
        for field in ('quoted','reserved','actual'):
            cents=item.pop(field+'_cents')
            item[field+'_usd']=None if cents is None else _usd(cents)
        return item

    def reserve(self,request_id,payload,quoted_cost,*,buffer_factor='1.05'):
        if not isinstance(request_id,str) or not request_id:
            raise ValueError('A stable request ID is required')
        encoded=json.dumps(payload,sort_keys=True,separators=(',',':'),allow_nan=False)
        if any(key in encoded.lower() for key in ('api_key','password','secret','access_token')):
            raise ValueError('Credentials must not be persisted in request payloads')
        fingerprint=sha256(encoded.encode()).hexdigest()
        quote=_money(quoted_cost)
        factor=_money(buffer_factor)
        if factor < 1:
            raise ValueError('A reservation cannot be smaller than its quote')
        reserved=_cents(quote*factor)+1
        now=datetime.now(timezone.utc).isoformat()
        with self._transaction() as db:
            row=db.execute('SELECT * FROM orders WHERE request_id=?',(request_id,)).fetchone()
            if row:
                if row['fingerprint']!=fingerprint or row['quoted_cents']!=_cents(quote):
                    raise ValueError('Request ID already belongs to different quote/payload')
                return self._order(row)
            if db.execute("SELECT request_id FROM orders WHERE fingerprint=? AND status!='released'",(fingerprint,)).fetchone():
                raise ValueError('The same acquisition already has an unreleased reservation; reconcile or download it')
            if self._committed(db)+reserved > self.cap:
                raise BudgetExceeded('Order would exceed the authorized total reservation ceiling')
            db.execute('INSERT INTO orders VALUES (?,?,?,?,?,NULL,?,NULL,NULL,?,?)',
                       (request_id,encoded,fingerprint,_cents(quote),reserved,'reserved',now,now))
            return self._order(db.execute('SELECT * FROM orders WHERE request_id=?',(request_id,)).fetchone())

    def _transition(self,request_id,allowed,status,*,job_id=None,note=None,actual=None):
        with self._transaction() as db:
            row=db.execute('SELECT * FROM orders WHERE request_id=?',(request_id,)).fetchone()
            if not row or row['status'] not in allowed:
                raise ValueError('Unsafe or unknown order-state transition')
            if status=='submitting' and self._committed(db)>self.cap:
                raise BudgetExceeded('Recorded account commitments now exceed the authorization ceiling')
            if job_id is not None and (not job_id or row['job_id'] not in (None,job_id)):
                raise ValueError('Order is already bound to a different job')
            if job_id is not None and db.execute('SELECT request_id FROM orders WHERE job_id=? AND request_id!=?',(job_id,request_id)).fetchone():
                raise ValueError('Provider job is already bound to another reservation')
            db.execute('UPDATE orders SET status=?,job_id=COALESCE(?,job_id),note=?,actual_cents=COALESCE(?,actual_cents),updated_at=? WHERE request_id=?',
                       (status,job_id,note,actual,datetime.now(timezone.utc).isoformat(),request_id))

    def mark_submitting(self,request_id):
        self._transition(request_id,{'reserved'},'submitting')

    def mark_unknown(self,request_id,note):
        self._transition(request_id,{'submitting'},'unknown_held',note=str(note))

    def mark_submitted(self,request_id,job_id):
        self._transition(request_id,{'submitting','unknown_held'},'submitted',job_id=job_id)

    def settle(self,request_id,actual_cost):
        # Record real invoices even when unexpectedly larger; subsequent buying stops.
        self._transition(request_id,{'submitted'},'settled',actual=_cents(actual_cost))

    def release(self,request_id):
        # Only an order which never reached submission is safe to release automatically.
        self._transition(request_id,{'reserved'},'released')

    def summary(self):
        with self._transaction() as db:
            committed=self._committed(db)
            return {'cap_usd':_usd(self.cap),'external_spend_usd':_usd(db.execute("SELECT value FROM metadata WHERE name='external'").fetchone()[0]),
                    'committed_usd':_usd(committed),'remaining_usd':_usd(max(0,self.cap-committed)),
                    'over_budget':committed>self.cap,
                    'orders':[self._order(r) for r in db.execute('SELECT * FROM orders ORDER BY created_at,request_id')]}
