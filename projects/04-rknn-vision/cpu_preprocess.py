# SPDX-License-Identifier: AGPL-3.0-only
"""Fixed 1280x720 exact CPU preparation, caller-owned FP16 destination."""
import ctypes as ct
import hashlib
import json
from pathlib import Path
import subprocess
import time
import weakref

import numpy as np
import vision

ROOT=Path(__file__).resolve().parent
LIBRARY=ROOT/'build/cpu_preprocess.so'


def digest(path):return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def build():
    LIBRARY.parent.mkdir(exist_ok=True)
    source=Path(__file__).with_suffix('.cpp')
    command=['g++','-std=c++17','-O3','-fPIC','-shared','-fno-fast-math','-ffp-contract=off',str(source),'-o',str(LIBRARY)]
    subprocess.run(command,check=True,timeout=60)
    manifest={'command':command,'source_sha256':digest(source),'library_sha256':digest(LIBRARY)}
    vision.atomic_json(LIBRARY.with_suffix('.json'),manifest)
    return manifest


class Processor:
    fused=True
    def __init__(self):
        self.info=json.loads(LIBRARY.with_suffix('.json').read_text())
        if digest(Path(__file__).with_suffix('.cpp'))!=self.info['source_sha256'] or digest(LIBRARY)!=self.info['library_sha256']:
            raise RuntimeError('CPU preparation build/source mismatch; rebuild explicitly')
        self.lib=ct.CDLL(str(LIBRARY))
        self.lib.cp_run.argtypes=[ct.c_void_p,ct.c_size_t,ct.c_void_p,ct.c_void_p]
        self.lib.cp_check_lut.argtypes=[ct.c_void_p]
        self.lut=(np.arange(256,dtype=np.float32)/np.float32(255)).astype(np.float16).view(np.uint16)
        if self.lib.cp_check_lut(self.lut.ctypes.data):raise RuntimeError('NEON normalization differs from reference LUT')
        self.initialized={};self.calls=0;self.last_timing={}

    def batch(self,images,batch_size=None,out=None):
        if len(images)!=1 or batch_size not in (None,1):raise ValueError('CPU fused requires batch=1')
        image=images[0]
        if image.dtype!=np.uint8 or image.shape!=(720,1280,3) or not image.flags.c_contiguous:
            raise ValueError('CPU fused requires contiguous 1280x720 BGR UINT8')
        output=np.empty((1,640,640,3),np.float16) if out is None else out
        if output.dtype!=np.float16 or output.shape!=(1,640,640,3) or not output.flags.c_contiguous or not output.flags.writeable:
            raise ValueError('CPU fused requires writable packed FP16 destination')
        wall,cpu=time.perf_counter(),time.thread_time()
        # A weak reference prevents address reuse from skipping initialization.
        address=output.ctypes.data
        ref=self.initialized.get(address)
        if ref is None or ref() is not output:
            output[:, :140]=0;output[:, 500:]=0
            self.initialized={p:r for p,r in self.initialized.items() if r() is not None}
            self.initialized[address]=weakref.ref(output)
        clear_wall,clear_cpu=time.perf_counter(),time.thread_time()
        if self.lib.cp_run(image.ctypes.data,image.strides[0],address,self.lut.ctypes.data):
            raise RuntimeError('CPU fused preparation failed')
        end,end_cpu=time.perf_counter(),time.thread_time()
        self.calls+=1
        self.last_timing={'cpu_fused_border_wall_ms':(clear_wall-wall)*1000,'cpu_fused_border_cpu_ms':(clear_cpu-cpu)*1000,
            'cpu_fused_kernel_wall_ms':(end-clear_wall)*1000,'cpu_fused_kernel_cpu_ms':(end_cpu-clear_cpu)*1000}
        return output,[dict(width=1280,height=720,left=0,top=140,scale_x=.5,scale_y=.5)]

    def evidence(self):
        return {'backend':'cpu-fused','build':self.info,'successful_calls':self.calls,
            'rounding':'(four UINT8 pixels + 2) >> 2; FP32 x/255 -> FP16 RNE',
            'copies':'single BGR source pass directly to caller FP16; padded rows initialized once per buffer'}

    def close(self):self.initialized.clear()


if __name__=='__main__':print(json.dumps(build()))
