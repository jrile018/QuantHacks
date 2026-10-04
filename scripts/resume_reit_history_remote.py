"""Prepare a portable frozen REIT history run; acquisition requires --execute."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from src.reit_history_remote import (START_DATE, END_DATE, checkpoint, complete_metadata,
    file_hash, frozen_inputs, load_json, migrate_broker, prepare_metadata, run_batches, save_json,
    validate_prepared_resume)
from src.reit_acquisition import FetchBroker


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--old-project-root', required=True, help='Original project root encoded in retained paths')
    parser.add_argument('--new-project-root', required=True, type=Path, help='Root containing copied originals')
    parser.add_argument('--source-broker', required=True, type=Path, help='Original copied broker objects directory parent')
    parser.add_argument('--source-database', type=Path, help='Read-only SQLite backup; defaults to source-broker/broker.sqlite')
    parser.add_argument('--metadata', required=True, type=Path)
    parser.add_argument('--metadata-sha256', help='Optional prior metadata hash; always pinned in the new checkpoint')
    parser.add_argument('--universe', required=True, type=Path, help='Frozen universe_current.json; fixed approved hash')
    parser.add_argument('--plan', required=True, type=Path, help='Frozen history_batch_plan.json; fixed approved hash')
    parser.add_argument('--output', required=True, type=Path, help='Fresh derived run output')
    parser.add_argument('--contact', default='john.p.riley00@gmail.com')
    parser.add_argument('--rate', type=float, default=2)
    parser.add_argument('--max-exhibits', type=int, default=10000, help='Select all current enumerator output by default; smaller cap records omissions')
    parser.add_argument('--max-tasks', type=int, help='Optional per-stage task bound; immutable on resume')
    parser.add_argument('--resume', action='store_true')
    parser.add_argument('--execute', action='store_true', help='Acquire missing metadata and run history after offline preflight')
    args = parser.parse_args(argv)
    if '@' not in args.contact or not 0 < args.rate <= 2:
        parser.error('A contact email and a rate between 0 and 2 requests/s are required')
    if args.max_exhibits < 0 or (args.max_tasks is not None and args.max_tasks < 1):
        parser.error('Exhibit cap must be nonnegative and task cap positive')
    output = args.output.resolve()
    source_database = (args.source_database or args.source_broker/'broker.sqlite').resolve()
    originals = [args.metadata, args.universe, args.plan, args.source_broker, source_database]
    if any(path.resolve().is_relative_to(output) for path in originals) or output == args.new_project_root.resolve():
        parser.error('Derived output must be separate from retained originals and their project root')
    if (output/'checkpoint.json').exists() and not args.resume:
        parser.error('Existing checkpoint requires --resume')
    if args.resume and not (output/'checkpoint.json').exists():
        parser.error('--resume requires an existing checkpoint')
    # No collection-script import or broker mutation precedes frozen input checks.
    frozen = frozen_inputs(args.universe, args.plan)
    metadata_hash = file_hash(args.metadata)
    if args.metadata_sha256 and args.metadata_sha256 != metadata_hash:
        raise ValueError('Original metadata hash differs from the supplied immutable input hash')
    config = {'input_hashes': dict(frozen['input_hashes'], metadata=metadata_hash,
                                 broker_database=file_hash(source_database)),
              'old_project_root': args.old_project_root, 'new_project_root': str(args.new_project_root.resolve()),
              'source_broker': str(args.source_broker.resolve()), 'source_database': str(source_database),
              'metadata': str(args.metadata.resolve()), 'universe': str(args.universe.resolve()), 'plan': str(args.plan.resolve()),
              'output': str(output), 'contact': args.contact, 'rate': args.rate,
              'start_date': START_DATE, 'end_date': END_DATE, 'opening_context': '2022/2023 when available',
              'max_exhibits': args.max_exhibits, 'max_tasks': args.max_tasks,
              'batches': frozen['batches'], 'exhibit_enumeration_cap': 10000,
              'implementation_hashes': {str(path.relative_to(ROOT)): file_hash(path) for path in (
                  ROOT/'src/reit_history_remote.py', Path(__file__).resolve(),
                  ROOT/'scripts/collect_reit_history.py', ROOT/'src/reit_inventory.py', ROOT/'src/reit_acquisition.py')}}
    state = checkpoint(output, config)
    migration = validate_prepared_resume(output, state) if args.resume else None
    metadata, status = prepare_metadata(load_json(args.metadata), frozen['ciks'],
                                       old_root=args.old_project_root, new_root=args.new_project_root)
    save_json(output/'metadata_status.json', status)
    save_json(output/'metadata.json', {'metadata': metadata})
    if migration is None:
        migration = migrate_broker(args.source_broker, output/'broker', contact=args.contact,
                                  rate=args.rate, source_database=source_database)
        save_json(output/'cache_migration.json', migration)
        state['preparation_status'] = 'prepared'
        state['migration_sha256'] = file_hash(output/'cache_migration.json')
        save_json(output/'checkpoint.json', state)
    if args.execute:
        broker = FetchBroker(output/'broker', contact_email=args.contact, rate=args.rate)
        metadata = complete_metadata(metadata, frozen['ciks'], broker, output/'metadata_status.json')
        from scripts.collect_reit_history import history_stage
        run_batches(metadata, frozen, output, broker, state, history_stage=history_stage,
                    max_exhibits=args.max_exhibits, limit=args.max_tasks)
    summary = {'mode': 'execute' if args.execute else 'prepared_offline', 'issuers': len(frozen['ciks']),
               'batches': len(frozen['batches']), 'verified_cache_urls': migration['verified_count'],
               'unavailable_cache_urls': len(migration['unavailable']),
               'pending_metadata_pages_or_issuers': len(load_json(output/'metadata_status.json')['pending']),
               'completed_batches': state['completed_batches'], 'history_complete': False,
               'output': str(output)}
    save_json(output/'run_summary.json', summary)
    print(json.dumps(summary), flush=True)
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
