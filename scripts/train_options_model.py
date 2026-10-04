"""Audit point-in-time options tables; fit only when explicitly requested."""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
from pathlib import Path
import sys
from datetime import datetime, timezone

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from src.options_learning import build_dataset, train_model, timestamp, split_dataset, evaluate_final_test


def load_table(path):
    if path.suffix.lower() == '.csv':
        with path.open(encoding='utf-8-sig',newline='') as handle:
            return list(csv.DictReader(handle))
    if path.suffix.lower() == '.jsonl':
        return [json.loads(line) for line in path.read_text(encoding='utf-8-sig').splitlines() if line.strip()]
    raise ValueError('tables_require_csv_or_jsonl:' + str(path))


def write_json(path,value):
    with path.open('x',encoding='utf-8') as handle:
        json.dump(value,handle,indent=2,allow_nan=False)
        handle.write('\n')


def reserve_holdout(ledger, rows, config, provenance):
    """Atomically reserve one cohort/window before scoring; names do not reset holdouts."""
    test=split_dataset(rows,config)['test']
    identity={'target_rule_id':config['target_rule_id'],
              'test_start_utc':config['validation_end_utc'],'test_end_utc':config['test_end_utc'],
              'quote_provider':provenance['quote_provider'],
              'event_groups':sorted({(r.get('security_id',''),r['event_group_id']) for r in test})}
    event_keys=[{'security_id':r.get('security_id',''),'event_group_id':r['event_group_id'],
                 'decision_at_utc':timestamp(r['decision_at_utc']).isoformat()} for r in test]
    fingerprint=hashlib.sha256(json.dumps(identity,sort_keys=True).encode()).hexdigest()
    ledger.mkdir(parents=True,exist_ok=True)
    path=ledger/(fingerprint+'.json')
    lock=ledger/'.reservation-lock'
    try:
        with lock.open('x',encoding='utf-8') as handle:
            handle.write('Atomic heldout reservation in progress.\n')
    except FileExistsError as exc:
        raise ValueError('holdout_ledger_busy; retry after the current reservation finishes') from exc
    try:
        if path.exists():
            raise ValueError('heldout_already_reserved:' + str(path))
        for prior_path in ledger.glob('*.json'):
            prior=json.loads(prior_path.read_text(encoding='utf-8'))
            previous=prior.get('event_keys')
            if not isinstance(previous,list):
                raise ValueError('holdout_ledger_entry_missing_event_keys:' + str(prior_path))
            if any(a['security_id']==b['security_id'] and
                   (a['event_group_id']==b['event_group_id'] or a['decision_at_utc']==b['decision_at_utc'])
                   for a in event_keys for b in previous):
                raise ValueError('heldout_overlap:' + str(prior_path))
        write_json(path,{'holdout':identity,'event_keys':event_keys,'experiment_id':provenance['experiment_id'],
                         'reserved_at_utc':datetime.now(timezone.utc).isoformat(),
                         'status':'reserved_before_evaluation'})
    finally:
        lock.unlink()
    return path


def main(argv=None):
    parser=argparse.ArgumentParser(description=__doc__)
    for name in ('events','features','quotes','sessions','registry','provenance'):
        parser.add_argument('--'+name,type=Path,required=True)
    parser.add_argument('--config',type=Path,default=Path(__file__).resolve().parents[1]/'configs/options_learning.json')
    parser.add_argument('--output',type=Path,required=True,help='New run directory; existing paths are refused')
    parser.add_argument('--fit',action='store_true')
    parser.add_argument('--evaluation-ledger',type=Path,
                        default=Path(__file__).resolve().parents[1]/'data/processed/options_learning/holdout_ledger',
                        help='Persistent final-test reservations; retain across feature/model trials')
    args=parser.parse_args(argv)
    if args.output.exists():
        parser.error('output_directory_already_exists; preserve the prior experiment')
    try:
        provenance=json.loads(args.provenance.read_text(encoding='utf-8-sig'))
        registry=json.loads(args.registry.read_text(encoding='utf-8-sig'))
        config=json.loads(args.config.read_text(encoding='utf-8-sig'))
        tables=[load_table(getattr(args,n)) for n in ('events','features','quotes','sessions')]
        dataset=build_dataset(*tables,registry,provenance,config)
        dataset['input_sha256']={n:hashlib.sha256(getattr(args,n).read_bytes()).hexdigest()
                                 for n in ('events','features','quotes','sessions','registry','provenance','config')}
        args.output.mkdir(parents=True,exist_ok=False)
        write_json(args.output/'audit.json',dataset)
        fit=None
        if args.fit:
            # A retrospective study freezes its protocol now, not falsely in the past.
            run_at=datetime.now(timezone.utc)
            if timestamp(provenance['experiment_frozen_at_utc']) > run_at:
                raise ValueError('experiment_freeze_is_in_the_future')
            fit=train_model(dataset['rows'],config,evaluate_test=False)
            reservation=reserve_holdout(args.evaluation_ledger,dataset['rows'],config,provenance)
            fit=evaluate_final_test(fit,dataset['rows'],config)
            fit['provenance']=provenance
            fit['config']=config
            fit['input_sha256']=dataset['input_sha256']
            fit['evaluation_at_utc']=run_at.isoformat()
            fit['deployment_scope']='retrospective_not_historically_deployable'
            fit['evaluation_ledger_reservation']=str(reservation.resolve())
            write_json(args.output/'model.json',fit)
        print(str((args.output/('model.json' if fit else 'audit.json')).resolve()))
        return 0
    except (OSError,ValueError,TypeError,KeyError) as exc:
        if args.output.is_dir() and not (args.output/'failure.json').exists():
            write_json(args.output/'failure.json',{'status':'blocked','reason':str(exc)})
        print('Options training blocked: '+str(exc),file=sys.stderr)
        return 2


if __name__=='__main__':
    raise SystemExit(main())
