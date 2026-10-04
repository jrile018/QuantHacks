"""Bounded historical quote collection with observed timestamps and immutable sources."""
from datetime import datetime, timezone, timedelta
import hashlib
import json
from pathlib import Path
import re
from urllib.parse import urlsplit, unquote

from .document_manifest import atomic_json
from .document_language import utc_timestamp


def sip_iso(nanoseconds):
    if isinstance(nanoseconds, bool) or not isinstance(nanoseconds, int) or nanoseconds <= 0:
        raise ValueError('Positive integer SIP nanoseconds required')
    seconds, remainder = divmod(nanoseconds, 1_000_000_000)
    return datetime.fromtimestamp(seconds, timezone.utc).strftime('%Y-%m-%dT%H:%M:%S') + f'.{remainder:09d}Z'


def validate_page_url(url):
    parsed = urlsplit(url)
    if (parsed.scheme != 'https' or parsed.hostname != 'api.massive.com' or parsed.port not in (None, 443)
            or parsed.username or parsed.password or not parsed.path.startswith('/v3/quotes/')
            or 'apikey=' in parsed.query.lower()):
        raise ValueError('Untrusted quote pagination URL')
    return url


def collect_request(request, session, raw_dir, max_pages=4):
    """One finite request. Receipt is today; SIP event time is never called local receipt."""
    ticker = request['ticker']
    if not re.fullmatch(r'(?:O:)?[A-Z0-9.]+', ticker):
        raise ValueError('Invalid ticker')
    start, end = utc_timestamp(request['start_utc']), utc_timestamp(request['end_utc'])
    if not start or not end or not start < end or end-start > timedelta(days=1):
        raise ValueError('Supply a positive quote interval of at most one day')
    limit = request.get('max_records', 1000)
    if isinstance(limit, bool) or not isinstance(limit, int) or not 1 <= limit <= 50000 or not 1 <= max_pages <= 20:
        raise ValueError('Invalid quote collection bounds')
    directory = Path(raw_dir)
    directory.mkdir(parents=True, exist_ok=True)
    request_id = hashlib.sha256(json.dumps(request, sort_keys=True).encode()).hexdigest()
    url = 'https://api.massive.com/v3/quotes/' + ticker
    expected_path = urlsplit(url).path
    params = {'timestamp.gte': int(start.timestamp()) * 1_000_000_000 + start.microsecond * 1000,
              'timestamp.lt': int(end.timestamp()) * 1_000_000_000 + end.microsecond * 1000,
              'order': 'asc', 'sort': 'timestamp', 'limit': min(limit, 50000)}
    start_ns, end_ns = params['timestamp.gte'], params['timestamp.lt']
    records, pages, errors = [], [], []
    seen = set()
    more = False
    for page in range(max_pages):
        validate_page_url(url)
        if unquote(urlsplit(url).path) != expected_path:
            raise ValueError('Quote pagination changed ticker')
        if url in seen:
            raise ValueError('Quote pagination cycle')
        seen.add(url)
        page_key = hashlib.sha256(json.dumps({'url': url, 'params': params}, sort_keys=True).encode()).hexdigest()
        metadata_path = directory / (page_key + '.metadata.json')
        if metadata_path.exists():
            metadata = json.loads(metadata_path.read_text())
            if not re.fullmatch(r'[0-9a-f]{64}', metadata.get('sha256', '')):
                raise ValueError('Invalid quote cache hash')
            raw_path = directory / (metadata['sha256'] + '.json')
            raw = raw_path.read_bytes()
            if hashlib.sha256(raw).hexdigest() != metadata['sha256']:
                raise ValueError('Quote cache hash mismatch')
            payload = json.loads(raw)
        else:
            response = session.get(url, params=params, timeout=30)
            if response.status_code != 200:
                return {'request_id': request_id, 'status': 'access_blocked' if response.status_code in (401, 403, 429) else 'request_failed',
                        'http_status': response.status_code, 'quotes': records, 'pages': pages, 'complete': False}
            payload = response.json()
            raw = response.content
            digest = hashlib.sha256(raw).hexdigest()
            raw_path = directory / (digest + '.json')
            if raw_path.exists() and hashlib.sha256(raw_path.read_bytes()).hexdigest() != digest:
                raise ValueError('Quote cache hash mismatch')
            if not raw_path.exists():
                raw_path.write_bytes(raw)
            metadata = {'sha256': digest, 'retrieved_at_utc': datetime.now(timezone.utc).isoformat(),
                        'provider': 'Massive', 'request_id': request_id}
            atomic_json(metadata_path, metadata)
        pages.append(metadata)
        page_truncated = False
        for source in payload.get('results', []):
            if len(records) >= limit:
                page_truncated = True
                break
            try:
                sip = source['sip_timestamp']
                when = sip_iso(sip)
                if not start_ns <= sip < end_ns:
                    raise ValueError('Quote outside requested interval')
                row = {'quote_id': hashlib.sha256((ticker + ':' + json.dumps(source, sort_keys=True)).encode()).hexdigest(),
                       'ticker': ticker, 'timestamp_utc': when, 'sip_timestamp': sip,
                       'retrieved_at_utc': metadata['retrieved_at_utc'], 'receipt_at_utc': None,
                       'receipt_basis': 'historical_system_receipt_unknown', 'source_sha256': metadata['sha256'],
                       'bid': source['bid_price'], 'ask': source['ask_price'],
                       'bid_size': source['bid_size'], 'ask_size': source['ask_size']}
                records.append(row)
            except (KeyError, ValueError, TypeError) as error:
                errors.append({'reason': str(error), 'source_sha256': metadata['sha256']})
        next_url = payload.get('next_url')
        more = bool(next_url) or page_truncated
        if not next_url or len(records) >= limit:
            break
        url, params = validate_page_url(next_url), None
    return {'request_id': request_id, 'status': 'truncated' if more else ('completed_with_gaps' if errors else 'completed'),
            'complete': not more and not errors, 'quotes': records, 'pages': pages, 'errors': errors}
