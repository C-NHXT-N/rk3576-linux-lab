# SPDX-License-Identifier: AGPL-3.0-only
"""Bounded drawing/output; leases stay alive until BGR consumption completes."""
from collections import OrderedDict
import queue
import threading
import time

import cached_render
import thread_schedule


class QueuedEncoder:
    def __init__(self,factory,shared_cache=False):
        self.factory=factory;self.free=queue.Queue(2);self.pending=queue.Queue(2)
        labels=OrderedDict() if shared_cache else None
        self.renderers=[cached_render.Renderer(labels=labels) for _ in range(2)]
        for renderer in self.renderers:self.free.put(renderer)
        self.shared_cache=shared_cache
        self.error=None;self.encoder=None;self.frames=0;self.closed=False;self.encode_cpu_ms=0.;self.encode_wall_ms=0.
        self.thread=threading.Thread(target=self._work,name='encoder',daemon=True);self.thread.start()

    def _work(self):
        try:
            thread_schedule.apply('encoder')
            while True:
                task=self.pending.get()
                if task is None:break
                renderer,image,lease=task
                try:
                    if self.encoder is None:self.encoder=self.factory(image)
                    wall,cpu=time.perf_counter(),time.thread_time()
                    self.encoder.write(image)
                    self.encode_wall_ms+=(time.perf_counter()-wall)*1000;self.encode_cpu_ms+=(time.thread_time()-cpu)*1000;self.frames+=1
                finally:self._release(renderer,lease)
        except BaseException as error:self.error=error

    def _check(self):
        if self.error:raise RuntimeError('Output worker failed: '+str(self.error)) from self.error

    def _release(self,renderer,lease):
        try:
            if lease:lease.release()
        finally:self.free.put_nowait(renderer)

    def draw_submit(self,image,detections,detail,canvas=None,lease=None):
        # The optional lease transfers at entry, including failure branches.
        renderer=None
        try:
            started=time.perf_counter()
            while True:
                self._check()
                try:renderer=self.free.get(timeout=.1);break
                except queue.Full:pass
                except queue.Empty:pass
            waited=(time.perf_counter()-started)*1000;wall,cpu=time.perf_counter(),time.thread_time()
            rendered=renderer.draw(image,detections,detail,canvas=canvas)
            drawing=(time.perf_counter()-wall)*1000;drawing_cpu=(time.thread_time()-cpu)*1000
            while True:
                self._check()
                try:self.pending.put((renderer,rendered,lease),timeout=.1);break
                except queue.Full:pass
            renderer=lease=None
            return drawing,drawing_cpu,waited
        finally:
            if renderer:self._release(renderer,lease)
            elif lease:lease.release()

    def close(self):
        if self.closed:return
        self.closed=True
        try:
            while self.thread.is_alive() and not self.error:
                try:self.pending.put(None,timeout=.1);break
                except queue.Full:pass
            self.thread.join(timeout=30)
            if self.thread.is_alive():
                if self.encoder and hasattr(self.encoder,'cancel'):self.encoder.cancel()
                self.thread.join(timeout=12)
                if self.thread.is_alive():raise TimeoutError('Encoder worker failed to drain')
        finally:
            if not self.thread.is_alive():
                while True:
                    try:task=self.pending.get_nowait()
                    except queue.Empty:break
                    if task is not None:self._release(task[0],task[2])
                if self.encoder:self.encoder.close()
        self._check()
        entries=len(self.renderers[0].labels) if self.shared_cache else sum(len(r.labels) for r in self.renderers)
        cache=dict(hits=sum(r.hits for r in self.renderers),misses=sum(r.misses for r in self.renderers),entries=entries,shared=self.shared_cache)
        self.evidence=dict(backend='async',canvases=2,frames=self.frames,encode_wall_ms=self.encode_wall_ms,
            encode_cpu_ms=self.encode_cpu_ms,render_cache=cache,encoder=getattr(self.encoder,'evidence',{'backend':'x264'}))
