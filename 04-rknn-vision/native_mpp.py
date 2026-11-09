# SPDX-License-Identifier: AGPL-3.0-only
"""MPP C++ bridge with a bounded compressed queue and leased original BGR."""
import ctypes as ct
import json
import os
from pathlib import Path
import subprocess
import threading
import time
import weakref
import numpy as np

import media_backends as media
import media_support
import thread_accounting
import vision
import thread_schedule

ROOT=Path(__file__).resolve().parent
LIBRARY=ROOT/'build/native_mpp.so'
PARTS=('receive','sync_begin','uv_planar','convert','release')
digest=media_support.digest


def hardware_proven(proof,frames):
    current=proof.get('current_context',{})
    runtime=proof.get('runtime',[])
    mapped=any(any('librockchip_mpp.so' in name for name in r.get('library_maps',[])) and
        any(any(w in name for w in ('mpp_service','rkvdec','vpu_service')) for name in r.get('device_fds',[])) for r in runtime)
    return bool(mapped and current.get('hardware_frames')==frames and current.get('eos_received') and proof.get('eof_drained'))


def build():
    headers=ROOT/'build/FFmpeg-n5.1.6'
    if not (headers/'libavutil/avconfig.h').exists():media_support.ensure_headers()
    LIBRARY.parent.mkdir(exist_ok=True)
    source=Path(__file__).with_suffix('.cpp')
    mpp=Path('/lib/aarch64-linux-gnu/librockchip_mpp.so.1').resolve(strict=True)
    command=['g++','-std=c++17','-O3','-fPIC','-shared','-pthread','-fno-fast-math','-ffp-contract=off','-I'+str(headers),
             '-I/usr/include/rockchip',str(source),'-lrockchip_mpp','-ldl','-o',str(LIBRARY)]
    subprocess.run(command,check=True,timeout=90)
    manifest={'command':command,'source_sha256':digest(source),'library_sha256':digest(LIBRARY),
        'mpp_library':str(mpp),'mpp_sha256':digest(mpp),
        'mpp_headers_sha256':{str(p):digest(p) for p in Path('/usr/include/rockchip').glob('*.h')},
        'ffmpeg_archive_sha256':media_support.ARCHIVE_SHA256}
    manifest['pixel_source_sha256']=digest(ROOT/'cpu_preprocess.cpp')
    vision.atomic_json(LIBRARY.with_suffix('.json'),manifest)
    return {k:v for k,v in manifest.items() if k!='mpp_headers_sha256'}


class Timing(ct.Structure):
    _fields_=[('wall',ct.c_double*5),('cpu',ct.c_double*5),('pts',ct.c_int64),('prepare_wall',ct.c_double),('prepare_cpu',ct.c_double)]


class VideoReader:
    def __init__(self,path,loop=True,decode_threads=4,pool_size=11,frame_canvas=False):
        self.path,self.loop=str(path),loop
        self.handle=None;self.stop=threading.Event();self.pool=media_support.FramePool(pool_size,frame_canvas)
        self.index,self.cycle=0,0;self._stats={};self._completed_cycles=[]
        meta=media.probe(path)
        if (meta['width'],meta['height'])!=(1280,720) or meta.get('pix_fmt')!='yuv420p':
            raise ValueError('Native MPP requires 1280x720, 8-bit limited-range H.264 YUV420')
        self.count,self.fps=meta['frames'],meta['fps']
        manifest=json.loads(LIBRARY.with_suffix('.json').read_text())
        for p,key in [(Path(__file__).with_suffix('.cpp'),'source_sha256'),(LIBRARY,'library_sha256'),
                      (Path(manifest['mpp_library']),'mpp_sha256')]:
            if digest(p)!=manifest[key]:raise RuntimeError('Native MPP build/library mismatch; rebuild explicitly')
        if digest(ROOT/'cpu_preprocess.cpp')!=manifest.get('pixel_source_sha256'):raise RuntimeError('Native pixel kernel changed; rebuild')
        if any(digest(p)!=h for p,h in manifest['mpp_headers_sha256'].items()):
            raise RuntimeError('Native MPP headers changed; rebuild explicitly')
        self.paths=media_support.reference_libraries()
        self.lib=ct.CDLL(str(LIBRARY))
        self.lib.mp_open.argtypes=[ct.c_char_p]*5+[ct.c_char_p,ct.c_uint];self.lib.mp_open.restype=ct.c_void_p
        self.lib.mp_read.argtypes=[ct.c_void_p,ct.c_void_p,ct.c_size_t,ct.POINTER(Timing),ct.c_char_p,ct.c_uint]
        self.lib.mp_stats.argtypes=[ct.c_void_p];self.lib.mp_stats.restype=ct.c_char_p
        self.lib.mp_sender_tid.argtypes=[ct.c_void_p];self.lib.mp_sender_tid.restype=ct.c_int
        self.lib.mp_cancel.argtypes=[ct.c_void_p];self.lib.mp_close.argtypes=[ct.c_void_p]
        self._evidence={'backend':'mpp-native','build':{k:v for k,v in manifest.items() if k!='mpp_headers_sha256'},
            'reference_libraries':{p:digest(p) for p in self.paths},'runtime':[],
            'frames_read':0,'eof_drained':False,'frame_pool_capacity':pool_size,
            'frame_canvas':frame_canvas,
            'transport':'in-process MPP NV12 -> borrowed Y + reusable planar UV -> reference swscale -> leased BGR',
            'decode_threads_argument':decode_threads,'software_decode_workers':0,
            'start_policy':'submission is parked until first read, after measurement start barrier'}
        self._open()

    def _open(self):
        before=thread_accounting.before_creation();error=ct.create_string_buffer(1024)
        self.handle=self.lib.mp_open(self.path.encode(),*[p.encode() for p in self.paths],error,len(error))
        if not self.handle:raise RuntimeError(error.value.decode())
        thread_accounting.after_creation(before,'mpp_internal','created during MPP native initialization')
        thread_accounting.mark_native(self.lib.mp_sender_tid(self.handle),'mpp_submit','registered native packet submission thread')
        thread_schedule.apply('mpp_submit',self.lib.mp_sender_tid(self.handle))
        maps={line.split()[-1] for line in Path('/proc/self/maps').read_text().splitlines() if 'librockchip_mpp.so' in line}
        expected=Path(self._evidence['build']['mpp_library']).resolve()
        if {Path(p).resolve() for p in maps}!={expected}:
            self.close();raise RuntimeError('Mapped a different MPP runtime')

    @property
    def evidence(self):
        if self.handle:self._stats=json.loads(self.lib.mp_stats(self.handle).decode())
        return {**self._evidence,'current_context':self._stats,'completed_cycles':self._completed_cycles}

    def _read_into(self,lease):
        timing,error=Timing(),ct.create_string_buffer(1024)
        rc=self.lib.mp_read(self.handle,lease.image.ctypes.data,lease.image.nbytes+64,ct.byref(timing),error,len(error))
        if rc<0:raise RuntimeError(error.value.decode())
        return rc,timing

    def read(self):
        if self.stop.is_set():return None
        if self.index>=self.count:
            lease=self.pool.acquire(self.stop)
            if lease is None:return None
            try:
                rc,_=self._read_into(lease)
                if rc==2:return None
                if rc!=0:raise RuntimeError('MPP produced more frames than declared')
            finally:lease.release()
            self._evidence['eof_drained']=True
            if not self.loop:return None
            self._completed_cycles.append(self.evidence['current_context'])
            self.lib.mp_close(self.handle);self.handle=None;self._open()
            self.index=0;self.cycle+=1
        started=time.perf_counter();lease=self.pool.acquire(self.stop)
        if lease is None:return None
        pool_wait=(time.perf_counter()-started)*1000
        try:
            rc,timing=self._read_into(lease)
            if rc==2:lease.release();return None
            if rc!=1:raise RuntimeError(f'MPP EOF before declared frame count at {self.index}')
            parts={f'mpp_{name}_{kind}_ms':float(getattr(timing,kind)[i]) for i,name in enumerate(PARTS) for kind in ('wall','cpu')}
            item={'image':lease.image,'image_lease':lease,'source_frame':self.index,'cycle':self.cycle,
                'source_pts':int(timing.pts),'decode_started':started,'decode_ms':(time.perf_counter()-started)*1000,
                'decode_grab_ms':timing.wall[0],'decode_retrieve_ms':sum(timing.wall[1:]),
                'decode_cpu_ms':sum(timing.cpu),'decode_pool_wait_ms':pool_wait,
                'decode_convert_cpu_ms':timing.cpu[3],'media_parts':parts}
            self.index+=1;self._evidence['frames_read']+=1
            if self.index==1:self._evidence['runtime'].append(media.runtime_evidence(os.getpid()))
            return item
        except BaseException:lease.release();raise

    def cancel(self):
        self.stop.set()
        if self.handle:self.lib.mp_cancel(self.handle)

    def close(self):
        self.cancel()
        if self.handle:
            self._stats=json.loads(self.lib.mp_stats(self.handle).decode())
            self.lib.mp_close(self.handle);self.handle=None
        self.pool.close();self._evidence['active_frame_leases_after_close']=len(self.pool.active)



class FusedReader(VideoReader):
    """Receive and prepare into a caller-owned RKNN slot; no full BGR in detect."""
    def __init__(self,*args,keep_image=False,reuse_padding=False,**kwargs):
        self.keep_image=keep_image
        self.reuse_padding=reuse_padding;self.padding_refs={};self.padding_clears=0
        super().__init__(*args,**kwargs)
        self.lib.mp_read_fused.argtypes=[ct.c_void_p,ct.c_void_p,ct.c_size_t,ct.c_void_p,ct.c_int,ct.POINTER(Timing),ct.c_char_p,ct.c_uint]
        self._evidence.update(backend='mpp-fused',transport='NV12 -> 24-row reference BGR tiles -> bound FP16; optional retained display BGR',retained_bgr=keep_image,reuse_padding=reuse_padding)

    def read_prepared(self,output):
        if output.dtype!=np.float16 or output.shape!=(1,640,640,3) or not output.flags.c_contiguous:
            raise ValueError('Fused MPP requires packed writable FP16 input')
        if self.stop.is_set():return None
        if self.index>=self.count:
            if not self.loop:return None
            self._completed_cycles.append(self.evidence['current_context'])
            self.lib.mp_close(self.handle);self.handle=None;self._open();self.index=0;self.cycle+=1
        started=time.perf_counter();cpu=time.thread_time();lease=self.pool.acquire(self.stop) if self.keep_image else None
        if self.keep_image and lease is None:return None
        timing,error=Timing(),ct.create_string_buffer(1024)
        try:
            ref=self.padding_refs.get(output.ctypes.data)
            clear=not self.reuse_padding or ref is None or ref() is not output
            rc=self.lib.mp_read_fused(self.handle,lease.image.ctypes.data if lease else None,
                lease.image.nbytes+64 if lease else 0,output.ctypes.data,int(clear),ct.byref(timing),error,len(error))
            if rc<0:raise RuntimeError(error.value.decode())
            if rc!=1:
                if lease:lease.release()
                if rc==2:return None
                raise RuntimeError('Fused MPP ended before declared EOF')
            if clear:
                self.padding_refs={p:r for p,r in self.padding_refs.items() if r() is not None}
                self.padding_refs[output.ctypes.data]=weakref.ref(output);self.padding_clears+=1
            self._evidence['padding_initializations']=self.padding_clears
            parts={f'mpp_{name}_{kind}_ms':float(getattr(timing,kind)[i]) for i,name in enumerate(PARTS) for kind in ('wall','cpu')}
            item=dict(source_frame=self.index,cycle=self.cycle,source_pts=int(timing.pts),decode_started=started,
                decode_ms=sum(timing.wall),decode_grab_ms=timing.wall[0],decode_retrieve_ms=sum(timing.wall[1:]),
                decode_cpu_ms=sum(timing.cpu),decode_convert_cpu_ms=timing.cpu[3],decode_pool_wait_ms=0.,
                media_parts=parts,prepared=output,transforms=[dict(width=1280,height=720,left=0,top=140,scale_x=.5,scale_y=.5)],
                fused_prepare_ms=timing.prepare_wall,fused_prepare_cpu_ms=timing.prepare_cpu,
                fused_total_cpu_ms=(time.thread_time()-cpu)*1000)
            if lease:item.update(image=lease.image,image_lease=lease,canvas=lease.canvas)
            self.index+=1;self._evidence['frames_read']+=1
            if self.index==1:self._evidence['runtime'].append(media.runtime_evidence(os.getpid()))
            if self.index==self.count:
                end=Timing()
                rc=self.lib.mp_read_fused(self.handle,None,0,output.ctypes.data,0,ct.byref(end),error,len(error))
                if rc!=0:raise RuntimeError('Fused MPP EOF did not drain: '+error.value.decode())
                self._evidence['eof_drained']=True
            return item
        except BaseException:
            if lease:lease.release()
            raise

    def read(self):
        raise RuntimeError('FusedReader must prepare directly into an input slot')


class DirectSource:
    def __init__(self,reader):self.reader=reader
    def cancel(self):self.reader.cancel()
    def close(self):self.reader.close()


if __name__=='__main__':print(json.dumps(build()))
