"""Pin explicitly inspected CapEx guidance clauses, bounds, horizon and scope.

This registry deliberately admits only the evidence IDs reviewed for this task.
It does not promote all regex dollar matches to confirmed guidance.
"""
import re
import datetime as dt
from collect_power_capex import OUT, read, write

REVIEWED_IDS={
 '915d16e12e2666a1a82297cd','8cd36c0a25e4750bd92fcb46','0ed386c9958600170e14d604',
 '953b084656694d9c4335da92','6d319cca22b2058386e94875',
 'ab48d30df9b8b56528e17242','6ef863c443e04aa537a97f1d','e4aba323e0e81cce7e5b5296',
 'c2955ac7bcce6d31ce53f537','68ba7ee7ecbafb14fe61345f',
 '4403d0bb61c837d68444b74c','cf8c411fda65e80b3ae7ac28','3f584291df57a1c34a936306',
 '91e47f8883c09bd88fdcc272','41a2dce14111123fc5001609',
}


def main():
    registry=[]
    for r in read(OUT/'filing_candidates.csv'):
        if r['evidence_id'] in REVIEWED_IDS:
            excerpt=r['excerpt']
            # Inspect only the targeted forward CapEx phrase, not nearby historical tables.
            if r['ticker']=='QLYS':
                clause=excerpt[excerpt.index('Cash outflow for capital expenditures'):]
                horizon='annual'
                scope='reported_cash_capex_guidance_not_explicitly_data_center_or_PPE_only'
            elif r['ticker']=='BLKB':
                clause=excerpt.split('Investing Cash Flow ')[1].split('. 20')[0]
                horizon='annual'
                scope='total_capex_includes_capitalized_software_development_not_PPE_only'
            else:
                clause=excerpt
                horizon='remaining_year'
                scope='mixed_computer_software_equipment_office_buildout_and_possible_land_not_data_center_only'
            year=re.search(r'\b20\d{2}\b',clause).group(0)
            amounts=re.findall(r'\$([\d,.]+)\s*million',clause)
            if len(amounts)!=2:
                raise ValueError('Reviewed range changed: '+r['evidence_id'])
            low,high=[float(n.replace(',',''))*1e6 for n in amounts]
            if not 0<=low<=high:
                raise ValueError('Invalid reviewed bounds')
            registry.append(dict(evidence_id=r['evidence_id'],cik=r['cik'],ticker=r['ticker'],
                                 low_usd=low,high_usd=high,upper_bound_usd='',
                                 horizon_type=horizon,horizon_end=year+'-12-31',
                                 scope=scope,source_clause=clause,source_sha256=r['source_sha256'],
                                 review_status='exact_clause_amounts_and_horizon_inspected'))
        elif r['ticker']=='BKYI' and r['excerpt']=='We expect capital expenditures to be less than $100,000 during the next twelve months.':
            # Explicit upper bound only; do not invent a lower bound or point estimate.
            registry.append(dict(evidence_id=r['evidence_id'],cik=r['cik'],ticker=r['ticker'],
                                 low_usd='',high_usd='',upper_bound_usd=100000,
                                 horizon_type='next_12_months',
                                 horizon_end=(dt.date.fromisoformat(r['filed_date'])+dt.timedelta(days=365)).isoformat(),
                                 scope='total_capex_unspecified_asset_scope; horizon_end_assumed_filing_date_plus_365_days',
                                 source_clause=r['excerpt'],source_sha256=r['source_sha256'],
                                 review_status='exact_upper_bound_clause_inspected'))
    if not REVIEWED_IDS.issubset({r['evidence_id'] for r in registry}):
        raise ValueError('Reviewed evidence disappeared')
    write(OUT/'reviewed_capex_guidance.csv',registry)
    print('Reviewed numeric guidance disclosures',len(registry))


if __name__=='__main__':
    main()
