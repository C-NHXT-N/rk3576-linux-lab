# SPDX-License-Identifier: AGPL-3.0-only
from pathlib import Path
import shutil
import sys
import unittest
import json
import tempfile
from types import SimpleNamespace
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1]/'projects/04-rknn-vision'))
try:
    import cv2
    import numpy as np
    import detector
    import native_post
    import cached_render
    import video_bench as video
    import fast_bench as fast
except ImportError:
    cv2 = None


@unittest.skipIf(cv2 is None or shutil.which('g++') is None, 'Requires Linux compiler and NumPy/OpenCV')
class NativeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        native_post.build()

    def compare(self, outputs, transforms, batch, topk=300):
        p = native_post.Postprocessor()
        try:
            self.assertEqual(p.batch(outputs, transforms, batch, topk=topk),
                             detector.postprocess_batch(outputs, transforms, batch, topk=topk))
        finally:
            p.close()

    def test_random_half_float_batch_ties_threshold_topk_coordinates(self):
        rng = np.random.default_rng(381)
        transform = dict(width=1280, height=720, left=0, top=140, scale_x=.5, scale_y=.5)
        for dtype in (np.float16, np.float32):
            for n in (0, 1, 301, 8400):
                scores = rng.random((2, 80, n)).astype(dtype)
                boxes = rng.uniform(-300, 1300, (2, 4, n)).astype(dtype)
                if n:
                    scores[:, :, :min(n, 5)] = .25
                    scores[:, :2, min(n-1, 5)] = .99
                for k in (0, 1, 300, -1):
                    self.compare([boxes, scores], [transform, transform], 2, k)

    def test_invalid_outputs_checks_every_candidate(self):
        t = dict(width=640, height=640, left=0, top=0, scale_x=1., scale_y=1.)
        for dtype in (np.float16, np.float32):
            for target, value in ((0, np.nan), (0, np.inf), (0, -.01), (0, 1.02), (1, np.nan)):
                outputs = [np.zeros((1, 80, 2), dtype), np.zeros((1, 4, 2), dtype)]
                outputs[target][0, 0, 1] = value
                p = native_post.Postprocessor()
                try:
                    with self.assertRaises(ValueError): p.batch(outputs, [t], 1)
                    with self.assertRaises(ValueError): detector.postprocess_batch(outputs, [t], 1)
                finally:
                    p.close()
            outputs = [np.full((1,80,2), -.001, dtype), np.zeros((1,4,2), dtype)]
            self.compare(outputs, [t], 1)
            outputs[0][:] = np.asarray(1.001, dtype=dtype)
            self.compare(outputs, [t], 1)

    def test_numerical_selection_and_workspace_reuse(self):
        scores = np.zeros((1,80,6), np.float32)
        scores[0,0] = [.25, .5, .5, .8, .9, 1.]
        scores[0,1,1] = .5
        boxes = np.tile(np.array([1,2,30,40], np.float32)[None,:,None],(1,1,6))
        boxes[0,:,5] = [10,10,1,1]
        t = dict(width=640,height=640,left=0,top=0,scale_x=1.,scale_y=1.)
        p = native_post.Postprocessor()
        try:
            for k in (1,3,300):
                expected=detector.postprocess_batch([scores,boxes],[t],1,topk=k)
                actual=p.batch([scores,boxes],[t],1,topk=k)
                self.assertEqual(actual,expected)
                if actual:
                    saved=[dict(d,xyxy=list(d['xyxy'])) for d in actual[0]]
                    p.batch([scores*0,boxes],[t],1)
                    self.assertEqual(actual[0],saved)
        finally:
            p.close()

    def test_native_and_cached_pipeline_gate_order_and_metrics(self):
        from test_batch_pipeline import Runtime
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory)
            writer=cv2.VideoWriter(str(root/'clip.avi'),cv2.VideoWriter_fourcc(*'MJPG'),10,(80,40))
            for i in range(4): writer.write(np.full((40,80,3),i*20,np.uint8))
            writer.release()
            model=root/'model.rknn'; model.write_bytes(b'fixture')
            reference=SimpleNamespace(runtimes=[Runtime()],close=mock.Mock())
            engine=SimpleNamespace(runtimes=[Runtime(),Runtime()])
            with mock.patch.object(video,'Engine',return_value=reference):
                gate=fast.validate(engine,model,root/'clip.avi',1,count=9,post_backend='cpp',
                                   renderer=cached_render.Renderer())
            self.assertEqual(gate['native_exact_checks'],18)
            self.assertEqual(gate['render_exact_checks'],18)
            args=SimpleNamespace(video=root/'clip.avi',once=True,batch=1,queue_batches=8,
                post_workers=1,mode='display',post_backend='cpp',renderer=cached_render.Renderer())
            encoder=SimpleNamespace(write=lambda image: None,close=lambda: None,evidence={})
            with mock.patch.object(video,'Encoder',return_value=encoder):
                result=fast.execute(engine,args,5,root)
            self.assertEqual(result['submitted'],4)
            self.assertEqual(result['completed'],4)
            self.assertGreater(result['diagnostic_ms']['post_native_ms']['sum_ms'],0)
            rows=[json.loads(line) for line in (root/'frames.jsonl').read_text().splitlines()]
            self.assertEqual([r['source_frame'] for r in rows],list(range(4)))


@unittest.skipIf(cv2 is None, 'Requires NumPy/OpenCV')
class RenderTests(unittest.TestCase):
    def test_exact_edges_overlap_reuse_eviction_and_original_unchanged(self):
        rng=np.random.default_rng(81)
        renderer=cached_render.Renderer(limit=2)
        for height,width in ((720,1280),(40,80),(790,1280),(720,1280)):
            image=rng.integers(0,256,(height,width,3),dtype=np.uint8)
            original=image.copy()
            boxes=[[0,0,width,height],[width-1,height-1,width,height],
                   [0,height-2,width//2,height],[10,10,width//2,height//2],[-3,-2,20,20]]
            for count in (0,5,5,1,3):
                detections=[dict(class_id=i,name=detector.CLASSES[i],confidence=.251+i*.12,xyxy=b)
                            for i,b in enumerate(boxes[:count])]
                detail=f'Frame {count:04d} | {count} objects | batch 1 | playback 30 FPS'
                expected=video.decorate(image,detections,detail)
                actual=renderer.draw(image,detections,detail)
                np.testing.assert_array_equal(actual,expected)
                np.testing.assert_array_equal(image,original)
                self.assertLessEqual(len(renderer.labels),2)


if __name__ == '__main__':
    unittest.main()
