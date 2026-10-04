"""
45_offer_trades_v2.py - join the leak-free trade list (script 44) with the real quotes (script 22) into one trade file.

Move of the trade : from adjusted prices (next open to the close 5 market days after the signal), stock and XBI. Correct across splits.
Cost of the trade : from real Massive quotes. Half the stock spread on the way in, half on the way out, plus the same for the XBI hedge.
No price floor is applied here. The $1 rule is already in the trade list: real close on the SIGNAL day at least $1 (known before the trade).
Output: data/fds/offer_strategy_trades_v2.csv   Run after:  python 22_stock_real_costs.py --slice offer_signal_slice_v2.csv --out stock_trades_real_v2.csv
"""
import os, numpy as np, pandas as pd
here = os.path.dirname(os.path.abspath(__file__)); FDS = os.path.join(here, '..', 'data', 'fds')
N = pd.read_csv(os.path.join(FDS, 'offer_trades_v2.csv')); Q = pd.read_csv(os.path.join(FDS, 'stock_trades_real_v2.csv')).drop_duplicates(['cik', 'signal'])
N['entry'] = pd.to_datetime(N.entry).dt.strftime('%Y%m%d').astype(int); N['exit'] = pd.to_datetime(N['exit']).dt.strftime('%Y%m%d').astype(int)
T = N[['cik', 'tk', 'signal', 'entry', 'exit', 'p', 'hit', 'px_close_real', 'stock', 'xbi', 'gross']].merge(
    Q[['cik', 'signal', 'entry', 'exit', 'status', 's_in_bid', 's_in_ask', 's_out_bid', 's_out_ask', 'spread_in', 'spread_out', 'xbi_mid', 'xbi_real']], on=['cik', 'signal'], how='left', suffixes=('', '_q'))
print(f'trades in the leak-free list {len(N)} | quotes pulled {T.status.notna().sum()} | all four quotes found {(T.status == 0).sum()} | not pulled yet {T.status.isna().sum()} | no quote found {(T.status > 0).sum()}')
bad = T[(T.status == 0) & ((T.entry != T.entry_q) | (T['exit'] != T.exit_q))]
if len(bad): print('WARNING entry or exit date differs between the two files for', len(bad), 'trades'); print(bad[['tk', 'signal', 'entry', 'entry_q', 'exit', 'exit_q']].to_string(index=False))
T = T[T.status == 0].copy()
T['px_in'] = (T.s_in_bid + T.s_in_ask) / 2
T['cost'] = (T.spread_in + T.spread_out) / 2 + (T.xbi_mid - T.xbi_real)
T = T.rename(columns={'stock': 'adj_stock', 'xbi': 'adj_xbi'}); T['net'] = T.gross - T.cost
T['m'] = pd.to_datetime(T.entry.astype(str)).dt.strftime('%Y-%m')
chk = (T.px_in / T.px_close_real); print(f'check: real entry quote vs real close the day before, median ratio {chk.median():.3f}, more than 2x apart in {((chk > 2) | (chk < .5)).sum()} trades')
print(f'entry quote under $1 (real close the day before was at least $1): {(T.px_in < 1).sum()} trades')
print(f'cost per trade: mean {T.cost.mean()*100:.2f}%  median {T.cost.median()*100:.2f}%  | 2025 mean {T.cost[T.signal < 20260101].mean()*100:.2f}%  2026 mean {T.cost[T.signal >= 20260101].mean()*100:.2f}%')
T[['cik', 'tk', 'signal', 'entry', 'exit', 'p', 'hit', 'px_close_real', 'px_in', 'spread_in', 'spread_out', 'adj_stock', 'adj_xbi', 'cost', 'gross', 'net', 'm']].to_csv(os.path.join(FDS, 'offer_strategy_trades_v2.csv'), index=False)
print('saved offer_strategy_trades_v2.csv', len(T), 'trades')
