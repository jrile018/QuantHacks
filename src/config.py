"""Research configuration shared by the notebook and command-line runner."""

import pandas as pd

# ---- The 8-K event. One tertiary_category tag from the taxonomy (printed in the next section). ------
EVENT_TAG = "cfo_appointment"

# ---- Windows. In-sample is what you research on; out-of-sample is the most recent six months for
#      which every fixed horizon has resolved; the sealed window is the judges' and is not run here.
STUDY_START, STUDY_END = "2024-01-01", "2025-12-31"      # in-sample (plan has ~2 years of options history)
OOS_START, OOS_END = "2026-01-01", "2026-08-31"          # out-of-sample, run in this notebook
HOLDOUT_START, HOLDOUT_END = "2023-06-01", "2023-08-31"  # sealed: judges change these and flip RUN_HOLDOUT

# ---- Universe: the 100 largest US companies by market value (approximately the S&P 100), one
#      ticker per company, as of September 2026. A static list, so mind the caveat in the appendix.
TOP_100 = """
AAPL ABBV ABT ACN ADBE AIG AMD AMGN AMT AMZN AVGO AXP BA BAC BK BKNG BLK BMY BRK.B C
CAT CHTR CL CMCSA COF COP COST CRM CSCO CVS CVX DE DHR DIS DUK EMR FDX GD GE GILD
GM GOOGL GS HD HON IBM INTC INTU ISRG JNJ JPM KO LIN LLY LMT LOW MA MCD MDLZ MDT
MET META MMM MO MRK MS MSFT NEE NFLX NKE NOW NVDA ORCL PEP PFE PG PLTR PM PYPL QCOM
RTX SBUX SCHW SO T TGT TMO TMUS TSLA TXN UBER UNH UNP UPS USB V VZ WFC WMT XOM
""".split()
assert len(TOP_100) == 100 and len(set(TOP_100)) == 100

# ---- Expiry buckets: name -> (min, max, target) calendar days to expiry from the pre-event session.
EXPIRY_BUCKETS = {
    "1m":   (21, 45, 30),
    "2m":   (46, 80, 60),
    "3-6m": (90, 180, 120),
}
BASELINE_BUCKET = "3-6m"     # the headline bucket: the out-of-sample test is on options 3-6 months out

# ---- Fixed horizons (sessions after the conservative entry session). Do not change. ---------------
HORIZONS = [1, 2, 3, 5, 10, 21, 42, 63]

# ---- Strategy parameters -----------------------------------------------------------------------
OTM_PCT = 0.05              # covered call / collar sell the call ~5% above spot; protective put / collar / cash-secured put use the put ~5% below
OTM_GRID = [0.03, 0.05, 0.10]   # neighbours for the parameter-sensitivity check; OTM_PCT must be one of them
ENTRY = "post"              # "post": next-session close after filing date; "pre": last close before filing date (hypothetical)
RISK_FREE = 0.04            # flat carry rate used in put-call parity to recover spot from the chain

# ---- Mechanics -----------------------------------------------------------------------------------
STRIKE_WINDOW = 0.25        # keep strikes within ±25% of spot once spot is known
MAX_STALE_SESSIONS = 3      # a leg's last trade may be at most this many sessions old to count as a mark
MAX_EVENTS = None           # e.g. 15 for a smoke test; None = all events

# ---- Stretch toggles -----------------------------------------------------------------------------
RUN_PLACEBO = True          # the same measurement on ordinary days for the same names
N_PLACEBO = 120
PLACEBO_GAP_DAYS = 30
FETCH_ACCEPTANCE_TIMES = False  # optional SEC timing audit; default entry rule is conservative without it
SEC_USER_AGENT = "GatorQuantHacks team-name your@email.edu"   # the SEC requires a contact in the User-Agent
RUN_HOLDOUT = False         # judges flip this

assert OTM_PCT in OTM_GRID and BASELINE_BUCKET in EXPIRY_BUCKETS and ENTRY in ("pre", "post")

# ---- Catch impossible dates (e.g. "2024-06-31") here rather than deep in the pipeline -----------
for _name in ("STUDY_START", "STUDY_END", "OOS_START", "OOS_END", "HOLDOUT_START", "HOLDOUT_END"):
    try:
        pd.Timestamp(globals()[_name])
    except ValueError:
        raise ValueError(f"{_name} = {globals()[_name]!r} is not a real date (check the day of the month)") from None
assert STUDY_START < STUDY_END and OOS_START < OOS_END and HOLDOUT_START < HOLDOUT_END, "each window's start must be before its end"
STRATEGIES = ["stock", "long_call", "covered_call", "protective_put", "collar", "cash_secured_put"]
STRATEGY_LABEL = {"stock": "Stock only (synthetic)", "long_call": "1 · Long call", "covered_call": "2 · Covered call",
                  "protective_put": "3 · Protective put", "collar": "4 · Collar", "cash_secured_put": "5 · Cash-secured put"}
COST_HAIRCUT = 0.05
RISK_FRACTION = 0.01  # maximum loss per event as a fraction of available capital
MAX_VOLUME_PARTICIPATION = 0.05  # at most 5% of the least-traded option leg
