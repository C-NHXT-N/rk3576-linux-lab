# SPDX-License-Identifier: AGPL-3.0-only
from pathlib import Path
from types import SimpleNamespace
import json
from itertools import product
import sys
import tempfile
import time
import unittest
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1]/'projects/04-rknn-vision'))
try:
    import cv2
    import numpy as np
    import detector
    import fast_bench as fast
except ImportError:
    cv2 = None


class Runtime:
    def __init__(self, delay=0, fail=False):
        self.delay, self.fail = delay, fail

    def inference(self, inputs, **kwargs):
        time.sleep(self.delay)
        if self.fail:
            raise RuntimeError('fixture inference failed')
        batch = len(inputs[0])
        scores = np.zeros((batch, 80, 2), np.float32)
        scores[:, 0] = [.8, .25]
        boxes = np.tile(np.array([[[1, 1], [2, 2], [30, 30], [35, 35]]], np.float32), (batch, 1, 1))
        return [scores, boxes]


@unittest.skipIf(cv2 is None, 'Requires NumPy/OpenCV')
class BatchTests(unittest.TestCase):
    def test_pixels_transforms_and_padding(self):
        images = [np.full((40, 80, 3), [i, i+1, i+2], np.uint8) for i in range(2)]
        batch, transforms = detector.preprocess_batch(images, 4)
        for i, image in enumerate(images):
            expected, transform = detector.preprocess(image)
            np.testing.assert_array_equal(batch[i], expected[0])
            self.assertEqual(transforms[i], transform)
        np.testing.assert_array_equal(batch[2:], np.repeat(batch[1:2], 2, axis=0))
        reused = np.empty_like(batch)
        actual, _ = detector.preprocess_batch(images, 4, out=reused)
        self.assertIs(actual, reused)
        np.testing.assert_array_equal(actual, batch)

    def test_each_slot_has_independent_topk_and_coordinates(self):
        images = [np.zeros((640, 640, 3), np.uint8), np.zeros((320, 320, 3), np.uint8)]
        batch, transforms = detector.preprocess_batch(images)
        outputs, _ = fast.infer(Runtime(), batch)
        outputs[0][1, 0] = [.4, .9]
        result = detector.postprocess_batch(outputs, transforms, 2, topk=1)
        self.assertEqual([len(r) for r in result], [1, 1])
        self.assertAlmostEqual(result[0][0]['confidence'], .8, places=5)
        self.assertAlmostEqual(result[1][0]['confidence'], .9, places=5)
        self.assertEqual(result[0][0]['xyxy'], [1, 2, 30, 35])
        self.assertEqual(result[1][0]['xyxy'], [.5, 1, 15, 17.5])
        with self.assertRaises(ValueError):
            detector.postprocess_batch(outputs, transforms, 1)

    def fixture(self, path, count):
        writer = cv2.VideoWriter(str(path), cv2.VideoWriter_fourcc(*'MJPG'), 10, (80, 40))
        self.assertTrue(writer.isOpened())
        for i in range(count):
            writer.write(np.full((40, 80, 3), i*10, np.uint8))
        writer.release()

    def test_tail_order_and_worker_drain(self):
        for count, allocate in product((2, 3, 4, 10), (False, True)):
            with self.subTest(count=count, allocate=allocate), tempfile.TemporaryDirectory() as directory:
                root = Path(directory)
                self.fixture(root/'clip.avi', count)
                engine = SimpleNamespace(runtimes=[Runtime(.025), Runtime()])
                args = SimpleNamespace(video=root/'clip.avi', once=True, batch=3,
                                       queue_batches=2, post_workers=2, mode='detect', allocate_inputs=allocate)
                summary = fast.execute(engine, args, 5, root)
                rows = [json.loads(line) for line in (root/'frames.jsonl').read_text().splitlines()]
                self.assertEqual([r['frame'] for r in rows], list(range(count)))
                self.assertEqual([r['source_frame'] for r in rows], list(range(count)))
                self.assertEqual(summary['completed'], count)
                self.assertEqual(summary['submitted'], count)
                self.assertEqual(summary['batches'], (count+2)//3)
                self.assertEqual(rows[-1]['batch_valid'], (count-1)%3+1)
                self.assertFalse(engine.workers_active)

    def test_worker_failure_does_not_deadlock(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory)/'clip.avi'
            self.fixture(path, 4)
            engine = SimpleNamespace(runtimes=[Runtime(fail=True)])
            args = SimpleNamespace(video=path, once=True, batch=2,
                                   queue_batches=1, post_workers=1, mode='detect')
            with self.assertRaisesRegex(RuntimeError, 'fixture inference failed'):
                fast.execute(engine, args, 5)
            self.assertFalse(engine.workers_active)

    def test_output_failure_stops_queued_workers(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self.fixture(root/'clip.avi', 10)
            engine = SimpleNamespace(runtimes=[Runtime(), Runtime()])
            args = SimpleNamespace(video=root/'clip.avi', once=True, batch=2,
                                   queue_batches=2, post_workers=2, mode='display')
            with mock.patch.object(fast.video, 'Encoder', side_effect=OSError('fixture encoder failure')):
                with self.assertRaisesRegex(OSError, 'fixture encoder failure'):
                    fast.execute(engine, args, 5, root)
            self.assertFalse(engine.workers_active)

    def test_manifest_mismatch_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            model = Path(directory)/'model.rknn'
            model.write_bytes(b'model')
            with self.assertRaises(ValueError):
                fast.check_model(model, 2)
            model.with_suffix('.json').write_text(json.dumps({'batch': 2, 'precision': 'fp16', 'model_sha256': 'wrong'}))
            with self.assertRaisesRegex(ValueError, 'hash'):
                fast.check_model(model, 2)

    def test_decoder_validation_matches_cycles_for_short_clips(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            path = root/'clip.avi'
            self.fixture(path, 4)
            model = root/'model.rknn'
            model.write_bytes(b'fixture')
            reference = SimpleNamespace(runtimes=[Runtime()], close=mock.Mock())
            def fake_reader(path, loop, backend, log_path):
                self.assertEqual(backend, 'mpp')
                reader = fast.video.VideoReader(path, loop=loop)
                reader.evidence = {'backend': 'fixture only'}
                return reader
            with mock.patch.object(fast.video, 'Engine', return_value=reference), \
                 mock.patch.object(fast, 'make_reader', side_effect=fake_reader):
                result = fast.validate(SimpleNamespace(runtimes=[Runtime()]), model, path, 1,
                                       count=9, decode_backend='mpp', output=root)
            self.assertTrue(result['passed'])
            self.assertEqual(len(result['pixel_differences']), 9)
            reference.close.assert_called_once()

    def test_comparison_does_not_reuse_matches_or_ignore_order(self):
        first = {'class_id': 0, 'confidence': .8, 'xyxy': [1, 2, 30, 35]}
        second = {'class_id': 1, 'confidence': .7, 'xyxy': [2, 3, 31, 36]}
        fast.compare_detections([first, second], [dict(first), dict(second)])
        with self.assertRaises(ValueError):
            fast.compare_detections([first, second], [second, first])
        with self.assertRaises(ValueError):
            fast.compare_detections([first, second], [first, first])
        tied = dict(second, confidence=.8)
        fast.compare_detections([first, tied], [tied, first])

    def test_fp16_validation_failure_retains_raw_witness(self):
        class Visible(Runtime):
            def inference(self,*a,**kw):
                outputs=super().inference(*a,**kw)
                outputs[1][0,:,0]=[80,200,240,300]
                return outputs
        class Different(Visible):
            info={'input_mode':'fp16-pass'}
            def inference(self,*a,**kw):
                outputs=super().inference(*a,**kw)
                outputs[0][0,0,0]=.95
                return outputs
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);clip=root/'clip.avi';self.fixture(clip,4)
            model=root/'model.rknn';model.write_bytes(b'fixture')
            reference=SimpleNamespace(runtimes=[Visible()],close=mock.Mock())
            with mock.patch.object(fast.video,'Engine',return_value=reference):
                with self.assertRaisesRegex(ValueError,'Validation frame'):
                    fast.validate(SimpleNamespace(runtimes=[Different()]),model,clip,1,count=1,output=root)
            with np.load(root/'input-failure.npz') as witness:
                self.assertEqual(set(witness.files),{'rgb','reference_scores','reference_boxes','actual_scores','actual_boxes'})
                self.assertEqual(witness['rgb'].shape,(1,640,640,3))

    def test_parallel_preparation_keeps_tensor_frame_pairing_and_reaps_failure(self):
        class FrameRuntime(Runtime):
            def inference(self,inputs,**kwargs):
                outputs=super().inference(inputs,**kwargs)
                index=round(float(inputs[0][0,320,320,0])/10)
                outputs[0].fill(0);outputs[0][0,index,0]=.9
                outputs[1][0,:,0]=[200,200,240,240]
                return outputs
        original=detector.preprocess_batch
        def out_of_order(images,*args,**kwargs):
            if round(float(images[0].mean())/10)%2==0:time.sleep(.02)
            return original(images,*args,**kwargs)
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);clip=root/'clip.avi';self.fixture(clip,10)
            engine=SimpleNamespace(runtimes=[FrameRuntime(),FrameRuntime()])
            args=SimpleNamespace(video=clip,once=True,batch=1,queue_batches=4,post_workers=1,
                mode='detect',pre_workers=2)
            with mock.patch.object(detector,'preprocess_batch',side_effect=out_of_order):
                result=fast.execute(engine,args,5,root)
            rows=[json.loads(line) for line in (root/'frames.jsonl').read_text().splitlines()]
            self.assertEqual(result['completed'],10)
            self.assertEqual([r['source_frame'] for r in rows],list(range(10)))
            self.assertEqual([r['detections'][0]['class_id'] for r in rows],list(range(10)))
            self.assertEqual({r['preparation_worker'] for r in rows},{0,1})
            self.assertFalse(engine.workers_active)
            with mock.patch.object(detector,'preprocess_batch',side_effect=RuntimeError('preparation failure')):
                with self.assertRaisesRegex(RuntimeError,'preparation failure'):fast.execute(engine,args,5)
            self.assertFalse(engine.workers_active)


if __name__ == '__main__':
    unittest.main()
