"""Record October 3 source-context review decisions; never infer spending from these."""
import json
import re
import pandas as pd
from extract_infrastructure_evidence import HERE, OUT
from review_infrastructure_sources import source_text

# Each amount was read in the full cached SEC footnote, including adjacent clauses.
REVIEWS = [
 ('PLTR','a5a5dbb9db676eb1cb68e75f',1490000000,
  r'minimum annual commitment to purchase cloud hosting services of at least \$ 1\.49 billion over six contract years[^.]*\.',
  'Reported six-contract-year amount; annual minimum schedule and carryover conditions exist. Do not multiply this amount by six.'),
 ('CRWD','15c5dd48db836c6a384a4b18',600000000,
  r'Under the new pricing addendum, the minimum commitment is \$ 600\.0 million of cloud services from AWS through September 2026\.',
  'AWS contract minimum, not remaining obligations or annual expense.'),
 ('PATH','c0506c2f1b20f171de9e4dcd',138100000,
  r'we made commitments to purchase \$ 138\.1 million of cloud infrastructure services from a third-party vendor',
  'Separate $35.8m alliance service-credit commitments are excluded; mixed total purchase-obligation table is excluded.'),
 ('SOUN','2057f8c14b989eaceffa082d',98000000,
  r'Company committed to pay a minimum of \$ 98\.0 million in cloud costs over a seven-year period subject to variable increases based on usage\.',
  'Seven-year platform-hosting minimum; variable usage increases and remaining obligations are distinct.'),
 ('GWRE','c2b6967f320efb6c340731d3',600000000,
  r'entered into a new agreement with a cloud infrastructure services provider for a total obligation of \$ 600 million over a five-year period\.',
  'Replacement five-year agreement; not $600m annual expenditure.'),
 ('ESTC','f76c4177bdbafc37cd59b0c6',270000000,
  r'amendment to a non-cancelable cloud hosting capacity agreement, effective December 31, 2022, for a total purchase commitment of \$ 270\.0 million payable over the four years following the date of the agreement\.',
  'Four-year amended cloud-hosting commitment.'),
 ('S','07aa7f1a61b8ac06a2e066d4',860000000,
  r'agreement with a cloud infrastructure vendor, under which we committed to spend an aggregate of at least \$860\.0 million between March 2023 and February 2029\.',
  'Contract interval stated as months; source references a March 2023 annual report, so this observed June filing is not claimed as the first disclosure.'),
 ('NOW','9f7ca983407a90b000879bb6',805000000,
  r'agreements with cloud service providers, under which we have committed to spend an aggregate of \$ 805 million through 2029 on cloud services\.',
  'Aggregate cloud agreements; adjacent general operating commitments and debt principal are excluded.'),
 ('AI','d8da432e953893f6385979c5',355000000,
  r'remaining purchase commitments of \$ 355\.0 million related to cloud hosting and associated services',
  'Cloud and associated services remaining commitment. Separate $43.5m professional services excluded. Adjacent incurred costs cover both arrangements and are not treated as cloud-only expense.'),
 ('GTLB','f0a1a34a78626788bdcfad2d',130000000,
  r'new \$ 130 million, five-year cloud infrastructure agreement entered into during the three months ended April 30, 2025',
  'Cloud agreement amount only; mixed $238.5m total purchase obligations excluded. Annual minimum range is not actual annual spending.'),
 ('FIG','6cecef13fa45fd45440c2892',545000000,
  r'Company committed to purchase a minimum of \$ 545\.0 million in cloud hosting services over the next five years',
  'May 2025 replacement contract total; $535.8m June remaining minimum obligations are distinct.'),
 ('MDB','5d2c2e9a39bc8ac5eea444c9',300000000,
  r'renewal agreement with a cloud infrastructure provider that includes a non-cancelable commitment of \$ 300 million to be paid over a period from October 2025 through October 2028\.',
  'Three-year cloud renewal minimum; month-only dates preserved in source text.'),
]


def main():
    path=HERE/'infrastructure_review_registry.json'
    registry=json.loads(path.read_text(encoding='utf-8'))
    candidates=pd.read_csv(OUT/'cloud_commitment_amount_candidates.csv').fillna('')
    old={r['evidence_id']:r for r in registry.get('additional_cloud_commitment_reviews',[])}
    reviews=[]
    for ticker,evidence_id,amount,pattern,note in REVIEWS:
        selected=candidates[candidates.ticker.eq(ticker)&candidates.evidence_id.eq(evidence_id)&candidates.amount_usd_candidate.eq(amount)]
        if len(selected)!=1: raise ValueError('Review candidate missing or ambiguous: '+ticker)
        text,digest=source_text(selected.iloc[0].local_path)
        if not re.search(pattern,text): raise ValueError('Source clause mismatch: '+ticker)
        if evidence_id in old and old[evidence_id]['source_sha256']!=digest:
            raise ValueError('Source changed; fresh manual review required: '+ticker)
        remaining=ticker=='AI'
        reviews.append({'ticker':ticker,'evidence_id':evidence_id,'amount_usd':amount,'source_pattern':pattern,
                        'source_sha256':digest,'scope_note':note,
                        'metric':'cloud_remaining_obligations' if remaining else 'cloud_contract_minimum_total',
                        'measure_type':'remaining_cloud_and_associated_services_commitment_not_cash_paid' if remaining else 'contract_total_not_period_expense'})
    registry['additional_cloud_commitment_reviews']=reviews
    path.write_text(json.dumps(registry,indent=2,ensure_ascii=False)+'\n',encoding='utf-8')
    print('Registered source-checked cloud commitment reviews:',len(reviews))


if __name__=='__main__':
    main()
