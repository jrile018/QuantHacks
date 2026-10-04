import hashlib
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from scripts import run_document_batch as batch
from scripts import export_ocr_training_pairs as pairs
from hpc import submit_document_job as launch

class BatchTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.addCleanup(self.temp.cleanup)

    def manifest(self,records):
        path = self.root/'inputs.jsonl'
        path.write_text(''.join(json.dumps(r)+'\n' for r in records),encoding='utf8')
        return path

    def reviewed(self,split,company,date,doc):
        image = self.root/(doc+'.png')
        image.write_bytes(b'image '+doc.encode())
        source = self.root/(doc+'.pdf')
        source.write_bytes(b'source '+doc.encode())
        return dict(document_id=doc,company_id=company,public_at_utc=date,split=split,image_path=str(image),source_path=str(source),source_sha256=hashlib.sha256(source.read_bytes()).hexdigest(),transcript='Reviewed loss (10), not growth.',annotation_status='human_reviewed',annotator='researcher',rubric_revision='ocr_transcript_v1',page_number=1)

    def test_resumes_hash_and_rejects_changed_artifact(self):
        source = self.root/'one.txt'
        source.write_text('Revenue did not rise (-10).')
        records = self.manifest([dict(document_id='one',source_path=str(source))])
        output = self.root/'out'
        self.assertEqual(batch.run_batch(records,output,{'engine':'native'})['completed'],1)
        self.assertEqual(batch.run_batch(records,output,{'engine':'native'})['skipped'],1)
        completed = json.loads((output/'manifest.jsonl').read_text().splitlines()[0])
        Path(completed['output_path']).write_text('tampered')
        self.assertEqual(batch.run_batch(records,output,{'engine':'native'})['failed'],1)

    def test_failures_do_not_stop_batch(self):
        source = self.root/'good.txt'
        source.write_text('Net loss was (10).')
        records = self.manifest([dict(document_id='missing',source_path='absent.txt'),dict(document_id='hash',source_path=str(source),source_sha256='0'*64),dict(document_id='good',source_path=str(source))])
        self.assertEqual(batch.run_batch(records,self.root/'out',{'engine':'native'}),dict(completed=1,failed=2,skipped=0,records=3))

    def test_empty_manifest_and_torn_journal_rejected(self):
        with self.assertRaisesRegex(ValueError,'empty'):
            batch.run_batch(self.manifest([]),self.root/'out',{'engine':'native'})
        output = self.root/'out'
        output.mkdir(exist_ok=True)
        (output/'manifest.jsonl').write_text('{"broken":')
        source = self.root/'one.txt'
        source.write_text('one')
        with self.assertRaisesRegex(ValueError,'journal'):
            batch.run_batch(self.manifest([dict(document_id='one',source_path=str(source))]),output,{'engine':'native'})

    def test_config_change_does_not_reuse(self):
        source = self.root/'one.txt'
        source.write_text('one')
        records = self.manifest([dict(document_id='one',source_path=str(source))])
        batch.run_batch(records,self.root/'out',dict(engine='native',dpi=200))
        self.assertEqual(batch.run_batch(records,self.root/'out',dict(engine='native',dpi=300))['completed'],1)

    def test_input_metadata_change_creates_new_lineage_record(self):
        source = self.root/'one.txt'
        source.write_text('Revenue declined.')
        first = dict(document_id='one',source_path=str(source),company_id='issuer-A',public_at_utc='2020-01-01T00:00:00Z')
        records = self.manifest([first])
        output = self.root/'out'
        batch.run_batch(records,output,dict(engine='native'))
        records = self.manifest([{**first,'company_id':'issuer-B','public_at_utc':'2021-01-01T00:00:00Z'}])
        self.assertEqual(batch.run_batch(records,output,dict(engine='native'))['completed'],1)
        entries = [json.loads(line) for line in (output/'manifest.jsonl').read_text().splitlines()]
        self.assertEqual(len(entries),2)
        self.assertNotEqual(entries[0]['resume_key'],entries[1]['resume_key'])
        self.assertEqual(entries[1]['input_record']['company_id'],'issuer-B')

    def test_glm_html_stays_native(self):
        source = self.root/'one.html'
        source.write_text('<p>Net loss was not reduced.</p>')
        config = dict(engine='glm',model_revision='2e85a62840ccac27daa451df36c736c4636b8628',model_cache=str(self.root))
        with patch('src.glm_document_ocr.GLMOCRProvider.recognize',side_effect=AssertionError('GPU not allowed')):
            result = batch.run_batch(self.manifest([dict(document_id='one',source_path=str(source))]),self.root/'out',config)
        self.assertEqual(result['completed'],1)

    def test_export_sharegpt_hashes(self):
        records = [self.reviewed('train','A','2020-01-01T00:00:00Z','train'),self.reviewed('validation','B','2021-01-01T00:00:00Z','val')]
        report = pairs.export_pairs(self.manifest(records),self.root/'dataset')
        rows = json.loads((self.root/'dataset/train.json').read_text())
        self.assertEqual(rows[0]['messages'][0]['content'],'<image>Text Recognition:')
        self.assertEqual(rows[0]['messages'][1]['content'],records[0]['transcript'])
        self.assertEqual(report['counts'],dict(train=1,validation=1))
        provenance = json.loads((self.root/'dataset/provenance.json').read_text())
        self.assertEqual(provenance['records'][0]['source_sha256'],records[0]['source_sha256'])
        self.assertEqual(len(provenance['records'][0]['image_sha256']),64)

    def test_export_rejects_unreviewed_and_leakage(self):
        for field,value in [('annotation_status','machine_unreviewed'),('company_id','A'),('public_at_utc','2019-01-01T00:00:00Z'),('document_id','train')]:
            with self.subTest(field=field):
                train = self.reviewed('train','A','2020-01-01T00:00:00Z','train')
                val = self.reviewed('validation','B','2021-01-01T00:00:00Z','val')
                val[field] = value
                with self.assertRaises(ValueError):
                    pairs.export_pairs(self.manifest([train,val]),self.root/'dataset')
                self.assertFalse((self.root/'dataset/train.json').exists())

    def test_slurm_requires_allocation(self):
        source = self.root/'source.png'
        source.write_bytes(b'fake')
        records = self.manifest([dict(document_id='one',source_path=str(source))])
        config = dict(account='actual-account',qos='actual-qos',partition='actual-partition',gres='gpu:1',cpus_per_task=2,memory='8G',time='00:10:00',workdir=str(self.root),python='/env/bin/python',output_dir=str(self.root/'outputs'),model_cache='/models',model_revision='2e85a62840ccac27daa451df36c736c4636b8628',dtype='bfloat16',environment_script='/env/activate.sh')
        command = launch.build_command(config,records,mode='ocr')
        self.assertIn('--account=actual-account',command)
        self.assertIn(str(records.resolve()),command)
        self.assertIn('--gres=gpu:1',command)
        for key in ('account','qos','workdir','model_revision','environment_script'):
            with self.subTest(key=key),self.assertRaises(ValueError):
                launch.build_command({**config,key:''},records,mode='ocr')

    def test_multiple_pages_same_document_allowed(self):
        first = self.reviewed('train','A','2020-01-01T00:00:00Z','train')
        second = {**first,'page_number':2}
        val = self.reviewed('validation','B','2021-01-01T00:00:00Z','val')
        report = pairs.export_pairs(self.manifest([first,second,val]),self.root/'dataset')
        self.assertEqual(report['counts']['train'],2)

    def test_cli_path_configuration_is_json_serializable(self):
        source = self.root/'one.html'
        source.write_text('<p>Net loss was not reduced.</p>')
        config = dict(engine='glm',model_revision='2e85a62840ccac27daa451df36c736c4636b8628',model_cache=self.root)
        result = batch.run_batch(self.manifest([dict(document_id='one',source_path=str(source))]),self.root/'out',config)
        self.assertEqual(result['completed'],1)
        row = json.loads((self.root/'out/manifest.jsonl').read_text())
        self.assertEqual(row['config']['model_cache'],str(self.root))

    def test_lora_config_uses_reviewed_validation_and_local_checkpoint(self):
        from hpc.prepare_lora_config import prepare_config
        from types import SimpleNamespace
        from unittest.mock import Mock
        records = [self.reviewed('train','A','2020-01-01T00:00:00Z','train'),self.reviewed('validation','B','2021-01-01T00:00:00Z','val')]
        manifest = self.manifest(records)
        pairs.export_pairs(manifest,self.root/'dataset')
        snapshot = Mock(return_value='/local/pinned/snapshot')
        with patch.dict('sys.modules',{'huggingface_hub':SimpleNamespace(snapshot_download=snapshot)}):
            result = prepare_config(manifest,self.root/'dataset',self.root/'train-output','2e85a62840ccac27daa451df36c736c4636b8628',self.root/'cache')
        self.assertTrue(snapshot.call_args.kwargs['local_files_only'])
        self.assertEqual(snapshot.call_args.kwargs['allow_patterns'],
                         ['*.json', '*.safetensors', '*.jinja', '*.txt', '*.model'])
        self.assertEqual(result['model_name_or_path'],'/local/pinned/snapshot')
        self.assertEqual(result['eval_dataset'],'reviewed_ocr_validation')
        self.assertEqual(result['template'],'glm_ocr')
        self.assertFalse(result['overwrite_output_dir'])
        self.assertTrue((self.root/'train-output/training-provenance.json').is_file())
        self.assertTrue((self.root/'train-output/lora-config.yaml').is_file())
        (self.root/'dataset/train.json').write_text('[]')
        with self.assertRaisesRegex(ValueError,'artifact'):
            prepare_config(manifest,self.root/'dataset',self.root/'bad-output','2e85a62840ccac27daa451df36c736c4636b8628',self.root/'cache')

    def test_lora_rejects_existing_output_without_overwriting_provenance(self):
        from hpc.prepare_lora_config import prepare_config
        from types import SimpleNamespace
        from unittest.mock import Mock
        records = [self.reviewed('train','A','2020-01-01T00:00:00Z','train'),self.reviewed('validation','B','2021-01-01T00:00:00Z','val')]
        manifest = self.manifest(records)
        pairs.export_pairs(manifest,self.root/'dataset')
        output = self.root/'prior-training'
        (output/'adapter/checkpoint-1').mkdir(parents=True)
        original = b'{"original": "immutable provenance"}'
        (output/'training-provenance.json').write_bytes(original)
        (output/'lora-config.json').write_bytes(b'{"original": "immutable config"}')
        snapshot = Mock(return_value='/local/pinned/snapshot')
        with patch.dict('sys.modules',{'huggingface_hub':SimpleNamespace(snapshot_download=snapshot)}), self.assertRaisesRegex(ValueError,'fresh'):
            prepare_config(manifest,self.root/'dataset',output,'2e85a62840ccac27daa451df36c736c4636b8628',self.root/'cache')
        self.assertEqual((output/'training-provenance.json').read_bytes(),original)
        snapshot.assert_not_called()

    def test_lora_shell_uses_configured_interpreter_and_prepares_before_freeze(self):
        script = (Path(__file__).resolve().parents[1]/'hpc/document_lora.sbatch').read_text()
        self.assertIn('"$python_bin" -m llamafactory.cli train',script)
        self.assertLess(script.index('hpc/prepare_lora_config.py'),script.index('-m pip freeze'))

    def test_lora_launcher_keeps_slurm_log_outside_fresh_training_output(self):
        source = self.root/'source.png'
        source.write_bytes(b'fake')
        records = self.manifest([dict(document_id='one',source_path=str(source))])
        output = self.root/'fresh-training'
        config = dict(account='actual-account',qos='actual-qos',partition='actual-partition',gres='gpu:1',cpus_per_task=2,memory='8G',time='00:10:00',workdir=str(self.root),python='/env/bin/python',output_dir=str(output),model_cache='/models',model_revision='2e85a62840ccac27daa451df36c736c4636b8628',dtype='bfloat16',environment_script='/env/activate.sh',training_dataset_dir=str(self.root/'dataset'))
        command = launch.build_command(config,records,mode='lora')
        log_argument = next(arg for arg in command if arg.startswith('--output='))
        self.assertEqual(Path(log_argument.split('=',1)[1]).parent,output.parent)
        self.assertFalse(output.exists())

if __name__ == '__main__':
    unittest.main()
