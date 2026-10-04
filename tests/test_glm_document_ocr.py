import hashlib
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, MagicMock, patch
from src import glm_document_ocr as gpu
PIN = '2e85a62840ccac27daa451df36c736c4636b8628'

class GLMOCRTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.addCleanup(self.temp.cleanup)

    def test_validation(self):
        for kwargs in ({'model_revision':'main'}, {'device':'cpu'}, {'dtype':'float32'}):
            with self.subTest(kwargs=kwargs), self.assertRaises(ValueError):
                gpu.GLMConfig(**{**dict(model_revision=PIN,cache_dir=self.root),**kwargs})

    def test_native_pdf_never_loads_gpu(self):
        path = self.root/'native.pdf'
        path.write_bytes(b'fake PDF')
        provider = Mock(config=gpu.GLMConfig(PIN,self.root))
        with patch.object(gpu.ocr,'_native_pdf_texts',return_value=['revenue was not reduced -10']):
            result = gpu.extract_document(path,provider=provider)
        provider.recognize.assert_not_called()
        self.assertEqual(result.pages[0].method,'native_pdf_text')
        self.assertEqual(result.sha256,hashlib.sha256(path.read_bytes()).hexdigest())
        self.assertEqual(result.engine,'pdfium')

    def test_scanned_fallback_preserves_pages_confidence(self):
        path = self.root/'mixed.pdf'
        path.write_bytes(b'fake PDF')
        image = Mock(size=(100,200))
        provider = Mock(config=gpu.GLMConfig(PIN,self.root))
        provider.recognize.return_value = ('(10) loss, not growth',[])
        with patch.object(gpu.ocr,'_native_pdf_texts',return_value=['native first',None]), patch.object(gpu.ocr,'_page_images',return_value=iter([image])), patch.object(gpu.ocr,'_prepare_image',return_value=image):
            result = gpu.extract_document(path,provider=provider)
        self.assertEqual([p.number for p in result.pages],[1,2])
        self.assertIsNone(result.pages[1].confidence)
        self.assertEqual(result.pages[1].text,'(10) loss, not growth')
        self.assertEqual(result.settings['model_revision'],PIN)
        image.close.assert_called_once()

    def test_input_validation_precedes_provider(self):
        provider = Mock()
        with self.assertRaises(FileNotFoundError):
            gpu.extract_document(self.root/'absent.pdf',provider=provider)
        path = self.root/'bad.exe'
        path.write_bytes(b'bad')
        with self.assertRaises(ValueError):
            gpu.extract_document(path,provider=provider)
        provider.recognize.assert_not_called()

    def test_recipe_generated_token_slice(self):
        provider = gpu.GLMOCRProvider(gpu.GLMConfig(PIN,self.root,max_new_tokens=12))
        processor, model, torch = Mock(),Mock(),MagicMock()
        inputs = {'input_ids':SimpleNamespace(shape=(1,5)),
                  'pixel_values': SimpleNamespace(numel=lambda: 12),
                  'image_grid_thw': SimpleNamespace(numel=lambda: 3)}
        processor.apply_chat_template.return_value.to.return_value = inputs
        generated = MagicMock()
        generated.__getitem__.return_value = [1,2]
        model.generate.return_value = generated
        processor.decode.return_value = 'recognized'
        provider._model,provider._processor,provider._torch = model,processor,torch
        text,flags = provider.recognize(Mock())
        self.assertEqual(text,'recognized')
        generated.__getitem__.assert_called_once_with((0,slice(5,None)))
        model.generate.assert_called_once_with(**inputs,max_new_tokens=12,do_sample=False)

    def test_missing_image_data_never_reaches_generation(self):
        for images in ({}, {'pixel_values': None, 'image_grid_thw': None},
                       {'pixel_values': SimpleNamespace(numel=lambda: 0),
                        'image_grid_thw': SimpleNamespace(numel=lambda: 3)}):
            with self.subTest(images=images):
                provider = gpu.GLMOCRProvider(gpu.GLMConfig(PIN,self.root))
                provider._model, provider._processor, provider._torch = Mock(), Mock(), MagicMock()
                provider._model.generate.return_value = MagicMock()
                provider._processor.apply_chat_template.return_value.to.return_value = {
                    'input_ids': SimpleNamespace(shape=(1,13)), **images}
                with self.assertRaisesRegex(RuntimeError, 'image data'):
                    provider.recognize(Mock())
                provider._model.generate.assert_not_called()

    def test_lazy_load_pins_and_disallows_download(self):
        provider = gpu.GLMOCRProvider(gpu.GLMConfig(PIN,self.root))
        torch,processor_class,model_class = MagicMock(),Mock(),Mock()
        torch.cuda.is_available.return_value = True
        torch.cuda.is_bf16_supported.return_value = True
        snapshot = self.root / PIN
        snapshot.mkdir()
        (snapshot / 'processor_config.json').write_text('{}')
        resolver = Mock(return_value=str(snapshot))
        fake = SimpleNamespace(AutoProcessor=processor_class, Glm46VProcessor=processor_class,
                               GlmOcrForConditionalGeneration=model_class)
        with patch.dict('sys.modules',{'torch':torch,'transformers':fake,
                                      'huggingface_hub': SimpleNamespace(snapshot_download=resolver)}):
            provider._load()
        self.assertTrue(model_class.from_pretrained.call_args.kwargs['local_files_only'])
        self.assertEqual(resolver.call_args.kwargs['revision'], PIN)
        self.assertTrue(resolver.call_args.kwargs['local_files_only'])
        self.assertEqual(processor_class.from_pretrained.call_args.args, (str(snapshot),))
        self.assertEqual(model_class.from_pretrained.call_args.args, (str(snapshot),))
        self.assertFalse(processor_class.from_pretrained.call_args.kwargs['trust_remote_code'])
        model_class.from_pretrained.return_value.to.assert_called_once_with('cuda:0')

    def test_missing_processor_configuration_fails_before_weights(self):
        provider = gpu.GLMOCRProvider(gpu.GLMConfig(PIN,self.root))
        model = Mock()
        fake = SimpleNamespace(AutoProcessor=Mock(), Glm46VProcessor=Mock(),
                               GlmOcrForConditionalGeneration=model)
        with patch.dict('sys.modules', {'torch': MagicMock(), 'transformers': fake,
             'huggingface_hub': SimpleNamespace(snapshot_download=Mock(return_value=str(self.root)))}):
            with self.assertRaisesRegex(RuntimeError, 'processor_config.json'):
                provider._load()
        model.from_pretrained.assert_not_called()

    def test_source_mutation_rejected(self):
        path = self.root/'source.png'
        path.write_bytes(b'original')
        provider = Mock(config=gpu.GLMConfig(PIN,self.root))
        def recognize(_):
            path.write_bytes(b'changed')
            return 'text',[]
        provider.recognize.side_effect = recognize
        with patch.object(gpu.ocr,'_page_images',return_value=iter([Mock(size=(10,10))])), patch.object(gpu.ocr,'_prepare_image'), self.assertRaises(RuntimeError):
            gpu.extract_document(path,provider=provider)

if __name__ == '__main__':
    unittest.main()
