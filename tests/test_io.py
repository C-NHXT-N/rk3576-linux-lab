# SPDX-License-Identifier: AGPL-3.0-only
import sys
from pathlib import Path
import threading
from types import SimpleNamespace
import unittest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'04-rknn-vision'))
try:
 import native_rknn as nr
 import experiment
except ImportError:nr=None

@unittest.skipIf(nr is None,'Requires board NumPy/OpenCV')
class BoundOwnershipTests(unittest.TestCase):
 def runtimes(self,count=4,slots=2):
  return [SimpleNamespace(input_arrays=[object() for _ in range(slots)],
   output_arrays=[[object(),object()] for _ in range(slots)]) for _ in range(count)]
 def test_context_routing_and_exact_capacity(self):
  pool=nr.BoundPool(self.runtimes(),True,2);abort=threading.Event();leases=[pool.acquire(abort) for _ in range(8)]
  self.assertEqual([x.worker for x in leases],[0,1,2,3,0,1,2,3])
  ready=nr.PreparedQueues(4,8)
  for lease in leases:ready.put({'target_context':lease.worker,'slot':lease.slot})
  for i,q in enumerate(ready.queues):self.assertEqual([q.get()['target_context'] for _ in range(2)],[i,i])
  abort.set();self.assertIsNone(pool.acquire(abort))
  pool.reclaim();self.assertEqual(len(pool.active),0);self.assertEqual([q.qsize() for q in pool.free],[2,2,2,2])
 def test_two_contexts_share_eight_slots_without_skew(self):
  pool=nr.BoundPool(self.runtimes(2,4),True,4);abort=threading.Event()
  leases=[pool.acquire(abort) for _ in range(8)]
  self.assertEqual([x.worker for x in leases],[0,1,0,1,0,1,0,1])
  self.assertEqual([q.qsize() for q in pool.free],[0,0])
  pool.reclaim();self.assertEqual([q.qsize() for q in pool.free],[4,4])
 def test_fixed_binding_lease_prevents_early_output_reuse(self):
  pool=nr.BoundPool(self.runtimes(slots=1),False,1);abort=threading.Event()
  held=pool.acquire(abort,1)
  self.assertEqual(pool.free[1].qsize(),0)
  held.release();other=pool.acquire(abort,1)
  self.assertEqual((other.worker,other.slot),(1,0))
  pool.reclaim();self.assertEqual([q.qsize() for q in pool.free],[1,1,1,1])
 def test_output_held_until_release_and_idempotent_cancel(self):
  pool=nr.BoundPool(self.runtimes(),False,2);abort=threading.Event()
  held=pool.acquire(abort,2);other=pool.acquire(abort,2)
  self.assertNotEqual(held.slot,other.slot);self.assertEqual(pool.free[2].qsize(),0)
  held.release();held.release();self.assertEqual(pool.free[2].qsize(),1)
  pool.reclaim();self.assertEqual(pool.free[2].qsize(),2);self.assertEqual(len(pool.active),0)
 def test_native_capacity_does_not_change_logical_tensor(self):
  import numpy as np
  a=nr.output_array((1,4,8400),np.float16,134400)
  self.assertEqual(a.nbytes,67200)
  root=a
  while isinstance(root.base,np.ndarray):root=root.base
  self.assertGreaterEqual(root.nbytes,134400)
 def test_applicability_flags_do_not_enter_timing_quantiles(self):
  import cv2,numpy as np,tempfile
  from tests.test_batch_pipeline import Runtime
  import fast_bench as fast
  with tempfile.TemporaryDirectory() as d:
   clip=Path(d)/'clip.avi';w=cv2.VideoWriter(str(clip),cv2.VideoWriter_fourcc(*'MJPG'),10,(80,40))
   for _ in range(4):w.write(np.zeros((40,80,3),np.uint8))
   w.release();r=Runtime()
   def run(batch,outputs,profile=False):
    for dst,src in zip(outputs,r.inference([batch])):np.copyto(dst,src)
    return outputs,{'rknn_inputs_set_applicable':False,'rknn_input_sync_wall_ms':.1}
   r.run_into=run
   engine=SimpleNamespace(runtimes=[r],output_pool=nr.OutputPool([(1,80,2),(1,4,2)],8))
   args=SimpleNamespace(video=clip,once=False,batch=1,queue_batches=8,post_workers=1,mode='infer',max_frames=4)
   result=fast.execute(engine,args,5)
   self.assertEqual(result['completed'],4)
   self.assertNotIn('rknn_inputs_set_applicable',result['runtime_metrics'])
   self.assertIn('rknn_input_sync_wall_ms',result['runtime_metrics'])

if __name__=='__main__':unittest.main()
