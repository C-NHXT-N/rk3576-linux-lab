# SPDX-License-Identifier: AGPL-3.0-only
"""Pipelined MPP encoding with NEON BGR-to-NV12 conversion."""
import ctypes as ct
from fractions import Fraction
import json
import os
from pathlib import Path
import subprocess
import time

import media_backends as media
import vision

ROOT=Path(__file__).resolve().parent
LIBRARY=ROOT/'build/native_output.so'


def build():
    LIBRARY.parent.mkdir(exist_ok=True)
    temporary=LIBRARY.with_suffix(f'.{os.getpid()}.tmp.so')
    command=['g++','-std=c++17','-O3','-fPIC','-shared','-pthread','-I/usr/include/rockchip',
        str(Path(__file__).with_suffix('.cpp')),'-lrockchip_mpp','-o',str(temporary)]
    try:
        subprocess.run(command,check=True,timeout=120)
        temporary.replace(LIBRARY)
    finally:temporary.unlink(missing_ok=True)
    vision.atomic_json(LIBRARY.with_suffix('.json'),dict(command=command,input_buffers=3,
        scope='independent packet draining; explicit input-frame return'))


def library():
    lib=ct.CDLL(str(LIBRARY))
    lib.out_open.argtypes=[ct.c_char_p]+[ct.c_int]*5+[ct.c_char_p,ct.c_uint];lib.out_open.restype=ct.c_void_p
    lib.out_write.argtypes=[ct.c_void_p,ct.c_void_p,ct.c_int,ct.c_char_p,ct.c_uint]
    lib.out_finish.argtypes=[ct.c_void_p,ct.c_char_p,ct.c_uint]
    lib.out_close.argtypes=[ct.c_void_p];lib.out_cancel.argtypes=[ct.c_void_p]
    lib.out_stats.argtypes=[ct.c_void_p];lib.out_stats.restype=ct.c_char_p
    lib.out_test.argtypes=[ct.c_void_p,ct.c_int,ct.c_int,ct.c_int,ct.c_char_p,ct.c_uint]
    return lib


class Encoder:
    def __init__(self,path,image,fps,bitrate=14000000):
        self.path=Path(path);self.raw=self.path.with_suffix('.h264');self.fps=fps;self.handle=None;self.closed=False
        self.lib=library();self.error=ct.create_string_buffer(2048)
        rate=Fraction(fps).limit_denominator(1001);height,width=image.shape[:2]
        self.handle=self.lib.out_open(str(self.raw).encode(),width,height,rate.numerator,rate.denominator,
            bitrate,self.error,len(self.error))
        if not self.handle:raise RuntimeError(self.error.value.decode())
        self.evidence=dict(backend='mpp-native',pipeline='pipelined',color='neon',input_buffers=3,
            bitrate_target=bitrate,input_memory='MPP default group',
            transport='caller BGR consumed before write returns; three independent NV12 buffers and packet thread',
            buffer_release='KEY_INPUT_FRAME plus end-of-image',runtime=media.runtime_evidence(os.getpid()))

    def write(self,image):
        if self.closed:raise RuntimeError('Encoder already closed')
        if self.lib.out_write(self.handle,image.ctypes.data,image.strides[0],
                self.error,len(self.error)):
            raise RuntimeError(self.error.value.decode())

    def cancel(self):
        if self.handle:self.lib.out_cancel(self.handle)

    def configure_test(self,delay_ms=0,fail_after=-1,partition_bytes=0):
        if self.lib.out_test(self.handle,delay_ms,fail_after,partition_bytes,self.error,len(self.error)):
            raise RuntimeError(self.error.value.decode())

    def close(self):
        if self.closed:return
        self.closed=True
        try:
            code=self.lib.out_finish(self.handle,self.error,len(self.error))
            self.evidence.update(json.loads(self.lib.out_stats(self.handle).decode()))
            if code:raise RuntimeError(self.error.value.decode())
            stats=self.evidence
            if stats['frames'] and (stats['frames']!=stats['completed'] or not stats['eos_received'] or stats['free_buffers']!=3):
                raise RuntimeError('Pipelined encoder did not drain/return every input')
        finally:
            if self.handle:self.lib.out_close(self.handle);self.handle=None
        if not self.evidence['frames']:
            self.raw.unlink(missing_ok=True);return
        started=time.perf_counter()
        with self.path.with_suffix('.mux.log').open('w') as log:
            subprocess.run(['ffmpeg','-hide_banner','-loglevel','error','-y','-r',str(self.fps),'-i',str(self.raw),
                '-an','-c:v','copy','-color_range','tv','-colorspace','smpte170m','-movflags','+faststart',str(self.path)],
                stdout=log,stderr=log,check=True,timeout=30)
        self.evidence['mux_ms']=(time.perf_counter()-started)*1000
        self.raw.unlink(missing_ok=True)
