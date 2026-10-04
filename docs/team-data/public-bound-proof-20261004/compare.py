"""Offline comparison of historical capture with Industry's retained February originals."""
import hashlib
import html
from html.parser import HTMLParser
import json
from pathlib import Path
import re
import unicodedata

class Text(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.parts = []
        self.skip = 0
    def handle_starttag(self, tag, attrs):
        if tag in {'script','style','noscript'}: self.skip += 1
        elif tag in {'p','div','br','tr','li','h1','h2','h3'}: self.parts.append(' ')
    def handle_endtag(self, tag):
        if tag in {'script','style','noscript'} and self.skip: self.skip -= 1
        elif tag in {'p','div','tr','li','h1','h2','h3'}: self.parts.append(' ')
    def handle_data(self, data):
        if not self.skip: self.parts.append(data)
def normalized(data):
    p = Text()
    p.feed(data.decode('utf-8',errors='replace'))
    return ws(html.unescape(''.join(p.parts)))

here = Path(__file__).resolve().parent
source = Path('/tmp/quanthaxs-reit-pilot-repair-20261004-v1/source-pack')
raw = source / 'objects/d3e0d2b13d9b4ff50cb104362855975b96dfc354804343f5bdfe1a9c842c3a62'
native = source / 'release-sources-v2/0001053507-24-000009-press_release_exhibit.txt'
capture = here / 'feb_sec_capture.raw'
current = here / 'feb_sec_current.raw'
def sha(b): return hashlib.sha256(b).hexdigest()
def ws(s): return re.sub(r'\s+', ' ', unicodedata.normalize('NFKC', s).replace('\u00ad','')).strip()
r, n, c, v = raw.read_bytes(), native.read_bytes(), capture.read_bytes(), current.read_bytes()
rt, ct = normalized(r), normalized(c)
nt = ws(n.decode('utf-8'))
first = next((i for i, (x,y) in enumerate(zip(c,r)) if x != y), min(len(c),len(r)))
last = 0
for x,y in zip(reversed(c), reversed(r)):
    if x != y: break
    last += 1
out = {
  'retained_raw_path': str(raw), 'retained_raw_bytes': len(r), 'retained_raw_sha256': sha(r),
  'retained_native_text_path': str(native), 'retained_native_text_bytes': len(n), 'retained_native_text_sha256': sha(n),
  'current_sec_raw_sha256': sha(v), 'current_sec_equals_retained_raw': v == r,
  'archive_raw_sha256': sha(c), 'archive_raw_equals_retained_raw': c == r,
  'archive_vs_retained_first_byte_difference_at': first, 'archive_vs_retained_common_suffix_bytes': last,
  'archive_difference_context_hex': {'archive': c[max(0,first-24):first+80].hex(), 'retained': r[max(0,first-24):first+80].hex()},
  'normalization': 'HTMLParser skips script/style/noscript, decodes entities; Unicode NFKC, remove soft hyphen, collapse whitespace; compare full strings',
  'archive_full_normalized_text_chars': len(ct), 'retained_raw_full_normalized_text_chars': len(rt),
  'archive_full_normalized_text_sha256': sha(ct.encode()), 'retained_raw_full_normalized_text_sha256': sha(rt.encode()),
  'archive_full_normalized_text_equals_retained_raw': ct == rt,
  'retained_native_whitespace_normalized_chars': len(nt), 'retained_native_whitespace_normalized_sha256': sha(nt.encode()),
  'archive_text_equals_retained_native_whitespace_normalized': ct == nt,
}
(here / 'comparison.json').write_text(json.dumps(out, indent=2)+'\n',encoding='utf-8')
print(json.dumps(out, indent=2))
