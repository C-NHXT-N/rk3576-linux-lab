# SPDX-License-Identifier: AGPL-3.0-only
# Copyright (c) 2026 C-NHXT-N and contributors
import importlib.util
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
PROJECT = ROOT / '04-rknn-vision'
sys.path.insert(0, str(PROJECT))
try:
    import cv2
    import numpy as np
    import detector
    import vision
except ImportError:
    cv2 = None


@unittest.skipIf(cv2 is None, 'Install the recorded NumPy/OpenCV environment for detector tests')
class DetectionTests(unittest.TestCase):
    def test_letterbox_rgb_and_inverse_coordinates(self):
        image = np.zeros((300, 800, 3), np.uint8)
        image[:] = [1, 2, 3]
        batch, transform = detector.preprocess(image)
        self.assertEqual(batch.shape, (1, 640, 640, 3))
        self.assertEqual(batch.dtype, np.uint8)
        np.testing.assert_array_equal(batch[0, 320, 320], [3, 2, 1])
        np.testing.assert_array_equal(batch[0, 0, 0], [0, 0, 0])
        scores = np.zeros((1, 80, 1), np.float32)
        scores[0, 0, 0] = .9
        box = np.array([[[0], [200], [640], [440]]], np.float32)
        results = detector.postprocess([scores, box], transform)
        self.assertEqual(results[0]['xyxy'], [0, 0, 800, 300])

    def test_topk_threshold_swapped_outputs_and_empty(self):
        _, transform = detector.preprocess(np.zeros((640, 640, 3), np.uint8))
        scores = np.zeros((1, 80, 3), np.float32)
        scores[0, 0] = [.25, .9, .8]
        boxes = np.array([[[1, 1, 1], [2, 2, 2], [100, 100, 100], [200, 200, 200]]], np.float32)
        result = detector.postprocess([boxes, scores], transform, threshold=.25, topk=1)
        self.assertEqual(len(result), 1)
        self.assertAlmostEqual(result[0]['confidence'], .9, places=5)
        self.assertEqual(detector.postprocess([scores * 0, boxes], transform), [])
        self.assertEqual(detector.postprocess([np.zeros((1, 80, 0)), np.zeros((1, 4, 0))], transform), [])

    def test_invalid_shapes_and_values_fail(self):
        _, transform = detector.preprocess(np.zeros((20, 20, 3), np.uint8))
        for outputs in [None, [], [np.zeros((1, 1000))],
                        [np.zeros((1, 80, 2)), np.zeros((1, 4, 3))],
                        [np.full((1, 80, 1), np.nan), np.zeros((1, 4, 1))],
                        [np.full((1, 80, 1), 2), np.zeros((1, 4, 1))]]:
            with self.assertRaises(ValueError):
                detector.postprocess(outputs, transform)

    def test_bad_config_values_and_migration(self):
        with tempfile.TemporaryDirectory(dir=ROOT / 'build') as temporary:
            folder = Path(temporary)
            (folder/'a').write_bytes(b'fixture')
            file = folder/'config.json'
            for change in [{'labels':'labels.txt'}, {'camera':'/dev/video0'}, {'topk':0},
                           {'topk': True}, {'score_threshold':2}, {'score_threshold':float('nan')},
                           {'interval':float('inf')}]:
                file.write_text(json.dumps({'model':'a','image':'a',**change}))
                with self.assertRaises(ValueError):
                    vision.load_config(file)

    def test_resource_release_and_failed_health(self):
        class Runtime:
            NPU_CORE_0 = 1
            def load_rknn(self, path): return 0
            def init_runtime(self, **kwargs): return 0
            def release(self): self.released = True
        with tempfile.TemporaryDirectory(dir=ROOT / 'build') as temporary:
            folder = Path(temporary)
            model = folder/'model.rknn'
            model.write_bytes(b'fixture')
            image = folder/'broken.jpg'
            image.write_bytes(b'not an image')
            config = {'model':model, 'image':image, 'health':folder/'health.json', 'frames':1,
                      'interval':1, 'score_threshold':.25, 'topk':300, 'output_dir':folder/'out'}
            instance = Runtime()
            factory = mock.Mock(return_value=instance)
            factory.NPU_CORE_0 = 1
            with mock.patch.object(vision, 'dependencies', return_value=(cv2,np,factory,detector)), \
                 mock.patch.object(vision, 'select_runtime', return_value=Path('/fixture.so')), \
                 mock.patch.object(vision, 'bind_runtime'), \
                 mock.patch.object(vision, 'mapped_runtime', return_value=['/fixture.so']):
                with self.assertRaisesRegex(RuntimeError, 'decode'):
                    vision.run(config)
            self.assertTrue(instance.released)
            self.assertEqual(json.loads((folder/'health.json').read_text())['status'], 'error')

    def test_write_failure_is_not_a_success(self):
        with tempfile.TemporaryDirectory(dir=ROOT / 'build') as temporary:
            target = Path(temporary)/'not-a-directory'
            target.write_text('existing file')
            with self.assertRaises(OSError):
                vision.save_result(cv2, detector, np.zeros((10,10,3),np.uint8), {'detections':[]}, target)
            with mock.patch.object(cv2, 'imencode', return_value=(False,None)):
                with self.assertRaisesRegex(RuntimeError, 'encode'):
                    vision.save_result(cv2, detector, np.zeros((10,10,3),np.uint8), {'detections':[]}, Path(temporary)/'out')

if __name__ == '__main__':
    (ROOT/'build').mkdir(exist_ok=True)
    unittest.main()
