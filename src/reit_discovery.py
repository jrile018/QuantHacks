"""Observed discovery adapters and conservative filing-backed eligibility cues."""
from html.parser import HTMLParser
import re


def normalized_name(value):
    value=str(value).lower().strip()
    value=re.sub(r'\s*/[a-z]{2}/\s*$','',value)
    value=re.sub(r'\bcorporation\b','corp',value)
    value=re.sub(r'\bincorporated\b','inc',value)
    value=re.sub(r'\bclass\s+[a-z]\b','',value)
    value=value.replace('&','and')
    return re.sub(r'[^a-z0-9]','',value)


def reitwatch_candidates(pages, *, source_url, source_sha256, retrieved_at=None):
    rows=[]
    for page in pages:
        text=page['text']
        if 'REITs in the FTSE Nareit All REITs Index' not in text:
            continue
        for match in re.finditer(r'^\s*\d+\s+(.+?)\s+([A-Z][A-Z0-9.\-]{0,7})\s+(Equity|Mortgage)\b.*$',text,re.MULTILINE):
            quote=match.group(0).strip()
            rows.append({'cik':None,'name':match.group(1).strip(),'ticker':match.group(2),
                         'reit_category':match.group(3),'source_url':source_url,'source_sha256':source_sha256,
                         'source_quote':quote,'source_locator':f"page {page['number']}, character {match.start()}",
                         'retrieved_at':retrieved_at,'discovery_status':'candidate_only',
                         'limitation':'Dated index constituent; neither exhaustive universe nor historical ticker-to-CIK proof.'})
    return rows


def resolve_candidates(candidates, exchange_map):
    by_ticker={}
    for row in exchange_map:
        by_ticker.setdefault(row['ticker'],[]).append(row)
    result=[]
    for candidate in candidates:
        item=dict(candidate)
        matches=by_ticker.get(candidate['ticker'],[])
        exact=[m for m in matches if normalized_name(m['name'])==normalized_name(candidate['name'])]
        if len(exact)==1:
            item.update(cik=exact[0]['cik'],exchange=exact[0]['exchange'],resolution='current_ticker_and_name_candidate',
                        security_id=exact[0]['cik']+':'+candidate['ticker']+':common_candidate')
        else:
            item.update(cik=None,resolution='ticker_name_conflict' if matches else 'no_current_exchange_match',
                        possible_current_matches=matches)
        result.append(item)
    return result


class FilingText(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.parts=[]
        self.rows=[]
        self.row=None
        self.cell=None
        self.hidden=[]

    def handle_starttag(self,tag,attrs):
        attrs=dict(attrs)
        if tag in ('script','style','ix:header','ix:hidden'):
            self.hidden.append(tag)
            return
        if self.hidden:
            return
        if tag=='tr':
            self.row=[]
        if tag in ('td','th') and self.row is not None:
            self.cell=[]
        if tag in ('p','div','tr','br'):
            self.parts.append('\n')

    def handle_endtag(self,tag):
        if self.hidden:
            if self.hidden[-1]==tag:
                self.hidden.pop()
            return
        if tag in ('td','th') and self.cell is not None:
            if self.row is not None:
                self.row.append(' '.join(''.join(self.cell).split()))
            self.cell=None
        if tag=='tr' and self.row is not None:
            self.rows.append(self.row)
            self.row=None
        if tag in ('p','div','tr'):
            self.parts.append('\n')

    def handle_data(self,text):
        if not self.hidden:
            self.parts.append(text)
            if self.cell is not None:
                self.cell.append(text)


def _tax_status_evidence(base, paragraphs):
    """Retain qualification context; contradictions require manual dated review."""
    subject=r'\b(?:We|The Company|The Trust)\b'
    tax=r'\b(?:real estate investment trust|REIT)\b'
    current=re.compile(subject+r'\s+(?:'
        r'(?:have|has)\s+elected\s+to\s+be\s+(?:taxed|treated)|'
        r'(?:are|is)\s+(?:taxed|treated)|operate(?:s)?|qualif(?:y|ies)|'
        r'continue(?:s)?\s+to\s+qualify)\s+as\s+(?:a\s+)?'+tax,re.I)
    historical=re.compile(subject+r'\s+(?:(?:have|has)\s+)?'
        r'(?:elected\s+to\s+be\s+(?:taxed|treated)|qualified)\s+as\s+(?:a\s+)?'+tax,re.I)
    negative=(r'(?:revoked|terminated|withdrawn|abandoned)|'
        r'(?:(?:do|does|did|have|has)\s+not|no\s+longer|fail(?:ed|s)?\s+to|'
        r'ceas(?:ed|es)\s+to)\s+qualif(?:y|ies|ied)|'
        r'(?:are|is|were|was)\s+(?:not|never|no\s+longer)\s+(?:qualified|taxed|treated|a\b)')
    contradiction=re.compile(r'(?:'+subject+r'[^.!?;]{0,200}(?:'+negative+r')[^.!?;]{0,100}'+tax+
        r'|'+subject+r'[^.!?;]{0,200}'+tax+r'[^.!?;]{0,100}(?:'+negative+r')'+
        r'|\bOur\s+'+tax+r'\s+(?:election|status|qualification)[^.!?;]{0,100}(?:'+negative+r')'+
        r'|\bOur\s+election[^.!?;]{0,100}'+tax+r'[^.!?;]{0,100}(?:'+negative+r'))',re.I)
    uncertain=re.compile(r'\b(?:if|unless|could|would|should|may|might|assuming|believe|intend|intends|expect|expects)\b',re.I)
    positive,review,blockers=[],[],[]
    for index,paragraph in enumerate(paragraphs):
        locator='normalized filing paragraph '+str(index)
        for clause in re.split(r'(?<=[.!?;])\s+',paragraph):
            negative_match=contradiction.search(clause)
            if negative_match and not uncertain.search(clause[:negative_match.end()]):
                blockers.append(dict(base,kind='reit_status_review',value=None,review_required=True,
                    reason='contradictory_or_terminated_tax_status',quote=paragraph,locator=locator))
            match=current.search(clause)
            if match:
                if uncertain.search(clause):
                    review.append(dict(base,kind='reit_status_review',value=None,review_required=True,
                        reason='conditional_or_uncertain_qualification',quote=paragraph,locator=locator))
                else:
                    positive.append(dict(base,kind='reit_status',value=True,quote=paragraph,locator=locator))
            elif historical.search(clause):
                review.append(dict(base,kind='reit_status_review',value=None,review_required=True,
                    reason='historical_or_conditional_qualification',quote=paragraph,locator=locator))
    if blockers:
        # An earlier election cannot resolve an explicitly terminated or failed
        # status elsewhere. Retain both contexts without inventing effective dates.
        review.extend(dict(row,kind='reit_status_review',value=None,review_required=True,
                           reason='positive_claim_conflicts_with_tax_status') for row in positive)
        rows=blockers+review
    else:
        rows=positive[:1]+review
    return list({(row['kind'],row['quote'],row.get('reason')):row for row in rows}.values())


def filing_eligibility_evidence(document, html):
    """Current collection eligibility only; retrieval clock is not backdated.

    A dated filing claim has an evidence interval from its report date. The
    current retrieval is its supported knowledge clock here. Historical market
    eligibility needs separately established publication/continuity evidence.
    """
    parser=FilingText()
    parser.feed(html)
    paragraphs=[' '.join(part.split()) for part in ''.join(parser.parts).splitlines() if part.strip()]
    text=' '.join(paragraphs)
    if not document.get('issuer') or normalized_name(document['issuer']) not in normalized_name(text[:30000]):
        return []
    if not document.get('report_date') or not document.get('retrieved_at'):
        return []
    base={key:document[key] for key in ('cik','ticker','security_id')}
    base.update(valid_from=document['report_date'],known_from=document['retrieved_at'],
                source_available_at=document['retrieved_at'],source_url=document['url'],
                source_sha256=document['sha256'],source_path=document.get('source_path'),
                clock_basis='current_retrieval_only',historical_trading_ready=False)
    proof=_tax_status_evidence(base,paragraphs)
    exchanges={'new york stock exchange':'NYSE','nyse':'NYSE','nasdaq':'Nasdaq','nasdaq stock market':'Nasdaq',
               'nasdaq global select market':'Nasdaq','nasdaq global market':'Nasdaq','nyse american':'NYSE American'}
    for index,cells in enumerate(parser.rows):
        joined=' | '.join(cells)
        if not any(cell.strip()==document['ticker'] for cell in cells):
            continue
        title=next((c for c in cells if re.search(r'\b(common stock|common shares|shares of beneficial interest)\b',c,re.I)
                    and not re.search(r'\bpreferred\b',c,re.I)),None)
        exchange=None
        for cell in cells:
            normalized=' '.join(cell.lower().split()).strip('® ')
            normalized=re.sub(r'^the\s+','',normalized)
            normalized=re.sub(r'\s+llc$','',normalized)
            if normalized in exchanges:
                exchange=exchanges[normalized]
        if title and exchange:
            proof.extend([dict(base,kind='listing',value=True,exchange=exchange,quote=joined,locator='cover table row '+str(index)),
                          dict(base,kind='security_type',value='common',quote=joined,locator='cover table row '+str(index))])
            break
    return proof
