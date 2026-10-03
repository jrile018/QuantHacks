"""Offline contract export checks for the Lattice options study."""

import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import pandas as pd

from src import data, implementation, main


def fixture():
    events = pd.DataFrame([{
        "cik": "123", "accession_number": "000123-24-000001", "ticker": "ABC",
        "event_date": pd.Timestamp("2024-01-08"), "t_pre": pd.Timestamp("2024-01-05"),
        "t_0": pd.Timestamp("2024-01-09"),
    }])
    bars = pd.DataFrame({"close": [4.0, 5.0], "volume": [20.0, 30.0]},
                        index=pd.DatetimeIndex(["2024-01-04", "2024-01-05"], name="session"))
    call = implementation.Leg("O:ABC240216C00100000", "call", 100.0, bars, 100)
    put = implementation.Leg("O:ABC240216P00100000", "put", 100.0, bars, 100)
    priced = implementation.PricedEvent(
        "ABC", pd.Timestamp("2024-01-08"), pd.Timestamp("2024-01-05"),
        pd.Timestamp("2024-01-09"), "front", pd.Timestamp("2024-02-16"),
        pd.Timestamp("2024-02-16"), 101.0, {"K": 100.0},
        {"C_K": call, "P_K": put, "C_U0.05": call},
    )
    return events, [priced]


class OptionExportTests(unittest.TestCase):
    def test_selected_legs_keep_event_identity_and_bars_deduplicate(self):
        events, priced = fixture()
        legs = implementation.option_leg_rows(events, priced)
        bars = implementation.option_bar_rows(priced)
        self.assertEqual(len(legs), 3)
        self.assertEqual(set(legs.event_id), {"CIK:0000000123:000123-24-000001:ABC"})
        self.assertEqual(legs.set_index("leg_code").loc["C_K", "contract_ticker"],
                         "O:ABC240216C00100000")
        self.assertEqual(legs.set_index("leg_code").loc["C_K", "shares_per_contract"], 100)
        self.assertEqual(legs.set_index("leg_code").loc["C_K", "spot_pre"], 101.0)
        self.assertEqual(len(bars), 4)  # two contracts times two observed sessions
        self.assertFalse(bars.duplicated(["contract_ticker", "session"]).any())

    def test_unknown_event_is_rejected(self):
        events, priced = fixture()
        events.loc[0, "ticker"] = "OTHER"
        with self.assertRaisesRegex(ValueError, "matching event"):
            implementation.option_leg_rows(events, priced)

    def test_missing_multiplier_is_not_assumed_standard(self):
        chain = [{"ticker": "A", "contract_type": "call", "strike_price": 100,
                  "expiration_date": "2024-02-16"},
                 {"ticker": "B", "contract_type": "put", "strike_price": 100,
                  "expiration_date": "2024-02-16", "shares_per_contract": 100}]
        with patch.object(data, "api_get_all", return_value=chain):
            got = data.fetch_chain("ABC", pd.Timestamp("2024-01-05"), 2, 60)
        self.assertEqual(got.ticker.tolist(), ["B"])
        self.assertIn("shares_per_contract", got.columns)

    def test_output_writes_contract_tables_and_manifest_hashes(self):
        events, priced = fixture()
        study = {"events": events, "priced": priced, "dropped": pd.DataFrame(),
                 "results": pd.DataFrame(), "board": pd.DataFrame()}
        with tempfile.TemporaryDirectory() as directory:
            out = Path(directory)
            main.write_outputs(study, pd.DataFrame(), out, {"entry": "post"})
            self.assertTrue((out / "option_legs.csv").is_file())
            self.assertTrue((out / "option_bars.csv").is_file())
            manifest = json.loads((out / "manifest.json").read_text(encoding="utf-8"))
            self.assertEqual(manifest["exported_tables"]["option_legs"]["rows"], 3)
            self.assertEqual(len(manifest["exported_tables"]["option_legs"]["sha256"]), 64)


if __name__ == "__main__":
    unittest.main()
