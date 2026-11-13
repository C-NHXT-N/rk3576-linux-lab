# SPDX-License-Identifier: AGPL-3.0-only
import ctypes as ct
import copy
import json
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import threading
from types import SimpleNamespace
import unittest
from unittest import mock

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'projects/04-rknn-vision'))
try:
    import cv2
    import numpy as np
    import native_rknn as native
    import fast_bench as fast
    import experiment
except ImportError:
    cv2=None


@unittest.skipIf(cv2 is None or not shutil.which('g++'),'Requires Linux C++/NumPy/OpenCV')
@unittest.skipUnless((ROOT/'projects/04-rknn-vision/third_party/rknn_api.h').is_file(),
                     'Fetch the official RKNN C header to run the native Runtime tests')
class NativeRuntimeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp=tempfile.TemporaryDirectory()
        cls.library=Path(cls.temp.name)/'fake_rknn.so'
        subprocess.run(['g++','-std=c++17','-O2','-shared','-fPIC','-pthread',
            '-I'+str(ROOT/'projects/04-rknn-vision/third_party'),str(ROOT/'tests/fixtures/fake_rknn.cpp'),
            '-o',str(cls.library)],check=True)
        native.build();cls.lib=native.load();cls.fixture=ct.CDLL(str(cls.library))

    @classmethod
    def tearDownClass(cls): cls.temp.cleanup()

    def tearDown(self):
        self.fixture.fixture_fail_stage(0)
        self.fixture.fixture_bad_native(0)
        self.assertEqual(self.fixture.fixture_live_buffers(),0)
        self.assertEqual(self.fixture.fixture_live_contexts(),0)

    def runtime(self,prealloc,input_mode='uint8'):
        return native.Runtime(self.lib,Path('fixture.rknn'),self.library,'0',prealloc,input_mode)

    def bound_runtime(self,slots=2,binding_mode='dynamic'):
        return native.BoundRuntime(self.lib,Path('fixture.rknn'),self.library,'0',True,
            'fp16-ready','fp16',io_mode='bind-both',binding_mode=binding_mode,slots=slots)

    def test_fp16_table_bits_submission_order_and_native_contract(self):
        expected=(np.arange(256,dtype=np.float32)/np.float32(255)).astype(np.float16).view(np.uint16)
        np.testing.assert_array_equal(native.lut_bits(self.lib),expected)
        r=self.runtime(True,'fp16-pass')
        try:
            rgb=np.tile(np.arange(256,dtype=np.uint8),4800).reshape(1,640,640,3)
            before=rgb.copy()
            outputs=[np.empty(s,np.float32) for s in r.shapes]
            _,parts=r.run_into(rgb,outputs)
            np.testing.assert_array_equal(rgb,before)
            actual=np.array([self.fixture.fixture_input_half(i) for i in range(256)],np.uint16)
            np.testing.assert_array_equal(actual,expected)
            self.assertEqual(self.fixture.fixture_input_type(),1)
            self.assertEqual(self.fixture.fixture_input_pass(),1)
            self.assertEqual(self.fixture.fixture_input_size(),2457600)
            self.assertGreater(parts['rknn_normalize_cpu_ms'],0)
            self.assertAlmostEqual(parts['rknn_input_total_cpu_ms'],
                parts['rknn_normalize_cpu_ms']+parts['rknn_inputs_set_cpu_ms'])
            r.run_into(np.full_like(rgb,255),outputs)
            self.assertEqual(float(outputs[0][0,0,0]),1.)
            r.run_into(np.zeros_like(rgb),outputs)
            self.assertEqual(float(outputs[0][0,0,0]),0.)
        finally:r.release()
        self.fixture.fixture_bad_native(1)
        with self.assertRaisesRegex(RuntimeError,'packed'):
            self.runtime(True,'fp16-pass')

    def test_prepared_fp16_is_borrowed_without_second_normalization(self):
        r=self.runtime(True,'fp16-ready')
        try:
            prepared=np.full((1,640,640,3),np.float16(7/255),np.float16)
            saved=prepared.copy();outputs=[np.empty(s,np.float32) for s in r.shapes]
            _,parts=r.run_into(prepared,outputs)
            np.testing.assert_array_equal(prepared,saved)
            self.assertEqual(parts['rknn_normalize_cpu_ms'],0)
            self.assertEqual(self.fixture.fixture_input_pass(),1)
            self.assertEqual(self.fixture.fixture_input_half(0),int(prepared.view(np.uint16)[0,0,0,0]))
            self.assertAlmostEqual(float(outputs[0][0,0,0]),float(prepared[0,0,0,0]))
            with self.assertRaises(ValueError):r.run_into(np.zeros(prepared.shape,np.uint8),outputs)
        finally:r.release()

    def test_half_output_pool_raw_and_public_float_contract(self):
        r=native.Runtime(self.lib,Path('fixture.rknn'),self.library,'0',True,'fp16-ready','fp16')
        pool=native.OutputPool(r.shapes,2,np.float16)
        try:
            batch=np.full((1,640,640,3),np.float16(7/255),np.float16)
            lease=pool.acquire(threading.Event())
            outputs,parts=r.run_into(batch,lease.arrays)
            self.assertTrue(all(a.dtype==np.float16 for a in outputs))
            self.assertEqual(sum(a.nbytes for a in outputs),1411200)
            np.testing.assert_array_equal(outputs[0],np.full(r.shapes[0],batch[0,0,0,0],np.float16))
            saved=outputs[0].copy()
            self.assertTrue(all(a.dtype==np.float32 for a in r.inference([batch])))
            np.testing.assert_array_equal(outputs[0],saved)
            self.assertEqual(parts['rknn_copy_wall_ms'],0)
            lease.release()
        finally:pool.reclaim();r.release()

    def test_output_lifetime_across_next_inference_and_profile(self):
        for prealloc in (False,True):
            with self.subTest(prealloc=prealloc):
                r=self.runtime(prealloc);pool=native.OutputPool(r.shapes,2);abort=threading.Event()
                try:
                    a,b=pool.acquire(abort),pool.acquire(abort)
                    r.run_into(np.full((1,640,640,3),7,np.uint8),a.arrays)
                    _,parts=r.run_into(np.full((1,640,640,3),13,np.uint8),b.arrays,True)
                    np.testing.assert_array_equal(a.arrays[0],np.full(r.shapes[0],np.float32(7/255)))
                    self.assertAlmostEqual(float(b.arrays[0][0,0,0]),13/255)
                    self.assertAlmostEqual(parts['rknn_device_ms'],1.234)
                    self.assertEqual(parts['rknn_perf_query_rc'],0)
                    if prealloc:self.assertEqual(parts['rknn_copy_wall_ms'],0)
                    abort.set();self.assertIsNone(pool.acquire(abort))
                    a.release();a.release();b.release()
                    self.assertEqual(pool.free.qsize(),2)
                finally:pool.reclaim();r.release();r.release()

    def test_bound_pool_sizes_dynamic_and_fixed_contexts(self):
        for slots,binding in ((4,'dynamic'),(1,'fixed')):
            with self.subTest(slots=slots,binding=binding):
                r=self.bound_runtime(slots,binding);inputs=native.BoundPool([r],True,slots)
                outputs=native.BoundPool([r],False,slots);abort=threading.Event()
                try:
                    in_lease=inputs.acquire(abort);out_lease=outputs.acquire(abort,0)
                    batch=np.full((1,640,640,3),np.float16(.5),np.float16)
                    np.copyto(in_lease.arrays[0],batch)
                    result,parts=r.run_into(in_lease.arrays[0],out_lease.arrays)
                    self.assertEqual(result[0].shape,(1,80,8400))
                    self.assertTrue(np.all(result[0]==np.float16(.5)))
                    self.assertTrue(parts['rknn_output_sync_wall_ms']>=0)
                    self.assertEqual(r.info['bound_memory']['fixed_binding'],binding=='fixed')
                    if binding=='fixed':self.assertNotIn('rknn_input_bind_wall_ms',parts)
                finally:
                    inputs.reclaim();outputs.reclaim();r.release()

    def test_sdk_perf_detail_is_queried_before_output_release(self):
        r=native.Runtime(self.lib,Path('fixture.rknn'),self.library,'0',True,
            'fp16-ready','fp16',collect_perf=True)
        try:
            batch=np.full((1,640,640,3),np.float16(.25),np.float16)
            outputs=[np.empty(shape,np.float16) for shape in r.shapes]
            _,parts=r.run_into(batch,outputs,profile=True)
            self.assertEqual(parts['rknn_perf_query_rc'],0)
            self.assertEqual(parts['rknn_perf_detail_query_rc'],0)
            self.assertIn('Conv fixture',parts['rknn_perf_detail'])
            self.assertGreater(parts['rknn_perf_detail_bytes'],0)
        finally:r.release()

    def test_api_failures_release_partial_runtime_allocations(self):
        for mode in ('uint8','fp16-pass'):
            for prealloc in (False,True):
                for stage in (1,2,3,4):
                    with self.subTest(mode=mode,prealloc=prealloc,stage=stage):
                        r=self.runtime(prealloc,mode)
                        try:
                            self.fixture.fixture_fail_stage(stage)
                            with self.assertRaises(RuntimeError):r.inference([np.zeros((1,640,640,3),np.uint8)])
                            self.assertEqual(self.fixture.fixture_live_buffers(),0)
                        finally:self.fixture.fixture_fail_stage(0);r.release()

    def test_pipeline_error_reclaims_leases_and_stops_workers(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);clip=root/'clip.avi'
            writer=cv2.VideoWriter(str(clip),cv2.VideoWriter_fourcc(*'MJPG'),10,(80,40))
            for i in range(8):writer.write(np.full((40,80,3),i*3,np.uint8))
            writer.release()
            for fail in (False,True):
                runtimes=[self.runtime(True) for _ in range(2)]
                pool=native.OutputPool(runtimes[0].shapes,2)
                e=SimpleNamespace(runtimes=runtimes,output_pool=pool)
                args=SimpleNamespace(video=clip,once=True,batch=1,queue_batches=2,
                    post_workers=1,mode='detect',decode_threads=1)
                try:
                    if fail:self.fixture.fixture_fail_stage(3)
                    if fail:
                        with self.assertRaisesRegex(RuntimeError,'outputs_get'):fast.execute(e,args,5)
                    else:
                        result=fast.execute(e,args,5)
                        self.assertEqual(result['completed'],8)
                        self.assertGreater(result['process_cpu_ms_per_image'],0)
                        self.assertAlmostEqual(result['process_cpu_ms']/8,result['process_cpu_ms_per_image'])
                    self.assertFalse(e.workers_active)
                    self.assertEqual(len(pool.active),0)
                    self.assertEqual(pool.free.qsize(),2)
                finally:
                    self.fixture.fixture_fail_stage(0)
                    for r in runtimes:r.release()



if __name__=='__main__':unittest.main()
