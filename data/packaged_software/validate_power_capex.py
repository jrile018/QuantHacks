"""Check saved modelling views against sources, clocks and original snapshots."""
import json
import sqlite3
from pathlib import Path
import numpy as np
import pandas as pd
from add_power_capex_features import TARGETS
from collect_power_capex import HERE, OUT, sha


def main():
    manifest=json.loads((OUT/'matrix_update_manifest.json').read_text(encoding='utf-8'))
    coverage=pd.read_csv(OUT/'matrix_feature_coverage.csv')
    features=list(coverage.feature)
    checks={}
    for target in TARGETS:
        if not target.exists():
            continue
        snapshot=OUT/'matrix_before_power_capex'/str(target.relative_to(HERE)).replace('\\','__').replace('/','__')
        base=pd.read_csv(snapshot,dtype=str,keep_default_na=False)
        updated=pd.read_csv(target,dtype=str,keep_default_na=False)
        assert updated[list(base)].equals(base),str(target)+': base changed'
        key='quarter' if 'quarter' in updated else 'period_end'
        assert not updated.duplicated(['cik',key]).any()
        assert updated.cik.nunique()==168
        numeric=pd.read_csv(target,dtype={'cik':str},low_memory=False)
        for feature in features:
            assert (numeric[feature].notna().astype(int)==numeric[feature+'__present']).all()
            for q,g in numeric.groupby(key):
                if g[feature].count()<5:
                    assert g[feature+'__rank'].isna().all()
                if g[feature].nunique()==1 and g[feature].count()>=5:
                    assert (g.loc[g[feature].notna(),feature+'__rank']==0).all()
        checks[str(target.relative_to(HERE))]=dict(rows=len(updated),columns=len(updated.columns),original_cells_preserved=True,
                                                 output_sha256=sha(target.read_bytes()))
    ledger=pd.read_csv(OUT/'matrix_feature_provenance.csv',dtype=str,keep_default_na=False)
    assert not ledger.duplicated(['cik','quarter','feature']).any()
    present=ledger[ledger.value!='']
    assert (present.available_date<=present.decision_date).all()
    assert (present.period_end<=present.decision_date).all()
    assert (present.missing_reason=='').all()
    assert (ledger[ledger.value==''].missing_reason!='').all()
    assert set(present.cik).issubset(set(pd.read_csv(HERE/'packaged_software_companies.csv',dtype=str).cik))
    final=pd.read_csv(HERE/'final/feature_matrix_backtest.csv',dtype={'cik':str},low_memory=False).set_index(['cik','quarter'])
    dictionary=pd.read_csv(HERE/'final/FEATURE_MATRIX_DICTIONARY.csv')
    assert (set(final.columns)|{'cik','quarter'}).issubset(set(dictionary.column))
    for database in [HERE/'output/dataset.sqlite',HERE/'final/dataset.sqlite']:
        with sqlite3.connect('file:'+str(database)+'?mode=ro',uri=True) as con:
            view=pd.read_sql_query('SELECT cik,quarter,'+','.join('"'+f+'"' for f in features)+' FROM fact_feature_matrix',con).set_index(['cik','quarter'])
            shared=final.index.intersection(view.index)
            assert len(shared)==len(view)
            for feature in features:
                assert np.allclose(pd.to_numeric(view.loc[shared,feature],errors='coerce'),final.loc[shared,feature],equal_nan=True),feature
            placeholders=','.join('?' for f in features)
            duplicates=con.execute(f'SELECT COUNT(*) FROM (SELECT cik,period_end,feature,COUNT(*) n FROM fact_panel WHERE feature IN ({placeholders}) GROUP BY cik,period_end,feature HAVING n>1)',features).fetchone()[0]
            assert duplicates==0
            count=con.execute(f'SELECT COUNT(*) FROM fact_panel WHERE feature IN ({placeholders})',features).fetchone()[0]
            assert count==len(ledger)
            checks[str(database.relative_to(HERE))]=dict(shared_rows_verified=len(shared),new_panel_cells_verified=count)
    auctions=pd.read_csv(OUT/'pjm_auctions.csv')
    assert auctions.price_usd_mw_day.tolist()==[50,34.13,28.92,269.92,329.17,333.44,325]
    assert auctions.available_date.tolist()==['2021-06-03','2022-06-22','2023-02-28','2024-07-31','2025-07-23','2025-12-18','2026-07-15']
    ferc=pd.read_csv(OUT/'ferc_search_coverage.csv')
    assert len(ferc)==168 and ferc.cik.nunique()==168
    assert not ferc.status.str.startswith('search_failed').any()
    result=dict(status='PASS',raw_features_added=len(features),final_rows=len(final),final_columns=len(final.columns)+2,
                populated_new_cells=len(present),all_existing_cells_preserved=True,
                selected_future_information_cells=0,ferc_companies_searched=168,
                ferc_truncated_companies=ferc[ferc.status.str.startswith('truncated')].ticker.tolist(),checks=checks)
    (OUT/'validation.json').write_text(json.dumps(result,indent=2)+'\n',encoding='utf-8')
    print(json.dumps(result,indent=2))


if __name__=='__main__':
    main()
