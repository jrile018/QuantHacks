"""Unified dataset: one SQLite file holding every table, keyed on CIK.

Replaces the scattered CSVs with one store that every analysis reads from. Rules:
  - cik (10 digits) is the only join key. ticker is an attribute, never a key, because
    tickers are reused and reassigned.
  - every fact table has a cik that must exist in dim_company; the build checks this.
  - raw filings stay in extracts/; the database holds the parsed values and the evidence
    references that point back to the source file.

Tables
  dim_company          one row per universe company, with identity and membership
  fact_prices          daily adjusted bars
  fact_factors         daily market and risk-free returns (market-wide, no cik)
  fact_panel           company x period feature values, with as_of and missing reason
  fact_financials      annual XBRL values (financial gaps, buybacks, public float, ...)
  fact_events          dated events: 8-K items, auditor changes, KEV, WARN, departures
  fact_contracts       federal awards by start date
  fact_exhibit_contracts  Exhibit 10 contract index
  fact_labels          forward excess return over 63 trading days after each quarter end
  edge_relations       undirected company links from every connectedness layer
  subsidiaries         Exhibit 21 subsidiary records (parent cik, subsidiary name)
  evidence             text spans that support a flag, value or event

Writes output/dataset.sqlite and output/dataset_validation.txt. Standard library only.
"""

from __future__ import annotations

import csv
import sqlite3
from collections import defaultdict
from pathlib import Path

HERE = Path(__file__).resolve().parent
OUT = HERE / "output"
EXTRACTS = HERE / "extracts"
DB = OUT / "dataset.sqlite"
HORIZON = 63

SCHEMA = """
CREATE TABLE dim_company (cik TEXT PRIMARY KEY, ticker TEXT, name TEXT, sic TEXT,
  lei TEXT, lei_match_confidence TEXT, auditor TEXT, exchanges TEXT, fiscal_year_end TEXT,
  state_of_incorporation TEXT, domain TEXT, total_employees TEXT, list_date TEXT,
  market_cap TEXT, membership_status TEXT, exit_date TEXT);
CREATE TABLE fact_prices (cik TEXT, date TEXT, open REAL, high REAL, low REAL, close REAL,
  volume REAL, vwap REAL, PRIMARY KEY (cik, date));
CREATE TABLE fact_factors (date TEXT PRIMARY KEY, mkt_rf REAL, smb REAL, hml REAL, rf REAL, mom REAL);
CREATE TABLE fact_panel (cik TEXT, period_end TEXT, feature TEXT, value TEXT, unit TEXT,
  source_file TEXT, as_of TEXT, missing_reason TEXT, evidence_ref TEXT);
CREATE TABLE fact_financials (cik TEXT, metric TEXT, source_tag TEXT, period_end TEXT,
  value REAL, unit TEXT, validation TEXT, filed TEXT, accession TEXT, source_file TEXT);
CREATE TABLE fact_events (event_id INTEGER PRIMARY KEY, cik TEXT, event_date TEXT,
  event_type TEXT, detail TEXT, value REAL, source_file TEXT);
CREATE TABLE fact_contracts (award_id TEXT, cik TEXT, start_date TEXT,
  award_amount REAL, awarding_agency TEXT, exact_name_match TEXT, description TEXT, source_file TEXT);
CREATE TABLE fact_exhibit_contracts (cik TEXT, filing_date TEXT, form TEXT, exhibit_file TEXT,
  title TEXT, contract_type TEXT, party_a TEXT, party_b TEXT, source_file TEXT);
CREATE TABLE fact_labels (cik TEXT, quarter_end TEXT, horizon_days INTEGER,
  excess_return REAL, PRIMARY KEY (cik, quarter_end, horizon_days));
CREATE TABLE edge_relations (layer TEXT, cik_a TEXT, cik_b TEXT, weight REAL, source_file TEXT);
CREATE TABLE subsidiaries (parent_cik TEXT, filing_date TEXT, subsidiary_name TEXT,
  jurisdiction TEXT, parse_method TEXT, source_file TEXT);
CREATE TABLE evidence (evidence_id INTEGER PRIMARY KEY, cik TEXT, doc_date TEXT, kind TEXT,
  text TEXT, source_file TEXT);
CREATE INDEX ix_prices ON fact_prices(cik, date);
CREATE INDEX ix_panel ON fact_panel(cik, period_end);
CREATE INDEX ix_events ON fact_events(cik, event_date);
CREATE INDEX ix_labels ON fact_labels(cik, quarter_end);
"""


def read(path: Path) -> list[dict]:
    if not path.exists():
        return []
    with path.open(newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def pad(cik: str) -> str:
    return str(cik or "").strip().zfill(10) if str(cik or "").strip() else ""


def fl(v) -> float | None:
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def main() -> int:
    OUT.mkdir(parents=True, exist_ok=True)
    if DB.exists():
        DB.unlink()
    con = sqlite3.connect(DB)
    con.executescript(SCHEMA)
    log = []

    # ---- dim_company ------------------------------------------------------------
    universe = [r for r in read(HERE / "packaged_software_companies.csv") if r["ticker"]]
    identity = {pad(r["cik"]): r for r in read(OUT / "company_identity.csv")}
    lei = {pad(r["cik"]): r for r in read(OUT / "company_lei.csv")}
    auditor = {pad(r["cik"]): r for r in read(OUT / "company_auditors.csv")}
    details = {r["ticker"]: r for r in read(OUT / "ticker_details.csv")}
    membership = {pad(r["cik"]): r for r in read(OUT / "membership_universe.csv")}
    companies = {}
    for c in universe:
        cik = pad(c["cik"])
        i, l, a = identity.get(cik, {}), lei.get(cik, {}), auditor.get(cik, {})
        d = details.get(c["ticker"], {})
        m = membership.get(cik, {})
        companies[cik] = c["ticker"]
        con.execute("INSERT INTO dim_company VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)", (
            cik, c["ticker"], c["name"], c["sic"], l.get("lei", ""), l.get("match_confidence", ""),
            a.get("auditor", ""), i.get("exchanges", ""), i.get("fiscal_year_end", ""),
            i.get("state_of_incorporation", ""), d.get("domain", ""), d.get("total_employees", ""),
            d.get("list_date", ""), d.get("market_cap", ""), m.get("status", "no_membership_record"), m.get("exit_date", "")))
    ticker_to_cik = {t: c for c, t in companies.items()}
    log.append(f"dim_company: {len(companies)} companies")

    def known(cik: str) -> bool:
        return cik in companies

    # ---- fact_prices and labels --------------------------------------------------
    prices = defaultdict(list)
    rows = []
    for r in read(EXTRACTS / "prices" / "daily_bars.csv"):
        cik = ticker_to_cik.get(r["ticker"], "")
        if not cik:
            continue
        rows.append((cik, r["date"], fl(r["open"]), fl(r["high"]), fl(r["low"]), fl(r["close"]),
                     fl(r["volume"]), fl(r["vwap"])))
        if fl(r["close"]):
            prices[cik].append((r["date"], fl(r["close"])))
    con.executemany("INSERT OR IGNORE INTO fact_prices VALUES (?,?,?,?,?,?,?,?)", rows)
    log.append(f"fact_prices: {len(rows)} bars")

    factors = {}
    for r in read(OUT / "factor_returns_daily.csv"):
        con.execute("INSERT OR IGNORE INTO fact_factors VALUES (?,?,?,?,?,?)", (
            r["date"], fl(r["mkt_rf"]), fl(r["smb"]), fl(r["hml"]), fl(r["rf"]), fl(r.get("mom"))))
        if fl(r["mkt_rf"]) is not None and fl(r["rf"]) is not None:
            factors[r["date"]] = (fl(r["mkt_rf"]) + fl(r["rf"])) / 100.0
    days = sorted(factors)

    labels = 0
    for cik, series in prices.items():
        series.sort()
        dates = [d for d, _ in series]
        for qy in range(2022, 2027):
            for qn, qe in ((1, f"{qy}-03-31"), (2, f"{qy}-06-30"), (3, f"{qy}-09-30"), (4, f"{qy}-12-31")):
                i0 = next((i for i, d in enumerate(dates) if d > qe), None)
                if i0 is None or i0 + HORIZON >= len(series) or i0 < 1:
                    continue
                p0 = series[i0 - 1][1]
                p1 = series[i0 + HORIZON][1]
                window = [d for d in dates[i0 - 1:i0 + HORIZON] if d in factors]
                if not window or not p0:
                    continue
                excess = (p1 / p0 - 1) - sum(factors[d] for d in window)
                con.execute("INSERT OR IGNORE INTO fact_labels VALUES (?,?,?,?)",
                            (cik, qe, HORIZON, round(excess, 6)))
                labels += 1
    log.append(f"fact_labels: {labels} company-quarters (forward {HORIZON}-day excess return)")

    # ---- fact_panel --------------------------------------------------------------
    n = 0
    for r in read(OUT / "feature_store_long.csv"):
        cik = pad(r["cik"])
        if not known(cik):
            continue
        con.execute("INSERT INTO fact_panel VALUES (?,?,?,?,?,?,?,?,?)", (
            cik, r["period_end"], r["feature"], r["value"], r["unit"], r["source_file"],
            r["as_of"], r["missing_reason"], r["evidence_ref"]))
        n += 1
    log.append(f"fact_panel: {n} cells")

    # ---- fact_financials ---------------------------------------------------------
    n = 0
    for name in ("xbrl_gaps_annual.csv", "financial_gaps_annual.csv", "buybacks_annual.csv"):
        for r in read(OUT / name):
            cik = pad(r["cik"])
            if not known(cik):
                continue
            metric = r["metric"]
            period = r.get("period_end") or r.get("fiscal_year_end") or ""
            con.execute("INSERT INTO fact_financials VALUES (?,?,?,?,?,?,?,?,?,?)", (
                cik, metric, r["source_tag"], period, fl(r["value"]), r["unit"],
                r.get("validation", ""), r.get("filed", ""), r.get("accession", ""), f"output/{name}"))
            n += 1
    log.append(f"fact_financials: {n} annual values")

    # ---- fact_events -------------------------------------------------------------
    n = 0

    def event(cik, date, kind, detail="", value=None, source=""):
        nonlocal n
        if known(cik) and date:
            con.execute("INSERT INTO fact_events (cik, event_date, event_type, detail, value, source_file) "
                        "VALUES (?,?,?,?,?,?)", (cik, date, kind, detail, value, source))
            n += 1

    for r in read(OUT / "8k_item_filings.csv"):
        cik = ticker_to_cik.get(r["ticker"], "")
        date = r["filing_folder"].split("_")[0]
        event(cik, date, f"8k_item_{r['item']}", r["form"], None, r["local_path"])
    for r in read(OUT / "auditor_changes.csv"):
        event(pad(r["cik"]), r["first_filing_with_new_auditor"], "auditor_change",
              f"{r['from_auditor']} -> {r['to_auditor']}", None, "output/auditor_changes.csv")
    for r in read(OUT / "kev_company_cves.csv"):
        event(pad(r["cik"]), r["date_added"], "kev_added", r["cve_id"], None, "output/kev_company_cves.csv")
    for r in read(OUT / "warn_ca_notices.csv"):
        cik = ticker_to_cik.get(r["ticker"], "")
        event(cik, r["notice_date"], "warn_ca_notice", r["action"], fl(r["employees_affected"]),
              "output/warn_ca_notices.csv")
    for r in read(OUT / "executive_departures.csv"):
        event(pad(r["cik"]), r["filing_date"], "executive_departure",
              f"immediate={r['immediate']} for_cause={r['for_cause']}", None, r["form"])
    log.append(f"fact_events: {n} dated events")

    # ---- fact_contracts ----------------------------------------------------------
    n = 0
    for r in read(OUT / "contract_awards.csv"):
        cik = pad(r["cik"])
        if not known(cik) or not r["award_id"]:
            continue
        # Key is award plus recipient: one award ID can name more than one company
        con.execute("INSERT INTO fact_contracts VALUES (?,?,?,?,?,?,?,?)", (
            r["award_id"], cik, r["start_date"], fl(r["award_amount"]), r["awarding_agency"],
            r["exact_name_match"], r["description"][:300], "output/contract_awards.csv"))
        n += 1
    log.append(f"fact_contracts: {n} awards")

    n = 0
    for r in read(OUT / "material_contracts.csv"):
        cik = pad(r["cik"])
        if not known(cik):
            continue
        con.execute("INSERT INTO fact_exhibit_contracts VALUES (?,?,?,?,?,?,?,?,?)", (
            cik, r["filing_date"], r["form"], r["exhibit_file"], r["title"][:200],
            r["contract_type"], r["party_a"], r["party_b"], r["source_file"]))
        n += 1
    log.append(f"fact_exhibit_contracts: {n} exhibits")

    # ---- edges and subsidiaries --------------------------------------------------
    n = 0
    for r in read(OUT / "connectedness_edges.csv"):
        a, b = ticker_to_cik.get(r["company_a"], ""), ticker_to_cik.get(r["company_b"], "")
        if a and b:
            con.execute("INSERT INTO edge_relations VALUES (?,?,?,?,?)",
                        (r["layer"], a, b, fl(r["weight"]), "output/connectedness_edges.csv"))
            n += 1
    log.append(f"edge_relations: {n} links")

    n = 0
    for r in read(OUT / "subsidiaries.csv"):
        cik = pad(r["parent_cik"])
        if known(cik):
            con.execute("INSERT INTO subsidiaries VALUES (?,?,?,?,?,?)", (
                cik, r["filing_date"], r["subsidiary_name"], r["jurisdiction"], r["parse_method"],
                r["source_file"]))
            n += 1
    log.append(f"subsidiaries: {n} records")

    # ---- evidence ----------------------------------------------------------------
    n = 0
    for r in read(OUT / "customer_concentration.csv"):
        cik = pad(r["cik"])
        if known(cik):
            con.execute("INSERT INTO evidence (cik, doc_date, kind, text, source_file) VALUES (?,?,?,?,?)",
                        (cik, r["filing_date"], f"customer_pct:{r['statement']}", r["sentence"][:600],
                         "output/customer_concentration.csv"))
            n += 1
    for r in read(OUT / "executive_departures.csv"):
        cik = pad(r["cik"])
        if known(cik) and r.get("sentence"):
            con.execute("INSERT INTO evidence (cik, doc_date, kind, text, source_file) VALUES (?,?,?,?,?)",
                        (cik, r["filing_date"], "executive_departure", r["sentence"][:600],
                         "output/executive_departures.csv"))
            n += 1
    log.append(f"evidence: {n} text spans")

    con.commit()

    # ---- validation --------------------------------------------------------------
    checks = []

    def check(name, sql, expect_zero=True):
        value = con.execute(sql).fetchone()[0]
        ok = (value == 0) if expect_zero else (value > 0)
        checks.append(f"{'PASS' if ok else 'FAIL'}  {name}: {value}")

    check("fact_prices keys missing from dim_company",
          "SELECT COUNT(*) FROM fact_prices WHERE cik NOT IN (SELECT cik FROM dim_company)")
    check("fact_panel keys missing from dim_company",
          "SELECT COUNT(*) FROM fact_panel WHERE cik NOT IN (SELECT cik FROM dim_company)")
    check("fact_events keys missing from dim_company",
          "SELECT COUNT(*) FROM fact_events WHERE cik NOT IN (SELECT cik FROM dim_company)")
    check("fact_financials keys missing from dim_company",
          "SELECT COUNT(*) FROM fact_financials WHERE cik NOT IN (SELECT cik FROM dim_company)")
    check("fact_labels keys missing from dim_company",
          "SELECT COUNT(*) FROM fact_labels WHERE cik NOT IN (SELECT cik FROM dim_company)")
    check("dim_company rows with a blank membership status",
          "SELECT COUNT(*) FROM dim_company WHERE membership_status = ''")
    # Known and labelled, not an error: companies whose CIK has no membership record
    no_record = con.execute("SELECT COUNT(*) FROM dim_company WHERE membership_status = 'no_membership_record'").fetchone()[0]
    checks.append(f"INFO  companies labelled no_membership_record (known gap): {no_record}")
    check("cik values not 10 characters",
          "SELECT COUNT(*) FROM dim_company WHERE length(cik) != 10")
    check("labels present", "SELECT COUNT(*) FROM fact_labels", expect_zero=False)
    check("prices present", "SELECT COUNT(*) FROM fact_prices", expect_zero=False)
    check("panel present", "SELECT COUNT(*) FROM fact_panel", expect_zero=False)

    table_counts = [f"  {t}: {con.execute(f'SELECT COUNT(*) FROM {t}').fetchone()[0]}"
                    for t in ("dim_company", "fact_prices", "fact_factors", "fact_panel", "fact_financials",
                              "fact_events", "fact_contracts", "fact_exhibit_contracts", "fact_labels",
                              "edge_relations", "subsidiaries", "evidence")]
    con.close()

    report = ["Unified dataset build", "", *log, "", "Row counts:", *table_counts, "", "Validation:", *checks]
    (OUT / "dataset_validation.txt").write_text("\n".join(report) + "\n", encoding="utf-8")
    print("\n".join(report))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
