#!/usr/bin/env python3
"""Render a run's reversion_study.json as one self-contained HTML page.

This closes ADR-007. That entry asked for an HTML report and named a
plotting stage (gm-plot) to produce it; neither was ever built, and
gm-report writes JSON and parquet instead.

The decision recorded here is to close it as a RENDERER rather than a
stage:

  - It is not a pipeline stage, so it cannot fail a run, has no manifest
    of its own, and adds nothing to the dependency graph. A presentation
    layer that can break a data pipeline is a liability.
  - It reads only the artifact, so it cannot disagree with the numbers.
    A stage that recomputed anything for display would be a second
    implementation of the study with its own bugs.
  - No dependencies and no network. One file out, openable anywhere,
    including from a machine that has never seen this repository.

What it deliberately does NOT do is decide anything. Where the study
reports a verdict, the page shows the verdict the artifact contains; it
does not compute one.

Usage:
    python3 tools/render_study.py runs/<run-id>/gm-report/reversion_study.json \
        [-o study.html]
"""

import argparse
import html
import json
import os
import sys
from datetime import datetime, timezone

CSS = """
:root{
  --bg:#fbfaf8; --surface:#ffffff; --ink:#1b1a18; --muted:#6a6660;
  --line:#e4e0d9; --accent:#8c5a2b; --good:#2f6b4f; --bad:#a33a2a;
  --mono:ui-monospace,SFMono-Regular,"SF Mono",Menlo,Consolas,monospace;
}
@media (prefers-color-scheme:dark){
  :root:not([data-theme="light"]){
    --bg:#161513; --surface:#1e1d1a; --ink:#ece8e1; --muted:#9a948a;
    --line:#312e29; --accent:#d59a5e; --good:#6fbd92; --bad:#e2806d;
  }
}
:root[data-theme="dark"]{
  --bg:#161513; --surface:#1e1d1a; --ink:#ece8e1; --muted:#9a948a;
  --line:#312e29; --accent:#d59a5e; --good:#6fbd92; --bad:#e2806d;
}
*{box-sizing:border-box}
body{margin:0;background:var(--bg);color:var(--ink);
  font:15px/1.6 ui-sans-serif,system-ui,-apple-system,"Segoe UI",Roboto,sans-serif}
.wrap{max-width:60rem;margin:0 auto;padding:2.5rem 1rem 5rem}
h1{font-size:1.8rem;line-height:1.2;margin:0 0 .3rem;text-wrap:balance}
h2{font-size:1.15rem;margin:2.6rem 0 .7rem;padding-bottom:.35rem;
  border-bottom:1px solid var(--line)}
h3{font-size:.95rem;margin:1.6rem 0 .5rem;color:var(--muted);
  text-transform:uppercase;letter-spacing:.06em}
p{margin:.6rem 0}
.sub{color:var(--muted);margin:0 0 2rem;font-size:.9rem}
.verdict{background:var(--surface);border:1px solid var(--line);
  border-left:4px solid var(--accent);border-radius:6px;padding:1.1rem 1.25rem;margin:1.5rem 0}
.verdict .big{font-size:1.25rem;font-weight:600;margin:0 0 .4rem}
.note{color:var(--muted);font-size:.87rem;margin:.5rem 0}
.scroll{overflow-x:auto;margin:.8rem 0}
table{border-collapse:collapse;width:100%;font-size:.88rem;
  background:var(--surface);border:1px solid var(--line);border-radius:6px}
th,td{padding:.45rem .7rem;text-align:right;border-bottom:1px solid var(--line);
  font-variant-numeric:tabular-nums}
th:first-child,td:first-child{text-align:left;font-variant-numeric:normal}
thead th{font-weight:600;color:var(--muted);font-size:.78rem;
  text-transform:uppercase;letter-spacing:.05em;white-space:nowrap}
tbody tr:last-child td{border-bottom:none}
.pos{color:var(--good)} .neg{color:var(--bad)}
code,.mono{font-family:var(--mono);font-size:.85em}
footer{margin-top:3rem;padding-top:1rem;border-top:1px solid var(--line);
  color:var(--muted);font-size:.82rem}
"""


def esc(value):
    return html.escape(str(value))


def num(value, places=4):
    if value is None:
        return "&mdash;"
    try:
        return ("%%.%df" % places) % float(value)
    except (TypeError, ValueError):
        return esc(value)


def signed(value, places=4):
    """Difference cells carry their sign in colour as well as in text -
    the sign is the finding, and a column of near-zero numbers should
    not need to be read digit by digit."""
    if value is None:
        return "&mdash;"
    cls = "pos" if float(value) > 0 else ("neg" if float(value) < 0 else "")
    return '<span class="%s">%+.*f</span>' % (cls, places, float(value))


def table(headers, rows):
    out = ['<div class="scroll"><table><thead><tr>']
    out += ["<th>%s</th>" % esc(h) for h in headers]
    out.append("</tr></thead><tbody>")
    for row in rows:
        out.append("<tr>" + "".join("<td>%s</td>" % c for c in row) + "</tr>")
    out.append("</tbody></table></div>")
    return "".join(out)


def render_spec(spec, title):
    parts = ["<h3>%s</h3>" % esc(title)]
    parts.append('<p class="note">%s</p>' % esc(spec.get("how_to_read", "")))

    parts.append(table(
        ["", "value"],
        [["covariates matched on", esc(", ".join(spec.get("covariates_used", [])) or "none")],
         ["covariates unavailable",
          esc(", ".join(spec.get("covariates_unavailable", [])) or "none")],
         ["treated excursions", "%d" % spec.get("treated_total", 0)],
         ["matched", "%d (%.1f%%)" % (spec.get("treated_matched", 0),
                                       100.0 * spec.get("match_rate", 0.0))],
         ["unmatched: outside caliper", "%d" % spec.get("unmatched_outside_caliper", 0)],
         ["unmatched: no controls in stratum",
          "%d" % spec.get("unmatched_no_controls_in_stratum", 0)],
         ["worst balance after matching",
          num(spec.get("worst_standardized_diff_after"), 4)]]))

    balance = spec.get("balance", [])
    if balance:
        parts.append("<h3>Covariate balance</h3>")
        parts.append('<p class="note">Below 0.1 after matching is the conventional bar. '
                     'A covariate that does not shrink is one the matching failed on.</p>')
        parts.append(table(
            ["covariate", "before", "after"],
            [[esc(b["covariate"]), signed(b["standardized_diff_before"]),
              signed(b["standardized_diff_after"])] for b in balance]))

    depth = spec.get("match_rate_by_depth_quartile", [])
    if depth:
        parts.append("<h3>Which excursions got matched</h3>")
        parts.append('<p class="note">An unmatched excursion has not been shown to be like '
                     'anything. If the deep ones fail to match, the difference is being '
                     'estimated on the shallow tail of the treatment.</p>')
        parts.append(table(
            ["depth quartile", "treated", "matched", "rate"],
            [[esc(d["bucket"]), "%d" % d["treated"], "%d" % d["matched"],
              "%.1f%%" % (100.0 * d["match_rate"])] for d in depth]))

    rows = []
    for h in spec.get("by_horizon", []):
        if "difference" not in h:
            rows.append(["H%d" % h["horizon_days"], esc(h.get("note", "")), "", "", "", "", ""])
            continue
        rows.append([
            "H%d" % h["horizon_days"],
            "%d" % h.get("pairs_scored", 0),
            signed(h.get("treated_mean_return")),
            signed(h.get("control_mean_return")),
            signed(h.get("difference")),
            num(h.get("se_clustered"), 5),
            signed(h.get("t_statistic"), 2),
        ])
    parts.append("<h3>Difference against matched controls</h3>")
    parts.append(table(
        ["horizon", "pairs", "treated", "control", "difference", "clustered SE", "t"], rows))
    return "".join(parts)


def main():
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("study", help="path to reversion_study.json")
    parser.add_argument("-o", "--out", default=None,
                        help="output HTML path (default: beside the study)")
    args = parser.parse_args()

    try:
        with open(args.study, encoding="utf-8") as handle:
            study = json.load(handle)
    except OSError as exc:
        sys.exit("cannot read study: %s" % exc)

    out_path = args.out or os.path.join(os.path.dirname(os.path.abspath(args.study)),
                                         "reversion_study.html")
    run_id = os.path.basename(os.path.dirname(os.path.dirname(os.path.abspath(args.study))))

    matched = study.get("matched_control", {})
    summary = matched.get("summary", {})
    primary = matched.get("primary", {})

    body = ['<div class="wrap">']
    body.append("<h1>Reversion study &mdash; %s</h1>" % esc(run_id))
    body.append('<p class="sub">ADR-013. Do points outside the boundary return inside, '
                'and do they do it more than comparable points that were never outside?</p>')

    # The verdict, taken from the artifact rather than recomputed.
    pos = summary.get("horizons_with_significant_positive_difference")
    neg = summary.get("horizons_with_significant_negative_difference")
    tested = summary.get("horizons_tested")
    if pos is not None:
        headline = ("Gate NOT passed" if pos == 0 else
                    "Positive difference at %d of %d horizons" % (pos, tested))
        body.append('<div class="verdict">')
        body.append('<p class="big">%s</p>' % esc(headline))
        body.append("<p>%d of %d horizons show a significant positive difference; "
                    "%d significant negative. Largest |t| in the primary specification: "
                    "%.2f.</p>" % (pos, tested, neg, summary.get("max_abs_t_primary", 0.0)))
        body.append('<p class="note">%s</p>' % esc(summary.get("reading", "")))
        body.append("</div>")

    body.append('<p class="note">%s</p>' % esc(study.get("gate_verdict_note", "")))

    body.append("<h2>Matched control</h2>")
    body.append('<p class="note">Outcome: %s</p>'
                % esc(matched.get("outcome_definition", "")))
    if primary:
        body.append(render_spec(primary, "Primary specification"))
    if matched.get("over_controlled"):
        body.append(render_spec(matched["over_controlled"],
                                 "Over-controlled specification (lower bound)"))

    sens = matched.get("caliper_sensitivity_primary", [])
    if sens:
        body.append("<h2>Caliper sensitivity</h2>")
        body.append('<p class="note">A result that exists only at one setting of a free '
                    'parameter is not a result. Tightening the caliper buys comparability '
                    'and costs sample.</p>')
        horizons = [h["horizon_days"] for h in sens[0]["by_horizon"]]
        rows = []
        for row in sens:
            cells = [esc("%.2f" % row["caliper_pooled_sd"]), "%d" % row["treated_matched"],
                     num(row["worst_standardized_diff_after"], 4)]
            by_h = {h["horizon_days"]: h for h in row["by_horizon"]}
            for h in horizons:
                entry = by_h.get(h)
                cells.append("%s<br><span class='note mono'>t=%+.1f</span>"
                             % (signed(entry["difference"]), entry["t_statistic"])
                             if entry else "&mdash;")
            rows.append(cells)
        body.append(table(["caliper", "pairs", "balance"] + ["H%d" % h for h in horizons], rows))

    horizon_block = study.get("reverted_within_horizon", {})
    if horizon_block:
        body.append("<h2>Base rates (Kaplan&ndash;Meier)</h2>")
        body.append('<p class="note">How often a flagged excursion comes back &mdash; not '
                    'whether it comes back more than an unflagged twin. This is the number '
                    'the matched control above exists to put in context. '
                    '<code>km overstatement</code> is the probability mass Kaplan&ndash;Meier '
                    'hands to reversion on behalf of episodes that could never revert.</p>')
        order = ["overall", "q1_shallowest", "q2", "q3", "q4_deepest",
                 "with_earnings_or_8k", "without_earnings_or_8k"]
        keys = [k for k in order if k in horizon_block]
        keys += [k for k in sorted(horizon_block) if k not in order]
        horizons = [h["horizon_days"] for h in horizon_block[keys[0]]["horizons"]]
        rows = []
        for key in keys:
            entry = horizon_block[key]
            cells = [esc(key), "%d" % entry.get("episodes", 0),
                     "%d" % entry.get("distinct_tickers", 0),
                     "%d" % entry.get("distinct_months", 0),
                     "%d" % entry.get("competing_events_delisted", 0)]
            by_h = {h["horizon_days"]: h for h in entry["horizons"]}
            for h in horizons:
                cell = by_h.get(h)
                cells.append(num(cell["reverted_by"], 3) if cell else "&mdash;")
            rows.append(cells)
        body.append(table(
            ["bucket", "episodes", "tickers", "months", "delisted"]
            + ["H%d" % h for h in horizons], rows))
        body.append('<p class="note">Episode counts are not independent observations: '
                    'the tickers and months columns are how far from independent.</p>')

    panel = study.get("panel", {})
    if panel:
        body.append("<h2>Panel</h2>")
        body.append(table(["", "value"],
                           [[esc(k.replace("_", " ")), esc(v)] for k, v in sorted(panel.items())]))

    body.append("<footer>Rendered from <code>%s</code> by "
                "<code>tools/render_study.py</code> on %s. Every figure on this page is read "
                "from that artifact; nothing here is recomputed. See "
                "<code>HYPOTHESES.md</code> for what is open and "
                "<code>BLOCKED.md</code> for what cannot be closed.</footer>"
                % (esc(os.path.basename(args.study)),
                   datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")))
    body.append("</div>")

    page = ("<!doctype html><html lang=\"en\"><head><meta charset=\"utf-8\">"
            "<meta name=\"viewport\" content=\"width=device-width,initial-scale=1\">"
            "<title>Reversion Study</title><style>%s</style></head><body>%s</body></html>"
            % (CSS, "".join(body)))

    with open(out_path, "w", encoding="utf-8") as handle:
        handle.write(page)
    print("wrote %s (%.1f KB)" % (out_path, len(page) / 1024.0))
    return 0


if __name__ == "__main__":
    sys.exit(main())
