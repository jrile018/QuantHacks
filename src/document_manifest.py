"""Offline SEC submission inventory and verified immutable download cache."""
import hashlib
import html
import binascii
import json
import os
import re
import tempfile
import threading
import time
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlsplit, unquote
from urllib.request import Request, urlopen, build_opener, HTTPRedirectHandler
from urllib.error import HTTPError

SCHEMA_VERSION = '1.0'


def _identity(cik, accession):
    cik = str(cik)
    accession = str(accession)
    if not re.fullmatch(r'\d{1,10}', cik) or int(cik) == 0:
        raise ValueError('Invalid CIK')
    if not re.fullmatch(r'\d{10}-\d{2}-\d{6}', accession):
        raise ValueError('Invalid accession')
    return cik.zfill(10), accession


def validate_sec_url(url, cik, accession):
    cik, accession = _identity(cik, accession)
    parsed = urlsplit(url)
    path = unquote(parsed.path)
    if (parsed.scheme != 'https' or parsed.hostname not in {'sec.gov', 'www.sec.gov'}
            or parsed.username or parsed.password or parsed.port not in (None, 443)
            or parsed.query or parsed.fragment or '\\' in path
            or any(p in {'.','..'} for p in path.split('/'))):
        raise ValueError('Invalid SEC archive URL')
    prefix = '/Archives/edgar/data/' + str(int(cik)) + '/'
    suffix = path[len(prefix):] if path.startswith(prefix) else ''
    if suffix != accession + '.txt' and not re.fullmatch(re.escape(accession.replace('-','')) + r'/[A-Za-z0-9_.-]+', suffix):
        raise ValueError('SEC archive identity mismatch')
    return url


def atomic_json(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(dir=path.parent, suffix='.tmp')
    try:
        with os.fdopen(fd, 'w', encoding='utf-8') as handle:
            json.dump(value, handle, indent=2)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary): os.unlink(temporary)


def inventory_from_submission(row, payload):
    cik, accession = _identity(row['cik'], row['accession'])
    header = payload.split(b'<DOCUMENT>', 1)[0].decode('ascii', errors='replace')
    header_accessions = re.findall(r'(?:ACCESSION NUMBER\s*:\s*|<SEC-DOCUMENT>\s*)(\d{10}-\d{2}-\d{6})', header, re.I)
    if any(value != accession for value in header_accessions):
        raise ValueError('Submission accession identity mismatch')
    filer = re.search(r'\bFILER\s*:(.*?)(?=\b(?:REPORTING-OWNER|SUBJECT COMPANY|FILED BY|ISSUER)\s*:|$)', header, re.I|re.S)
    company = re.search(r'\bCOMPANY DATA\s*:(.*?)(?=\b(?:FILING VALUES|BUSINESS ADDRESS|MAIL ADDRESS|FORMER COMPANY)\s*:|$)', filer.group(1), re.I|re.S) if filer else None
    issuer_ciks = re.findall(r'CENTRAL INDEX KEY\s*:\s*(\d+)', company.group(1), re.I) if company else []
    if any(_identity(value, accession)[0] != cik for value in issuer_ciks):
        raise ValueError('Submission issuer identity mismatch')
    identity_status = 'verified' if header_accessions and issuer_ciks else 'unverified'
    amends = row.get('amends_accession') or None
    if amends: _identity(cik, amends)
    group = f'{cik}:{amends or accession}'
    base = f'https://www.sec.gov/Archives/edgar/data/{int(cik)}/{accession.replace("-", "")}/'
    records = []
    def record(filename, kind, content, role, status, items=(), container_hash=None, encoding='raw'):
        digest = hashlib.sha256(content).hexdigest() if content is not None else None
        source_url = base + filename if filename else None
        if source_url: validate_sec_url(source_url, cik, accession)
        result = dict(schema_version=SCHEMA_VERSION, document_id=f'{cik}:{accession}:{filename or (status + ":" + kind)}', cik=cik,
                      accession=accession, form=row.get('form','8-K'), sec_items=list(items), document_role=role,
                      exhibit_type=kind if kind.startswith('EX-') else None, filename=filename,
                      source_url=source_url, url_status='constructed' if source_url else 'missing', source_sha256=digest,
                      content_type='application/pdf' if filename and filename.lower().endswith('.pdf') else 'text/html' if filename and filename.lower().endswith(('.htm','.html')) else 'text/plain',
                      receipt_at_utc=None, sec_acceptance_at_utc=row.get('acceptance_datetime') or None,
                      public_at_utc=None, public_at_evidence=None, event_group_id=group,
                      amends_accession=amends, inventory_status=status,
                      content=content.decode('utf-8',errors='replace') if content is not None else None,
                      content_bytes=content, duplicate_of_document_id=None, identity_status=identity_status,
                      container_content_sha256=container_hash, source_encoding=encoding)
        prior = next((d for d in records if digest and d['source_sha256']==digest), None)
        if prior: result['duplicate_of_document_id']=prior['document_id']
        records.append(result)
    for block in re.findall(rb'<DOCUMENT>\s*(.*?)</DOCUMENT>', payload, flags=re.I|re.S):
        def field(tag):
            match = re.search(rb'<' + tag + rb'>[^\S\r\n]*([^\r\n<]*)', block, re.I)
            return match.group(1).decode('ascii',errors='replace').strip() if match else ''
        kind, filename = field(b'TYPE').upper(), field(b'FILENAME')
        body = re.search(rb'<TEXT>(.*?)</TEXT>', block, re.I|re.S)
        content = body.group(1) if body else None
        container_hash = hashlib.sha256(content).hexdigest() if content is not None else None
        encoding = 'raw'
        unsupported = False
        if filename.lower().endswith('.pdf') and content is not None:
            candidate = re.sub(rb'^\s*<PDF>|</PDF>\s*$', b'', content, flags=re.I)
            if candidate.lstrip().startswith(b'%PDF-'):
                content = candidate
            else:
                encoded = re.search(rb'(?m)^begin [0-7]{3} [^\r\n]+\r?\n(.*?)^end\s*$', candidate, re.S|re.M)
                try:
                    decoded = b''.join(binascii.a2b_uu(line) for line in encoded.group(1).splitlines()) if encoded else b''
                except (binascii.Error, ValueError):
                    decoded = b''
                if decoded.startswith(b'%PDF-'):
                    content, encoding = decoded, 'sec_uuencode'
                else:
                    content, encoding, unsupported = None, 'unsupported', True
        plain = html.unescape(re.sub(r'<[^>]+>', ' ', (content or b'').decode('utf-8',errors='replace')))
        primary = kind in {'8-K','8-K/A'}
        items = sorted(set(re.findall(r'\bItem\s+(\d\.\d{2})\b', plain, re.I))) if primary else []
        role = 'primary_filing' if primary else 'other_exhibit' if kind.startswith('EX-') else 'unclassified'
        if kind.startswith('EX-99'):
            role = 'earnings_release' if re.search(r'\b(earnings|financial results|quarterly results|results of operations)\b',plain,re.I) and re.search(r'\b(revenue|income|sales|earnings per share|profit|loss)\b',plain,re.I) else 'unclassified'
        record(filename or None, kind, content, role, 'encoded_binary_unsupported' if unsupported else 'complete' if content is not None and filename else 'incomplete_text' if content is None else 'missing_filename', items, container_hash, encoding)
    primaries = [d for d in records if d['document_role']=='primary_filing']
    if not primaries: record(None, '', None, 'primary_filing', 'missing_primary')
    refs = set()
    for d in primaries:
        refs.update(re.findall(r'\bExhibit\s+(99(?:\.\d+)?)\b',html.unescape(re.sub(r'<[^>]+>', ' ', d['content'] or '')),re.I))
    present = {d['exhibit_type'][3:] for d in records if d['exhibit_type']}
    for ref in sorted(refs-present): record(None, 'EX-'+ref, None, 'unclassified', 'missing_exhibit')
    return records


class SECBlocked(RuntimeError):
    """SEC denied access; the caller must stop collection."""


class _ArchiveRedirect(HTTPRedirectHandler):
    def __init__(self, cik, accession): self.cik, self.accession = cik, accession
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        validate_sec_url(newurl, self.cik, self.accession)
        return super().redirect_request(req, fp, code, msg, headers, newurl)


# Shared across fetchers in a process, keeping aggregate request rate <= five/sec.
_rate_lock = threading.Lock()
_last_request = 0.0


class SecFetcher:
    def __init__(self, cache_dir, contact_email, rate=5):
        if not contact_email or '\n' in contact_email or '\r' in contact_email: raise ValueError('SEC contact email required')
        if not 0 < rate <= 5: raise ValueError('SEC request rate must be between zero and five')
        self.cache_dir, self.contact_email, self.rate = Path(cache_dir), contact_email, rate
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self.blocked = False

    def fetch(self, url, cik, accession):
        global _last_request
        validate_sec_url(url, cik, accession)
        metadata_path = self.cache_dir / (hashlib.sha256(url.encode()).hexdigest()+'.json')
        if metadata_path.exists():
            metadata = json.loads(metadata_path.read_text(encoding='utf-8'))
            expected_path = self.cache_dir / metadata['source_sha256']
            if Path(metadata['path']).resolve() != expected_path.resolve() or hashlib.sha256(expected_path.read_bytes()).hexdigest() != metadata['source_sha256']:
                raise ValueError('SEC cache content hash mismatch')
            return metadata
        if self.blocked: raise SECBlocked('SEC collection stopped after access block')
        with _rate_lock:
            time.sleep(max(0, 1/self.rate - (time.monotonic()-_last_request)))
            _last_request = time.monotonic()
        request = Request(url, headers={'User-Agent':'QuantHaxs document research '+self.contact_email})
        # Per-request opener ensures redirect targets are validated before access.
        opener = build_opener(_ArchiveRedirect(cik, accession))
        try:
            with urlopen(request, opener=opener) as response:
                validate_sec_url(response.geturl(), cik, accession)
                content = response.read()
                content_type = response.headers.get('Content-Type','application/octet-stream').split(';')[0]
        except HTTPError as error:
            if error.code in (403,429):
                self.blocked=True
                raise SECBlocked(f'SEC access blocked ({error.code})') from None
            raise
        digest = hashlib.sha256(content).hexdigest()
        path = self.cache_dir / digest
        if path.exists():
            if hashlib.sha256(path.read_bytes()).hexdigest()!=digest: raise ValueError('SEC cache content hash mismatch')
        else:
            fd, temporary = tempfile.mkstemp(dir=self.cache_dir, suffix='.tmp')
            try:
                with os.fdopen(fd,'wb') as handle:
                    handle.write(content); handle.flush(); os.fsync(handle.fileno())
                os.replace(temporary,path)
            finally:
                if os.path.exists(temporary): os.unlink(temporary)
        metadata = dict(path=str(path.resolve()), source_sha256=digest, receipt_at_utc=datetime.now(timezone.utc).isoformat(), content_type=content_type, source_url=url, url_status='fetched_verified')
        atomic_json(metadata_path,metadata)
        return metadata


# Isolated transport seam for offline tests; urllib's normal urlopen has no opener argument.
_urllib_urlopen = urlopen

def urlopen(request, *, opener=None):
    return opener.open(request, timeout=30) if opener else _urllib_urlopen(request, timeout=30)
