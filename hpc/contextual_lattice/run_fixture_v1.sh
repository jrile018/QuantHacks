#!/usr/bin/env bash
set -euo pipefail
ROOT=/home/john-riley/QuantHacks/contextual-lattice-20261003
PY=/home/john-riley/QuantHacks/.venv/bin/python
cd "$ROOT"
export OPENBLAS_NUM_THREADS=2 OMP_NUM_THREADS=2 MKL_NUM_THREADS=2 NUMEXPR_NUM_THREADS=2 ARROW_NUM_THREADS=2
exec 9>/home/john-riley/.cache/quanthaxs-heavy-compute.lock
printf 'WAITING_FOR_SHARED_LOCK\n'
flock 9
printf 'ACQUIRED_SHARED_LOCK\n'
ulimit -v 4194304
trap 'code=$?; printf "EXIT_CODE:%s\n" "$code"' EXIT
"$PY" -m unittest discover -s tests -p 'test_contextual_lattice*.py' -v > fixture_tests.log 2>&1
"$PY" scripts/contextual_lattice/export_integration_fixture.py --run-dir results/contextual-v1 --native-prices /home/john-riley/projects/geomarket/runs/pit-survivorship/gm-ingest/prices.parquet --output results/integration-2024-fixture-v1 --max-rows 3
"$PY" - <<'PY'
import csv,json,platform,sys
from collections import Counter
from datetime import datetime,timezone
from importlib.metadata import version
from pathlib import Path
root=Path('.')
counts=Counter();unique=set();trade=Counter()
with (root/'results/contextual-v1/all_opportunities.csv').open() as stream:
    for row in csv.DictReader(stream):
        counts['attempted_market_hypothesis_decisions']+=1
        counts['status/'+row['status']]+=1
        trade[row['trade_status']]+=1
        unique.add((row['market_group'],row['ticker'],row['date']))
with (root/'results/contextual-v1/all_candidate_decisions.csv').open() as stream:
    for row in csv.DictReader(stream):
        counts['candidate_ledger_rows']+=1
        counts['candidate/'+row['candidate']]+=1
record={'observed_after_run_at_utc':datetime.now(timezone.utc).isoformat(),
        'python':sys.version,'platform':platform.platform(),
        'packages':{name:version(name) for name in ('numpy','pandas','pyarrow')},
        'environment_basis':'observed after completed run; not a pre-fit dependency-lock claim',
        'counts':dict(counts),'trade_status_counts':dict(trade),
        'distinct_instrument_days':len(unique)}
(root/'runtime_and_counts.json').write_text(json.dumps(record,indent=2)+'\n')
print(json.dumps({'counts':dict(counts),'distinct_instrument_days':len(unique)}))
PY
