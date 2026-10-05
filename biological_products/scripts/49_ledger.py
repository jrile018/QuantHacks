"""
49_ledger.py - a cash-and-positions LEDGER for the offering short, replacing the weight-based daily curve of script 42.

Why: the lead's audit (A2, A3, A4) found that the old daily curve (a) counted a December trade's January days as "in sample",
(b) held a fixed 20% weight every day, which silently assumes daily rebalancing with no cost, and (c) mixed daily-bar moves with
quote-based costs. This script keeps ONE accounting policy, the one a real account would follow:

  * one continuous account from the first trade to the last, every scheduled market day, idle days included
  * fixed SHARE counts set at entry: stock shorted = slot x NAV at the bid, XBI bought = same dollars at the ask
  * entry at the first quote after the open on the day after the signal, exit at the last quote before the close 5 sessions later
    (the quotes in stock_trades_real_v2.csv, script 22); daily marks in between use the adjusted close series, converted to the
    real share basis, so a reverse split inside a hold changes the share count and not the position value
  * borrow fee accrued daily on the short market value; no interest on cash (conservative); no rebalancing
  * a trade enters only if a slot is free (at most 1/slot positions) and the entry quote is at least $1 (checked at entry, not after)
  * calendar windows are CLIPPED: a window's daily P&L is the account's P&L on the days inside the window. A position open across
    the boundary contributes its December days to the first window and its January days to the second. No profit is counted twice.
  * per-trade statistics are kept as a separate, descriptive table (they are event returns, not account returns)

Run:  python 49_ledger.py            (reads data/fds/offer_strategy_trades_v2.csv, stock_trades_real_v2.csv, data/raw/prices.csv, splits.csv)
Output: reports/ledger_daily.csv, reports/ledger_trades.csv, reports/ledger_summary.csv, and the equity chart reports/ledger_offering_short.png
Self-test:  python 49_ledger.py --selftest   (synthetic trades with known answers; exits non-zero on failure)
"""
import os, sys, argparse
import numpy as np, pandas as pd

ap = argparse.ArgumentParser()
ap.add_argument('--data', default=os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'data'))
ap.add_argument('--out', default=os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'reports'))
ap.add_argument('--trades', default='offer_strategy_trades_v3.csv'); ap.add_argument('--quotes', default='stock_trades_real_v3.csv')
ap.add_argument('--slot', type=float, default=0.20, help='share of NAV shorted per trade at entry (and the same bought in XBI)')
ap.add_argument('--borrow', type=float, default=0.30, help='annual borrow fee on the short market value')
ap.add_argument('--min_px', type=float, default=1.0); ap.add_argument('--nav0', type=float, default=1_000_000.0)
ap.add_argument('--is_start', default='2025-01-01'); ap.add_argument('--is_end', default='2025-10-31')
ap.add_argument('--os_start', default='2025-11-01'); ap.add_argument('--os_end', default='2026-08-31')
ap.add_argument('--boot', type=int, default=5000); ap.add_argument('--selftest', action='store_true'); ap.add_argument('--no_chart', action='store_true')
a = ap.parse_args()
RAW, FDS = os.path.join(a.data, 'raw'), os.path.join(a.data, 'fds'); os.makedirs(a.out, exist_ok=True)

def run_ledger(T, C, cal, split_ratio, slot, borrow, nav0, min_px, log=print):
    """T: trades with entry, exit (dates), tk, s_in_bid, s_in_ask, s_out_bid, s_out_ask, x_in_bid, x_in_ask, x_out_bid, x_out_ask.
    C: adjusted close matrix (date x ticker). split_ratio(tk, d): product of later-split ratios after day d (adjusted close / ratio = real close).
    Returns daily account frame and per-trade ledger frame."""
    T = T.sort_values(['entry', 'tk']).reset_index(drop=True)
    pos = {d: i for i, d in enumerate(cal)}
    first, last = pos[T.entry.min()], pos[T.exit.max()]
    days = cal[first:last + 1]; n = len(days)
    cash = nav0; nav = np.zeros(n); fee_acc = np.zeros(n); nshort = np.zeros(n, int); gross_short = np.zeros(n); gross_long = np.zeros(n)
    openpos = []            # dicts: tk, sh (shares short, in the share basis of the entry day), xsh, exit date, exit quotes, entry_i, trade id
    skipped = []; led = []
    maxpos = int(round(1 / slot))
    bytrade_entry = {d: T.index[T.entry == d].tolist() for d in T.entry.unique()}
    def real_close(tk, d): return C.at[d, tk] / split_ratio(tk, d)
    def shares_now(tk, d_entry, sh, d):   # a reverse split k:1 between entry and d divides the share count by k
        return sh * split_ratio(tk, d) / split_ratio(tk, d_entry)
    for i, d in enumerate(days):
        # 1. exits at the close of day d (last quote before the close)
        still = []
        for p in openpos:
            if p['exit'] == d:
                sh_now = shares_now(p['tk'], p['entry'], p['sh'], d); xsh = p['xsh']
                f = sh_now * p['s_out_ask'] * borrow / 252; p['fee'] += f; cash -= f; fee_acc[i] += f     # borrow for the exit day too (5 sessions in total)
                cover = sh_now * p['s_out_ask']; sell_x = xsh * p['x_out_bid']
                cash += -cover + sell_x
                p['pnl'] = (p['proceeds'] - cover) + (sell_x - p['x_cost']) - p['fee']
                p['exit_px'] = p['s_out_ask']; p['sh_exit'] = sh_now
                led.append(p)
            else: still.append(p)
        openpos = still
        # 2. entries at the open of day d (first quote after the open); NAV for sizing is the previous close NAV
        nav_prev = nav[i - 1] if i > 0 else nav0
        for j in bytrade_entry.get(d, []):
            r = T.loc[j]
            if len(openpos) >= maxpos: skipped.append((r.tk, d, 'no free slot')); continue
            if any(p['tk'] == r.tk for p in openpos): skipped.append((r.tk, d, 'already short this name')); continue
            if not (r.s_in_bid >= min_px): skipped.append((r.tk, d, f'entry bid under ${min_px:g}')); continue
            dollars = slot * nav_prev
            sh = dollars / r.s_in_bid; xsh = dollars / r.x_in_ask
            proceeds = sh * r.s_in_bid; x_cost = xsh * r.x_in_ask
            cash += proceeds - x_cost
            openpos.append(dict(tk=r.tk, signal=r.signal, entry=d, exit=r.exit, sh=sh, xsh=xsh, proceeds=proceeds, x_cost=x_cost, fee=0.0,
                                s_out_ask=r.s_out_ask, x_out_bid=r.x_out_bid, entry_px=r.s_in_bid, dollars=dollars, hit=r.hit))
        # 3. mark to market at the close; borrow fee on the short market value
        sv = 0.0; lv = 0.0
        for p in openpos:
            sh_now = shares_now(p['tk'], p['entry'], p['sh'], d); mv = sh_now * real_close(p['tk'], d)
            f = mv * borrow / 252; p['fee'] += f; cash -= f; fee_acc[i] += f
            sv += mv; lv += p['xsh'] * C.at[d, 'XBI']
        nav[i] = cash - sv + lv; nshort[i] = len(openpos); gross_short[i] = sv; gross_long[i] = lv
    if openpos: log('WARNING positions still open at the end:', [(p['tk'], p['exit']) for p in openpos])
    D = pd.DataFrame(dict(date=days, nav=nav, cash_minus_marks=np.nan, n_positions=nshort, short_mv=gross_short, long_mv=gross_long, borrow_fee=fee_acc))
    D['ret'] = D.nav.pct_change().fillna(D.nav.iloc[0] / nav0 - 1)
    L = pd.DataFrame(led)
    if len(L): L['ret_on_slot'] = L.pnl / L.dollars
    return D, L, pd.DataFrame(skipped, columns=['tk', 'date', 'reason'])

def sharpe_d(x): x = np.asarray(x, float); return x.mean() / x.std(ddof=1) * np.sqrt(252) if len(x) > 5 and x.std(ddof=1) > 0 else np.nan
def block_ci(x, block, boot, rng):
    x = np.asarray(x, float); m = len(x); out = np.empty(boot)
    for b in range(boot):
        idx = np.empty(m, dtype=int); t = 0
        while t < m:
            st = rng.integers(0, m); L_ = min(rng.geometric(1.0 / block), m - t); idx[t:t + L_] = (st + np.arange(L_)) % m; t += L_
        out[b] = sharpe_d(x[idx])
    return np.nanpercentile(out, 2.5), np.nanpercentile(out, 97.5)
def window_stats(D, d0, d1, boot, rng):
    w = D[(D.date >= d0) & (D.date <= d1)]
    if len(w) < 30: return dict(days=len(w))
    x = w.ret.values; eq = np.cumprod(1 + x); res = dict(days=len(w), first_day=w.date.min().date(), last_day=w.date.max().date(), total_return_pct=(eq[-1] - 1) * 100,
        annual_return_pct=(eq[-1] ** (252 / len(x)) - 1) * 100, vol_pct=x.std(ddof=1) * np.sqrt(252) * 100, sharpe=sharpe_d(x),
        max_drawdown_pct=(eq / np.maximum.accumulate(eq) - 1).min() * 100, days_with_no_position=int((w.n_positions == 0).sum()), avg_positions=w.n_positions.mean())
    for b in (5, 10, 20, 40):
        lo, hi = block_ci(x, b, boot, rng); res[f'ci_lo_block{b}'] = lo; res[f'ci_hi_block{b}'] = hi
    return res

# ------------------------------------------------------------------ self test
if a.selftest:
    cal = pd.bdate_range('2025-01-01', '2025-03-31'); ok = True
    def check(name, got, want, tol=1e-6):
        global ok
        good = abs(got - want) <= tol; ok &= good; print(f'  {"PASS" if good else "FAIL"} {name}: got {got:.6f} want {want:.6f}')
    # fixture 1: stock rises 50% then 100%, XBI flat, no borrow, no spread -> fixed shares lose exactly 20% of initial NAV (the audit's example)
    C = pd.DataFrame(100.0, index=cal, columns=['AAA', 'XBI']); C.loc[cal[2], 'AAA'] = 150; C.loc[cal[3]:, 'AAA'] = 200
    T = pd.DataFrame([dict(tk='AAA', signal=0, entry=cal[1], exit=cal[3], hit=0, s_in_bid=100, s_in_ask=100, s_out_bid=200, s_out_ask=200, x_in_bid=100, x_in_ask=100, x_out_bid=100, x_out_ask=100)])
    D, L, S = run_ledger(T, C, cal, lambda tk, d: 1.0, 0.20, 0.0, 1000.0, 1.0)
    print('fixture 1: short 2 shares at $100, stock goes to $200, XBI flat, no costs')
    check('terminal NAV / initial - 1', D.nav.iloc[-1] / 1000 - 1, -0.20); check('trade P&L', L.pnl.iloc[0], -200.0); check('NAV after day with stock at 150', D.nav.iloc[1] / 1000 - 1, -0.10)
    # fixture 2: wide spreads and -30% move: exact cash P&L
    C = pd.DataFrame(100.0, index=cal, columns=['BBB', 'XBI']); C.loc[cal[3]:, 'BBB'] = 70
    T = pd.DataFrame([dict(tk='BBB', signal=0, entry=cal[1], exit=cal[3], hit=0, s_in_bid=98, s_in_ask=102, s_out_bid=68, s_out_ask=72, x_in_bid=99, x_in_ask=101, x_out_bid=99, x_out_ask=101)])
    D, L, S = run_ledger(T, C, cal, lambda tk, d: 1.0, 0.20, 0.0, 1000.0, 1.0)
    sh = 200 / 98; xsh = 200 / 101; want = sh * (98 - 72) + xsh * (99 - 101)
    print('fixture 2: -30% move with 4% spreads, XBI flat with 2% spread'); check('trade P&L equals exact cash', L.pnl.iloc[0], want); check('NAV change equals trade P&L', D.nav.iloc[-1] - 1000, want)
    # fixture 3: reverse split 1-for-10 inside the hold: adjusted series continuous, real price jumps x10, share count /10, P&L unchanged by the split
    C = pd.DataFrame(100.0, index=cal, columns=['CCC', 'XBI']); C.loc[cal[3]:, 'CCC'] = 110    # adjusted: +10%
    sr = lambda tk, d: (10.0 if (tk == 'CCC' and d < cal[3]) else 1.0)                      # split on cal[3]: before it, adjusted = real x 10
    T = pd.DataFrame([dict(tk='CCC', signal=0, entry=cal[1], exit=cal[4], hit=0, s_in_bid=10, s_in_ask=10, s_out_bid=110, s_out_ask=110, x_in_bid=100, x_in_ask=100, x_out_bid=100, x_out_ask=100)])
    D, L, S = run_ledger(T, C, cal, sr, 0.20, 0.0, 1000.0, 1.0)
    print('fixture 3: 1-for-10 reverse split inside the hold, stock +10% in real terms'); check('shares at exit = shares at entry / 10', L.sh_exit.iloc[0], L.sh.iloc[0] / 10); check('trade P&L = -10% of the slot', L.pnl.iloc[0], -20.0)
    # fixture 4: borrow fee accrual: flat stock, 36.5%/yr for 5 marked days -> fee = 5 x mv x 0.365/252
    C = pd.DataFrame(100.0, index=cal, columns=['DDD', 'XBI'])
    T = pd.DataFrame([dict(tk='DDD', signal=0, entry=cal[1], exit=cal[5], hit=0, s_in_bid=100, s_in_ask=100, s_out_bid=100, s_out_ask=100, x_in_bid=100, x_in_ask=100, x_out_bid=100, x_out_ask=100)])
    D, L, S = run_ledger(T, C, cal, lambda tk, d: 1.0, 0.20, 0.365, 1000.0, 1.0)
    print('fixture 4: flat stock, borrow 36.5%/yr, 5 sessions (entry day to exit day)'); check('fee', L.fee.iloc[0], 5 * 200 * 0.365 / 252)
    # fixture 4b: borrow must follow MARKET value, not entry dollars: stock doubles on day 2 and stays, 2 sessions
    C = pd.DataFrame(100.0, index=cal, columns=['DDD', 'XBI']); C.loc[cal[2]:, 'DDD'] = 200
    T = pd.DataFrame([dict(tk='DDD', signal=0, entry=cal[1], exit=cal[2], hit=0, s_in_bid=100, s_in_ask=100, s_out_bid=200, s_out_ask=200, x_in_bid=100, x_in_ask=100, x_out_bid=100, x_out_ask=100)])
    D, L, S = run_ledger(T, C, cal, lambda tk, d: 1.0, 0.20, 0.365, 1000.0, 1.0)
    print('fixture 4b: stock doubles, borrow on market value'); check('fee = (200 + 400) x 0.365/252', L.fee.iloc[0], (200 + 400) * 0.365 / 252)
    # fixture 5: window clipping: a trade across a boundary puts its days in each window; sums reconcile to the whole
    C = pd.DataFrame(100.0, index=cal, columns=['EEE', 'XBI']); C['EEE'] = np.linspace(100, 80, len(cal))
    T = pd.DataFrame([dict(tk='EEE', signal=0, entry=cal[20], exit=cal[55], hit=0, s_in_bid=C.EEE.iloc[20], s_in_ask=C.EEE.iloc[20], s_out_bid=C.EEE.iloc[55], s_out_ask=C.EEE.iloc[55], x_in_bid=100, x_in_ask=100, x_out_bid=100, x_out_ask=100)])
    D, L, S = run_ledger(T, C, cal, lambda tk, d: 1.0, 0.20, 0.0, 1000.0, 1.0)
    b = cal[23]; sh = 200 / C.EEE.iloc[20]
    print('fixture 5: one trade across a window boundary (short, price falls linearly, XBI flat)')
    # expected P&L inside each window from the known price path: short gains sh x (price drop) over the days of that window
    want1 = sh * (C.EEE.iloc[20] - C.EEE.iloc[22]); want2 = sh * (C.EEE.iloc[22] - C.EEE.iloc[55])
    w1 = D[D.date < b]; w2 = D[(D.date >= b)]
    check('window 1 P&L from the price path', w1.nav.iloc[-1] - 1000, want1); check('window 2 P&L from the price path', w2.nav.iloc[-1] - w1.nav.iloc[-1], want2)
    rng_ = np.random.default_rng(1); st2 = window_stats(D, b, cal[-1], 50, rng_)
    check('window_stats return equals the clipped NAV change', st2['total_return_pct'] / 100 * w1.nav.iloc[-1], want2, tol=1e-6)
    check('window_stats counts only days inside the window', float(st2['days']), float(len(w2)))
    # fixture 5b: a short that loses more than 100% of its stake
    C = pd.DataFrame(100.0, index=cal, columns=['HHH', 'XBI']); C.loc[cal[2]:, 'HHH'] = 350
    T = pd.DataFrame([dict(tk='HHH', signal=0, entry=cal[1], exit=cal[2], hit=0, s_in_bid=100, s_in_ask=100, s_out_bid=350, s_out_ask=350, x_in_bid=100, x_in_ask=100, x_out_bid=100, x_out_ask=100)])
    D, L, S = run_ledger(T, C, cal, lambda tk, d: 1.0, 0.20, 0.0, 1000.0, 1.0)
    print('fixture 5b: short loses 250% of its stake'); check('trade P&L = -250% of slot', L.pnl.iloc[0], -500.0); check('NAV = initial - 500', D.nav.iloc[-1], 500.0)
    # fixture 6: entry rejected under $1 and when no slot
    C = pd.DataFrame(100.0, index=cal, columns=['FFF', 'GGG', 'XBI']); C['FFF'] = 0.9
    T = pd.DataFrame([dict(tk='FFF', signal=0, entry=cal[1], exit=cal[3], hit=0, s_in_bid=0.9, s_in_ask=0.95, s_out_bid=0.9, s_out_ask=0.95, x_in_bid=100, x_in_ask=100, x_out_bid=100, x_out_ask=100)])
    D, L, S = run_ledger(T, C, cal, lambda tk, d: 1.0, 0.20, 0.0, 1000.0, 1.0)
    print('fixture 6: entry quote under $1'); check('trade skipped', float(len(S)), 1.0); check('no P&L', D.nav.iloc[-1] - 1000, 0.0)
    # fixture 6b: no free slot (slot = 50% -> at most 2 positions; third same-day trade is skipped)
    C = pd.DataFrame(100.0, index=cal, columns=['A1', 'A2', 'A3', 'XBI'])
    q = dict(s_in_bid=100, s_in_ask=100, s_out_bid=100, s_out_ask=100, x_in_bid=100, x_in_ask=100, x_out_bid=100, x_out_ask=100)
    T = pd.DataFrame([dict(tk=t_, signal=0, entry=cal[1], exit=cal[3], hit=0, **q) for t_ in ('A1', 'A2', 'A3')])
    D, L, S = run_ledger(T, C, cal, lambda tk, d: 1.0, 0.50, 0.0, 1000.0, 1.0)
    print('fixture 6b: three trades, two slots'); check('one trade skipped for no slot', float((S.reason == 'no free slot').sum()), 1.0); check('two trades taken', float(len(L)), 2.0)
    print('SELFTEST', 'PASS' if ok else 'FAIL'); sys.exit(0 if ok else 1)

# ------------------------------------------------------------------ real run
T = pd.read_csv(os.path.join(FDS, a.trades)); Q = pd.read_csv(os.path.join(FDS, a.quotes)).drop_duplicates(['cik', 'signal'])
T = T.merge(Q[['cik', 'signal', 's_in_bid', 's_in_ask', 's_out_bid', 's_out_ask', 'x_in_bid', 'x_in_ask', 'x_out_bid', 'x_out_ask', 'status']], on=['cik', 'signal'], how='inner')
T = T[T.status == 0].copy(); T['entry'] = pd.to_datetime(T.entry.astype(str)); T['exit'] = pd.to_datetime(T['exit'].astype(str))
P = pd.read_csv(os.path.join(RAW, 'prices.csv'), usecols=['ticker', 'date', 'close']); P['date'] = pd.to_datetime(P.date)
C = P.pivot(index='date', columns='ticker', values='close'); cal = C.index[C['XBI'].notna()]; C = C.loc[cal].ffill(limit=5)
SPL = pd.read_csv(os.path.join(RAW, 'splits.csv'), parse_dates=['execution_date']); SPL['r'] = SPL.split_from / SPL.split_to
spl = {tk: list(zip(g.execution_date, g.r)) for tk, g in SPL.groupby('ticker')}
def split_ratio(tk, d):
    out = 1.0
    for e, r in spl.get(tk, []):
        if d < e: out *= r
    return out
D, L, S = run_ledger(T, C, cal, split_ratio, a.slot, a.borrow, a.nav0, a.min_px)
rng = np.random.default_rng(49)
print(f'LEDGER | {len(T)} candidate trades | taken {len(L)} | skipped {len(S)} {S.reason.value_counts().to_dict() if len(S) else ""}')
print(f'account from {D.date.min().date()} to {D.date.max().date()} | {len(D)} market days | days with no position {(D.n_positions == 0).sum()} | avg positions {D.n_positions.mean():.2f} | borrow fees paid {D.borrow_fee.sum() / a.nav0 * 100:.2f}% of initial NAV')
print(f'whole account: NAV {D.nav.iloc[-1] / a.nav0 - 1:+.1%} | Sharpe {sharpe_d(D.ret):+.2f} | max drawdown {(np.cumprod(1 + D.ret) / np.maximum.accumulate(np.cumprod(1 + D.ret)) - 1).min():+.1%}')
rows = []
for name, d0, d1 in (('in sample', a.is_start, a.is_end), ('out of sample', a.os_start, a.os_end)):
    st = window_stats(D, pd.Timestamp(d0), pd.Timestamp(d1), a.boot, rng); st = dict(window=name, start=d0, end=d1, **st); rows.append(st)
    if 'sharpe' in st:
        print(f'{name:14s} {d0}..{d1}: {st["days"]} days, first mark {st["first_day"]}, last mark {st["last_day"]} | return {st["total_return_pct"]:+.1f}% | Sharpe {st["sharpe"]:+.2f} | '
              f'95% block bootstrap: 5d [{st["ci_lo_block5"]:+.2f}, {st["ci_hi_block5"]:+.2f}] 10d [{st["ci_lo_block10"]:+.2f}, {st["ci_hi_block10"]:+.2f}] 20d [{st["ci_lo_block20"]:+.2f}, {st["ci_hi_block20"]:+.2f}] 40d [{st["ci_lo_block40"]:+.2f}, {st["ci_hi_block40"]:+.2f}] | '
              f'max drawdown {st["max_drawdown_pct"]:+.1f}% | idle days {st["days_with_no_position"]}')
# reconciliation: sum of trade P&L + fees = NAV change
recon = L.pnl.sum() - (D.nav.iloc[-1] - a.nav0)
print(f'reconciliation: sum of trade P&L {L.pnl.sum():,.0f} vs NAV change {D.nav.iloc[-1] - a.nav0:,.0f} | difference {recon:,.2f} (should be 0)')
assert abs(recon) < 0.01, 'ledger does not reconcile to the cent'
D.to_csv(os.path.join(a.out, 'ledger_daily.csv'), index=False); L.to_csv(os.path.join(a.out, 'ledger_trades.csv'), index=False); S.to_csv(os.path.join(a.out, 'ledger_skipped.csv'), index=False)
pd.DataFrame(rows).to_csv(os.path.join(a.out, 'ledger_summary.csv'), index=False)
if not a.no_chart:
    import matplotlib; matplotlib.use('Agg'); import matplotlib.pyplot as plt, matplotlib.ticker
    BLUE, ORANGE, INK, INK2, GRID, SURF = '#2a78d6', '#eb6834', '#0b0b0b', '#52514e', '#e4e3df', '#fcfcfb'
    plt.rcParams.update({'font.family': 'DejaVu Sans', 'font.size': 10, 'figure.facecolor': SURF, 'axes.facecolor': SURF, 'savefig.facecolor': SURF, 'axes.edgecolor': GRID, 'text.color': INK, 'axes.labelcolor': INK2, 'xtick.color': INK2, 'ytick.color': INK2})
    fig, ax = plt.subplots(figsize=(11, 4.8)); eq = (D.nav / a.nav0 - 1) * 100
    ax.plot(D.date, eq, color=BLUE, linewidth=2)
    for d0, d1, lab, col in ((a.is_start, a.is_end, 'in sample', ORANGE), (a.os_start, a.os_end, 'out of sample', BLUE)):
        ax.axvspan(pd.Timestamp(d0), pd.Timestamp(d1), color=col, alpha=0.07, lw=0); 
        st = [r for r in rows if r['window'] == lab][0]
        if 'sharpe' in st: ax.text(pd.Timestamp(d0) + (pd.Timestamp(d1) - pd.Timestamp(d0)) / 2, ax.get_ylim()[1] if False else eq.max() * 0.98, f'{lab}\n{st["total_return_pct"]:+.1f}%, Sharpe {st["sharpe"]:+.2f}', ha='center', va='top', fontsize=9, color=INK2)
    ax.plot([D.date.iloc[-1]], [eq.iloc[-1]], 'o', color=BLUE, markersize=5); ax.annotate(f'{eq.iloc[-1]:+.0f}%', (D.date.iloc[-1], eq.iloc[-1]), xytext=(6, 0), textcoords='offset points', va='center', fontsize=9)
    ax.set_title('Offering short: one continuous account, fixed shares, real quotes, 30%/yr borrow', loc='left', fontsize=11, fontweight='bold', pad=22)
    ax.text(0, 1.02, f'{len(L)} trades, {a.slot:.0%} of NAV per trade, idle cash earns nothing. Shaded: the two evaluation windows (clipped by calendar).', transform=ax.transAxes, fontsize=9, color=INK2, va='bottom')
    ax.grid(axis='y', color=GRID, lw=0.8); ax.set_axisbelow(True); ax.axhline(0, color=INK2, lw=0.8); ax.yaxis.set_major_formatter(matplotlib.ticker.FuncFormatter(lambda v, _: f'{v:+.0f}%'))
    for sp in ('top', 'right', 'left'): ax.spines[sp].set_visible(False)
    ax.tick_params(length=0); fig.tight_layout(); fig.savefig(os.path.join(a.out, 'ledger_offering_short.png'), dpi=150); plt.close(fig)
print('written to', os.path.abspath(a.out))
