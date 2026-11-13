# SPDX-License-Identifier: AGPL-3.0-only
import json
from pathlib import Path
import sys
import tempfile
import time
from types import SimpleNamespace
import unittest
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1]/'projects/04-rknn-vision'))
try:
    import cv2
    import numpy as np
    import fast_bench as fast
except ImportError:
    cv2 = None
from test_batch_pipeline import Runtime


@unittest.skipIf(cv2 is None, 'Requires NumPy/OpenCV')
class BoundaryTests(unittest.TestCase):
    def fixture(self, path):
        writer = cv2.VideoWriter(str(path), cv2.VideoWriter_fourcc(*'MJPG'), 10, (80, 40))
        self.assertTrue(writer.isOpened())
        for i in range(4):
            writer.write(np.full((40, 80, 3), i*30, np.uint8))
        writer.release()

    def test_decoder_threads_survive_reopen_and_preserve_pixels(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory)/'clip.avi'
            self.fixture(path)
            for n in (2, 4):
                with mock.patch.object(fast.video.cv2, 'VideoCapture', wraps=cv2.VideoCapture) as opened:
                    reader = fast.video.VideoReader(path, decode_threads=n)
                    try:
                        images = [reader.read()['image'] for _ in range(6)]
                    finally:
                        reader.close()
                    self.assertEqual(opened.call_count, 2)
                    self.assertTrue(all(c.args[2] == [cv2.CAP_PROP_N_THREADS, n] for c in opened.call_args_list))
                    np.testing.assert_array_equal(images[0], images[4])
                reference = SimpleNamespace(runtimes=[Runtime()], close=mock.Mock())
                model = Path(directory)/'model.rknn'; model.write_bytes(b'fixture')
                with mock.patch.object(fast.video, 'Engine', return_value=reference):
                    result = fast.validate(SimpleNamespace(runtimes=[Runtime()]), model, path, 1,
                                           count=9, decode_threads=n)
                self.assertTrue(result['passed'])
                self.assertTrue(all(r['max_absolute_error'] == 0 for r in result['pixel_differences']))

    def test_pure_inference_prepares_32_frames_and_skips_video_outputs(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory); self.fixture(root/'clip.avi')
            engine = SimpleNamespace(runtimes=[Runtime(.003), Runtime(.003)])
            args = SimpleNamespace(video=root/'clip.avi', once=False, batch=1,
                                   queue_batches=8, post_workers=1, mode='infer', decode_threads=2)
            result = fast.execute(engine, args, .06, root)
            self.assertEqual(result['infer_pool_frames'], 32)
            self.assertEqual(result['completed'], result['submitted'])
            self.assertGreater(result['completed'], 0)
            self.assertFalse((root/'frames.jsonl').exists())
            self.assertEqual(result['diagnostic_ms']['draw_ms']['sum_ms'], 0)
            self.assertFalse(engine.workers_active)

    def test_output_timing_includes_json_and_encoder_drain(self):
        class Encoder:
            def __init__(self, *a, **kw): pass
            def write(self, image): time.sleep(.003)
            def close(self): time.sleep(.006)
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory); self.fixture(root/'clip.avi')
            engine = SimpleNamespace(runtimes=[Runtime()])
            args = SimpleNamespace(video=root/'clip.avi', once=True, batch=1,
                                   queue_batches=8, post_workers=1, mode='display')
            with mock.patch.object(fast.video, 'Encoder', Encoder):
                result = fast.execute(engine, args, 5, root)
            self.assertEqual(result['completed'], 4)
            self.assertGreater(result['diagnostic_ms']['encode_write_ms']['mean'], 2)
            self.assertGreater(result['diagnostic_ms']['json_write_ms']['sum_ms'], 0)
            self.assertGreater(result['encoder_drain_ms'], 5)
            self.assertGreater(result['elapsed_s']*1000, result['encoder_drain_ms'])
            rows = [json.loads(line) for line in (root/'frames.jsonl').read_text().splitlines()]
            self.assertEqual([r['frame'] for r in rows], list(range(4)))



if __name__ == '__main__':
    unittest.main()
