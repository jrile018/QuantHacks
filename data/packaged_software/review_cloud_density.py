"""Publish individually reviewed additional cloud evidence from pinned SEC bytes."""
import hashlib
import json
import re
from pathlib import Path

import pandas as pd

from review_infrastructure_sources import source_text

ROOT = Path(__file__).resolve().parent
OUT = ROOT / "extracts/infrastructure_evidence"
# Clauses and surrounding footnote/table context were read, not inferred from names.
REVIEWS = [
    ("a5f69810196c084731cdec51", "dd656c3c031d2383c65dc57eece2b271b5e19c7a93612e4b049c60e60bbd9f3c",
     "cloud_contract_minimum_total_disclosed_usd", 230300000,
     r'for a total commitment of \$ 230\.3 million from August 2024 to July 2027\.',
     "", "2024-09-30", "AWS three-year contract total; annual schedule and $10m spent are distinct. Microsoft euro commitment excluded."),
    ("e985b9390e5799960028bc24", "2f45b8f9bb3929b41f7a6888182275a90b8290c5a09fc1895f502a0c5fe7b309",
     "mixed_services_commitments_primarily_cloud_disclosed_usd", 28100000,
     r'Our total commitments under these agreements are \$28\.1 million and are primarily for cloud infrastructure and cloud services\.',
     "", "2023-12-31", "Non-cancelable third-party agreements, primarily cloud. Not a pure cloud-only total or actual expense."),
    ("63f51c530e87a916c0c3b3d9", "335b007f51daa5073a6e0a86634712a8f0223a0c6f2d197c3646bc809b6fbf54",
     "mixed_services_commitments_primarily_cloud_disclosed_usd", 156400000,
     r'Our total commitments under these agreements are \$156\.4 million and are primarily for cloud infrastructure and cloud services\.',
     "", "2024-12-31", "Non-cancelable third-party agreements, primarily cloud. Not a pure cloud-only total or actual expense."),
    ("1cb90de588919b246ff43504", "09c827b22c38fa82100a0aed159a99391d1fab28336239e77bc594fb7665170b",
     "mixed_services_commitments_primarily_cloud_disclosed_usd", 121400000,
     r'Our total commitments under these agreements are \$121\.4 million and are primarily for cloud infrastructure and cloud services\.',
     "", "2025-12-31", "Non-cancelable third-party agreements, primarily cloud. Not a pure cloud-only total or actual expense."),
    ("b0cdf12f7ec2d6398c3e8ae7", "fbcd34446d292e40784dfd4c1a8a49af5716e43e21165757c14018c842fe0701",
     "unused_cloud_commitment_expense_quarter_disclosed_usd", 1312000,
     r'Unused cloud hosting commitment expense 1,312',
     "2024-01-01", "2024-03-31", "G&A expense table in thousands, current 2024 quarter column. One-time termination-related expense, not recurring cloud operating cost; prose rounds to $1.3m."),
]


def main():
    candidate_path = OUT / "cloud_commitment_amount_candidates.csv"
    candidates = pd.read_csv(candidate_path, dtype=str).fillna("")
    rows = []
    for evidence, expected_hash, feature, value, pattern, start, end, scope in REVIEWS:
        # A sentence can generate several amount candidates; the reviewed exact
        # source clause, not the first nearby candidate amount, defines the value.
        match = candidates[candidates.evidence_id == evidence].drop_duplicates(
            ["cik", "ticker", "filed_date", "local_path", "source_url"])
        if len(match) != 1:
            raise ValueError("Missing or ambiguous reviewed evidence: " + evidence)
        r = match.iloc[0]
        text, actual_hash = source_text(r.local_path)
        if actual_hash != expected_hash:
            raise ValueError("Source changed; new review required")
        clause = re.search(pattern, text)
        if not clause:
            raise ValueError("Reviewed source clause changed")
        if r.ticker == "KLTR":
            before = text[max(0, clause.start() - 650):clause.start()]
            if not all(s in before for s in ["Three Months Ended March 31", "2024 2023", "in thousands"]):
                raise ValueError("Expense table scope/unit check failed")
        available = (pd.Timestamp(r.filed_date) + pd.Timedelta(days=1)).date().isoformat()
        rows.append(dict(cik=r.cik, ticker=r.ticker, feature=feature, value=value,
                         available_date=available, period_start=start, period_end=end,
                         source_file="extracts/infrastructure_evidence/additional_reviewed_cloud_observations.csv",
                         evidence_ref=evidence, quality_status="individually_reviewed_exact_clause_scope_and_source_hash",
                         scope=scope, source_url=r.source_url, source_sha256=actual_hash,
                         local_path=r.local_path, source_clause=clause.group(),
                         source_context=text[max(0, clause.start()-900):clause.end()+450], unit="USD"))
    dest = OUT / "additional_reviewed_cloud_observations.csv"
    pd.DataFrame(rows).to_csv(dest, index=False)
    audit = dict(reviewed_records=len(rows), companies=len({r["cik"] for r in rows}),
                 input_sha256=hashlib.sha256(candidate_path.read_bytes()).hexdigest(),
                 output_sha256=hashlib.sha256(dest.read_bytes()).hexdigest(),
                 source_sha256={r["local_path"]: r["source_sha256"] for r in rows},
                 limitations="Four commitment records and one exceptional expense. Mixed commitments do not become cloud-only commitments; no cash payments inferred.")
    (OUT / "additional_cloud_review_audit.json").write_text(json.dumps(audit, indent=2) + "\n")
    print(json.dumps({k: v for k, v in audit.items() if "sha256" not in k}, indent=2))


if __name__ == "__main__":
    main()
