"""Join reviewed audit/dataflow annotations to an immutable actual Graphify graph."""
from __future__ import annotations
import argparse
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
REPORT = ROOT / 'artifacts/lattice-math-audit/run-v1'
GRAPH = ROOT / '.planning/graphs/lattice-math-audit/graph.json'
OUTPUT = ROOT / 'artifacts/lattice-math-audit/audit-map.json'
nodes, edges = [], []


def add(identifier, lane, stage, label, status, short, input_, output, units, clock, scope, limitation, refs=()):
    references = []
    for relative, line in refs:
        path = ROOT / relative
        references.append({'label': f'{relative}:{line}', 'path': path.as_posix(), 'line': line,
                           'sha256': hashlib.sha256(path.read_bytes()).hexdigest()})
    nodes.append({'id': identifier, 'lane': lane, 'stage': stage, 'label': label,
                  'status': status, 'short': short,
                  'details': [['Input', input_], ['Output', output], ['Units', units], ['Clock', clock],
                              ['Scope', scope], ['Limitation', limitation]], 'references': references})


def link(source, target, label='feeds', kind='reviewed-dataflow'):
    edges.append({'source': source, 'target': target, 'label': label, 'kind': kind})


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--visual-output', type=Path)
    args = parser.parse_args()
    residual = json.loads((ROOT/'artifacts/lattice-strategies/reports-v1/residual_report.json').read_text())
    risk = json.loads((ROOT/'artifacts/lattice-strategies/reports-v1/risk_report.json').read_text())
    frozen = json.loads((REPORT/'frozen-target-audit.json').read_text())
    witness = json.loads((REPORT/'native-witness.json').read_text())
    add('prices', 'equity', 0, 'Stock prices', 'observed', '12 names · 2,011 sessions',
        'Yahoo/native adjusted closes, 2018–2025; 24,132 rows', 'Common 12-stock return panel',
        'Currency/share → fractional returns', 'Assumed post-close decision; next-session outcome',
        'Latest signal and risk study; already inspected 2024/2025 outcomes',
        'Historical universe, adjustment vintage and receipt clock not independently qualified.',
        [('scripts/lattice_strategies/run_study.py', 1)])
    add('formation', 'equity', 1, 'Peer relationships', 'method', 'Earlier 126 sessions',
        'Earlier stock returns, excluding 60 calibration sessions', 'MST / same-degree correlation / price-path peers',
        'Residual correlation and distance: dimensionless', 'Graph cutoff is t−60; no future labels',
        'Python adaptation; signed correlation MST, not native kNN/RIE',
        'A correlation relationship does not establish price convergence or an economic link.',
        [('src/lattice_strategies/residuals.py', 47), ('src/lattice_strategies/graphs.py', 19)])
    add('hedge', 'equity', 2, 'Fit stock minus peers', 'method', 'Signed two-factor hedge',
        'Target stock, leave-target-out market and peer mean', 'Intercept, two slopes and frozen security weights',
        'Intercept: fraction/session; slopes and weights: dimensionless',
        'Hedge fit on earlier formation; held fixed through calibration and target',
        'Unconstrained factor regression; distinct from native simplex basket',
        'Gross normalization does not guarantee dollar, beta or volatility neutrality.',
        [('src/lattice_strategies/residuals.py', 79)])
    add('state', 'equity', 2, 'Measure the leftover gap', 'method', 'Later 60 sessions',
        'Calibration returns minus earlier fitted intercept/factors', 'Cumulative residual state and fitted AR(1)',
        'Additive fractional-return state; phi dimensionless; tau in sessions',
        'Calibration through t, first target t+1', 'Disjoint windows avoid exact OLS endpoint pinning',
        'A passing AR coefficient and time cap do not prove stationarity.',
        [('src/lattice_strategies/residuals.py', 106), ('tests/audit/test_signal_math.py', 29)])
    add('prediction', 'equity', 3, 'Predict gap change', 'interpretation', 'Future factor means set to zero',
        'State, equilibrium, AR slope and formation intercept', 'Expected additive hedged return',
        'Fractional return; secondary 5/20-session sums are not compounded P&L',
        'Frozen daily prediction for t+1; secondary paths separately tracked',
        'Raw-stock reading additionally assumes zero conditional future factors',
        'Prediction of a relative gap and prediction of a stock move are different targets.',
        [('src/lattice_strategies/residuals.py', 221), ('tests/audit/test_signal_math.py', 48)])
    h1 = residual['horizons']['1']
    stock_pct = 100*(h1['models']['mst_peer_state']['mse']/h1['models']['zero']['mse']-1)
    add('raw-mse', 'equity', 4, 'Stock forecast error', 'observed', f'{stock_pct:.2f}% worse than zero',
        'Seven frozen forecasts on the same actual stock outcome', 'Common-cohort squared forecast error',
        'Fractional return squared; lower is better', '6,012 opportunities / 501 decision dates',
        'MST: 0.000382134; zero: 0.000370885. 5/20-session error also worse.',
        'This rejects this raw-stock forecast; it cannot alone reject hedged alpha or native Lattice.',
        [('src/lattice_strategies/evaluation.py', 41), ('docs/research/lattice-math-audit/signals-and-adaptation.md', 1)])
    own = next(x for x in frozen['comparisons'] if x['model']=='mst_peer_state' and x['horizon']==1 and x['cohort']=='available_basket')
    gain = own['hedge_outcome']['paired']['relative_improvement_pct']
    add('hedge-mse', 'equity', 4, 'Same-basket forecast error', 'observed', f'{abs(gain):.2f}% '+('better' if gain>0 else 'worse')+' than zero',
        'Existing MST forecasts versus their own frozen hedge outcomes', 'Candidate-versus-zero MSE on identical hedge target',
        'Unnormalized additive hedge fraction squared', f"{own['rows']:,} available-basket observations; no refits",
        'All available baskets: 4.84% worse; 4,562 valid-model rows separately: 6.56% worse. Post-result exploratory audit.',
        'Other models have different baskets; cross-model hedged MSE ranking is invalid.',
        [('scripts/lattice_strategies/audit_frozen_targets.py', 1)])
    add('marks', 'equity', 5, 'Daily trading proxy', 'observed', '−0.91 bp before costs',
        'Forecast sign × next frozen hedge return, divided by gross exposure', 'Independent daily basket marks, plus assumed roundtrip costs',
        'Return per unit gross; 1 bp = 0.01%', 'Assumed same-close entry and next-close exit; no actual fills',
        'MST mean −0.91 bp/opportunity before costs, −8.50 bp at 5 bp each way',
        'No threshold, persistence, netting, short availability or account model; native policy not tested.',
        [('src/lattice_strategies/evaluation.py', 84)])
    add('weakness', 'equity', 5, 'What could cause weakness?', 'not-tested', 'Cause not isolated',
        'Weak raw forecasts and negative daily sign marks', 'Candidate explanations for controlled follow-up',
        'Hypotheses, not measured effect sizes', 'Historical data already exposed',
        'Stale hedge, noisy parameters, weak MST substitutes, zero factors, tiny-signal daily trades',
        'No ablation has isolated which mechanism caused the loss.',
        [('docs/research/lattice-math-audit/signals-and-adaptation.md', 1)])
    add('covariance', 'risk', 1, 'Estimate co-movement risk', 'method', 'Five covariance methods',
        'Same trailing 126-session stock return matrix', 'Diagonal, sample, LW, one-factor, tree covariance',
        'Fractional return squared/session', 'Includes information through t only',
        'Python Gaussian tree adaptation; not native RIE or LoGo',
        'Tree non-edge correlations are forced to products of edge correlations.',
        [('src/lattice_strategies/risk.py', 20), ('src/lattice_strategies/graphs.py', 50)])
    add('factor-bias', 'risk', 2, 'Portfolio as its own factor', 'interpretation', 'Mechanical upward adjustment',
        'Equal-weight book used as factor; residual covariances discarded', 'Above its variance floor: sample book variance plus a nonnegative diagonal residual term',
        'Variance: fractional return squared/session', 'Same trailing window and book as other controls',
        'Average one-factor forecast roughly 15.9% above sample',
        'A better score does not demonstrate superior independent market-factor identification.',
        [('src/lattice_strategies/risk.py', 31), ('tests/audit/test_signal_math.py', 72)])
    add('fixed-book', 'risk', 3, 'Keep the portfolio identical', 'method', 'Equal weights for all methods',
        'Each covariance and the same equal-weight stock holdings', 'Next-session book variance forecast',
        'Fractional return squared/session', 'Target is next equal-book return squared',
        'Controls are tested on the same held portfolio',
        'Squared returns proxy a second moment; variance reading assumes negligible conditional mean.',
        [('src/lattice_strategies/risk.py', 120)])
    add('risk-loss', 'risk', 4, 'Risk forecast result', 'observed', 'No clear tree advantage',
        '501 common dates, same fixed-book target', 'QLIKE primary, squared variance error secondary',
        'QLIKE lower better; squared variance error: return⁴', 'Next-session diagnostic; unadjusted block intervals',
        'Tree −8.0202; sample −8.0296; LW −8.0092; one-factor −8.0551',
        'Tree differences versus stronger controls have intervals crossing zero.',
        [('src/lattice_strategies/evaluation.py', 108)])
    add('allocation', 'risk', 5, 'Separate allocation test', 'observed', 'Tree: more turnover',
        'Covariances → weekly long-only capped weights → drifted holdings', 'Separate daily net mark proxy with entry/exit/rebalance costs',
        'Portfolio fractional returns; cost in basis points', 'Weekly first observed session; cap applies at rebalance',
        'At 5 bp: tree std 2.29% higher and mean 10.58% lower than LW',
        'Changing portfolios tests allocation, not pure covariance accuracy or residual alpha.',
        [('src/lattice_strategies/risk.py', 56), ('src/lattice_strategies/evaluation.py', 123)])
    add('futures-data', 'futures', 0, 'Futures quotes + definitions', 'observed', 'ES · ZN · CL · GC',
        'Databento actual-contract BBO-1m, definitions and session/calendar bars', 'Dated contract identities and sampled bid/ask marks',
        'Contract price points, quote sizes; contract definitions', 'Prior information at 09:30; sampled mark around 09:36 ET',
        'Existing futures pilot; ES/MES scaling is a separate instrument question',
        'Not stock percentage returns; no continuous-contract roll jump treated as profit.',
        [('src/multi_market/futures_study.py', 86)])
    add('futures-features', 'futures', 1, 'Comparable daily shocks', 'method', 'Same-contract change / prior risk',
        'Point changes and prior contract risk scale', 'Standardized innovations, correlation relationships and context',
        'Dimensionless price-risk units', 'Features precede the decision; next mark uses the same contract',
        'Existing futures contextual study; not the newest 12-equity residual study',
        'A common standardized shock is not common dollar P&L.',
        [('src/multi_market/futures_study.py', 144)])
    add('futures-target', 'futures', 3, 'Predict next-session marks', 'method', 'Catch-up · reversal · movement',
        'Price/context/Lattice features with simple controls', 'Signed mark and absolute movement forecasts',
        'Same-contract point move / prior risk; movement has no direction',
        '09:36 next-session mark; different holding interval from equity close-to-close',
        'Six candidate models within each market/hypothesis cell',
        'Only 60–61 qualified training rows per futures cell.',
        [('src/contextual_lattice/evaluation.py', 69)])
    add('futures-result', 'futures', 4, 'Existing futures result', 'observed', 'Simple controls strongest',
        'Registered exploratory futures forecast cells', 'Signed cells favor zero; movement cells favor ticker mean',
        'Matched-target squared forecast error', 'Previously inspected 2024/2025 subset',
        'Context+Lattice wins none of the full 15 equity/futures cells',
        'Sparse training makes broad market conclusions premature.',
        [('docs/research/2026-10-03-contextual-lattice-results.md', 1)])
    add('futures-gate', 'futures', 5, 'Trading + hedge accounting', 'data-gate', 'Dollar test not qualified',
        'Contracts, multipliers, rolls, margin, stock/options exposures and costs', 'Own trading profit and cross-asset hedge benefits tested separately',
        'Currency per contract; shared risk/holdings units required', 'Synchronize both exposure and contract holding intervals',
        'User-approved economic questions; no demonstrated result yet',
        'No qualified multiplier/roll/margin/funding/portfolio hedge account in this study.',
        [('docs/research/lattice-implementation/design-v1.md', 1)])
    add('option-selection', 'options', 0, 'Event-study selected contracts', 'observed', '654 distinct · 712 assignments',
        'CFO event export and Massive as-of option reference chain', '89 event/expiry groups of selected option legs',
        'Underlying, expiry, strike, call/put and contract ID', 'Retrospective event-study selection; prospective universe not proven',
        'Selection rules, not all listed options or an untouched random sample',
        '654 contracts repeat across 712 assignments; not 712 independent observations.',
        [('docs/databento-options-backfill.md', 91), ('src/implementation.py', 1)])
    add('option-trades', 'options', 1, 'Daily trade bars', 'observed', 'OHLCV ≠ a bid or ask',
        'Massive daily closes; Databento OPRA ohlcv-1d existing request', 'Trade-derived OHLC and volume by venue/UTC day',
        'Currency/share, trade volume; quote depth is different', 'UTC-day OPRA bars versus Eastern qualifying-trade aggregation',
        'Recorded completed request: 375,337 venue rows, 651/654 contracts observed',
        'Multiple venue rows can exist; a single row is not whole-market close or an executable quote.',
        [('docs/databento-options-backfill.md', 106)])
    add('option-quotes', 'options', 1, 'Minute consolidated BBO', 'observed', 'Bid · ask · sizes · timestamp',
        'Databento OPRA cbbo-1m for selected contracts; GD full-chain cache',
        '82,843 imported daily quote marks in the existing options packet',
        'Bid/ask/mid currency/share; sizes are displayed contracts',
        'Latest valid 09:30–16:00 ET sample; interval boundary ≠ original quote-update time',
        'Spread-aware historical descriptive marks; no carry across sessions',
        'Builder drops original event/sequence; quote freshness and fills remain unqualified.',
        [('scripts/build_databento_daily_quotes.py', 1), ('docs/research/lattice-implementation/existing-option-packet.md', 1)])
    add('option-join', 'options', 2, 'Attach stock geometry', 'method', 'Exact underlying + pre-date',
        'Option marks and native equity View B anomaly scores', 'Separate event/option feature and outcome tables',
        'Geometry score dimensionless; option premium currency/share',
        'Exact pre-event session join; missing geometry remains missing',
        'Observed integration supplies context; no option pricing equation',
        'Stock outlyingness does not identify option underpricing or overpricing.',
        [('stat-arb/tools/options_native.py', 346), ('stat-arb/tools/options_bridge.py', 146)])
    add('option-diagnostic', 'options', 3, 'Underlying move + option mark', 'method', 'Describe fixed-contract changes',
        'Selected contracts, pre/post quote mids and stock prices', 'Option midpoint changes paired with absolute stock log changes',
        'Option-mark and stock-movement units remain separate', 'Pre/post sampled marks; expiry/event grouping retained',
        '34 attempted events / 90 event-expiry rows / 31 descriptive events',
        'Not an implied-volatility inversion or fill-based options return.',
        [('src/contextual_lattice/options.py', 139)])
    add('option-result', 'options', 4, 'Options evidence gate', 'data-gate', '18 primary events < 20 required',
        'Qualified primary event cohort', 'Inconclusive descriptive study',
        'Independent events, not prediction-row count', '20 prediction rows do not create 20 independent events',
        'Coverage insufficient under the predeclared gate',
        'Does not establish option alpha, useful surface forecast or trading profit.',
        [('docs/research/2026-10-03-contextual-lattice-results.md', 1)])
    add('option-gate', 'options', 5, 'Price and trade options', 'data-gate', 'Additional context needed',
        'Synchronized stock/option quotes, forward/rates/dividends, contract deliverables and fees',
        'Expiry-aware volatility/surface or relative-value hypothesis and real holdings ledger',
        'Premium currency/share → contract currency using authoritative deliverables',
        'Historical receipt and quote-update freshness; exercise/assignment/settlement clocks',
        'Possible future use; not implemented or proved in the current result',
        'Assumed 100-share multiplier is not authoritative adjusted-contract evidence.',
        [('docs/research/lattice-implementation/existing-option-packet.md', 1)])
    add('native-correlation', 'native', 0, 'Native return geometry', 'method', 'T observations × N assets',
        'Native multi-stock rolling return panel', 'Correlation, signed distances and optional denoising',
        'Correlation/distance dimensionless; aspect q=N/T', 'Close-t graph, causal for later execution',
        'Native C++ path; separate from newest Python MST experiment',
        'Historical missing dates can bridge multi-session returns.',
        [('stat-arb/apps/gm-geometry/main.cpp', 330)])
    add('native-lw', 'native', 1, 'Native LW normalization', 'math-defect', 'Extra off-diagonal shrinkage',
        'Sample-standardized returns with covariance divisor T', 'Diagonal overwritten instead of full correlation normalization',
        'Reported correlation contains unintended (T−1)/T factor off diagonal',
        'Exact compiled local source witness, not full native backtest',
        f"Two-point witness: delta approximately 0, rho {witness['lw_zero_delta']['actual_correlation']:g}; correct rho 1",
        'Used in native shrink_clip; NOT used by latest Python sklearn LW or signal adaptation.',
        [('stat-arb/libs/gm-geometry/src/shrinkage.cpp', 70), ('tests/audit/native_spectral_witness.cpp', 1)])
    add('native-rie', 'native', 1, 'Native singular RIE branch', 'math-defect', 'Zero-eigenvalue correction omitted',
        'Sample correlation when assets exceed observations (q>1)',
        'Sample null eigenvalues are assigned zero, leaving singular directions',
        'Eigenvalues of correlation; companion-transform correction required',
        'Compiled rank-two witness at q=4/3', 'High priority if RIE is selected; default estimator is shrink_clip',
        'Not active in the latest Python study; replacing zeros with epsilon is not the literature estimator.',
        [('stat-arb/libs/gm-geometry/src/rie.cpp', 58), ('docs/research/lattice-math-audit/native-spectral.md', 1)])
    add('native-mp', 'native', 1, 'MP edge metadata', 'math-defect', 'Zero atom ≠ lower bulk edge',
        'q=N/T, q>1', 'Reported lower edge zero instead of positive continuous support edge',
        'Dimensionless spectral edge', 'Compiled witness q=4/3: correct edge about 0.02393',
        'Metadata defect; present clip loop uses the upper edge',
        'Does not by itself change clipping or explain Python performance.',
        [('stat-arb/libs/gm-geometry/src/rmt.cpp', 29)])
    add('native-map', 'native', 2, 'Full-distance peers + MDS', 'method', 'Display and peer graph differ',
        'Cleaned signed-correlation distances', 'Full-distance kNN/MST peers; truncated MDS coordinates aligned to prior frame',
        'MDS display coordinates dimensionless; raw coordinates not unit-normalized',
        'Current graph with prior-only Procrustes anchor', 'Signal app consumes kNN flags; MST-only bridges excluded',
        'Three-dimensional display loses distances; native peers are built BEFORE this compression.',
        [('stat-arb/apps/gm-geometry/main.cpp', 353), ('stat-arb/libs/gm-geometry/src/mds.cpp', 24)])
    add('native-ou', 'native', 3, 'Native log-basket + OU', 'interpretation', 'Core OU mapping correct',
        'Nonnegative simplex peer weights and log-price spread', 'OU equilibrium, diffusion, half-life and z-score',
        'Theta 1/session; half-life sessions; z dimensionless',
        'Prior coefficients; same-day graph can affect current peer selection',
        'Compiled non-unit-dt guard defect: compares physical time to count',
        'Default dt=1 unaffected; log spread is not exactly account P&L.',
        [('stat-arb/libs/gm-signals/src/ou_fit.cpp', 50), ('stat-arb/libs/gm-signals/src/peer_basket.cpp', 88)])
    add('native-boundary', 'native', 3, 'Rarity / historical depth', 'interpretation', 'Not mispricing probability',
        'Current cross-section (A) or prior per-ticker coordinates (B)',
        'Mahalanobis/FastMCD tail reference or KDE density/depth',
        'Estimator-specific dimensionless scores; not directly comparable',
        'A fits and scores same sample; B uses prior history',
        'Core Gaussian KDE normalization correct; fitted scores uncalibrated',
        'Chi-square p-value does not demonstrate a 5% future false-alert rate; rarity ≠ trade direction.',
        [('stat-arb/libs/gm-boundaries/src/mahalanobis.cpp', 130), ('stat-arb/libs/gm-boundaries/src/kde.cpp', 30)])
    add('native-excursion', 'native', 4, 'Refitted z-score excursions', 'interpretation', 'Duration compresses missing fits',
        'Only successfully fitted, daily-changing z-score rows', 'Band-return labels and compressed index difference called duration_days',
        'Successful-observation steps, not necessarily elapsed sessions',
        'Missing/invalid-fit periods disappear from excursion sequence',
        'Static source defect: no empirical prevalence measured',
        'Changing fitted equilibrium can show reentry without fixed-basket convergence.',
        [('stat-arb/apps/gm-signals/main.cpp', 476), ('stat-arb/apps/gm-signals/main.cpp', 538)])
    add('native-policy', 'native', 5, 'Native strategy verdict', 'not-tested', 'Pilot does not reproduce this',
        'Native kNN, simplex hedge, OU thresholds/holding rules and account engine',
        'A separate source-corrected, registered native validation is needed',
        'Cost-bearing holdings/account returns', 'After fixing estimator/time-axis defects and qualifying source clocks',
        'Current negative Python result does not reject the entire native repository',
        'No broad profitability promise; native backtest/account math not comprehensively certified here.',
        [('docs/research/lattice-math-audit/signals-and-adaptation.md', 1)])
    add('context-data', 'context', 0, 'Filings + financial context', 'observed', 'Numbers behind the figure',
        'SEC disclosures, extracted financial facts and issuer/industry relationships',
        'Evidence-backed candidate context with entity, period, unit and source',
        'Currency, ratios or categories; different release clocks',
        'Publication versus receipt versus historical availability must remain separate',
        'Other project owners supply canonical financial/industry packets',
        'OCR success or a disclosed number does not prove historical availability or economic relevance.',
        [('docs/coordination/objects/features-and-targets.md', 1)])
    add('context-model', 'context', 2, 'Specify the relationship', 'interpretation', 'What should respond to what?',
        'Known-at-cutoff own/peer events, regimes and signed business links',
        'Separate catch-up, reversal and magnitude mechanisms with controls',
        'Signed economic exposures distinct from unsigned price correlation',
        'Use prior context; future disclosure identity belongs in labels only',
        'Price proxies implemented; actual-news surprise and signed links unqualified',
        'A price graph cannot invent missing business links, news expectations or shock sign.',
        [('src/contextual_lattice/context.py', 1), ('docs/research/2026-10-03-contextual-lattice.md', 1)])
    add('context-result', 'context', 4, 'Contextual forecast result', 'observed', '0 / 15 cells won',
        'Matched contextual, Lattice-only, baseline, zero and mean forecasts',
        'Context+Lattice not best in any registered market/hypothesis cell',
        'Common-target squared forecast error', 'Already inspected outcomes; not untouched final validation',
        'Equity/futures price-proxy study, not actual-news surprise test',
        'Frozen-training exposure control cannot isolate filtering skill from holdout exposure changes.',
        [('src/contextual_lattice/evaluation.py', 247)])
    for a,b,label in [('prices','formation','returns'),('formation','hedge','peer sets'),('hedge','state','frozen coefficients'),
                      ('state','prediction','state/dynamics'),('prediction','raw-mse','raw-stock reading'),
                      ('prediction','hedge-mse','same frozen hedge'),('prediction','marks','forecast sign'),('hedge','marks','signed security weights'),
                      ('raw-mse','weakness','observed weakness'),('marks','weakness','policy weakness'),
                      ('prices','covariance','same returns'),('covariance','factor-bias','self-factor control'),
                      ('covariance','fixed-book','same fixed book'),('factor-bias','risk-loss','control interpretation'),
                      ('fixed-book','risk-loss','next squared book return'),('covariance','allocation','weekly weights'),
                      ('futures-data','futures-features','dated same contract'),('futures-features','futures-target','prior risk units'),
                      ('futures-target','futures-result','matched outcome'),('futures-result','futures-gate','economic follow-up'),
                      ('option-selection','option-trades','chosen contract IDs'),('option-selection','option-quotes','chosen contract IDs'),
                      ('option-trades','option-join','premium/volume marks'),('option-quotes','option-join','spread/mid marks'),
                      ('option-join','option-diagnostic','pre-event context'),('option-diagnostic','option-result','event cohort'),
                      ('option-result','option-gate','unqualified pricing/trading'),
                      ('native-correlation','native-lw','default shrink_clip'),('native-correlation','native-rie','optional RIE'),
                      ('native-lw','native-mp','MP upper clipping'),('native-mp','native-map','full-distance graph'),
                      ('native-rie','native-map','alternative cleaned correlation'),('native-map','native-ou','kNN peers'),
                      ('native-map','native-boundary','embedding coordinates'),('native-ou','native-excursion','daily refitted z'),
                      ('native-excursion','native-policy','signal labels, not account'),('native-boundary','option-join','exact stock/date context'),
                      ('context-data','context-model','known-at-cutoff facts'),('context-model','context-result','proxy test'),
                      ('context-model','futures-target','market context')]:
        link(a,b,label)
    link('prediction','raw-mse','zero-factor assumption','interpretation-warning')
    link('factor-bias','risk-loss','mechanical variance inflation','interpretation-warning')
    link('option-result','option-gate','coverage/lifecycle gates','gate')
    link('futures-result','futures-gate','multiplier/holding-clock gates','gate')
    graph = json.loads(GRAPH.read_text(encoding='utf-8-sig'))
    graph_nodes = graph['nodes']
    graph_links = graph.get('links', graph.get('edges', []))
    for n in nodes:
        relative_refs = [str(Path(r['path']).relative_to(ROOT)).replace('\\','/') for r in n['references']]
        matches = [g for g in graph_nodes if any(str(g.get('source_file','')).replace('\\','/').endswith(ref) for ref in relative_refs)]
        matched_ids = {g['id'] for g in matches}
        n['code_nodes'] = [{k:g[k] for k in ('id','label','source_file','source_location','_origin') if k in g} for g in matches]
        n['code_links'] = [{'source':g['source'],'target':g['target'],
                            'kind':str(g.get('relation',g.get('type','code structure')))+' / '+str(g.get('confidence','unspecified')),
                            'confidence':g.get('confidence'), 'origin':g.get('_origin')}
                           for g in graph_links if g.get('source') in matched_ids and g.get('target') in matched_ids]
    payload = {'title':'Lattice: data → calculation → test → result', 'selected':'raw-mse',
               'stage_labels':['Data','Relationships','Fit / transform','Prediction / score','Measured result','Trading / interpretation'],
               'lanes':[{'id':x,'label':y} for x,y in [('equity','Equities · relative gap'),('risk','Equities · risk / allocation'),
                         ('futures','Futures · daily pilot'),('options','Options · existing data'),('native','Native Lattice · math'),('context','Context · filings / fundamentals')]],
               'metadata':{'native_checkout':'0d77fc4d15e1a84e0e6d5798617cc110c9f0390e',
                           'math_source_archive_sha256':'5ee056e266a842c877ed85b278fd266b31509dbbb734f5501f7b0a7eff638101',
                           'graph_sha256':hashlib.sha256(GRAPH.read_bytes()).hexdigest(),
                           'graph_nodes':len(graph_nodes),'graph_links':len(graph_links),
                           'semantic_edges':'Reviewed source/result annotations; not automatically extracted causality',
                           'code_edges':'Actual Graphify: 1,047 EXTRACTED / 14 INFERRED confidence; structural, not runtime/economic proof',
                           'verification':'10 small math tests plus compiled native witnesses; zero model refits',
                           'economic_scope':'Exploratory 2024/2025; no fills, purchases or promotion'},
               'nodes':nodes,'edges':edges}
    ids = {n['id'] for n in nodes}
    assert len(ids)==len(nodes)
    assert all(e['source'] in ids and e['target'] in ids for e in edges)
    assert all(n['code_nodes'] for n in nodes if n['references'][0]['label'].startswith('src/lattice_strategies/'))
    OUTPUT.write_text(json.dumps(payload,indent=2,allow_nan=False)+'\n',encoding='utf-8')
    print(f'Wrote {len(nodes)} audit nodes / {len(edges)} reviewed links / {len(graph_nodes)} Graphify code nodes')
    if args.visual_output:
        template = (ROOT/'artifacts/lattice-math-audit/audit-view-template.html').read_text(encoding='utf-8')
        assert template.count('__AUDIT_DATA_JSON__') == 1
        fragment = template.replace('__AUDIT_DATA_JSON__', json.dumps(payload,allow_nan=False).replace('<', r'\u003c'))
        assert len(fragment.encode('utf-8')) < 1_000_000
        args.visual_output.write_text(fragment,encoding='utf-8')
        assert args.visual_output.read_text(encoding='utf-8') == fragment
        print(f'Wrote verified {len(fragment.encode("utf-8")):,}-byte interactive fragment')


if __name__=='__main__':
    main()
