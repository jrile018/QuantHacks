Biologics backtest bundle for HiPerGator.
  scripts/40_offer_strategy_pnl.py  offering strategy: Sharpe ratio, 95% interval (block bootstrap), audit
  scripts/39_strategy_audit.py      trial stage strategy: same, for the design half and the holdout half
  scripts/38_strategy_pnl.py        trial stage strategy: simple version (trades + daily profit and loss)
  data/fds/stock_trades_real_adj.csv  offering trades with real bid/ask costs from Massive
  data/fds/ct_event_study.csv         trial registry change events with returns and context
  data/raw/prices.csv                 daily prices (split adjusted), includes XBI and SPY
Run:   sbatch run_backtest.sbatch      then   squeue -u $USER      then   cat backtest_*.log
Needs only Python with pandas and numpy. Run time under 2 minutes.
