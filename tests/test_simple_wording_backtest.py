import hashlib
import json
import shutil
import tempfile
import unittest
from pathlib import Path

from scripts.run_simple_wording_backtest import run_simple_wording_backtest, _transport_reader
from src.research_validation.trials import read_ledger

SOURCE = Path(__file__).resolve().parents[1]


def digest(data):
    return hashlib.sha256(data).hexdigest()


class SimpleWorkflowTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        config = json.loads((SOURCE/'configs/simple_wording_workflow-v1.json').read_text())
        paths = ['configs/simple_wording_workflow-v1.json',
                 config['protocol']['path'], config['calendar']['path'],
                 config['mode_policy']['engineering']['fixture']['path'],
                 *config['code_paths']]
        for name in paths:
            original = SOURCE/name
            if original.is_file():
                target = self.root/name
                target.parent.mkdir(parents=True,exist_ok=True)
                shutil.copy2(original,target)
        self.fixture = self.root/config['mode_policy']['engineering']['fixture']['path']

    def test_one_command_engineering_is_obviously_synthetic(self):
        report=run_simple_wording_backtest(self.root,'engineering',output_dir='results/one')
        self.assertEqual(report['status'],'synthetic_contract_only')
        self.assertFalse(report['canonical_economic_qualified'])
        self.assertIsNone(report['wording_pnl'])
        self.assertIsNone(report['wording_sharpe'])
        self.assertIn('SYNTHETIC',report['label'])
        self.assertEqual(len(report['panels']['wording']['panel']['rows']),252)
        self.assertEqual(report['replay_status'],'contract_replayed')
        self.assertEqual(report['assessment']['eligible_count'],3)
        self.assertEqual(report['panels']['wording']['panel']['status'],'contract_exported')
        self.assertEqual(report['panels']['baseline']['panel']['status'],'contract_exported')
        self.assertEqual(report['panels']['wording']['panel']['scope'],'synthetic_engineering')
        self.assertEqual(report['panels']['wording']['probe_args']['reference_returns'],[0.0]*252)
        self.assertEqual([r['kind'] for r in read_ledger(self.root/'results/one/trials.jsonl')],
                         ['freeze','trial_start','trial_result'])
        written=json.loads((self.root/'results/one/report.json').read_text())
        self.assertEqual(written['status'],report['status'])

    def test_changed_fixture_and_wrong_mode_refused_before_output(self):
        self.fixture.write_bytes(self.fixture.read_bytes()+b' ')
        with self.assertRaises(ValueError):
            run_simple_wording_backtest(self.root,'engineering',output_dir='results/tampered')
        self.assertFalse((self.root/'results/tampered').exists())
        with self.assertRaises(ValueError):
            run_simple_wording_backtest(self.root,'bogus',output_dir='results/mode')
        with self.assertRaisesRegex(ValueError,'engineering_mode_uses_only_pinned_fixture'):
            run_simple_wording_backtest(self.root,'engineering',output_dir='results/wrong-mode',
                packet_path='data/producer.json',packet_sha256='0'*64)
        with self.assertRaises(ValueError):
            run_simple_wording_backtest(self.root,'qualified',output_dir='results/qualified')

    def test_fresh_output_only_and_root_path_guards(self):
        run_simple_wording_backtest(self.root,'engineering',output_dir='results/one')
        with self.assertRaises(ValueError):
            run_simple_wording_backtest(self.root,'engineering',output_dir='results/one')
        with self.assertRaises(ValueError):
            run_simple_wording_backtest(self.root,'engineering',output_dir='../outside')
        with self.assertRaises(ValueError):
            run_simple_wording_backtest(self.root,'engineering',output_dir=str(self.root/'absolute'))

    def test_transport_requires_exact_descriptor_mapping_and_bytes(self):
        artifact=b'local synthetic artifact'
        local=self.root/'data/proof.bin'
        local.parent.mkdir(parents=True,exist_ok=True)
        local.write_bytes(artifact)
        original={'path':'originals/source.pdf','sha256':digest(artifact)}
        reader=_transport_reader(self.root, {'schema_version':'wording-artifact-transport-map-v1',
            'entries':[{'original_path':original['path'],'sha256':original['sha256'],
                        'local_path':'data/proof.bin'}]})
        self.assertEqual(reader(original),artifact)
        with self.assertRaises(ValueError):
            reader({'path':'alias/source.pdf','sha256':original['sha256']})
        local.write_bytes(b'changed')
        with self.assertRaises(ValueError):
            reader(original)

    def test_qualified_unapproved_packet_yields_null_headlines(self):
        packet={'schema_version':'wording-equity-pilot-producer-packet-v1',
                'candidate_rows':[]}
        data=(json.dumps(packet,sort_keys=True)+'\n').encode()
        path=self.root/'data/producer.json'
        path.parent.mkdir(parents=True,exist_ok=True)
        path.write_bytes(data)
        report=run_simple_wording_backtest(self.root,'qualified',
            packet_path='data/producer.json',packet_sha256=digest(data),
            output_dir='results/unapproved')
        self.assertEqual(report['status'],'insufficient')
        self.assertIsNone(report['wording_pnl'])
        self.assertFalse(report['panels']['wording']['probe_args']['timing_verified'])
        self.assertFalse(report['panels']['wording']['probe_args']['marks_complete'])
        self.assertEqual(report['intake']['status'],'insufficient')

    def test_input_changed_during_run_records_failed_trial(self):
        from unittest import mock
        import src.research_validation.wording_equity_pilot as bridge
        original=bridge.replay_wording_pilot
        def mutate_then_replay(*args,**kwargs):
            replay=original(*args,**kwargs)
            self.fixture.write_bytes(self.fixture.read_bytes()+b' ')
            return replay
        with mock.patch.object(bridge,'replay_wording_pilot',side_effect=mutate_then_replay):
            with self.assertRaises(ValueError):
                run_simple_wording_backtest(self.root,'engineering',output_dir='results/changed')
        rows=read_ledger(self.root/'results/changed/trials.jsonl')
        self.assertEqual(rows[-1]['kind'],'trial_result')
        self.assertEqual(rows[-1]['trial']['outcome'],'failed')
        self.assertFalse((self.root/'results/changed/report.json').exists())

    def test_cli_one_command_uses_root_relative_output(self):
        import subprocess
        import sys
        result=subprocess.run([sys.executable,'-B',str(SOURCE/'scripts/run_simple_wording_backtest.py'),
            '--root',str(self.root),'--mode','engineering','--output-dir','results/cli'],
            capture_output=True,text=True,timeout=30)
        self.assertEqual(result.returncode,0,result.stderr)
        summary=json.loads(result.stdout)
        self.assertEqual(summary['status'],'synthetic_contract_only')
        self.assertFalse(summary['headline_eligible'])
        self.assertTrue((self.root/'results/cli/report.json').is_file())
    def test_packet_cannot_alias_pinned_config_or_code_path(self):
        sha=digest((self.root/'configs/wording_equity_pilot-v2.json').read_bytes())
        with self.assertRaisesRegex(ValueError,'duplicate_input_path'):
            run_simple_wording_backtest(self.root,'qualified',
                packet_path='configs/wording_equity_pilot-v2.json',packet_sha256=sha,
                output_dir='results/alias')


    def test_receipt_byte_pin_and_canonical_intake_digest_are_distinct(self):
        from unittest import mock
        import src.research_validation.pilot_intake as intake_module
        packet={'schema_version':'wording-equity-pilot-producer-packet-v1','candidate_rows':[]}
        market={'schema_version':'pilot-market-packet-v1','artifacts':{}}
        approval={'schema_version':'pilot-reviewed-evidence-receipt-v1',
                  'proof_scope':'real_historical','reviewer':'synthetic-spy'}
        transport={'schema_version':'wording-artifact-transport-map-v1','entries':[]}
        descriptors={}
        for name,value in (('packet',packet),('market',market),('approval',approval),('transport',transport)):
            data=(json.dumps(value,sort_keys=True,indent=2)+'\n').encode()
            path=self.root/('data/'+name+'.json')
            path.parent.mkdir(parents=True,exist_ok=True)
            path.write_bytes(data)
            descriptors[name]=(str(path.relative_to(self.root)).replace('\\','/'),digest(data))
        self.assertNotEqual(descriptors['approval'][1],intake_module.canonical_sha256(approval))
        observed=[]
        def spy(_packet,_market,_approval,**kwargs):
            observed.append(kwargs['expected_approval_sha256'])
            return {'report':{'status':'insufficient','exclusions':[]},
                    'candidates':[],'quote_rows':[]}
        with mock.patch.object(intake_module,'inspect_pilot_intake',side_effect=spy):
            report=run_simple_wording_backtest(self.root,'qualified',
                output_dir='results/receipt',
                packet_path=descriptors['packet'][0],packet_sha256=descriptors['packet'][1],
                market_path=descriptors['market'][0],market_sha256=descriptors['market'][1],
                approval_path=descriptors['approval'][0],approval_sha256=descriptors['approval'][1],
                transport_map_path=descriptors['transport'][0],
                transport_map_sha256=descriptors['transport'][1])
        canonical=intake_module.canonical_sha256(approval)
        self.assertEqual(observed,[canonical])
        self.assertEqual(report['approval_receipt_pins'],
                         {'byte_sha256':descriptors['approval'][1],
                          'canonical_sha256':canonical})
        frozen=read_ledger(self.root/'results/receipt/trials.jsonl')[0]['frozen_config']
        self.assertEqual(frozen['approval_receipt_pins'],report['approval_receipt_pins'])
