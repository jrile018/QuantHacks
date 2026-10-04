"""
52_finra_evidence.py - coverage evidence for the FINRA short interest file (lead's audit, A7). Read only.
Reports: settlement dates covered, rows per ticker, tickers with no rows, gaps, and whether listed (not only OTC) names are present.
The files were pulled by script 23 from cdn.finra.org/equity/otcmarket/biweekly/shrtYYYYMMDD.csv; despite the path name FINRA
publishes its consolidated short interest (exchange listed and OTC) in these files. The values are as published at pull time; FINRA
corrections replace earlier values, so a later pull could differ. We cannot reconstruct the as-first-published values.
"""
import os, pandas as pd
here = os.path.dirname(os.path.abspath(__file__)); RAW = os.path.join(here, '..', 'data', 'raw'); FDS = os.path.join(here, '..', 'data', 'fds')
si = pd.read_csv(os.path.join(RAW, 'finra_shortint.csv')); lk = pd.read_csv(os.path.join(FDS, 'fds_lookup_cik_ticker.csv'))
si['settle'] = pd.to_datetime(si.settle.astype(str)); pulled = pd.Timestamp(os.path.getmtime(os.path.join(RAW, 'finra_shortint.csv')), unit='s').date()
d = si.settle.drop_duplicates().sort_values(); gaps = d.diff().dt.days
print(f'file pulled on {pulled} | settlement dates {len(d)} from {d.min().date()} to {d.max().date()} | spacing days: {gaps.value_counts().sort_index().to_dict()}')
print(f'rows {len(si)} | tickers in our universe {len(lk)} | with at least one row {si.ticker.isin(lk.ticker).sum() and si[si.ticker.isin(lk.ticker)].ticker.nunique()} | rows per ticker: median {si.groupby("ticker").size().median():.0f}, min {si.groupby("ticker").size().min()}, max {si.groupby("ticker").size().max()}')
miss = sorted(set(lk.ticker) - set(si.ticker)); print('tickers with NO rows:', miss if miss else 'none')
few = si.groupby('ticker').size(); few = few[few < len(d) * 0.8]; print(f'tickers present on fewer than 80% of dates ({len(few)}):', few.to_dict() if len(few) < 25 else f'{len(few)} tickers')
listed = ['ADMA', 'IOVA', 'OTLK', 'VOR', 'SANA']; print('exchange-listed names present (shows the file is not OTC only):', {t: int((si.ticker == t).sum()) for t in listed})
print('zero short interest rows:', int((si.short_int == 0).sum()), '| missing short interest values:', int(si.short_int.isna().sum()), '(a ticker absent from a date is "not in file", not zero)')
