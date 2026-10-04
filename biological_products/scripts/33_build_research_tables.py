"""Build trial, product, program, phase, and delay research tables.

This is a retrospective research dataset. Current registry records and labels
cannot be used as if they were available on earlier trading dates.
"""

import argparse
import json
import math
import re
import unicodedata
import zipfile
from collections import Counter, defaultdict
from datetime import date
from difflib import SequenceMatcher
from pathlib import Path

import numpy as np
import pandas as pd


TODAY = pd.Timestamp("2026-10-04")
NCT_RE = re.compile(r"NCT\d{8}", re.I)
CODE_RE = re.compile(r"[A-Z]{2,5}[- ]?\d{2,6}[A-Z0-9-]*", re.I)
NAMED_SUFFIX = ("mab", "nib", "vir", "ase", "ciclib", "tide", "cel", "parin")


def clean(value):
    value = unicodedata.normalize("NFKD", str(value or ""))
    value = "".join(c for c in value if not unicodedata.combining(c))
    return re.sub(r"[^a-z0-9]+", " ", value.lower()).strip()


def clinical_date(value):
    if not value:
        return ""
    if len(value) == 7:
        return value + "-01"
    return value


def date_struct(obj):
    obj = obj or {}
    return clinical_date(obj.get("date", "")), obj.get("type", ""), "month" if len(obj.get("date", "")) == 7 else "day"


def phase_name(phases):
    phases = set(phases or [])
    if "PHASE2" in phases and "PHASE3" in phases:
        return "Phase 2/3"
    if "PHASE1" in phases and "PHASE2" in phases:
        return "Phase 1/2"
    for key, value in (("EARLY_PHASE1", "Early Phase 1"), ("PHASE1", "Phase 1"),
                       ("PHASE2", "Phase 2"), ("PHASE3", "Phase 3"), ("PHASE4", "Phase 4")):
        if key in phases:
            return value
    return "Not reported"


def phase_level(value):
    return {"Early Phase 1": 1, "Phase 1": 1, "Phase 1/2": 2, "Phase 2": 2,
            "Phase 2/3": 3, "Phase 3": 3, "Phase 4": 4}.get(value, 0)


def family_match(name, aliases):
    value = clean(name)
    if not value:
        return "", ""
    for alias in aliases:
        alias_value = clean(alias)
        if len(alias_value) >= 4 and value == alias_value:
            return alias, "high"
    for alias in aliases:
        alias_value = clean(alias)
        if len(alias_value) >= 6 and (value.startswith(alias_value + " ") or
                                     (" " + alias_value + " ") in (" " + value + " ")):
            return alias, "medium"
    return "", ""


def parse_trial(record, group, ticker, cik, company, match_type, match_confidence, history_count):
    p = record.get("protocolSection", {})
    ident, status = p.get("identificationModule", {}), p.get("statusModule", {})
    design = p.get("designModule", {})
    sponsor = p.get("sponsorCollaboratorsModule", {})
    arms = p.get("armsInterventionsModule", {})
    locations = p.get("contactsLocationsModule", {})
    start, start_type, start_precision = date_struct(status.get("startDateStruct"))
    pc, pc_type, pc_precision = date_struct(status.get("primaryCompletionDateStruct"))
    completion, completion_type, completion_precision = date_struct(status.get("completionDateStruct"))
    first, _, _ = date_struct(status.get("studyFirstPostDateStruct"))
    last, _, _ = date_struct(status.get("lastUpdatePostDateStruct"))
    results, _, _ = date_struct(status.get("resultsFirstPostDateStruct"))
    enrollment = design.get("enrollmentInfo") or {}
    lead = (sponsor.get("leadSponsor") or {}).get("name", "")
    return dict(nct_id=ident.get("nctId", ""), sponsor=lead, sponsor_group=group,
                matched_company=company, sponsor_match_type=match_type,
                match_confidence=match_confidence, ticker=ticker, cik=cik,
                phase=phase_name(design.get("phases")), overall_status=status.get("overallStatus", ""),
                start_date=start, start_date_type=start_type, start_date_precision=start_precision,
                primary_completion_date=pc, primary_completion_type=pc_type,
                primary_completion_precision=pc_precision,
                completion_date=completion, completion_type=completion_type,
                completion_precision=completion_precision,
                enrollment=enrollment.get("count"), enrollment_type=enrollment.get("type", ""),
                n_arms=len(arms.get("armGroups") or []), n_sites=len(locations.get("locations") or []),
                study_type=design.get("studyType", ""),
                condition=";".join(p.get("conditionsModule", {}).get("conditions") or []),
                results_posted=int(bool(record.get("hasResults") or results)), results_posted_date=results,
                why_stopped=status.get("whyStopped", ""), first_posted_date=first,
                last_update_date=last, n_record_versions=history_count,
                history_available=int(history_count > 0),
                status_known_date=last, record_observed_date=str(TODAY.date()))


def source_trials(data, ranking):
    raw = data / "raw"
    group_a = pd.read_csv(raw / "trials.csv", usecols=["ticker", "nct_id"])
    lookup = pd.read_csv(data / "fds" / "fds_lookup_cik_ticker.csv")
    t2c = dict(zip(lookup.ticker.astype(str), lookup.cik.astype(int)))
    a_ticker = dict(zip(group_a.nct_id, group_a.ticker))
    histories = raw / "ct_history"
    def history_count(nct):
        path = histories / f"{nct}.json"
        if not path.exists():
            return 0
        payload = json.loads(path.read_text(encoding="utf-8"))
        return len(payload.get("versions", {})) if payload.get("completed_utc") else 0
    selected = {}
    records = {}
    for path in sorted((raw / "research_cache" / "ct_v2_group_a").glob("batch_*.json")):
        payload = json.loads(path.read_text(encoding="utf-8"))
        for study in payload.get("studies", []):
            record = study.get("protocolSection", {}).get("identificationModule", {}).get("nctId")
            if record not in a_ticker:
                continue
            ticker = a_ticker[record]
            selected[record] = parse_trial(study, "A", ticker, t2c.get(ticker), ticker,
                                           "existing_ticker_map", "high", history_count(record))
            records[record] = study
    print(f"Group A current v2 records found: {len(selected)}")
    b_by_rank = {int(row["rank"]): row for row in ranking.to_dict("records")}
    candidates = {}
    for path in sorted((raw / "research_cache" / "ct_v2_group_b").rglob("page_*.json")):
        try:
            rank = int(path.parent.parent.name)
        except ValueError:
            continue
        company = b_by_rank.get(rank)
        if company is None:
            continue
        aliases = str(company["aliases"]).split(";")
        payload = json.loads(path.read_text(encoding="utf-8"))
        for study in payload.get("studies", []):
            p = study.get("protocolSection", {})
            nct = p.get("identificationModule", {}).get("nctId", "")
            if not nct or nct in selected:
                continue
            sponsor = p.get("sponsorCollaboratorsModule", {})
            lead = (sponsor.get("leadSponsor") or {}).get("name", "")
            _, confidence = family_match(lead, aliases)
            match_type = "lead_sponsor" if confidence else ""
            if not confidence:
                for collaborator in sponsor.get("collaborators") or []:
                    _, found = family_match(collaborator.get("name", ""), aliases)
                    if found:
                        confidence = "low"
                        match_type = "collaborator"
                        break
            if not confidence:
                continue
            start = clinical_date((p.get("statusModule", {}).get("startDateStruct") or {}).get("date", ""))
            if p.get("designModule", {}).get("studyType") != "INTERVENTIONAL" or (start and start < "2018-01-01"):
                continue
            row = parse_trial(study, "B", company["ticker"] if pd.notna(company["ticker"]) else "",
                              None, company["company"], match_type, confidence, history_count(nct))
            old = candidates.get(nct)
            score = {"high": 3, "medium": 2, "low": 1}
            if old is None or score[confidence] > score[old[0]["match_confidence"]]:
                candidates[nct] = (row, study)
    for nct, (row, study) in candidates.items():
        selected[nct] = row
        records[nct] = study
    print(f"Group B matched interventional records found: {len(candidates)}")
    return selected, records


def approved_products(data, ranking, group_a_rows):
    path = data / "raw" / "research_cache" / "drug-drugsfda-0001-of-0001.json.zip"
    with zipfile.ZipFile(path) as archive:
        fda = json.loads(archive.read(archive.namelist()[0]))["results"]
    a_sponsors = defaultdict(set)
    for row in group_a_rows.values():
        if row["sponsor_group"] == "A" and row["sponsor"]:
            a_sponsors[row["ticker"]].add(row["sponsor"])
    products = []
    for item in fda:
        app = item.get("application_number", "")
        if not app.startswith(("NDA", "BLA")):
            continue
        originals = [x for x in item.get("submissions", []) if x.get("submission_type") == "ORIG" and
                     x.get("submission_status") == "AP" and "20180101" <= x.get("submission_status_date", "") <= "20261004"]
        if not originals:
            continue
        first = sorted(originals, key=lambda x: x["submission_status_date"])[0]
        date_string = pd.to_datetime(first["submission_status_date"], format="%Y%m%d").strftime("%Y-%m-%d")
        sponsor = item.get("sponsor_name", "")
        family = ""
        for row in ranking.itertuples(index=False):
            if family_match(sponsor, str(row.aliases).split(";"))[1]:
                family = row.company
                break
        if not family:
            for ticker, names in a_sponsors.items():
                if family_match(sponsor, names)[1]:
                    family = ticker
                    break
        label_path = data / "raw" / "research_cache" / "fda_labels" / f"{app}.json"
        cited = set()
        label_effective = ""
        if label_path.exists():
            label = json.loads(label_path.read_text(encoding="utf-8"))
            if label.get("results"):
                result = label["results"][0]
                label_effective = result.get("effective_time", "")
                text = " ".join(str(x) for field in ("clinical_studies", "clinical_studies_table", "indications_and_usage")
                                for x in result.get(field, []))
                cited = {x.upper() for x in NCT_RE.findall(text)}
        names = set()
        for product in item.get("products", []):
            brand = product.get("brand_name", "").strip()
            generic = ";".join(x.get("name", "").strip() for x in product.get("active_ingredients", []))
            if brand or generic:
                names.add((brand, generic))
        if not names:
            names.add(("", ""))
        for brand, generic in sorted(names):
            products.append(dict(application_number=app, brand_name=brand, generic_name=generic,
                                 sponsor=sponsor, sponsor_family=family, approval_date=date_string,
                                 application_type=app[:3], review_type=first.get("review_priority", ""),
                                 orphan_flag="", breakthrough_flag="", accelerated_flag="",
                                 approval_pathway="not reported by bulk source",
                                 nct_ids_cited=";".join(sorted(cited)), label_effective_date=label_effective,
                                 link_observed_date=str(TODAY.date()), outcome_known_date=date_string,
                                 current_product_list_flag=1))
    frame = pd.DataFrame(products).drop_duplicates(["application_number", "brand_name", "generic_name"])
    print(f"FDA original NDA/BLA applications since 2018: {len(set(frame.application_number))}; current product rows: {len(frame)}")
    return frame


def interventions_table(records, product_names):
    names = {clean(x) for x in product_names if clean(x)}
    rows = []
    for nct, study in records.items():
        for item in study.get("protocolSection", {}).get("armsInterventionsModule", {}).get("interventions") or []:
            name = item.get("name", "").strip()
            if not name:
                continue
            key = clean(name)
            # A code name is a 2 to 5 letter prefix followed by digits, with
            # optional separators and suffixes. A named flag needs an FDA name
            # match or a likely INN suffix; otherwise the name is uncertain.
            is_code = int(bool(CODE_RE.fullmatch(name.replace(" ", ""))))
            is_named = int(not is_code and (key in names or any(key.endswith(s) for s in NAMED_SUFFIX)))
            rows.append(dict(nct_id=nct, intervention_name=name,
                             intervention_type=item.get("type", ""), intervention_key=key,
                             is_code_name=is_code, is_named=is_named,
                             naming_rule="FDA name or INN suffix" if is_named else "code pattern" if is_code else "uncertain"))
    return pd.DataFrame(rows).drop_duplicates(["nct_id", "intervention_key", "intervention_type"])


def links_table(trials, interventions, products):
    trial_by_nct = {r["nct_id"]: r for r in trials.values()}
    by_key = defaultdict(set)
    for row in interventions.itertuples(index=False):
        if row.intervention_key and row.intervention_key not in ("placebo", "standard of care"):
            by_key[row.intervention_key].add(row.nct_id)
    product_rows = products.to_dict("records")
    links = {}
    def add(nct, product, confidence, rule):
        trial = trial_by_nct.get(nct)
        if not trial:
            return
        trial_pc = trial.get("primary_completion_date", "")
        preapproval = int(bool(trial_pc) and trial_pc <= product["approval_date"] and
                          (not trial.get("start_date") or trial["start_date"] <= product["approval_date"]))
        key = (nct, product["application_number"], product["brand_name"], product["generic_name"])
        if key in links and {"high": 3, "medium": 2, "low": 1}[links[key]["link_confidence"]] >= {"high": 3, "medium": 2, "low": 1}[confidence]:
            return
        pivotal = int(preapproval and confidence in ("high", "medium") and
                      (trial["phase"] in ("Phase 2/3", "Phase 3") or
                       trial["phase"] == "Phase 2" and product["accelerated_flag"] == "1"))
        links[key] = dict(nct_id=nct, application_number=product["application_number"],
                          product_brand=product["brand_name"], product_generic=product["generic_name"],
                          trial_sponsor=trial["sponsor"], product_sponsor=product["sponsor"],
                          trial_phase=trial["phase"], link_confidence=confidence, link_rule=rule,
                          preapproval_trial=preapproval, pivotal_success=pivotal,
                          approval_date=product["approval_date"], outcome_known_date=product["approval_date"],
                          link_observed_date=product["link_observed_date"])
    for product in product_rows:
        for nct in filter(None, product["nct_ids_cited"].split(";")):
            add(nct, product, "high", "NCT cited in current FDA label")
        family = product["sponsor_family"]
        if not family:
            continue
        name_keys = {clean(product["brand_name"])}
        name_keys.update(clean(x) for x in product["generic_name"].split(";"))
        for name_key in filter(None, name_keys):
            for nct in by_key.get(name_key, set()):
                trial = trial_by_nct[nct]
                if trial["matched_company"] == family and trial.get("primary_completion_date", "") and trial["primary_completion_date"] <= product["approval_date"]:
                    add(nct, product, "medium", "same intervention and sponsor family before approval")
    # Fuzzy links are restricted to an already matched sponsor family.
    programs_by_family = defaultdict(list)
    for row in interventions.itertuples(index=False):
        trial = trial_by_nct.get(row.nct_id)
        if trial and trial["matched_company"]:
            programs_by_family[trial["matched_company"]].append((row.nct_id, row.intervention_key))
    for product in product_rows:
        family = product["sponsor_family"]
        if not family:
            continue
        targets = [clean(product["brand_name"])] + [clean(x) for x in product["generic_name"].split(";")]
        for nct, key in programs_by_family.get(family, []):
            if len(key) < 6 or key in ("placebo", "standard of care"):
                continue
            trial = trial_by_nct[nct]
            if not trial.get("primary_completion_date") or trial["primary_completion_date"] > product["approval_date"]:
                continue
            if any(len(target) >= 6 and SequenceMatcher(None, key, target).ratio() >= 0.90 for target in targets):
                add(nct, product, "low", "fuzzy intervention name and sponsor family before approval")
    return pd.DataFrame(links.values())


def program_tables(trials, interventions, links):
    trial_by_nct = {r["nct_id"]: r for r in trials.values()}
    approved_by_nct = defaultdict(list)
    if len(links):
        for row in links.itertuples(index=False):
            if row.link_confidence in ("high", "medium") and row.preapproval_trial:
                approved_by_nct[row.nct_id].append(row.approval_date)
    groups = defaultdict(set)
    naming = defaultdict(list)
    for row in interventions.itertuples(index=False):
        trial = trial_by_nct[row.nct_id]
        if row.intervention_key in ("placebo", "standard of care") or not row.intervention_key:
            continue
        family = trial["matched_company"] or trial["sponsor"]
        key = (family, row.intervention_key)
        groups[key].add(row.nct_id)
        naming[key].append((row.is_named, row.is_code_name))
    rows = []
    trial_program = defaultdict(list)
    for (family, intervention_key), ncts in groups.items():
        members = [trial_by_nct[nct] for nct in ncts]
        for nct in ncts:
            trial_program[nct].append((family, intervention_key))
        starts = {level: sorted(r["start_date"] for r in members if phase_level(r["phase"]) == level and r["start_date"]) for level in (1, 2, 3)}
        known_approvals = sorted(d for nct in ncts for d in approved_by_nct.get(nct, []))
        latest = max(members, key=lambda r: r["last_update_date"] or "")
        statuses = {r["overall_status"] for r in members}
        if known_approvals:
            outcome, known_date = "approved_FDA", known_approvals[0]
        elif statuses & {"RECRUITING", "ACTIVE_NOT_RECRUITING", "NOT_YET_RECRUITING", "ENROLLING_BY_INVITATION"}:
            outcome, known_date = "ongoing", latest["last_update_date"]
        elif statuses and statuses.issubset({"TERMINATED", "WITHDRAWN", "SUSPENDED"}):
            outcome, known_date = "stopped", latest["last_update_date"]
        else:
            completed = [r for r in members if r["completion_date"] and r["completion_type"] == "ACTUAL"]
            last_completion = max((r["completion_date"] for r in completed), default="")
            if last_completion and pd.Timestamp(last_completion) + pd.DateOffset(years=4) <= TODAY:
                outcome, known_date = "stalled_after_4y", str((pd.Timestamp(last_completion) + pd.DateOffset(years=4)).date())
            else:
                outcome, known_date = "completed_without_approval_unknown", latest["last_update_date"]
        rows.append(dict(program_company=family, intervention_key=intervention_key,
                         n_trials=len(ncts), sponsor_group="A" if any(r["sponsor_group"] == "A" for r in members) else "B",
                         highest_phase=max((phase_level(r["phase"]) for r in members), default=0),
                         first_start_date=min((r["start_date"] for r in members if r["start_date"]), default=""),
                         first_phase1_start=starts[1][0] if starts[1] else "",
                         first_phase2_start=starts[2][0] if starts[2] else "",
                         first_phase3_start=starts[3][0] if starts[3] else "",
                         final_outcome=outcome, outcome_known_date=known_date,
                         ever_named=int(any(x[0] for x in naming[(family, intervention_key)])),
                         code_only=int(all(x[1] for x in naming[(family, intervention_key)])),
                         nct_ids=";".join(sorted(ncts))))
    return pd.DataFrame(rows), trial_program


def phase_statistics(trials, programs, trial_program):
    pmap = {(r.program_company, r.intervention_key): r.final_outcome for r in programs.itertuples(index=False)}
    trial_rows = []
    for row in trials.values():
        if row["study_type"] != "INTERVENTIONAL":
            continue
        outcomes = [pmap.get(x) for x in trial_program.get(row["nct_id"], [])]
        later_approved = int("approved_FDA" in outcomes)
        item = dict(sponsor_group=row["sponsor_group"], phase=row["phase"], status=row["overall_status"],
                    later_approved=later_approved, pc_months=np.nan, completion_months=np.nan)
        start = row["start_date"]
        if start and row["start_date_type"] == "ACTUAL" and row["start_date_precision"] == "day":
            for field, typ, precision, target in (("primary_completion_date", "primary_completion_type", "primary_completion_precision", "pc_months"),
                                                  ("completion_date", "completion_type", "completion_precision", "completion_months")):
                if row[field] and row[typ] == "ACTUAL" and row[precision] == "day":
                    duration = (pd.Timestamp(row[field]) - pd.Timestamp(start)).days / 30.4375
                    if duration >= 0:
                        item[target] = duration
        trial_rows.append(item)
    frame = pd.DataFrame(trial_rows)
    output = []
    for scope, group in [("overall", frame)] + [(x, frame[frame.sponsor_group == x]) for x in ("A", "B")]:
        for (phase, status, approved), sample in group.groupby(["phase", "status", "later_approved"], dropna=False):
            record = dict(stat_kind="phase_status", sponsor_group=scope, phase=phase, status=status,
                          later_approved=approved, n_trials=len(sample))
            for field in ("pc_months", "completion_months"):
                vals = sample[field].dropna()
                prefix = field.replace("_months", "")
                record.update({f"{prefix}_n_actual":len(vals),f"{prefix}_median_months":vals.median(),
                               f"{prefix}_mean_months":vals.mean(),f"{prefix}_p25_months":vals.quantile(.25),
                               f"{prefix}_p75_months":vals.quantile(.75)})
            output.append(record)
        subset = programs if scope == "overall" else programs[programs.sponsor_group == scope]
        phase1 = subset[subset.first_phase1_start != ""]
        for years in (3, 5):
            eligible = phase1[pd.to_datetime(phase1.first_phase1_start) <= TODAY - pd.DateOffset(years=years)]
            for next_phase, field in ((2, "first_phase2_start"), (3, "first_phase3_start")):
                reached = sum(bool(r[field]) and pd.Timestamp(r[field]) <= pd.Timestamp(r.first_phase1_start) + pd.DateOffset(years=years) for _, r in eligible.iterrows())
                output.append(dict(stat_kind="phase1_continuity", sponsor_group=scope, phase="Phase 1",
                                   status=f"reach_phase{next_phase}_within_{years}y", n_programs=len(eligible),
                                   n_reached=reached, share_reached=reached/len(eligible) if len(eligible) else np.nan))
        for named_label, selected in (("ever_named", subset[subset.ever_named == 1]),
                                      ("code_only", subset[subset.code_only == 1])):
            approved = (selected.final_outcome == "approved_FDA").sum()
            output.append(dict(stat_kind="naming", sponsor_group=scope, status=named_label,
                               n_programs=len(selected), n_reached=approved,
                               share_reached=approved/len(selected) if len(selected) else np.nan))
    return pd.DataFrame(output)


def slip_statistics(data, trials, programs, trial_program):
    path = data / "raw" / "ct_changes.csv"
    cols = ["nct_id", "sponsor_group", "phase", "slip_count", "slip_bucket", "total_slip_days",
            "first_slip_days", "program_outcome", "outcome_known_date"]
    if not path.exists():
        return pd.DataFrame(columns=cols)
    changes = pd.read_csv(path)
    slips = changes[(changes.change_type == "primary_completion_date_change") &
                    (changes.initial == 0) & (changes.days_shifted > 0)]
    pmap = {(r.program_company, r.intervention_key): (r.final_outcome, r.outcome_known_date) for r in programs.itertuples(index=False)}
    rows = []
    for nct, trial in trials.items():
        if trial["sponsor_group"] != "A" or not trial["history_available"]:
            continue
        events = slips[slips.nct_id == nct].sort_values(["version_date", "version_number"])
        outcomes = [pmap.get(x, ("unknown", "")) for x in trial_program.get(nct, [])]
        outcome = next((x for x in outcomes if x[0] == "approved_FDA"), None)
        outcome = outcome or next((x for x in outcomes if x[0] in ("stopped", "stalled_after_4y")), None)
        outcome = outcome or ("unknown", trial["last_update_date"])
        count = len(events)
        rows.append(dict(nct_id=nct, sponsor_group="A", phase=trial["phase"],
                         slip_count=count, slip_bucket=str(count) if count < 3 else "3+",
                         total_slip_days=events.days_shifted.sum() if count else 0,
                         first_slip_days=events.days_shifted.iloc[0] if count else np.nan,
                         program_outcome=outcome[0], outcome_known_date=outcome[1]))
    return pd.DataFrame(rows, columns=cols)


def save_table(name, frame, folder):
    path = folder / f"{name}.csv"
    if path.exists():
        raise SystemExit(f"Refusing to edit existing output: {path}")
    frame.to_csv(path, index=False)
    date_cols = [c for c in frame.columns if c.endswith("_date") and c not in ("record_observed_date", "link_observed_date")]
    dates = []
    for col in date_cols:
        dates.extend(pd.to_datetime(frame[col], errors="coerce").dropna().tolist())
    first, last = (min(dates).date(), max(dates).date()) if dates else ("none", "none")
    print(f"TABLE {name}: rows {len(frame)}; first date {first}; last date {last}")
    print(frame.head(5).to_string(index=False) if len(frame) else "(empty)")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data", type=Path, default=Path(__file__).resolve().parent.parent / "data")
    args = parser.parse_args()
    folder = args.data / "raw" / "research"
    folder.mkdir(parents=True, exist_ok=True)
    names = ("trials_all", "interventions", "products_approved", "trial_product_links",
             "program_outcomes", "phase_stats", "slip_stats")
    if any((folder / f"{name}.csv").exists() for name in names):
        raise SystemExit("One or more research outputs already exist; refusing to edit them")
    ranking = pd.read_csv(args.data / "raw" / "top100_pharma.csv")
    trials, records = source_trials(args.data, ranking)
    products = approved_products(args.data, ranking, trials)
    product_names = list(products.brand_name) + [x for value in products.generic_name for x in str(value).split(";")]
    interventions = interventions_table(records, product_names)
    links = links_table(trials, interventions, products)
    linked_ncts = set(links.nct_id) if len(links) else set()
    trials = {nct: row for nct, row in trials.items() if row["study_type"] == "INTERVENTIONAL" and
              (row["start_date"] >= "2018-01-01" or nct in linked_ncts)}
    records = {nct: record for nct, record in records.items() if nct in trials}
    interventions = interventions[interventions.nct_id.isin(trials)]
    links = links[links.nct_id.isin(trials)] if len(links) else links
    programs, trial_program = program_tables(trials, interventions, links)
    phase_stats = phase_statistics(trials, programs, trial_program)
    slips = slip_statistics(args.data, trials, programs, trial_program)
    trial_frame = pd.DataFrame(trials.values()).sort_values("nct_id")
    for name, frame in (("trials_all", trial_frame), ("interventions", interventions),
                        ("products_approved", products), ("trial_product_links", links),
                        ("program_outcomes", programs), ("phase_stats", phase_stats), ("slip_stats", slips)):
        save_table(name, frame, folder)
    print("Sponsor groups:")
    print(trial_frame.sponsor_group.value_counts(dropna=False).to_string())
    print("Random sponsor match audit (20):")
    print(trial_frame[["nct_id", "sponsor", "sponsor_group", "matched_company", "sponsor_match_type", "match_confidence"]].sample(min(20, len(trial_frame)), random_state=0).to_string(index=False))
    high_apps = set(links.loc[links.link_confidence == "high", "application_number"]) if len(links) else set()
    linked_apps = set(links.application_number) if len(links) else set()
    all_apps = set(products.application_number)
    print(f"Approved applications with high-confidence linked trial: {len(high_apps)} / {len(all_apps)}")
    print("Random link audit (15):")
    print(links.sample(min(15, len(links)), random_state=0).to_string(index=False) if len(links) else "(none)")
    print(f"Approved applications with no linked trial: {len(all_apps - linked_apps)} / {len(all_apps)} ({len(all_apps - linked_apps)/len(all_apps):.3f})")
    print("Survivorship: current trial API includes terminated and withdrawn records, but sponsor search, missing older Group B trials, and current label citations can undercount programs without approval. Unknown is kept separate from failure.")
    if len(slips):
        summary = slips.groupby(["slip_bucket", "program_outcome"]).size().unstack(fill_value=0)
        print("Slip count by outcome, counts:")
        print(summary.to_string())
        print("Slip count by outcome, within-outcome shares:")
        print((summary / summary.sum(axis=0)).round(3).to_string())
        print("Median total slip days by phase and outcome:")
        print(slips.groupby(["phase", "program_outcome"]).total_slip_days.median().to_string())
    else:
        print("Slip analysis unavailable: no complete Group A history rows in ct_changes.csv")


if __name__ == "__main__":
    main()
