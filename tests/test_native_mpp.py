# SPDX-License-Identifier: AGPL-3.0-only
import copy
import json
import platform
from pathlib import Path
import subprocess
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest import mock

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'projects/04-rknn-vision'))
try:
    import cv2
    import numpy as np
    import cpu_preprocess,native_post,native_mpp
    import fast_bench as fast
    import video_bench as video
    import experiment
    import thread_accounting
except ImportError:cv2=None


@unittest.skipIf(cv2 is None or platform.machine()!='aarch64','Requires board MPP/NEON')
class NativeMppTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp=tempfile.TemporaryDirectory();cls.root=Path(cls.temp.name);cls.clip=cls.root/'bframes.mp4'
        subprocess.run(['ffmpeg','-v','error','-f','lavfi','-i','testsrc2=size=1280x720:rate=30',
            '-frames:v','12','-c:v','libx264','-threads','1','-bf','2','-pix_fmt','yuv420p',str(cls.clip)],check=True,timeout=30)
        cpu_preprocess.build();native_post.build()

    @classmethod
    def tearDownClass(cls):cls.temp.cleanup()

    def test_pixels_pts_eos_hardware_proof_and_held_frame(self):
        old=video.VideoReader(self.clip,loop=False,decode_threads=4)
        new=native_mpp.VideoReader(self.clip,loop=False,pool_size=2)
        held=None
        try:
            self.assertEqual(new.evidence['current_context']['accepted_packets'],0)
            previous=None
            for i in range(12):
                a,b=old.read(),new.read()
                np.testing.assert_array_equal(a['image'],b['image'])
                self.assertEqual(b['source_frame'],i)
                if previous is not None:self.assertGreater(b['source_pts'],previous)
                previous=b['source_pts'];video.release_image(a)
                if i==0:held=b;saved=b['image'].copy()
                else:video.release_image(b)
                np.testing.assert_array_equal(held['image'],saved)
            video.release_image(held);held=None
            self.assertIsNone(new.read());self.assertTrue(native_mpp.hardware_proven(new.evidence,12))
            wrong=copy.deepcopy(new.evidence);wrong['current_context']['hardware_frames']=11
            self.assertFalse(native_mpp.hardware_proven(wrong,12))
        finally:
            if held:video.release_image(held)
            old.close();new.close()
        self.assertEqual(new.evidence['active_frame_leases_after_close'],0)

    def test_loop_and_cancel_reap_sender_without_raw_frame_children(self):
        reader=native_mpp.VideoReader(self.clip,loop=True,pool_size=2)
        try:
            for i in range(14):
                item=reader.read();self.assertEqual((item['cycle'],item['source_frame']),(i//12,i%12));video.release_image(item)
            sender=reader.evidence['current_context']['sender_tid']
            source=video.Prefetch(reader);item=source.read();video.release_image(item);source.close()
            self.assertFalse(source.thread.is_alive());self.assertFalse((Path('/proc/self/task')/str(sender)).exists())
            self.assertIsNone(reader.handle)
        finally:reader.close()

    def test_reused_padding_is_initialized_once_per_live_slot(self):
        reader=native_mpp.FusedReader(self.clip,loop=False,reuse_padding=True)
        reference=video.VideoReader(self.clip,loop=False)
        processor=cpu_preprocess.Processor()
        import numpy as np
        slots=[np.empty((1,640,640,3),np.float16) for _ in range(2)]
        try:
            for index in range(12):
                item=reader.read_prepared(slots[index%2]);old=reference.read()
                expected,_=processor.batch([old['image']])
                np.testing.assert_array_equal(slots[index%2],expected)
                video.release_image(item)
            self.assertEqual(reader.evidence['padding_initializations'],2)
            self.assertTrue(native_mpp.hardware_proven(reader.evidence,12))
        finally:reader.close();reference.close();processor.close()

    def test_pipeline_ownership_cpu_roles_and_error_cleanup(self):
        from test_batch_pipeline import Runtime
        base=None
        for failing in (False,True):
            thread_accounting.enable()
            processor=cpu_preprocess.Processor();reader=native_mpp.VideoReader(self.clip,loop=False,pool_size=5)
            sender=reader.evidence['current_context']['sender_tid']
            args=SimpleNamespace(video=self.clip,once=True,batch=1,queue_batches=2,post_workers=1,
                mode='detect',max_frames=12,pre_workers=1,feed_path='fused',input_mode='fp16-ready',output_mode='fp16',
                preprocessor=processor,preprocessors=[processor],preprocess_backend='cpu-fused',post_backend='cpp',
                decode_backend='mpp-native',thread_accounting=True)
            engine=SimpleNamespace(runtimes=[Runtime(.001,fail=failing),Runtime(.002,fail=failing)])
            try:
                with mock.patch.object(fast,'make_reader',return_value=reader):
                    if failing:
                        with self.assertRaisesRegex(RuntimeError,'fixture inference'):fast.execute(engine,args,20)
                    else:
                        base=fast.execute(engine,args,20)
                        self.assertEqual(base['completed'],12)
                        self.assertTrue(native_mpp.hardware_proven(base['media']['decoder'],12))
                        self.assertIn('mpp_convert_cpu_ms',base['runtime_metrics'])
                        self.assertIn('mpp_submit',base['thread_accounting']['roles'])
                        self.assertEqual(base['thread_accounting']['vanished_threads'],[])
                self.assertFalse(engine.workers_active)
                self.assertIsNone(reader.handle);self.assertEqual(reader.evidence['active_frame_leases_after_close'],0)
                self.assertFalse((Path('/proc/self/task')/str(sender)).exists())
            finally:processor.close();reader.close()
        self.__class__.base=base



if __name__=='__main__':unittest.main()
