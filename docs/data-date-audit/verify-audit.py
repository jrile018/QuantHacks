"""Verify bounded audit structure, relative links and protected document pin."""
from pathlib import Path
import collections
import datetime as dt
import hashlib
import json
import re
import shutil

BASE = Path(__file__).resolve().parent
ROOT = BASE.parents[1]
NOW = dt.datetime.now(dt.timezone.utc).isoformat()


def read(name):
    return json.loads((BASE / name).read_text(encoding="utf-8-sig"))


def write(name, value):
    (BASE / name).write_text(json.dumps(value, indent=2, ensure_ascii=True) + "\n", encoding="utf-8")


parsed = []
for path in sorted(BASE.rglob("*.json")):
    assert path.stat().st_size < 2_000_000, str(path)
    json.loads(path.read_text(encoding="utf-8-sig"))
    parsed.append(path.relative_to(BASE).as_posix())
ledger = read("gap-ledger.json")
inventory = read("availability-date-matrix.json")
performance = read("performance-availability.json")
minimal = read("first-arm-blocker-map.json")
reporting = read("receipts/reporting-decision.json")
gap_ids = {g["id"] for g in ledger["gaps"]}
evidence_ids = {e["id"] for e in ledger["evidence"]}
assert len(gap_ids) == len(ledger["gaps"]) == 22
assert len(evidence_ids) == len(ledger["evidence"])
assert len({r["id"] for r in ledger["requirements"]}) == 30
required = {"id", "arm_priority", "status", "claimed_state", "verified_state", "discrepancy_counterexample", "consequence", "owner", "dependency", "next_action", "acceptance_condition", "evidence", "observed_at"}
for gap in ledger["gaps"]:
    assert required <= gap.keys(), gap["id"]
    assert gap["status"] in {"done", "partial", "missing", "blocked", "deferred", "not verifiable"}
    assert set(gap["evidence"]) <= evidence_ids, gap["id"]
    assert all(gap[k] for k in required - {"evidence"}), gap["id"]
for requirement in ledger["requirements"]:
    assert requirement["gap_ids"] and set(requirement["gap_ids"]) <= gap_ids
assert set(next(r for r in ledger["requirements"] if r["id"] == "R30")["gap_ids"]) == gap_ids
assert len({p["id"] for p in inventory["packets"]}) == len(inventory["packets"])
for packet in inventory["packets"]:
    assert set(packet["gap_ids"]) <= gap_ids
    assert set(packet["evidence"]) <= evidence_ids
    assert packet["historically_observed_location"] and packet["live_location_status"]
    assert packet["economic_consumer_current_binding_accepted"] is False
fields = {f["field"]: f for f in inventory["time_fields"]}
assert len(fields) == len(inventory["time_fields"]) == 17
assert fields["provider_receive"]["coverage"] is None
assert fields["quote_update"]["coverage"] is None
assert "quote_update_interval_endpoint" not in fields
assert fields["vendor_interval_endpoint"]["coverage"] == 1028190
assert fields["last_trade_event"]["coverage"] == {"parsed": 1013110, "missing": 15080}
assert fields["sec_acceptance"]["coverage"] == 8
assert len(performance["paths"]) == 4
for path in performance["paths"]:
    assert path["measured"] is False
    assert all(v is None for v in path["values"].values())
    assert set(path["values"]) == set(path["null_reasons"])
    assert all(path["null_reasons"].values())
assert reporting["answer"] == "Wait for qualified inputs before reporting performance"
assert reporting["message"] == "01a1060a-c9cb-7b91-9a3f-0668dbd47fae"
assert ledger["decision_frontier"]["pending_existing_elsewhere"] is None
assert ledger["decision_frontier"]["new_questions"] == []
assert minimal["pending_human_question"] is None
assert minimal["canonical_consumer"]["economic_acceptance"] is False
assert {g["id"] for g in minimal["ordered_dependencies"]} <= gap_ids
calendar = read("receipts/calendar-reconciliation.json")
assert (calendar["financial_rows"], calendar["financial_unique_dates"], calendar["reference_sessions"], calendar["issuer_session_rows"], calendar["difference_rows"]) == (2092, 523, 502, 2008, 84)
assert len(calendar["financial_dates_absent_calendar"]) == 21
assert calendar["calendar_dates_absent_financial"] == []
assert calendar["issuer_sets_equal"] and calendar["no_zero_fill"]
post = read("receipts/post-evidence.json")
assert post["fresh_hash_verification"]["all_eight_match"]
assert not post["fresh_hash_verification"]["suite_rerun"]
assert not post["fresh_hash_verification"]["full196source_reaudit"]
assert len([x for x in post["fresh_hash_verification"]["checks"] if x.get("match")]) == 8

links = []
for name in ["FINDINGS.md"]:
    text = (BASE / name).read_text(encoding="utf-8")
    assert "<<<<<<<" not in text and ">>>>>>>" not in text
    assert "It remains pending in that chat" not in text
    assert "Wait for qualified inputs before reporting performance" in text
    for target in re.findall(r"\]\(([^)\s]+)\)", text):
        if target.startswith(("https://", "http://", "#")):
            continue
        assert (BASE / target.split("#")[0]).exists(), target
        links.append(target)
alpha = ROOT / "docs/research/2026-10-04-alpha-pilot-and-lean-review.md"
alpha_sha = hashlib.sha256(alpha.read_bytes()).hexdigest()
assert alpha_sha == "9b6dbc6ab013f3a50c90af2e5072235ab29cabf50bc2875bd76dbe3e2140f25e"
for name in ["seed-audit-2026-10-04.md", "evidence-snapshot.json", "handoff-prompt.md"]:
    assert (BASE / name).is_file()

storage = read("receipts/storage-binding-evidence.json")
verification = {"schema_version": "data-date-audit-verification-v1", "observed_at_utc": NOW, "commands": ["python docs/data-date-audit/refresh-audit.py", "python docs/data-date-audit/verify-audit.py"], "result": "pass", "json_files_parsed": parsed, "gap_count": 22, "requirement_count": 30, "packet_count": len(inventory["packets"]), "time_field_count": 17, "references_valid": True, "findings_local_links_checked": links, "all_performance_values_null_with_reasons": True, "reporting_choice_directly_verified": reporting["message"], "alpha_review_sha256_unchanged": alpha_sha, "original_seed_snapshot_handoff_preserved_by_action_scope": True, "source_snapshot_hash_domain": "Current owned file bytes; initial seed byte hash was not independently captured by this verifier", "source_suite_or_job_rerun": False, "storage_notice_does_not_negate_historical_proofs": True, "C_free_bytes_at_check": shutil.disk_usage(ROOT).free, "independent_review": {"agent": "/root/audit_review", "reviewed_generated_recorded_at_utc": "2026-10-04T08:35:18.708514+00:00", "result": "no remaining must-fix claim or reference issue", "later_changes": "Exact human qualified-only reporting answer and nonblocking label polish; final structure/link/hash check covers current outputs"}}
write("verification.json", verification)
byid = {g["id"]: g for g in ledger["gaps"]}
byid["DD20"]["verified_state"] = "Initial OS112 shell/Node/write failures retained. Scoped metadata reads/writes,22-gap/30-requirement JSON/reference checks,17timecategories,local findings links and protected alpha hash now pass. Broad disk capacity and source migration remain separate."
byid["DD20"]["closed_subgates"] = ["Bounded audit metadata read/write recovered", "Current audit structure/link/hash verification passed"]
byid["DD20"]["next_action"] = "Keep small metadata I/O; use DD22 exact live bindings for migrated consumed inputs; do not delete others' files or duplicate bulk"
write("gap-ledger.json", ledger)
for i, gap in enumerate(minimal["ordered_dependencies"]):
    if gap["id"] == "DD20":
        minimal["ordered_dependencies"][i] = byid["DD20"]
write("first-arm-blocker-map.json", minimal)
closure = read("closure-receipts.json")
closure["current_reporting_decision"] = reporting
closure["question_boundary"] = "Reporting choice settled: wait for qualified inputs; no repeated interview or provisional performance permission"
write("closure-receipts.json", closure)
plan = f"""# Data and date audit: completed bounded checkpoints

Recorded {NOW}. Progress: 6/6 named audit checkpoints. This is completion of the evidence/register/handoff work, not completion of the economic backtest.

- [x] Restore seed, instructions and owner boundaries; preserve original seed/snapshot/handoff and root Post plans.
- [x] Verify exact human scope and later long/short, gross cap, cash-yield and qualified-only reporting decisions.
- [x] Collect bounded independent Post, Industry, financial and Lattice receipts; deliver scoped owner requests.
- [x] Reconcile actual523/502date sets, cohort/model clocks, v1/v2 recipes, new2024candidate/2023aggregate versions and migrated input bindings.
- [x] Save22-gap/30-requirement register,23-packet/17-clock inventory, metric-null table and one canonical first-arm blocker map.
- [x] Clear independent review; pass fresh owned JSON/reference/link checks, retain protected alpha hash and record delivery separately from acceptance.

Only docs/data-date-audit/ was edited. Planning skill: writing-plans; execution/audit/parallel routing/verification skills applied. Systematic-debugging identified the inventory-tool limit error and patch context order; the storage owner was found via an independent bounded lookup. No producer code, source adapter, acquisition, model fit, full suite, cleanup, remote bulk fetch, merge, deployment, final-test opening or live trade was launched by this chat.

Initial OS112 shell/Node/write failures are retained. Small metadata I/O recovered. Ten named Industry root metadata files are now locally absent; nine historical hashes match recorded backup entries. Actual remote bytes still require consumer verification. Benchmark/Post worktree input/config/calendar files remain separate and freshly match their retained hashes. See DD22 and the storage binding receipt; never silently alias an old path.

Human reporting answer directly inspected: message01a1060a-c9cb-7b91-9a3f-0668dbd47fae in Organize Benchmark Data Push: Wait for qualified inputs before reporting performance. Prior pending-Q4 references remain historical. No new interview is required. Zero passive cash yield retains balances/flat days; <=100%gross does not force investment. All other settled choices and delegated Post recipe ownership persist.

Canonical economic replay remains Post-owned. Two AMT2024research candidates exist; the completed Benchmark packet still has fourselected2023events/threediagnostic/zeroqualified. Needed: exact2024text/version/scores/public bound/model provenance; calendar/security/quote/actions/costs/short lifecycle; accepted input path bindings; then regularly marked net accounts and registered dependence-aware inference. No measured PnL/Sharpe/win rate is reported. Financial-only and derivative requirements stay deferred unless consumed. Lattice's separate full approved work continues under its own human override.

Commands and byte fingerprints: verification.json and artifact-manifest.json. Delivery receipts: closure-receipts.json. Successful delivery never implies downstream consumer acceptance.
"""
(BASE / "plan-progress.md").write_text(plan, encoding="utf-8")
manifest = {"schema_version": "data-date-audit-artifact-manifest-v1", "observed_at_utc": NOW, "hash_domain": "Exact owned audit file bytes, including preserved original snapshots; excludes this manifest to avoid self-reference", "files": []}
for path in sorted(BASE.rglob("*")):
    if path.is_file() and path.name != "artifact-manifest.json" and "__pycache__" not in path.parts:
        data = path.read_bytes()
        manifest["files"].append({"path": path.relative_to(BASE).as_posix(), "bytes": len(data), "sha256": hashlib.sha256(data).hexdigest()})
write("artifact-manifest.json", manifest)
print(json.dumps({"result": "pass", "gaps": 22, "requirements": 30, "packets": len(inventory["packets"]), "time_fields": 17, "local_links": len(links), "artifact_files": len(manifest["files"]), "C_free_bytes": verification["C_free_bytes_at_check"], "alpha_hash_unchanged": True}))
