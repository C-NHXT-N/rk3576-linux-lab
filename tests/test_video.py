# SPDX-License-Identifier: AGPL-3.0-only
# Copyright (c) 2026 C-NHXT-N and contributors
from pathlib import Path
from types import SimpleNamespace
import sys
import tempfile
import unittest
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT/'projects/04-rknn-vision'))
try:
    import cv2
    import numpy as np
    import video_bench as video
except ImportError:
    cv2 = None


@unittest.skipIf(cv2 is None, 'Requires NumPy/OpenCV')
class VideoTests(unittest.TestCase):
    def fixture(self, directory):
        path = Path(directory)/'clip.avi'
        writer = cv2.VideoWriter(str(path),cv2.VideoWriter_fourcc(*'MJPG'),10,(80,40))
        self.assertTrue(writer.isOpened())
        for index in range(4):
            writer.write(np.full((40,80,3),index*40,np.uint8))
        writer.release()
        return path

    def test_loop_and_exact_once(self):
        with tempfile.TemporaryDirectory() as directory:
            path = self.fixture(directory)
            reader = video.VideoReader(path,loop=True)
            try:
                indices = [(v['source_frame'],v['cycle']) for v in [reader.read() for _ in range(6)]]
                self.assertEqual(indices,[(0,0),(1,0),(2,0),(3,0),(0,1),(1,1)])
            finally:
                reader.close()
            reader = video.VideoReader(path,loop=False)
            source = video.Prefetch(reader)
            try:
                self.assertEqual([source.read()['source_frame'] for _ in range(4)],[0,1,2,3])
                self.assertIsNone(source.read())
            finally:
                source.close()
            self.assertFalse(source.thread.is_alive())

    def test_bad_video_and_decode_failure(self):
        with tempfile.TemporaryDirectory() as directory:
            with self.assertRaises(RuntimeError):
                video.VideoReader(Path(directory)/'missing.mp4')
            reader = video.VideoReader(self.fixture(directory))
            try:
                reader.cap.release()
                with self.assertRaisesRegex(RuntimeError,'before declared EOF'):
                    reader.read()
            finally:
                reader.close()

    def test_wall_clock_stability_and_partial_window(self):
        rows = [{'completed_s':i/10, **{k:1 for k in ['decode_ms','preprocess_ms','inference_ms',
                'postprocess_ms','output_ms','latency_ms']}} for i in range(1,101)]
        summary = video.summarize(rows,10.05,target=10)
        self.assertTrue(summary['stable'])
        self.assertEqual(len(summary['second_fps']),10)
        self.assertAlmostEqual(summary['fps'],100/10.05)
        self.assertFalse(video.summarize(rows,20,target=10)['stable'])


    def test_header_preserves_geometry_and_engine_init_failure_releases(self):
        image = np.zeros((100,200,3),np.uint8)
        rendered = video.decorate(image,[],'test')
        np.testing.assert_array_equal(rendered[70:], image)
        class Runtime:
            NPU_CORE_0=1
            def load_rknn(self,path): return 0
            def init_runtime(self,**kw): return -1
            def release(self): self.released=True
        instance=Runtime()
        factory=mock.Mock(return_value=instance)
        factory.NPU_CORE_0=1
        with mock.patch.object(video.vision,'dependencies',return_value=(cv2,np,factory,None)), \
             mock.patch.object(video.vision,'select_runtime',return_value=Path('/fixture')), \
             mock.patch.object(video.vision,'bind_runtime'):
            with self.assertRaisesRegex(RuntimeError,'init_runtime'):
                video.Engine(Path('/fixture'),['0'])
        self.assertTrue(instance.released)


if __name__ == '__main__':
    unittest.main()
