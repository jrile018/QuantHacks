"""Build bounded audit documents from owned, independently inspected receipts.

Reads small metadata only. Does not execute producers, strategies, or test suites.
"""
import collections
import datetime as dt
import hashlib
import json
from pathlib import Path

BASE = Path(__file__).resolve().parent
ROOT = BASE.parents[1]
NOW = dt.datetime.now(dt.timezone.utc).isoformat()


def read(name):
    return json.loads((BASE / name).read_text(encoding="utf-8-sig"))


def write(name, data):
    (BASE / name).write_text(json.dumps(data, indent=2, ensure_ascii=True) + "\n", encoding="utf-8")


def link(name, label=None):
    return f"[{label or name}](./{name})"


ledger = read("gap-ledger.json")
post = read("receipts/post-evidence.json")
industry = read("receipts/industry-evidence.json")
financial = read("receipts/financial-evidence.json")
calendar = read("receipts/calendar-reconciliation.json")
root_receipt = read("receipts/root-evidence.json")
lattice = read("receipts/lattice-evidence.json") if (BASE / "receipts/lattice-evidence.json").exists() else None
first_arm_refresh = read("receipts/first-arm-owner-refresh.json") if (BASE / "receipts/first-arm-owner-refresh.json").exists() else None
storage_binding = read("receipts/storage-binding-evidence.json") if (BASE / "receipts/storage-binding-evidence.json").exists() else None
reporting_decision = read("receipts/reporting-decision.json") if (BASE / "receipts/reporting-decision.json").exists() else None

# Correct an approximate receipt-staging time; retain the inspector's real limits.
if "received_at_utc" in industry:
    industry["original_staging_time_not_verified"] = industry.pop("received_at_utc")
    industry["root_recorded_at_utc"] = NOW
    write("receipts/industry-evidence.json", industry)

new_evidence = [
    ("E13", "inspected small artifact bytes", "receipts/root-evidence.json", "Git HEAD does not identify mutable artifacts; mtime is not publication"),
    ("E14", "delegated inspected artifact + fresh bounded hashes + retained runtime", "receipts/post-evidence.json", "Eight runtime receipts freshly hashed; 196 source matches retained, not freshly repeated; some input hashes are declared pins"),
    ("E15", "delegated inspected local artifact bytes", "receipts/industry-evidence.json", "Remote market bytes not reread; publication proxies assumed; producer diagnostics not consumer acceptance"),
    ("E16", "delegated inspected local metadata + retained runtime", "receipts/financial-evidence.json", "Producer output pins read, not all rehashed; no full native audit or remote archive rerun"),
    ("E17", "fresh actual date-set comparison and byte hashes", "receipts/calendar-reconciliation.json", "Classifies scaffold dates; does not qualify price, security, schedule knowledge or execution joins"),
]
if lattice:
    new_evidence.append(("E18", "delegated inspected Lattice metadata", "receipts/lattice-evidence.json", "Adjusted-close numerical diagnostics, not accepted wording account performance; no remote input rehash or fit"))
if first_arm_refresh:
    new_evidence.append(("E19", "bounded new first-arm owner version refresh", "receipts/first-arm-owner-refresh.json", "New producer candidate/input versions do not imply Post acceptance; receipt distinguishes owner report from byte proof"))
new_evidence.append(("E20", "relayed human-authorized storage boundary" if not storage_binding else "bounded storage binding metadata inspection", "receipts/first-arm-owner-refresh.json" if not storage_binding else "receipts/storage-binding-evidence.json", "Historical observed paths and backup manifest pins are not a current live remote byte verification or consumer binding"))
if reporting_decision:
    new_evidence.append(("E21", "directly inspected exact human message", "receipts/reporting-decision.json", "Settles reporting mode; no provisional performance,final-test or live-capital permission"))
ids = {e[0] for e in new_evidence}
ledger["evidence"] = [e for e in ledger["evidence"] if e["id"] not in ids]
for eid, klass, name, limitation in new_evidence:
    ledger["evidence"].append({"id": eid, "class": klass, "location": (BASE / name).as_posix(), "recorded_at": NOW, "observation_times": "see scoped receipt; records are not an atomic simultaneous snapshot", "limitation": limitation})

updates = {
    "DD01": ("partial", "2092 financial rows = 523 identical issuer weekdays; 2008 document decisions = 502 sessions (252 in2024,250 in2025). Exact difference is21 exchange closures x4=84 rows, no session absent financial grid. Six early-close decisions at12:30 local precede13:00close.", "Classification is closed. Financial21:00Z diagnostic clock is not issuer15:30 or executable quote time; retrospective calendar is not proof of schedule known at an earlier decision.", "P1 financial date classification; P0 only actual wording calendar/session consumer join", ["E14", "E16", "E17"]),
    "DD02": ("partial", "Wording15docs=8primary8Ks+7exhibits,8accessions,4CIKs; conditional13docs/7accessions/2248fragments versus total2391fragments. Financial45originals,37requests,36historyaccessions,8384cells,424groups,500XMLnodes,844states remain separate grains.", "Current pinned packet taxonomy is reconciled. Event grouping, admissible opportunities, predictions, orders/fills, closed episodes and daily NAV require actual consumer denominators; fragments are not independent events.", "P0 wording / P1 financial", ["E14", "E16"]),
    "DD03": ("partial", "Post22sources:20conditional and2quarantined. Industry current-v2:35rows/13proxy candidates/22excluded; history-v2:37rows/0proxy candidates; history-v3:37rows/37proxy candidates/0flags, but0known public/0observed ready/canonical_ready=false.", "Post filing-day-end+60s/byte-equality and Industry SECacceptance+24h are assumptions. No exact-version supported historical public-by proof or actual historical receipt is established.", "P0 wording", ["E14", "E15"]),
    "DD04": ("partial", "Post3008unadjusted daily bars=752each fourtickers,2023-01-03..2025-12-31. Industry configured window2024-01-01..2026-01-01exclusive;98selected files scanned,46derivativequote files unscanned. Its128AMTcandidates are one-day2024-01-02 12:01..16:34UTC producer diagnostics, outcomes unread/consumer_accepted=false.", "Existing2023 daily text/bar date overlap does not establish required executable open+60s/close-60s quotes. New producer event aggregation may supersede the current packet; global absence of text/quotes is not proved.", "P0 wording", ["E14", "E15"]),
    "DD05": ("partial", "Post2024 diagnostic has752forecasts/188dates and unadjusted next-close target excluding dividendcash; MSEratio1.0426 versuszero. Lattice adjusted-close targets/hedge controls and distinct horizons remain separate.", "MSE is not portfolio PnL, Sharpe or win rate; later closing prices cannot enter earlier decision features. Lattice numerical diagnostics are not a matched wording comparator.", "P1 diagnostic reconciliation; P0 if target/comparison consumed", ["E14"] + (["E18"] if lattice else [])),
    "DD06": ("partial", "EQUS1028190 interval rows;15080 ts_event missing,1013110 parsed events,1028190 parsed receives. ts_event is optional last trade; ts_recv vendor minute endpoint, not our historical receipt or quote update.", "Component venue does not establish NBBO, fills or quote freshness; missing trade times are not filled, and no last-trade age screen can certify quote age.", "P0 equity", ["E15"]),
    "DD07": ("partial", "Frozen quality rule has21degraded dates, distinct from the21calendar closure dates. Adapter feature/holding intersection exists; actual wording consumer mask accepted=false, independent historical identity/action qualification=false.", "Implemented checks do not prove propagation through actual event, quote, order, fill and valuation cohort. Preserve no-fill, censored and excluded observations, including action/borrow uncertainty.", "P0 equity", ["E15"]),
    "DD08": ("partial", "ProsusAI/finbert@db38d3727cbaed87c9aed72df7b3519e2ba5cca1 scored15docs/2391fragments,0failed,1truncated; completed2026-10-04T02:22:47.209449Z. V2 aggregation recipe now frozen.", "Training cutoff and historical model/version availability are unqualified. Current processing completion is not historical signal readiness; document/text span, dedup/truncation and event aggregation still need accepted provenance.", "P0 wording", ["E14"]),
    "DD09": ("partial", "V2 recipe exactbyteSHA e7197cea447fe9e413fe659b4ab2bdd41468e6cdb4933d7f82fb4560bab78acb supersedes preservedv1; freeze2026-10-04T08:00:11.116997Z. Linked252-session2024calendar file/row hashes match. USD1m, long/short, equally sized eligible targets,<=100%gross,no leverage; zero passive cash yield preserves cash balances/flat days.", "Static contract/entry+flat-close checks do not establish qualified source/model/identity/actions/costs/borrow/short lifecycle or continuous intraday gross cap. Forced full investment is not authorized; unknown costs are not zero.", "P0 policy/execution", ["E02", "E03", "E14"]),
    "DD10": ("missing", "No accepted regularly marked, costed USD1m challenger/matched-long/cash account series is evidenced in this bounded audit.", "Sparse/terminal or synthetic fixture marks cannot support measured return, SharpeCI, drawdown or win rate. Retain open/cash/flat/loss/no-fill/action/dividend/borrow flows; zero cash yield does not mean zero balance.", "P0 account/metrics", ["E14"]),
    "DD11": ("partial", "Existing inference research/plan inspected: regularly marked account daily net returns, temporal dependence, joint matched paths, HAC/studentized block bootstrap and declared95%CI. No accepted inference input exists.", "Event/fragment counts are not independent observations. Existing2024/25 inspection is DEVELOPMENT; a config excluding2025 does not restore untouched status. Final test remains closed; no human success threshold is invented.", "P0 inference after accepted net series", ["E13", "E14"] + (["E18"] if lattice else [])),
    "DD12": ("partial", "Seed, evidence-snapshot and handoff preserved. Current receipt versions and hash domains are explicitly separated: Industrycurrentv2/historyv3, financialproducerV7/auditorV8, Postv1/v2. Root alpha-review SHA remains9b6dbc6ab013f3a50c90af2e5072235ab29cabf50bc2875bd76dbe3e2140f25e.", "Concurrent owner edits mean this is bounded versioned evidence, not an atomic latest-state snapshot. Coordinator shared-record amendments and downstream pins remain pending owner acceptance.", "P0 shared / P1 financial", ["E13", "E14", "E15", "E16"]),
    "DD13": ("deferred", "Four entity-wide GAAP USD instant tags retained separately. Historical8368selected cells have no AAT prior-period warnings; current16cells have15AATwarnings with March31operand versus June30latest accession. Historical/public clocks unqualified; proposal inactive.", "Fiscal instant is not disclosure. June native facts do not silently replace March aggregate; liabilities are not debt. Exact AMT later-disclosed old-period comparison remains pending.", "P1 financial next; P0 only if consumed", ["E16"]),
    "DD14": ("deferred", "Macro820observations=818numeric+2null;0historical-asof-qualified. BLS CUUR0000SA0/LNS14000000:2025:M10 official dashes retained as null; current retrieval/processing2026-10-04.", "Retrieval/current value is not first-release/revision vintage; do not backdate or fill missing values.", "P1 macro; P0 only if consumed", ["E16"]),
    "DD15": ("deferred", "Universe counts53SIC candidates/100configured/5observed options are distinct scopes.", "Disjoint scopes do not establish non-REIT status, historical membership, survivor-free selection or instrument identity.", "P2 universe; no first equity dependency", ["E15"]),
    "DD16": ("deferred", "OPRA882288definition rows/292251ids versus259852151quote rows; GLBX64622definition rows=17987F+46635S versus5063606BBO rows. Multipliers/deliverables/actions/calendars/rolls/execution unaccepted.", "Download integrity and definition counts do not qualify contracts or costs; unknown multiplier is not default100. Derivatives remain separate later arm.", "P2 derivatives", ["E15"]),
    "DD17": ("done", "All eight collected final runtime receipt hashes freshly match; collection verifier and acceptance capsule independently hashed. Retained final690tests/0skips/5.450s/exit0,196source matches,110outputs/109bindings/8roles. Actual3descriptive groups/4rawnodes/1state;0canonical/0human gold.", "Closure is bounded descriptive transport/namespace receipt verification. The690suite/196source sweep/full numeric audit were not rerun and do not establish public-time or economic eligibility.", "P1 native; P0 only if consumed", ["E14", "E16"]),
    "DD18": ("partial", "Final producer delivery receipt inspected:21local thin metadata files; remote V7archive pin14216041bytes/SHAfd39baea32a63349eabb4e043e4710a38add56e14ad55d0bd3650d6f6a7a2dc1; role/path/inner manifest pins retained.", "Live remote archive bytes/hash not reverified or downloaded by audit. Thin metadata, archive and small prepared fixture are separate objects, no economic grant.", "P2 archive/storage", ["E16"]),
    "DD19": ("partial", "Direct human decisions/amendments verified. Existing delayed post-release gate permits evidenced exact-version public-by bound with latency while earliest remains unknown. Initial six owner requests and changed Post/parent checkpoint delivered; past delivery failures retained.", "Shared policy record can lag direct human decisions. Delivery is not acceptance. Existing DataPushQ4 qualification-before-headlines versus labelled provisional scenario is pending; elapsed time/recommendation is not an answer.", "P0 decisions/delivery", ["E02", "E03", "E11", "E13", "E14"]),
    "DD20": ("partial", "Initial OS112 shell/Node/write failures retained. Scoped reads, receipt writes and exact date comparison now succeed; final small artifact verification pending. No cleanup, bulk copy or local heavy job performed by audit.", "Audit metadata path recovered; broad disk capacity is not certified. Storage failure does not negate prior retained runtime proofs or authorize deleting others' files.", "P1 storage operation; P0 if metadata cannot be completed", ["E10", "E13", "E14", "E17"]),
    "DD21": ("missing", "Pinned wording packet has8primary filing/accession events with SECacceptance2023-01-05..2023-03-01 and7exhibits with null acceptance. Frozenv2 window remains2024-01-01..2025-01-01exclusive.", "No2024 accession/filing event in this pinned2023packet under frozen event-window rule. This is not global no2024text/quotes or a completed market join. If event_date differs, require row evidence; newer Benchmark aggregation is pending.", "P0 wording alignment", ["E14", "E15"]),
}
for gap in ledger["gaps"]:
    if gap["id"] == "DD22":
        continue
    status, verified, discrepancy, priority, evidence = updates[gap["id"]]
    gap.update(status=status, verified_state=verified, discrepancy_counterexample=discrepancy, arm_priority=priority, observed_at=NOW)
    gap["evidence"] = list(dict.fromkeys(gap["evidence"] + evidence))
    gap["consequence"] = "Bounded descriptive receipt gate closed; no field-clock/economic readiness" if status == "done" else ("Separate later arm remains disabled until its own qualification" if status == "deferred" else "Audit classification is recorded; listed consumer acceptance remains pending")
    gap["next_action"] = gap["next_action"].replace("cash0 comparator", "zero-yield cash comparator with retained balances")

byid = {g["id"]: g for g in ledger["gaps"]}
byid["DD01"]["closed_subgates"] = ["Actual523/502date-set subtraction,21named closures,84issuer rows", "Six early-close decisions before actual close; no missing equity session"]
byid["DD01"]["next_action"] = "Post bind actualv2 entry/exit/account dates to accepted known-at-decision product calendar; Benchmark retain financial scaffold diagnostic. No holiday zero-fill."
byid["DD01"]["acceptance_condition"] = "Calendar classification receipt is accepted for bounded audit; consumer session/time/security/schedule qualification has exact receipt before economic use"
byid["DD08"]["next_action"] = "Benchmark bind existing exact scored spans/model revision and aggregation to eligible event manifest; Post accept or exclude model/text/time qualification without a new model"
byid["DD09"]["claimed_state"] = "Direct human: hypotheticalUSD1m,long/short,equal eligible targets,gross<=100%,no leverage,zero passive cash yield; v2 static freeze inspected"
byid["DD10"]["next_action"] = "Post produce regularly marked three net account paths, with cash balance/flat/no-fill sessions and explicit costs, collateral, actions and closed-episode tie/censor rules"
byid["DD11"]["next_action"] = "Sharpe lane finish owned inference contract/negative fixtures; apply registered joint dependence-aware95%interval only after Post net-series acceptance; preserve trial/fold ledger and DEVELOPMENT labels"
byid["DD17"]["next_action"] = "Preserve completed bounded runtime receipt verification; leave clock/numeric/economic requirements under their own gaps"
byid["DD20"]["owner"] = "Audit metadata verification; storage capacity remains external"
byid["DD20"]["next_action"] = "Finish small audit JSON/link/hash checks; retain OS112 history and avoid bulk I/O"
byid["DD21"]["next_action"] = "Benchmark/Post publish exact admissible existing event-date cohort and Industry executable holding-window coverage, or explicit versioned recipe/window revision within human-delegated scope; never reopen protected tests"
byid["DD21"]["acceptance_condition"] = "Row-level exact text/version/public-by/model/event/security/calendar/quote/action/cost admissible intersection accepted by Post, with excluded/censored/no-fill counts; otherwise first-arm result unavailable"
storage_gap = {"id": "DD22", "arm_priority": "P0 consumed input bindings;P1 unconsumed historical storage", "status": "partial", "claimed_state": "Another human-authorized owner migrating backed non-Databento root data/artifacts/cache to remote snapshot/archive", "verified_state": "Relayed owner notice names home-pc:/tmp/quanthaxs-riley-20261004/repo, immutable archive and29102-row backup manifest; exact current first-arm binding receipt pending" if not storage_binding else "Named small path/backup binding checks recorded in receipts/storage-binding-evidence.json; inspect individual local/remote verification flags before consumer use", "discrepancy_counterexample": "A previously hashed root path can become unavailable; retained historical proof does not certify current local or remote input bytes. Worktree inputs are separate roots and cannot be silently remapped.", "consequence": "Post requires current exact consumed path/byte/hash/version binding before replay; unrelated prior runtime receipts remain valid past facts", "owner": "Storage owner + Industry/Benchmark producers + Post consumer", "dependency": "DD03,DD04,DD08,DD09", "next_action": "Coordinate exact affected first-arm bindings with storage owner; verify matching backup/restore hashes and accepted current input manifest. Keep bulk remote; no duplicate backup or cleanup by audit.", "acceptance_condition": "For each consumed input, explicit local/remote path, bytes,SHA256,role,version,verification time and Post accepted consumer binding; missing live file remains unavailable until restored/mapped", "evidence": ["E19", "E20"] if first_arm_refresh else ["E20"], "observed_at": NOW}
ledger["gaps"] = [g for g in ledger["gaps"] if g["id"] != "DD22"] + [storage_gap]
byid["DD22"] = storage_gap

for req in ledger["requirements"]:
    if req["id"] == "R19":
        req["requirement"] = "USD1m equal eligible targets long/short<=100%gross,no leverage,zero passive cash yield; cash balances/flat days retained,short collateral,integer quantities/drift enforcement"
    req["audit_trace_status"] = "mapped to bounded evidence and explicit owner/acceptance condition; not a claim of implementation closure"
    if req["id"] in ["R02", "R13", "R18", "R26", "R27", "R29", "R30"]:
        req["gap_ids"] = list(dict.fromkeys(req["gap_ids"] + ["DD22"]))
ledger["observed_at"] = NOW
ledger["persistence"] = "Integrated bounded receipts; source snapshots preserved; consumer/economic gates remain open"
ledger["decision_frontier"]["new_questions"] = []
ledger["decision_frontier"]["cash_clarification"] = "Zero cash yield/passive income; no forced full investment or zero cash balance"
ledger["performance"]["reason"] = "No accepted costed regular net account replay; zero-variance cash Sharpe/delta undefined; Q4 pending elsewhere"
ledger["coverage_boundary"] = f"{len(ledger['gaps'])} known gaps/30 requirements traced through named small metadata packets; no exhaustive raw corpus/remote market scan, no atomic latest-state claim"
if first_arm_refresh:
    ledger["latest_first_arm_owner_refresh"] = {"receipt": (BASE / "receipts/first-arm-owner-refresh.json").as_posix(), "evidence": "E19", "effect": "New producer candidate versions are additional packets; original pinned2023cohort finding remains scoped to that packet. Follow exact blocker map, not a global absence claim."}
    for gid in ["DD02", "DD03", "DD04", "DD08", "DD09", "DD12", "DD19", "DD21"]:
        byid[gid]["evidence"] = list(dict.fromkeys(byid[gid]["evidence"] + ["E19"]))
        byid[gid]["new_owner_receipt"] = (BASE / "receipts/first-arm-owner-refresh.json").as_posix()
    byid["DD02"]["verified_state"] += " New Benchmark completed packet:4selected2023accessions/3diagnosticdocuments/925diagnosticfragments/1642selectedscoredfragments,0qualified/0economic/0complete2024events; producer completion is not consumer acceptance."
    byid["DD21"]["verified_state"] += " New Industry research candidates:AMT2024-02-27/2024-10-29,2documents,0accepted public bounds; exact retained exhibit bytes/scores not established. Benchmark minimal2024check active at receipt cutoff."
    byid["DD08"]["verified_state"] += " Model provenance summary byte-hashed:2023-06-05safetensors variant metadata matches retained weight OID, but current weight body not rehashed, earlier-checkpoint equivalence/training cutoff unknown, historical transform and weight rights not accepted. Format commit date is not proof of future training."
if reporting_decision:
    ledger["decision_frontier"]["pending_existing_elsewhere"] = None
    ledger["decision_frontier"]["resolved_existing_elsewhere"] = reporting_decision
    ledger["decision_frontier"]["settled"] = list(dict.fromkeys(ledger["decision_frontier"]["settled"] + ["Wait for qualified inputs before reporting performance"]))
    ledger["performance"]["reason"] = "No accepted costed regular net account replay; zero-variance cash Sharpe/delta undefined; human requires qualified inputs before performance"
    byid["DD19"]["verified_state"] += " Reporting mode directly verified in humanmessage01a1060a-c9cb-7b91-9a3f-0668dbd47fae:Wait for qualified inputs before reporting performance. Prior pending references are historical."
    byid["DD19"]["discrepancy_counterexample"] = "Shared records and downstream pins require current version acknowledgement; delivery is not acceptance. Reporting choice is settled; no duplicate interview or provisional performance permission."
    byid["DD19"]["next_action"] = "Deliver exact human reporting answer and current blocker map; retain past failed deliveries and snapshot versions; continue only input qualification needed for canonical Post replay"
    byid["DD19"]["evidence"] = list(dict.fromkeys(byid["DD19"]["evidence"] + ["E21"]))
write("gap-ledger.json", ledger)

packets = []


def packet(pid, owner, location, purpose, grain, coverage, eligibility, gaps, evid, version=None, hashes=None, times=None, observed=NOW):
    return {"id": pid, "owner": owner, "canonical_location": location, "purpose_arm": purpose, "unit_grain": grain, "scope_coverage": coverage, "eligibility": eligibility, "gap_ids": gaps, "evidence": evid, "observed_at": observed, "schema_adapter_code_version_input_output_manifest_hash_commit": version, "exact_input_output_manifest_sha": hashes, "time_fields": times or {}, "unknown_reason": "Uninspected fields remain unknown; Git HEAD and mtime are not artifact identity/public availability"}


for n, item in enumerate(post["inventory"], 1):
    path = item["canonical_path"]
    absolute = path if Path(path).is_absolute() or path.startswith("C:") else post["canonical_root"].rstrip("/\\") + "/" + path
    if "native-v7" in path:
        gaps = ["DD17", "DD18"]
    elif "publication" in path:
        gaps = ["DD03", "DD08"]
    elif "sessions" in path or "calendar" in path:
        gaps = ["DD01", "DD09", "DD21"]
    elif "decisions" in path:
        gaps = ["DD01", "DD04", "DD05", "DD10"]
    elif "stock_bars" in path:
        gaps = ["DD04", "DD05", "DD07", "DD21"]
    elif "diagnostic" in path:
        gaps = ["DD05", "DD11"]
    elif "configs/" in path or "configs\\" in path:
        gaps = ["DD08", "DD09", "DD21"]
    elif "wording_results" in path:
        gaps = ["DD08"]
    else:
        gaps = ["DD02", "DD03", "DD08", "DD21"]
    packets.append(packet(f"post-{n:02d}", item["owner"], absolute, item["purpose_arm"], item["unit_grain"], item["scope_eligibility"], "Inspected static/diagnostic/runtime scope only; no trading grant", gaps, ["E14"], item["schema_code_version"], item["input_output_manifest_hash_commit"], item.get("time_fields"), item["observed_at"]))
for idx, key in [(0, "current_v2"), (1, "historical_v2"), (2, "historical_v3")]:
    f = industry["files"][idx]
    packets.append(packet("industry-" + key, "Industry", f["path"], "publication candidate", industry["clocks"]["grain"], industry["clocks"][key], "Assumed proxy only;0observed public/ready; source schema name qualified does not change evidence", ["DD03", "DD12"], ["E15"], {"schema": industry["clocks"]["schema"], "policy": industry["clocks"]["policy"], "code_sha": industry["clocks"]["historical_v3"].get("code_sha256") if key == "historical_v3" else None, "mutable_artifact_commit": None}, {"sha256": f["sha256"], "hash_evidence": f["hash_evidence"]}, {"reviewed_at": industry["clocks"][key]["reviewed_at"], "earliest_public": None, "historical_receipt": None}))
packets.append(packet("industry-market", "Industry", industry["files"][7]["path"], "wording equity candidate; derivatives later", "input configuration/producer summary describing vendor minute and definition rows;remote raw bytes uninspected", industry["market"], "producer scope only; outcomes unread/consumer_accepted=false", ["DD04", "DD06", "DD07", "DD16", "DD21"], ["E15"], {"schema": industry["market"]["schema"], "qualification_schema": industry["market"]["qualification_schema"], "location_kind": "configuration summary,not raw quote bytes", "raw_remote_byte_bindings_inspected": False}, {"raw_config_file_sha256": industry["files"][7]["sha256"], "normalized_config_sha256": industry["market"]["normalized_config_sha256"], "different_hash_domains": True}, industry["timestamps"]))
packets.append(packet("industry-quality-mask", "Industry", industry["files"][6]["path"], "equity holding quality", "excluded dates and decision/holding intersections", industry["exclusions"], "implemented; actual wording cohort mask not accepted", ["DD07"], ["E15"], {"adapter": industry["exclusions"]["adapter"]}, {"frozen_selection_sha256": industry["files"][6]["sha256"], "quality_rule_sha256": industry["exclusions"]["quality_rule_sha256"]}))
packets.append(packet("financial-native", "Benchmark", financial["definition_path"], "P1 financial next", financial["grain"], financial["counts"], "inactive optional proposal; public/trading clocks unqualified", ["DD02", "DD13", "DD17"], ["E16"], {"producer": "V7", "auditor": "V8", "source": financial["source_id"], "schema": financial["definition_schema"], "producer_commit": financial["producer_commit"], "unit": financial["unit"], "definitions": financial["definitions"]}, {"definition_pin": financial["definition_sha_pin"], "rehashed": False}, financial["time_limits"]))
packets.append(packet("financial-calendar-scaffold", "Benchmark/Post", calendar["input_files"][0]["path"], "P1 financial diagnostic", "issuer weekday/decision", {"rows": 2092, "dates": 523, "four_issuer_sets_equal": True, "session_count": 502, "extra_closure_dates": calendar["financial_dates_absent_calendar"], "missing_session_dates": []}, "diagnostic_no_outcome,not executable session join", ["DD01"], ["E16", "E17"], {"calendar_use": calendar["calendar_use"]}, {"fresh_sha256": calendar["input_files"][0]["sha256"], "bytes": calendar["input_files"][0]["bytes"]}, {"decision_clock": calendar["financial_decision_clock"], "min_date": "2024-01-01", "max_date": "2025-12-31"}, calendar["observed_at_utc"]))
packets.append(packet("macro-cache", "Benchmark", financial["v8"]["path"], "P1 macro", "series period/current cached response", financial["v8"]["macro"], "0historical vintage qualified; missing official values null", ["DD14"], ["E16"], {"auditor": "V8"}, {"raw_sha_pin": financial["v8"]["macro"]["raw_sha_pin"], "definition_sha_pin": financial["v8"]["macro"]["definition_sha_pin"], "rehashed": False}, {"retrieved_at": financial["v8"]["macro"]["retrieved_at"], "processed_at": financial["v8"]["macro"]["processed_at"], "historical_first_release_revision": None}))
packets.append(packet("native-remote-archive", "Benchmark/Post", financial["archive"]["remote"], "P2 archive", "delivery archive vs local metadata", financial["archive"], "retained delivery pin; live archive bytes not reverified,not field/economic grant", ["DD18"], ["E16"], {"producer": "V7"}, {"sha_pin": financial["archive"]["sha_pin"], "bytes_pin": financial["archive"]["bytes_pin"], "rehashed": False}))
for key, filename, gaps in [("sharpe-inference-design", "2026-10-04-sharpe-confidence-and-monte-carlo.md", ["DD10", "DD11"]), ("gpu-plan", "2026-10-04-inference-training.md", ["DD11"])]:
    f = next(f for f in root_receipt["files"] if Path(f["path"]).name == filename)
    packets.append(packet(key, "Sharpe / GPU owner", f["path"], "inference plan;GPU optional CPU-first", "registered method/plan", "method inspected;no accepted account input or new runtime", "plan only; no empirical performance/speedup", gaps, ["E13"], {"artifact_commit": None}, {"fresh_sha256": f["sha256"], "bytes": f["bytes"]}, {"mtime_utc": f["mtime_utc"], "mtime_is_publication": False}, f["observed_at"]))
packets.append(packet("lattice-diagnostic", "Lattice", (ROOT / "artifacts/lattice-strategies/reports-v1/input_audit.json").as_posix(), "P1 numerical diagnostic context", "adjusted-close targets and own hedge horizons", lattice or "owner report,exact metadata receipt pending", "not accepted wording comparator or account performance", ["DD05", "DD11"], ["E18"] if lattice else ["E01"], {"versions": "preservedv1 diagnostic;v2DEVELOPMENT continuation", "remote_input_rehashed": False}))
if first_arm_refresh:
    packets.append(packet("new-first-arm-owner-inputs", "Benchmark/Industry/Post", (BASE / "receipts/first-arm-owner-refresh.json").as_posix(), "minimal2024wording equity input refresh", "source/event aggregation and input qualification status", first_arm_refresh, "Read exact receipt flags; producer completion does not establish canonical Post economic acceptance", ["DD02", "DD03", "DD04", "DD08", "DD09", "DD21"], ["E19"], {"canonical_policy": "wording_equity_pilot-v2", "separate_prior_packet": True}))
for item in packets:
    item["historically_observed_location"] = item["canonical_location"]
    item["live_location_status"] = "Observed path at receipt cutoff only; current existence/restore binding not inferred. See DD22 for consumed inputs."
    item["economic_consumer_current_binding_accepted"] = False
    if item["canonical_location"].replace("\\", "/").startswith(ROOT.as_posix()) and any(x in item["canonical_location"].replace("\\", "/") for x in ["/data/", "/artifacts/", "/cache/"]):
        item["storage_migration_scope"] = "Root cache path may have moved; no silent alias. Separate observed hash from current input binding."
        item["gap_ids"] = list(dict.fromkeys(item["gap_ids"] + ["DD22"]))

time_fields = read("availability-date-matrix.json")["time_fields"]
for field in time_fields:
    field["status"] = "scoped actual values and unknowns listed by packet; not global time equivalence"
    field["observed_at"] = NOW
    if field["field"] == "provider_receive":
        field.update(meaning="actual provider receipt timestamp distinct from vendor interval endpoint", timezone=None, min=None, max=None, coverage=None, precision_sentinel_null_evidence="Actual receipt unknown; ts_recv is a minute interval endpoint and supplies no receipt proof")
    elif field["field"] in ["quote_update_interval_endpoint", "quote_update"]:
        field.update(field="quote_update", meaning="actual quote update timestamp", timezone=None, min=None, max=None, coverage=None, precision_sentinel_null_evidence="Quote update/freshness unknown; ts_event is last trade and ts_recv is interval endpoint")
    elif field["field"] == "our_retrieval":
        field.update(min=financial["v8"]["macro"]["retrieved_at"], max=financial["v8"]["macro"]["retrieved_at"], timezone="UTC", coverage="one inspected macro retrieval batch only; not all sources or historical receipt", precision_sentinel_null_evidence="fractional seconds; current2026retrieval not historical publication/vintage")
    elif field["field"] == "our_processing":
        field.update(min="2026-10-04T02:22:47.209449Z", max="2026-10-04T02:22:47.209449Z", timezone="UTC", coverage="one FinBERT run completion only", precision_sentinel_null_evidence="fractional seconds,currentteachercompletion; historicalready unknown")
    elif field["field"] == "decision":
        field.update(coverage={"legacy_document_decisions": 2008, "legacy_sessions": 502, "pilot_v2_sessions": 252}, precision_sentinel_null_evidence="legacy13:00earlyclose=>12:30decision; actualUTC/DST values inPostreceipt. V2decision/entry=open+60s andexit=close-60s are static policy,not actualfills. Financial21:00Zdiagnostic clock separate")
    elif field["field"] == "fiscal_period_instant":
        field.update(coverage="AATcurrentMarch31operand andJune30native period inspected; not a complete fiscal range", precision_sentinel_null_evidence="date/instant has no timezone; source accession/unit/definition distinct; not publication")
time_fields.append({"field": "sec_acceptance", "meaning": "administrative filing acceptance,not first public or exactversion public-by", "packet_scope": "pinned8primary wording filings;7exhibits null", "timezone": "UTC", "min": "2023-01-05T21:40:33Z", "max": "2023-03-01T11:38:13Z", "coverage": 8, "precision_sentinel_null_evidence": "seconds; exhibitacceptance null,never imputed", "gap_id": "DD03", "status": "inspected primary chronology", "observed_at": post["observed_at_utc"]})
time_fields.append({"field": "vendor_interval_endpoint", "meaning": "EQUS ts_recv vendor minute interval endpoint,not provider or our receipt", "packet_scope": "inspected structural EQUS metadata", "timezone": "UTC", "min": None, "max": None, "coverage": 1028190, "precision_sentinel_null_evidence": "ns representation; exactaggregate range not recomputed", "gap_id": "DD06", "status": "known structural semantics;execution unqualified", "observed_at": NOW})
time_fields.append({"field": "last_trade_event", "meaning": "EQUS optional ts_event last trade,not quote update or quote age", "packet_scope": "inspected structural EQUS metadata", "timezone": "UTC", "min": None, "max": None, "coverage": {"parsed": 1013110, "missing": 15080}, "precision_sentinel_null_evidence": "ns; missing remains null; no inference of quote freshness", "gap_id": "DD06", "status": "known structural semantics;execution unqualified", "observed_at": NOW})
# One row per semantic category on repeated refreshes.
time_fields = list({f["field"]: f for f in time_fields}.values())
write("availability-date-matrix.json", {"schema_version": "data-date-audit-availability-time-v2", "persistence": "integrated bounded actual receipts; unknowns and evidence domains retained", "observed_at": NOW, "coverage_boundary": ledger["coverage_boundary"], "packets": packets, "time_fields": time_fields})

metrics = ["period", "coverage", "initial_observed_usd", "terminal_usd", "gross_pnl_usd", "gross_return_pct", "net_pnl_usd", "net_return_pct", "annualized_net_return", "maximum_drawdown_pct", "gross_exposure", "net_exposure", "turnover", "total_cost_usd", "net_closed_episode_win_rate", "closed_episode_count", "sharpe", "sharpe_95_ci", "incremental_net_pnl_usd", "incremental_sharpe", "incremental_sharpe_95_ci"]
paths = []
for name in ["wording_challenger", "matched_always_long", "zero_yield_cash", "challenger_minus_matched_long"]:
    reasons = {m: "No accepted regularly marked costed net account/cohort; unmeasured" for m in metrics}
    if name == "zero_yield_cash":
        for m in ["sharpe", "sharpe_95_ci", "incremental_sharpe", "incremental_sharpe_95_ci"]:
            reasons[m] = "Undefined for zero-variance cash; no delta-Sharpe versus cash"
    paths.append({"path": name, "planned_initial_capital_usd": 1000000 if name != "challenger_minus_matched_long" else None, "measured": False, "values": dict.fromkeys(metrics), "null_reasons": reasons})
write("performance-availability.json", {"schema_version": "data-date-performance-availability-v1", "observed_at": NOW, "paths": paths, "return_unit": "regularly marked account daily net returns including flat/no-fill sessions", "cash_convention": "zero passive cash yield; balances and restricted short collateral retained; actual dividends/actions/borrow/costs attributed", "excess_sharpe": "only separately declared matched risk-free reference subtraction; do not fabricate account income", "win_rate_denominator": "net closed episodes; freeze tie/zero-return/censored/no-fill treatment before measured report", "inference": "registered joint dependence-aware95%method follows accepted paths; no arbitrary success or sample cutoff; no final-test reopening", "pending_question": ledger["decision_frontier"]["pending_existing_elsewhere"]})

regular_url = calendar["calendar_sources"]["regular"]
exception_url = calendar["calendar_sources"]["exceptions"][0]["url"]
status_counts = dict(collections.Counter(g["status"] for g in ledger["gaps"]))
findings = f"""# Bounded data and date audit

The existing pinned wording packet cannot supply a 2024 accession/filing event under the current frozen 2024 pilot rule. Its eight primary filings have 2023 SEC acceptance times. New Benchmark aggregation may replace that packet; this finding does not establish global absence of text, quotes or trading opportunities. Exact event-date meaning, text/version public-by evidence, model vintage and executable holding-window coverage still need Post's consumer acceptance.

Audit recorded at {NOW}; individual receipt observation times differ. This register traces {len(ledger['gaps'])} known gaps and 30 requirements through named small metadata artifacts. The original seed, snapshot and handoff remain preserved. It does not claim an exhaustive raw corpus scan or economic readiness.

| Evidence | Bounded finding | What it permits |
|---|---|---|
| Calendar | 523 financial weekdays versus 502 equity sessions; 21 closures x 4 = 84 rows; no missing equity session | Classifies dates; executable timestamps and known-at-decision schedule remain separate |
| Wording | 15 documents = 8 primary + 7 exhibits; 8 accessions, 4 CIKs, 2,391 fragments. Conditional: 13 documents, 7 accessions, 2,248 fragments | Describes the pinned cohort; fragments are not independent events |
| Dates | Primary acceptance: 2023-01-05 to 2023-03-01; v2 pilot: 2024 only | No 2024 filing/accession event in this packet under that window; an alternative event date needs row evidence |
| Recipe | Exact v2 file and 252-session 2024 calendar file/row hashes match; v1 retained | Static contract; quote, fill and account acceptance pending |
| Publication | Post: 20 conditional, 2 quarantined. Industry current v2: 13 proxy candidates; history v3: 37 | Assumed dissemination/SEC + 24h is not evidenced exact-version public-by; 0 observed ready |
| Market | 3,008 Post daily bars, 2023-25. Industry: 128 AMT candidates on 2024-01-02, outcomes unread | Daily marks and one-day producer diagnostics do not establish execution or broad coverage |
| Native delivery | Eight runtime receipt hashes freshly match; retained 690 tests/196 source matches | Descriptive verification: 3 groups, 0 canonical, 0 human gold. No suite or source sweep rerun |
| Financial next | 45 originals, 37 requests, 36 historical accessions, 8,384 cells, 424 groups, 500 XML nodes, 844 states | Distinct denominators; financial fields inactive until separately qualified |
| Performance | Accepted regularly marked costed account input unavailable | PnL, Sharpe 95% CI, drawdown and win rate remain null with reasons |

The 21 extra financial dates match scheduled NYSE holidays and the 2025-01-09 mourning closure. [NYSE's 2022 calendar announcement]({regular_url}) supports the regular dates and early closes; [NYSE's 2025-01-02 memo]({exception_url}) supports the exceptional closure. The memo cannot be treated as knowledge at an earlier decision. Six legacy early-close decisions occur at 12:30 local before the 13:00 close, with next-session endpoints skipping closures. The 21 Industry degraded-market dates are a separate set; do not conflate the equal counts.

The immediate P0 chain is DD21 compatible dated events, DD03 exact-version publication bound and latency, DD08 existing model/text aggregation, DD06-07 identity/quotes/actions/quality, DD09 costs/borrow/collateral/gross enforcement, then DD10 regular net account and DD11 dependence-aware inference. Post, Benchmark and Industry retain their producer and consumer responsibilities. Existing 2023 daily bars overlap the old text year but do not establish the pilot's open + 60s / close - 60s executable quotes. Owners must publish an admissible existing intersection or an explicit versioned study-window revision within delegated scope; otherwise report unavailable. The audit launched no acquisition, model change or protected-test access.

The human's hypothetical USD1m policy permits long and short equally sized eligible positions, at most 100% gross exposure, no leverage and zero passive cash yield. Uninvested balances and no-signal/no-fill sessions remain in NAV; there is no forced investment. Short proceeds remain restricted. Actual dividends, actions, fees and borrow costs require explicit attribution and acceptance; unknown costs are not zero. No success, drawdown or promotion threshold is invented.

| Planned path | Initial scenario | Terminal/netPnL/drawdown/win rate | Sharpe/95%CI |
|---|---:|---|---|
| Wording challenger | USD1m | Unmeasured | Unavailable: accepted regular net returns absent |
| Matched always-long | USD1m | Unmeasured | Unavailable: same input gate |
| Zero-yield cash | USD1m | No measured replay | Undefined for zero variance |
| Challenger minus matched-long | Matched comparison | Unmeasured | Unavailable: paired accepted paths absent |

Use account daily net returns for inference, preserving flat days and temporal, event and cross-asset dependence. Fragment/event counts are not independent samples. A conventional excess Sharpe needs a separately declared matched risk-free subtraction; it does not add hypothetical account income. Win rate needs net closed episodes and a frozen tie, zero-return, censor and no-fill denominator. Previously inspected 2024/25 remains DEVELOPMENT even where a new recipe excludes 2025; it cannot regain untouched status retrospectively. GPU or Monte Carlo speed and diagnostic forecast errors do not substitute for this account gate.

The existing DataPush Q4 asks whether to qualify before economic headlines or allow a labelled provisional scenario. It remains pending in that chat; no recommendation or elapsed time is treated as an answer. Settled policy choices are retained, and no duplicate question is opened here. File and owner facts are resolved by evidence work first.

Status counts: {json.dumps(status_counts, sort_keys=True)}. DD17 closes only bounded descriptive receipt verification; pending and deferred rows retain owner, dependency, next action and acceptance condition. Disk-full OS112 failures remain in history; small metadata I/O recovered, broad capacity is unverified. This audit did not delete others' files or launch heavy work.

{link('gap-ledger.json','Gap register and requirement trace')} | {link('availability-date-matrix.json','Packet and clock inventory')} | {link('performance-availability.json','Full metric availability and null reasons')} | {link('receipts/calendar-reconciliation.json','Actual date comparison')} | {link('receipts/post-evidence.md','Post evidence')} | {link('receipts/industry-evidence.json','Industry evidence')} | {link('receipts/financial-evidence.json','Financial evidence')}
"""
(BASE / "FINDINGS.md").write_text(findings, encoding="utf-8")
if first_arm_refresh:
    with (BASE / "FINDINGS.md").open("a", encoding="utf-8") as handle:
        handle.write("\nA later bounded owner refresh adds the newly published 2024 candidates and Benchmark aggregate diagnostics. Read their exact version and acceptance flags in " + link("receipts/first-arm-owner-refresh.json", "the first-arm refresh") + ". They supersede neither the old packet's provenance nor Post's required consumer acceptance. The minimal owner/blocker map is " + link("first-arm-blocker-map.json", "recorded separately") + ".\n")
    text = (BASE / "FINDINGS.md").read_text(encoding="utf-8")
    text = text.replace("The existing pinned wording packet cannot supply a 2024 accession/filing event under the current frozen 2024 pilot rule.", "Two AMT 2024 release candidates have now been identified, but neither has an accepted exact-text public bound or complete accepted scored event. Benchmark's completed handoff contains four selected 2023 accessions, three diagnostic scores and zero qualified events. Its separate 2024 input check remains owner work at the receipt cutoff. The existing pinned wording packet cannot supply a 2024 accession/filing event under the frozen 2024 rule.")
    (BASE / "FINDINGS.md").write_text(text, encoding="utf-8")
with (BASE / "FINDINGS.md").open("a", encoding="utf-8") as handle:
    handle.write("\nDD22 records the storage migration boundary: historically observed local paths are not a current live input binding. Consumed inputs must resolve to the original bytes through an explicit local or remote path, SHA256, role and accepted Post manifest. Retained historical test and acceptance receipts remain past facts. Bulk stays remote; this audit performed no cleanup or backup.\n")
if reporting_decision:
    text = (BASE / "FINDINGS.md").read_text(encoding="utf-8")
    text = text.replace("The existing DataPush Q4 asks whether to qualify before economic headlines or allow a labelled provisional scenario. It remains pending in that chat; no recommendation or elapsed time is treated as an answer. Settled policy choices are retained, and no duplicate question is opened here. File and owner facts are resolved by evidence work first.", "The human explicitly answered: **Wait for qualified inputs before reporting performance**. This resolves DataPush Q4 and the subsequent ambiguous wording; the exact human message is recorded in " + link("receipts/reporting-decision.json", "the decision receipt") + ". Continue alignment repairs and input/exclusion diagnostics; hold empirical strategy performance until the qualified inputs and regular net account are accepted. No duplicate interview, provisional result, final-test or live-capital permission is inferred.")
    (BASE / "FINDINGS.md").write_text(text, encoding="utf-8")
minimal_gaps = ["DD21", "DD22", "DD03", "DD08", "DD01", "DD06", "DD07", "DD09", "DD10", "DD11"]
write("first-arm-blocker-map.json", {"schema_version": "minimal-wording-equity-blocker-map-v1", "recorded_at": NOW, "canonical_consumer": {"thread": "01a1029b-f907-7bc1-9127-bf22a03633cd", "protocol": "wording_equity_pilot-v2", "sha256": "e7197cea447fe9e413fe659b4ab2bdd41468e6cdb4933d7f82fb4560bab78acb", "economic_acceptance": False}, "producer_refresh": first_arm_refresh, "storage_binding_refresh": storage_binding, "ordered_dependencies": [byid[g] for g in minimal_gaps], "outside_first_arm": ["financial-only native counts/calendar/vintages unless consumed", "derivatives/universe expansions", "GPU acceleration/full MonteCarlo path work"], "historical_Lattice_owner_scope": "separate full approved work continues under its own human override; this audit launches no job", "pending_human_question": ledger["decision_frontier"]["pending_existing_elsewhere"], "action_boundary": "one canonical Post replay; no second strategy implementation,acquisition,cleanup,merge,live capital or protected-test access by audit"})
print(json.dumps({"recorded_at": NOW, "gaps": len(ledger["gaps"]), "requirements": len(ledger["requirements"]), "packets": len(packets), "time_fields": len(time_fields), "status_counts": status_counts, "lattice_receipt_integrated": bool(lattice)}))
