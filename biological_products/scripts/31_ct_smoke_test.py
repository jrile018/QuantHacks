"""Run the trial history builders on temporary synthetic posted versions.

This verifies date lag, file shapes, and that all four downstream scripts run.
It does not validate the real source endpoint or market results.
"""

import json
import subprocess
import sys
import tempfile
from pathlib import Path

import pandas as pd


def version(nct, posted, completion, status, enrollment):
    return {"study": {"protocolSection": {
        "identificationModule": {"nctId": nct},
        "statusModule": {"overallStatus": status,
                         "studyFirstPostDateStruct": {"date": "2024-01-03"},
                         "lastUpdatePostDateStruct": {"date": posted},
                         "primaryCompletionDateStruct": {"date": completion},
                         "startDateStruct": {"date": "2024-01-01"}},
        "designModule": {"phases": ["PHASE2"],
                         "enrollmentInfo": {"count": enrollment, "type": "ESTIMATED"}},
        "outcomesModule": {"primaryOutcomes": [{"measure": "efficacy"}]},
        "contactsLocationsModule": {"locations": [{}]},
        "armsInterventionsModule": {"armGroups": [{}], "interventions": [{}]},
        "sponsorCollaboratorsModule": {"leadSponsor": {"name": "Test"}},
    }}}


def main():
    workspace = Path(__file__).resolve().parents[2]
    with tempfile.TemporaryDirectory(dir=workspace) as temporary:
        data = Path(temporary).resolve()
        assert data.is_relative_to(workspace.resolve())
        (data / "raw" / "ct_history").mkdir(parents=True)
        (data / "fds").mkdir()
        pd.DataFrame({"ticker": ["BEAM", "MAZE"],
                      "nct_id": ["NCT00000001", "NCT00000002"],
                      "title": ["Test ACU123 trial", "Test MAZ123 trial"]}).to_csv(data / "raw" / "trials.csv", index=False)
        pd.DataFrame({"ticker": ["BEAM", "MAZE"], "cik": [1, 2]}).to_csv(
            data / "fds" / "fds_lookup_cik_ticker.csv", index=False)
        dates = pd.bdate_range("2024-01-02", periods=180)
        features = [{"cik": cik, "date": int(day.strftime("%Y%m%d")),
                     "px_adv20_usd_m": 2, "px_close_raw": 10,
                     "fin_runway_q": 4, "fin_liq_m": 100}
                    for day in dates for cik in (1, 2)]
        prices = [{"ticker": ticker, "date": int(day.strftime("%Y%m%d")),
                   "open": (100 if ticker == "XBI" else 10) + i * 0.01,
                   "close": (100 if ticker == "XBI" else 10) + i * 0.01}
                  for i, day in enumerate(dates) for ticker in ("BEAM", "MAZE", "XBI")]
        pd.DataFrame(features).to_csv(data / "fds" / "fds_features.csv", index=False)
        pd.DataFrame(prices).to_csv(data / "raw" / "prices.csv", index=False)
        pd.DataFrame([{"cik": 1, "filing_date": "2024-02-15", "supporting_text": "unrelated"}]).to_csv(
            data / "raw" / "events_8k.csv", index=False)
        pd.DataFrame([{"ticker": "BEAM", "published_utc": "2024-02-20T12:00:00Z",
                       "title": "unrelated", "description": "unrelated"}]).to_csv(
            data / "raw" / "news.csv", index=False)
        for nct, ticker in (("NCT00000001", "BEAM"), ("NCT00000002", "MAZE")):
            versions = {"0": version(nct, "2024-01-03", "2024-03-01", "RECRUITING", 100)}
            if ticker == "BEAM":
                versions["1"] = version(nct, "2024-02-01", "2024-06-01",
                                        "ACTIVE_NOT_RECRUITING", 120)
            payload = {"nct_id": nct, "ticker": ticker,
                       "history": {"changes": [{"version": int(key)} for key in versions]},
                       "versions": versions, "completed_utc": "2024-03-01T00:00:00Z"}
            (data / "raw" / "ct_history" / f"{nct}.json").write_text(json.dumps(payload))
        for script in ("27b_ct_changes.py", "28_merge_ct_history.py",
                       "29_ct_event_study.py", "29b_ct_context.py"):
            result = subprocess.run([sys.executable, str(Path(__file__).parent / script),
                                     "--data", str(data)], capture_output=True, text=True)
            print(f"{script}: {'PASS' if result.returncode == 0 else 'FAIL'}")
            if result.returncode:
                print(result.stdout)
                print(result.stderr)
                raise SystemExit(result.returncode)
        frame = pd.read_csv(data / "fds" / "fds_trialhist.csv")
        first = frame[(frame.cik == 1) & (frame.date == 20240103)].iloc[0]
        next_day = frame[(frame.cik == 1) & (frame.date == 20240104)].iloc[0]
        assert first.ch_n_active_known == 0 and next_day.ch_n_active_known == 1
        print("Next-calendar-day availability: PASS")


if __name__ == "__main__":
    main()
