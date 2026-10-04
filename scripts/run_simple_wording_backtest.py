"""One-command, bounded wording pilot controller.

Engineering mode uses pinned FABRICATED quotes and candidate evidence only.
Qualified mode consumes the independent intake report. Neither mode reports
empirical alpha, Sharpe, win rate or an economic headline.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path, PureWindowsPath
import re
import sys

if __package__ in (None, ''):
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

WORKFLOW_PATH = 'configs/simple_wording_workflow-v1.json'
WORKFLOW_SHA256 = 'b71cd3d28e1918f776c6a4cf0354b20d58d8193910f74fadba0cfba7d604c75c'
PROTOCOL_PATH = 'configs/wording_equity_pilot-v2.json'
PROTOCOL_SHA256 = 'e7197cea447fe9e413fe659b4ab2bdd41468e6cdb4933d7f82fb4560bab78acb'
CALENDAR_PATH = 'configs/wording_equity_calendar-2024-v1.json'
CALENDAR_SHA256 = '0f9781d31c384a8ef9b74a3e68eaa1de57f1708cc627839f247ba5ccd6016c53'
HEX64 = re.compile(r'[0-9a-f]{64}\Z')


def _sha(data):
    return hashlib.sha256(data).hexdigest()


def _json_bytes(value):
    return (json.dumps(value, sort_keys=True, indent=2, allow_nan=False)+'\n').encode('utf-8')


def _contained(root, relative, *, must_exist=True):
    if (not isinstance(relative, str) or not relative or '\\' in relative or
        PureWindowsPath(relative).is_absolute() or PureWindowsPath(relative).drive or
        Path(relative).is_absolute() or
        any(part in ('', '.', '..') for part in relative.split('/'))):
        raise ValueError('root_relative_path_required')
    target = root/relative
    if not target.resolve().is_relative_to(root):
        raise ValueError('path_outside_root')
    cursor = root
    for part in relative.split('/'):
        cursor = cursor/part
        if cursor.is_symlink():
            raise ValueError('symlink_path_refused')
    if must_exist and not target.is_file():
        raise ValueError('regular_input_file_required')
    return target


def _read_pinned(root, descriptor):
    if (not isinstance(descriptor, dict) or not isinstance(descriptor.get('sha256'), str) or
        not HEX64.fullmatch(descriptor['sha256'])):
        raise ValueError('sha256_descriptor_required')
    path = _contained(root, descriptor.get('path'))
    data = path.read_bytes()
    if _sha(data) != descriptor['sha256']:
        raise ValueError('input_hash_mismatch:' + descriptor['path'])
    return data


def _load_json(data, label):
    try:
        return json.loads(data.decode('utf-8'),
            parse_constant=lambda _: (_ for _ in ()).throw(ValueError('nonfinite_json')))
    except (UnicodeError, json.JSONDecodeError) as exc:
        raise ValueError('invalid_json:' + label) from exc


def _transport_reader(root, mapping):
    """Read only exact original-path/SHA pairs mapped to pinned local files."""
    if not isinstance(mapping, dict) or mapping.get('schema_version') != 'wording-artifact-transport-map-v1' or not isinstance(mapping.get('entries'), list):
        raise ValueError('transport_map_schema_required')
    table = {}
    for row in mapping['entries']:
        if (not isinstance(row, dict) or not isinstance(row.get('original_path'), str) or
            not row['original_path'] or not isinstance(row.get('sha256'), str) or
            not HEX64.fullmatch(row['sha256'])):
            raise ValueError('transport_entry_required')
        key = (row['original_path'], row['sha256'])
        if key in table:
            raise ValueError('duplicate_transport_entry')
        local = _contained(root, row.get('local_path'))
        if _sha(local.read_bytes()) != row['sha256']:
            raise ValueError('transport_hash_mismatch')
        table[key] = row['local_path']

    def read_artifact(descriptor):
        if not isinstance(descriptor, dict):
            raise ValueError('artifact_descriptor_required')
        key = (descriptor.get('path'), descriptor.get('sha256'))
        if key not in table:
            raise ValueError('unmapped_artifact')
        local = _contained(root, table[key])
        data = local.read_bytes()
        if _sha(data) != key[1]:
            raise ValueError('artifact_hash_mismatch')
        return data

    return read_artifact


def _tracked_file(root, relative, expected=None):
    path = _contained(root, relative)
    actual = _sha(path.read_bytes())
    if expected is not None and actual != expected:
        raise ValueError('input_hash_mismatch:' + relative)
    return actual


def _pairs(path, sha, label):
    if (path is None) != (sha is None):
        raise ValueError(label + '_path_and_sha_required')
    if path is None:
        return None
    return {'path': path, 'sha256': sha}


def run_simple_wording_backtest(root, mode, *, output_dir,
                               packet_path=None, packet_sha256=None,
                               market_path=None, market_sha256=None,
                               approval_path=None, approval_sha256=None,
                               transport_map_path=None, transport_map_sha256=None):
    """Run one pinned contract trial with no economic headline promotion."""
    root = Path(root).resolve(strict=True)
    if mode not in ('engineering', 'qualified'):
        raise ValueError('unsupported_mode')
    if not isinstance(output_dir, str):
        raise ValueError('root_relative_output_required')
    output = _contained(root, output_dir, must_exist=False)
    if output.exists() or output == root:
        raise ValueError('fresh_output_directory_required')
    workflow_desc = {'path': WORKFLOW_PATH, 'sha256': WORKFLOW_SHA256}
    workflow = _load_json(_read_pinned(root, workflow_desc), 'workflow')
    if (workflow.get('schema_version') != 'simple-wording-workflow-v1' or
        workflow.get('max_trials') != 1 or
        workflow.get('protocol') != {'path': PROTOCOL_PATH, 'sha256': PROTOCOL_SHA256} or
        workflow.get('calendar') != {'path': CALENDAR_PATH, 'sha256': CALENDAR_SHA256}):
        raise ValueError('workflow_pin_mismatch')
    protocol = _load_json(_read_pinned(root, workflow['protocol']), 'protocol')
    calendar = _load_json(_read_pinned(root, workflow['calendar']), 'calendar')
    from src.research_validation.wording_equity_pilot import (
        replay_wording_pilot, validate_pilot_calendar)
    from src.research_validation.marked_account import export_marked_account_panel
    from src.research_validation.trials import (
        config_hash, finish_trial, freeze_experiment, start_trial)
    validate_pilot_calendar(calendar, protocol)
    tracked = {WORKFLOW_PATH: WORKFLOW_SHA256,
               PROTOCOL_PATH: PROTOCOL_SHA256, CALENDAR_PATH: CALENDAR_SHA256}
    code_hashes = {}
    for name in workflow['code_paths']:
        code_hashes[name] = _tracked_file(root, name)
        tracked[name] = code_hashes[name]
    descriptions = {}
    intake = None
    approval_receipt_pins = None
    if mode == 'engineering':
        if any(value is not None for value in (packet_path, packet_sha256,
               market_path, market_sha256, approval_path, approval_sha256,
               transport_map_path, transport_map_sha256)):
            raise ValueError('engineering_mode_uses_only_pinned_fixture')
        fixture_desc = workflow['mode_policy']['engineering']['fixture']
        fixture = _load_json(_read_pinned(root, fixture_desc), 'engineering_fixture')
        if (fixture.get('schema_version') != 'wording-equity-engineering-fixture-v1' or
            fixture.get('synthetic_fixture_id') != 'wording_equity_engineering-v1' or
            fixture.get('synthetic') is not True):
            raise ValueError('explicit_synthetic_fixture_required')
        tracked[fixture_desc['path']] = fixture_desc['sha256']
        descriptions['fixture'] = fixture_desc
        candidates, quotes = fixture['candidates'], fixture['quotes']
    else:
        if packet_path is None or packet_sha256 is None:
            raise ValueError('qualified_packet_and_sha_required')
        descriptors = {
            'packet': _pairs(packet_path, packet_sha256, 'packet'),
            'market': _pairs(market_path, market_sha256, 'market'),
            'approval': _pairs(approval_path, approval_sha256, 'approval'),
            'transport_map': _pairs(transport_map_path, transport_map_sha256, 'transport_map'),
        }
        if descriptors['approval'] and not descriptors['transport_map']:
            raise ValueError('approval_requires_transport_map')
        payloads = {}
        for key, item in descriptors.items():
            if item is not None:
                if item['path'] in tracked:
                    raise ValueError('duplicate_input_path')
                data = _read_pinned(root, item)
                payloads[key] = _load_json(data, key)
                tracked[item['path']] = item['sha256']
                descriptions[key] = item
            else:
                payloads[key] = None
        packet = payloads['packet']
        if not isinstance(packet, dict) or packet.get('schema_version') != workflow['mode_policy']['qualified']['producer_schema']:
            raise ValueError('unsupported_producer_packet_schema')
        if payloads['market'] is not None and payloads['market'].get('schema_version') != workflow['mode_policy']['qualified']['market_schema']:
            raise ValueError('unsupported_market_packet_schema')
        if payloads['approval'] is not None and payloads['approval'].get('schema_version') != workflow['mode_policy']['qualified']['approval_schema']:
            raise ValueError('unsupported_approval_receipt_schema')
        if payloads['approval'] is not None:
            from src.research_validation.pilot_intake import canonical_sha256
            approval_receipt_pins = {
                'byte_sha256': approval_sha256,
                'canonical_sha256': canonical_sha256(payloads['approval']),
            }
        if payloads['transport_map'] is None:
            def read_artifact(_descriptor):
                raise ValueError('unmapped_artifact')
        else:
            read_artifact = _transport_reader(root, payloads['transport_map'])
            for item in payloads['transport_map']['entries']:
                tracked[item['local_path']] = item['sha256']
    if any(_contained(root, name).is_relative_to(output) for name in tracked):
        raise ValueError('output_overlaps_input')
    trial_config = {
        'experiment_id': 'simple-wording-workflow-v1-' + mode,
        'horizon_id': protocol['horizon_id'], 'max_trials': 1,
        'holdout_id': None, 'final_test_enabled': False,
        'protocol_hash': PROTOCOL_SHA256,
        'data_hash': config_hash({'descriptors': descriptions,
                                  'approval_receipt_pins': approval_receipt_pins}),
        'approval_receipt_pins': approval_receipt_pins,
        'code_hash': config_hash(code_hashes),
        'mode': mode,
    }
    output.mkdir(parents=True, exist_ok=False)
    ledger_path = output/'trials.jsonl'
    freeze_experiment(ledger_path, trial_config)
    start_trial(ledger_path, trial_config, mode+'-1')
    try:
        if mode == 'qualified':
            from src.research_validation.pilot_intake import inspect_pilot_intake
            intake_result = inspect_pilot_intake(
                packet, payloads['market'], payloads['approval'],
                expected_approval_sha256=(approval_receipt_pins['canonical_sha256']
                    if approval_receipt_pins else None),
                protocol=protocol, calendar=calendar, read_artifact=read_artifact)
            intake = intake_result['report']
            approved_for_contract = (intake.get('status') == 'qualified_for_replay' and
                                     intake.get('synthetic_test_scope') is False)
            candidates = intake_result['candidates'] if approved_for_contract else []
            quotes = intake_result['quote_rows'] if approved_for_contract else []
        replay = replay_wording_pilot(candidates, quotes, calendar, protocol)
        if mode == 'engineering':
            replay['synthetic_fixture_id'] = 'wording_equity_engineering-v1'
        panel_scope = 'synthetic_engineering' if mode == 'engineering' else 'contract_only'
        panels = {arm: export_marked_account_panel(replay, calendar, protocol,
                          arm=arm, scope=panel_scope)
                  for arm in ('wording', 'baseline')}
        for name, expected in tracked.items():
            _tracked_file(root, name, expected)
        if mode == 'engineering':
            status = ('synthetic_contract_only' if replay['status'] == 'contract_replayed'
                      else 'insufficient')
            label = 'SYNTHETIC FABRICATED ENGINEERING ONLY; NO ALPHA OR PERFORMANCE HEADLINE'
        else:
            status = 'insufficient'
            label = 'QUALIFIED-ONLY INTAKE; ECONOMIC HEADLINES WITHHELD'
        report = {
            'schema_version': 'simple-wording-workflow-report-v1',
            'status': status, 'mode': mode, 'label': label,
            'canonical_economic_qualified': False, 'headline_eligible': False,
            'wording_pnl': None, 'baseline_pnl': None,
            'wording_sharpe': None, 'baseline_sharpe': None,
            'wording_win_rate': None, 'baseline_win_rate': None,
            'confidence_interval': None, 'edge_claim': None,
            'intake': intake, 'replay_status': replay['status'],
            'assessment': {'received': replay['assessment']['received'],
                           'eligible_count': len(replay['assessment']['eligible']),
                           'excluded': replay['assessment']['excluded']},
            'panels': panels, 'input_descriptors': descriptions,
            'approval_receipt_pins': approval_receipt_pins,
            'input_hashes': tracked, 'code_hashes': code_hashes,
            'workflow_sha256': WORKFLOW_SHA256,
            'trial_outcome': 'insufficient',
            'training_performed': False, 'protected_test_accessed': False,
        }
        panel_files = {}
        for arm in ('wording', 'baseline'):
            path = output/('panel_'+arm+'.json')
            path.write_bytes(_json_bytes(panels[arm]))
            panel_files[path.name] = _sha(path.read_bytes())
        finish_trial(ledger_path, trial_config,
                     {'trial_id': mode+'-1', 'outcome': 'insufficient',
                      'contract_status': replay['status']})
        report['artifacts'] = {**panel_files, 'trials.jsonl': _sha(ledger_path.read_bytes())}
        (output/'report.json').write_bytes(_json_bytes(report))
        return report
    except Exception as exc:
        try:
            finish_trial(ledger_path, trial_config,
                         {'trial_id': mode+'-1', 'outcome': 'failed',
                          'failure_reason': type(exc).__name__+':'+str(exc)})
        except ValueError:
            pass
        raise


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root', default=str(Path(__file__).resolve().parents[1]))
    parser.add_argument('--mode', required=True, choices=('engineering','qualified'))
    parser.add_argument('--output-dir', required=True)
    parser.add_argument('--packet')
    parser.add_argument('--packet-sha256')
    parser.add_argument('--market')
    parser.add_argument('--market-sha256')
    parser.add_argument('--approval')
    parser.add_argument('--approval-sha256')
    parser.add_argument('--transport-map')
    parser.add_argument('--transport-map-sha256')
    args = parser.parse_args(argv)
    report = run_simple_wording_backtest(
        args.root, args.mode, output_dir=args.output_dir,
        packet_path=args.packet, packet_sha256=args.packet_sha256,
        market_path=args.market, market_sha256=args.market_sha256,
        approval_path=args.approval, approval_sha256=args.approval_sha256,
        transport_map_path=args.transport_map,
        transport_map_sha256=args.transport_map_sha256)
    print(json.dumps({'status':report['status'], 'mode':report['mode'],
                      'output_dir':args.output_dir, 'headline_eligible':False},
                     sort_keys=True))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())