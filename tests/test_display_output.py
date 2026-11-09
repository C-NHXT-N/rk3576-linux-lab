# SPDX-License-Identifier: AGPL-3.0-only
from pathlib import Path
import json
import platform
import subprocess
import sys
import tempfile
import threading
import time
import unittest

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'04-rknn-vision'))
try:
    import cv2
    import numpy as np
    import cached_render,media_support,native_output,output_pipeline
except ImportError:cv2=None


@unittest.skipIf(cv2 is None,'Requires board OpenCV/NumPy')
class CanvasTests(unittest.TestCase):
    def test_inplace_pixels_and_slow_output_ownership(self):
        stop=threading.Event();pool=media_support.FramePool(3,canvas=True)
        saved=[]
        class Sink:
            def write(self,image):
                before=image.copy();time.sleep(.01)
                np.testing.assert_array_equal(before,image);saved.append(int(image[-1,-1,0]))
            def close(self):pass
        stage=output_pipeline.QueuedEncoder(lambda image:Sink(),shared_cache=True)
        reference=cached_render.Renderer()
        detections=[dict(xyxy=[4,8,100,180],class_id=0,name='person',confidence=.88)]
        try:
            for index in range(9):
                lease=pool.acquire(stop);lease.image[:]=index
                expected=reference.draw(lease.image,detections,str(index)).copy()
                actual=cached_render.Renderer().draw(lease.image,detections,str(index),canvas=lease.canvas)
                np.testing.assert_array_equal(expected,actual)
                # Restore pixels because the second draw must start from the source.
                lease.image[:]=index
                stage.draw_submit(lease.image,detections,str(index),canvas=lease.canvas,lease=lease)
            stage.close()
            self.assertEqual(saved,list(range(9)));self.assertEqual(len(pool.active),0)
            self.assertGreater(stage.evidence['render_cache']['hits'],0)
            self.assertTrue(stage.evidence['render_cache']['shared'])
        finally:stage.close();pool.close()

    def test_drawing_and_worker_errors_return_every_source_lease(self):
        stop=threading.Event();pool=media_support.FramePool(3,canvas=True)
        class Sink:
            def write(self,image):raise RuntimeError('injected output error')
            def close(self):pass
        stage=output_pipeline.QueuedEncoder(lambda image:Sink(),shared_cache=True)
        try:
            lease=pool.acquire(stop)
            with self.assertRaises(KeyError):stage.draw_submit(lease.image,[{}],'bad',canvas=lease.canvas,lease=lease)
            self.assertEqual(len(pool.active),0)
            lease=pool.acquire(stop);stage.draw_submit(lease.image,[],'worker',canvas=lease.canvas,lease=lease)
            stage.thread.join(timeout=2)
            with self.assertRaisesRegex(RuntimeError,'injected output error'):stage.close()
            self.assertEqual(len(pool.active),0)
        finally:stage.close();pool.close()


@unittest.skipUnless(cv2 is not None and platform.machine()=='aarch64','Requires RK3576 MPP/NEON')
class PipelinedEncoderTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):native_output.build()

    def _roundtrip(self,colors,delay=0,partition=0):
        with tempfile.TemporaryDirectory() as temporary:
            path=Path(temporary)/'video.mp4'
            image=np.zeros((790,1280,3),np.uint8)
            encoder=native_output.Encoder(path,image,30)
            encoder.configure_test(delay_ms=delay,partition_bytes=partition)
            try:
                for value in colors:
                    image[:]=value;encoder.write(image)
                    # write() has consumed the entire BGR source before returning.
                    image[:]=0
                encoder.close()
                self.assertEqual(encoder.evidence['frames'],len(colors))
                self.assertEqual(encoder.evidence['completed'],len(colors))
                self.assertEqual(encoder.evidence['free_buffers'],3)
                self.assertTrue(encoder.evidence['eos_received'])
                self.assertEqual([int(v[0]) for v in encoder.evidence['completion_events']],list(range(len(colors))))
                capture=cv2.VideoCapture(str(path))
                try:
                    for value in colors:
                        ok,actual=capture.read();self.assertTrue(ok);self.assertEqual(actual.shape,(790,1280,3))
                        self.assertLess(float(np.max(np.abs(actual[-2,-2].astype(np.int16)-np.array(value)))),12)
                    self.assertFalse(capture.read()[0])
                finally:capture.release()
                return encoder.evidence
            finally:
                encoder.close()

    def test_single_and_more_than_pool_slow_consumer(self):
        self._roundtrip([(20,50,220)])
        self._roundtrip([(20+i*8,50+i*4,220-i*10) for i in range(12)],delay=10)

    def test_partition_packets_preserve_frame_order(self):
        # Detailed test pattern forces more than one H.264 slice packet per image.
        with tempfile.TemporaryDirectory() as temporary:
            path=Path(temporary)/'partitions.mp4'
            image=np.random.default_rng(4).integers(0,256,(790,1280,3),dtype=np.uint8)
            encoder=native_output.Encoder(path,image,30)
            encoder.configure_test(partition_bytes=10000)
            try:
                for _ in range(5):encoder.write(image)
            finally:encoder.close()
            self.assertEqual(encoder.evidence['completed'],5)
            self.assertGreater(encoder.evidence['partition_packets'],0)
            self.assertEqual(encoder.evidence['free_buffers'],3)
            data=json.loads(subprocess.check_output(['ffprobe','-v','error','-count_frames','-select_streams','v:0',
                '-show_entries','stream=nb_read_frames','-of','json',str(path)],text=True))
            self.assertEqual(int(data['streams'][0]['nb_read_frames']),5)

    def test_error_cancel_and_empty_close_release_native_context(self):
        with tempfile.TemporaryDirectory() as temporary:
            image=np.zeros((790,1280,3),np.uint8)
            empty=native_output.Encoder(Path(temporary)/'empty.mp4',image,30);empty.close()
            self.assertIsNone(empty.handle)
            for cancel in (False,True):
                encoder=native_output.Encoder(Path(temporary)/f'error-{cancel}.mp4',image,30)
                if cancel:encoder.cancel()
                else:encoder.configure_test(fail_after=1)
                with self.assertRaises(RuntimeError):
                    for _ in range(8):encoder.write(image)
                with self.assertRaises(RuntimeError):encoder.close()
                self.assertIsNone(encoder.handle)


if __name__=='__main__':unittest.main()
