# SPDX-License-Identifier: AGPL-3.0-only
"""Synchronous RKNN C API, task-owned pooled outputs and per-call timing."""
import ctypes as ct
import hashlib
import json
from pathlib import Path
import queue
import subprocess
import threading
import time

import numpy as np
from detector import OUTPUT_NODES
import vision
import thread_accounting

ROOT = Path(__file__).resolve().parent
LIBRARY = ROOT/'build/native_rknn.so'
HEADER = ROOT/'third_party/rknn_api.h'
HEADER_SHA256 = '2d4160cd868efd7b83a72587e411c16d6972da5876e067bd73665cea778ce666'
PARTS = ('inputs_set', 'run', 'outputs_get', 'copy', 'outputs_release')
PASSTHROUGH_MODEL_SHA256 = '24992fbdfb161f2380b67a58ac3b028d0832de5afd81868adaea987a278d4b24'

def require_passthrough_model(model):
    digest = hashlib.sha256(model.read_bytes()).hexdigest()
    if digest == PASSTHROUGH_MODEL_SHA256:
        return
    manifest = model.with_suffix('.json')
    expected = dict(model_sha256=digest, target='rk3576', precision='fp16',
                    batch=1, input_shape=[1,640,640,3], outputs=OUTPUT_NODES,
                    preprocessing='rgb/255')
    if manifest.is_file():
        actual = json.loads(manifest.read_text(encoding='utf-8'))
        if all(actual.get(key) == value for key,value in expected.items()):
            return
    raise RuntimeError('FP16 pass-through requires the retained model or a matching convert.py FP16 manifest')


def build():
    if not HEADER.is_file():
        raise RuntimeError('Fetch the official C header with python fetch_sdk.py --role header')
    if hashlib.sha256(HEADER.read_bytes()).hexdigest() != HEADER_SHA256:
        raise RuntimeError('Pinned official RKNN v2.5.0 header hash mismatch')
    LIBRARY.parent.mkdir(exist_ok=True)
    source = Path(__file__).with_suffix('.cpp')
    command = ['g++', '-std=c++17', '-O3', '-fPIC', '-shared', '-fno-fast-math',
               '-ffp-contract=off', str(source), '-ldl', '-o', str(LIBRARY)]
    subprocess.run(command, check=True, timeout=60)
    manifest = {'source_sha256': hashlib.sha256(source.read_bytes()).hexdigest(),
                'header_sha256': HEADER_SHA256, 'library_sha256': hashlib.sha256(LIBRARY.read_bytes()).hexdigest(),
                'header_source': 'https://github.com/airockchip/rknn-toolkit2/blob/v2.5.0/rknpu2/runtime/Linux/librknn_api/include/rknn_api.h',
                'command': command}
    vision.atomic_json(LIBRARY.with_suffix('.json'), manifest)
    return manifest


class Timing(ct.Structure):
    _fields_ = [('wall', ct.c_double*5), ('cpu', ct.c_double*5),
                ('device_ms', ct.c_double), ('query_rc', ct.c_int),
                ('normalize_wall_ms', ct.c_double), ('normalize_cpu_ms', ct.c_double)]


def load():
    manifest = json.loads(LIBRARY.with_suffix('.json').read_text())
    for path, key in [(Path(__file__).with_suffix('.cpp'), 'source_sha256'),
                      (HEADER, 'header_sha256'), (LIBRARY, 'library_sha256')]:
        if hashlib.sha256(path.read_bytes()).hexdigest() != manifest[key]:
            raise RuntimeError('Rebuild native RKNN backend: '+str(path))
    lib = ct.CDLL(str(LIBRARY))  # CDLL releases the GIL during the entire C call.
    lib.nr_create.argtypes = [ct.c_char_p, ct.c_char_p, ct.c_int, ct.c_int, ct.c_char_p, ct.c_uint]
    lib.nr_create.restype = ct.c_void_p
    lib.nr_metadata.argtypes = [ct.c_void_p]; lib.nr_metadata.restype = ct.c_char_p
    lib.nr_destroy.argtypes = [ct.c_void_p]; lib.nr_destroy.restype = None
    lib.nr_infer.argtypes = [ct.c_void_p, ct.c_void_p, ct.c_uint, ct.c_void_p, ct.c_uint,
                            ct.c_void_p, ct.c_uint, ct.c_int, ct.c_int, ct.POINTER(Timing),
                            ct.c_char_p, ct.c_uint,ct.c_char_p,ct.c_uint,
                            ct.POINTER(ct.c_uint),ct.POINTER(ct.c_int)]
    lib.nr_infer.restype = ct.c_int
    lib.nr_lut.argtypes = [ct.c_void_p,ct.c_uint]; lib.nr_lut.restype = ct.c_int
    return lib


def lut_bits(lib):
    values=np.empty(256,np.uint16)
    if lib.nr_lut(values.ctypes.data,len(values)):
        raise RuntimeError('Could not obtain normalization table')
    return values


class Lease:
    def __init__(self, pool, arrays):
        self.pool, self.arrays, self.released = pool, arrays, False

    def release(self):
        with self.pool.lock:
            if not self.released:
                self.released = True
                self.pool.active.pop(id(self), None)
                self.pool.free.put_nowait(self.arrays)


def output_array(shape,dtype,capacity=None):
    dtype=np.dtype(dtype);count=int(np.prod(shape))
    storage=np.empty(max(count,(capacity or 0)//dtype.itemsize),dtype)
    return storage[:count].reshape(shape)


class OutputPool:
    def __init__(self, shapes, count, dtype=np.float32,capacities=None):
        self.free = queue.Queue(count)
        self.lock, self.active = threading.Lock(), {}
        for _ in range(count):
            self.free.put([output_array(shape,dtype,capacities[i] if capacities else None) for i,shape in enumerate(shapes)])

    def acquire(self, abort):
        while not abort.is_set():
            try:
                arrays = self.free.get(timeout=.1)
            except queue.Empty:
                continue
            lease = Lease(self, arrays)
            with self.lock:
                self.active[id(lease)] = lease
            return lease
        return None

    def reclaim(self):
        """Only after every worker has stopped, including failure cleanup."""
        for lease in list(self.active.values()):
            lease.release()


class Runtime:
    def __init__(self, lib, model, library, core, prealloc, input_mode='uint8', output_mode='fp32', io_mode='copy', collect_perf=False):
        self.io_mode=io_mode
        if input_mode not in ('uint8','fp16-pass','fp16-ready'):
            raise ValueError('Unknown native input mode')
        self.lib, self.prealloc, self.handle = lib, prealloc, None
        self.input_mode=input_mode
        if output_mode not in ('fp16','fp32'):raise ValueError('Unknown output mode')
        self.output_mode=output_mode
        self.output_dtype=np.dtype('float16' if output_mode=='fp16' else 'float32')
        self.collect_perf=collect_perf
        error = ct.create_string_buffer(1024)
        threads_before=thread_accounting.before_creation()
        self.handle = lib.nr_create(str(library).encode(), str(model).encode(),
                                    {'0': 1, '1': 2}[core], {'uint8':0,'fp16-pass':1,'fp16-ready':2}[input_mode]+(16 if output_mode=='fp16' else 0)+(32 if io_mode!='copy' else 0)+(64 if io_mode=='bind-both' else 0)+(128 if collect_perf else 0), error, len(error))
        if not self.handle:
            raise RuntimeError(error.value.decode())
        thread_accounting.after_creation(threads_before,'sdk_internal','created during RKNN context initialization')
        self.threads_tagged=False
        try:
            self.info = json.loads(lib.nr_metadata(self.handle).decode())
            self.info['collect_perf_detail']=collect_perf
            self.shapes = []
            for attr in self.info['outputs']:
                channels = next((c for c in (4,80) if attr['elements'] == c*8400), None)
                if channels is None or attr['dims'][0] != 1 or channels not in attr['dims']:
                    raise RuntimeError('Unexpected batch-one output contract')
                self.shapes.append((1,channels,8400))
            if sorted(s[1] for s in self.shapes) != [4,80]:
                raise RuntimeError('Expected full scores and boxes outputs')
        except BaseException:
            self.release()
            raise

    def run_into(self, batch, outputs, profile=False):
        dtype=np.float16 if self.input_mode=='fp16-ready' else np.uint8
        if batch.dtype != dtype or batch.shape != (1,640,640,3) or not batch.flags.c_contiguous:
            raise ValueError('Wrong prepared input dtype/shape/layout for '+self.input_mode)
        if len(outputs) != 2 or any(a.dtype != self.output_dtype or a.shape != s or not a.flags.c_contiguous
                                   for a,s in zip(outputs,self.shapes)):
            raise ValueError('Invalid caller-owned float output buffers')
        timing, error = Timing(), ct.create_string_buffer(1024)
        detail=ct.create_string_buffer(256*1024) if profile and self.collect_perf else None
        detail_size,detail_rc=ct.c_uint(),ct.c_int()
        threads_before=thread_accounting.before_creation() if not self.threads_tagged else None
        rc = self.lib.nr_infer(self.handle, batch.ctypes.data, batch.nbytes,
                              outputs[0].ctypes.data, outputs[0].nbytes,
                              outputs[1].ctypes.data, outputs[1].nbytes,
                              self.prealloc, profile, ct.byref(timing), error, len(error),
                              detail if detail else None,len(detail) if detail else 0,
                              ct.byref(detail_size) if detail else None,ct.byref(detail_rc) if detail else None)
        if not self.threads_tagged:
            thread_accounting.after_creation(threads_before,'sdk_first_inference','created during first inference; inferred owner')
            self.threads_tagged=True
        if rc:
            raise RuntimeError(error.value.decode())
        result = {f'rknn_{name}_{kind}_ms': float(getattr(timing,kind)[i])
                  for i,name in enumerate(PARTS) for kind in ('wall','cpu')}
        for kind in ('wall','cpu'):
            result['rknn_normalize_'+kind+'_ms']=float(getattr(timing,'normalize_'+kind+'_ms'))
            result['rknn_input_total_'+kind+'_ms']=(result['rknn_normalize_'+kind+'_ms']+
                                                   result['rknn_inputs_set_'+kind+'_ms'])
        if profile:
            result.update(rknn_device_ms=float(timing.device_ms), rknn_perf_query_rc=int(timing.query_rc))
            if self.collect_perf:
                result.update(rknn_perf_detail_query_rc=detail_rc.value,
                    rknn_perf_detail_bytes=detail_size.value,
                    rknn_perf_detail_truncated=detail_size.value>=len(detail)-1,
                    rknn_perf_detail=detail.value.decode('utf-8','replace'))
        return outputs, result

    def inference_raw(self, inputs, data_format=None):
        # Validation returns independent arrays, using exactly the selected API path.
        outputs = [np.empty(shape,self.output_dtype) for shape in self.shapes]
        return self.run_into(inputs[0], outputs)[0]

    def inference(self, inputs, data_format=None):
        # Public/debug contract stays FP32; production calls run_into directly.
        return [a.astype(np.float32,copy=False) for a in self.inference_raw(inputs,data_format)]

    def release(self):
        if self.handle:
            self.lib.nr_destroy(self.handle)
            self.handle = None


class Engine:
    def __init__(self, model, cores, depth, backend, input_mode='uint8', output_mode='fp32',io_mode='copy',binding_mode='dynamic',collect_perf=False):
        self.io_mode,self.binding_mode=io_mode,binding_mode
        self.runtimes = []
        self.output_mode=output_mode
        self.input_pool=self.output_pool=None
        if input_mode in ('fp16-pass','fp16-ready'):
            require_passthrough_model(Path(model))
        library, lib = vision.select_runtime(), load()
        try:
            for core in cores:
                runtime_cls=Runtime if io_mode=='copy' else BoundRuntime
                extra={'collect_perf':collect_perf}
                if io_mode!='copy':extra.update(io_mode=io_mode,binding_mode=binding_mode,
                    slots=(1 if binding_mode=='fixed' else depth//len(cores)))
                self.runtimes.append(runtime_cls(lib,model,library,core,backend=='native-prealloc',input_mode,output_mode,**extra))
            if str(library) not in vision.mapped_runtime():
                raise RuntimeError('Native backend mapped a different Runtime')
            if any(r.shapes != self.runtimes[0].shapes for r in self.runtimes):
                raise RuntimeError('Context output contracts differ')
            self.output_pool = None if io_mode=='bind-both' else OutputPool(
                self.runtimes[0].shapes,depth,self.runtimes[0].output_dtype,
                getattr(self.runtimes[0],'output_capacities',None))
            if io_mode!='copy':
                if depth!=8 or len(cores) not in (2,4) or depth%len(cores):
                    raise ValueError('Bound I/O requires depth eight and two or four contexts')
                if binding_mode not in ('dynamic','fixed') or (binding_mode=='fixed' and io_mode!='bind-both'):
                    raise ValueError('Fixed binding requires bind-both I/O')
                slots=1 if binding_mode=='fixed' else depth//len(cores)
                self.input_pool=BoundPool(self.runtimes,inputs=True,slots_per_context=slots)
                if io_mode=='bind-both':self.output_pool=BoundPool(self.runtimes,inputs=False,slots_per_context=slots)
            self.info = {'io_mode':io_mode,'binding_mode':binding_mode,'contexts': [r.info for r in self.runtimes], 'library': str(library),
                         'input_mode':input_mode,'output_mode':output_mode,'lut_sha256':hashlib.sha256(lut_bits(lib).tobytes()).hexdigest(),
                         'runtime_sha256': hashlib.sha256(library.read_bytes()).hexdigest(),
                         'build': json.loads(LIBRARY.with_suffix('.json').read_text())}
        except BaseException:
            self.close()
            raise

    def close(self):
        if self.input_pool:self.input_pool.reclaim()
        if self.output_pool:self.output_pool.reclaim()
        for runtime in self.runtimes:
            runtime.release()


class PreparedQueues:
    def __init__(self,count,depth):
        self.queues=[queue.Queue(depth) for _ in range(count)];self.end=0
    def put(self,task,timeout=.1):
        worker=task['target_context'] if task is not None else self.end%len(self.queues)
        self.queues[worker].put(task,timeout=timeout)
        if task is None:self.end+=1
    def qsize(self):return sum(q.qsize() for q in self.queues)


class BoundLease:
    def __init__(self,pool,worker,slot,arrays):
        self.pool,self.worker,self.slot,self.arrays=pool,worker,slot,arrays
        self.released=False
    def release(self):
        with self.pool.lock:
            if not self.released:
                self.released=True;self.pool.active.pop(id(self),None)
                self.pool.free[self.worker].put_nowait((self.worker,self.slot,self.arrays))


class BoundPool:
    def __init__(self,runtimes,inputs,slots_per_context):
        self.inputs=inputs;self.slots_per_context=slots_per_context
        self.lock=threading.Lock();self.active={};self.next_worker=0
        self.free=[queue.Queue(slots_per_context) for _ in runtimes]
        for worker,r in enumerate(runtimes):
            if len(r.input_arrays if inputs else r.output_arrays)!=slots_per_context:
                raise ValueError('Runtime allocation and lease pool capacity differ')
            for slot in range(slots_per_context):
                arrays=[r.input_arrays[slot]] if inputs else r.output_arrays[slot]
                self.free[worker].put((worker,slot,arrays))
    def acquire(self,abort,worker=None):
        while not abort.is_set():
            if self.inputs and worker is None:
                with self.lock:
                    start=self.next_worker
                    self.next_worker=(self.next_worker+1)%len(self.free)
                found=None
                for offset in range(len(self.free)):
                    w=(start+offset)%len(self.free)
                    try:found=self.free[w].get_nowait();break
                    except queue.Empty:pass
                if found is None:
                    time.sleep(.005);continue
                w,slot,arrays=found
            else:
                if worker is None:raise ValueError('Worker index required for output leases')
                try:w,slot,arrays=self.free[worker].get(timeout=.1)
                except queue.Empty:continue
            lease=BoundLease(self,w,slot,arrays)
            with self.lock:self.active[id(lease)]=lease
            return lease
        return None
    def reclaim(self):
        for lease in list(self.active.values()):lease.release()


class BoundRuntime(Runtime):
    def __init__(self,*args,io_mode,binding_mode='dynamic',slots=2,**kwargs):
        self.bound=None
        self.binding_mode=binding_mode;self.slots=slots
        super().__init__(*args,io_mode=io_mode,**kwargs)
        try:
            lib=self.lib
            lib.nr_bound_create.argtypes=[ct.c_void_p,ct.c_int,ct.c_int,ct.c_int,ct.c_char_p,ct.c_uint];lib.nr_bound_create.restype=ct.c_void_p
            lib.nr_bound_metadata.argtypes=[ct.c_void_p];lib.nr_bound_metadata.restype=ct.c_char_p
            lib.nr_bound_destroy.argtypes=[ct.c_void_p]
            lib.nr_bound_ptr.argtypes=[ct.c_void_p,ct.c_int,ct.c_int];lib.nr_bound_ptr.restype=ct.c_void_p
            lib.nr_bound_run.argtypes=[ct.c_void_p,ct.c_int,ct.c_int,ct.c_void_p,ct.c_uint,ct.c_void_p,ct.c_uint,
                ct.POINTER(ct.c_double),ct.POINTER(ct.c_double),ct.c_char_p,ct.c_uint]
            err=ct.create_string_buffer(1024)
            self.bound=lib.nr_bound_create(self.handle,io_mode=='bind-both',slots,binding_mode=='fixed',err,len(err))
            if not self.bound:raise RuntimeError(err.value.decode())
            def array(slot,tensor,shape):
                ptr=lib.nr_bound_ptr(self.bound,slot,tensor)
                if not ptr:raise RuntimeError('Missing bound memory pointer')
                return np.ctypeslib.as_array((ct.c_uint16*int(np.prod(shape))).from_address(ptr)).view(np.float16).reshape(shape)
            layout=json.loads(lib.nr_bound_metadata(self.bound))
            self.output_capacities=[max(a['size'],a['size_with_stride'],int(np.prod(shape))*2) for a,shape in zip(layout['outputs'],self.shapes)]
            self.input_arrays=[array(j,0,(1,640,640,3)) for j in range(slots)]
            self.output_arrays=[[array(j,i+1,shape) for i,shape in enumerate(self.shapes)] for j in range(slots)] if io_mode=='bind-both' else []
            self.input_slots={a.ctypes.data:i for i,a in enumerate(self.input_arrays)}
            self.output_slots={a[0].ctypes.data:i for i,a in enumerate(self.output_arrays)}
            self.info.update(io_mode=io_mode,binding_mode=binding_mode,bound_memory=layout,
                api_applicability={'inputs_set':False,'outputs_get':io_mode!='bind-both'},input_slots=slots,
                output_slots=slots if self.output_arrays else 0,
                init_flags=(0x4000|(0x8000 if self.output_arrays else 0)))
        except BaseException:
            self.release()
            raise
    def run_into(self,batch,outputs,profile=False):
        if profile:raise ValueError('Bound I/O profiling is separate from throughput')
        slot=self.input_slots.get(batch.ctypes.data)
        if slot is None:raise ValueError('Input is not leased from this context')
        out=self.output_slots.get(outputs[0].ctypes.data,0)
        if self.output_arrays and outputs[0].ctypes.data not in self.output_slots:raise ValueError('Wrong output lease')
        wall,cpu=(ct.c_double*7)(),(ct.c_double*7)();err=ct.create_string_buffer(1024)
        def capacity(a):
            root=a
            while isinstance(root.base,np.ndarray):root=root.base
            return root.nbytes
        if not self.output_arrays and any(capacity(a)<n for a,n in zip(outputs,self.output_capacities)):
            raise ValueError('Output allocation smaller than SDK native capacity')
        rc=self.lib.nr_bound_run(self.bound,slot,out,outputs[0].ctypes.data,capacity(outputs[0]),
            outputs[1].ctypes.data,capacity(outputs[1]),wall,cpu,err,len(err))
        if rc:raise RuntimeError(err.value.decode())
        names=('input_bind','input_sync','run','output_bind','output_sync','outputs_get','layout')
        result={f'rknn_{name}_{kind}_ms':float(values[i]) for i,name in enumerate(names)
                for kind,values in [('wall',wall),('cpu',cpu)] if values[i]>=0}
        result['rknn_inputs_set_applicable']=False
        result['rknn_outputs_get_applicable']=self.io_mode!='bind-both'
        result['rknn_input_bind_applicable']=self.binding_mode!='fixed'
        result['rknn_output_bind_applicable']=self.binding_mode!='fixed' and self.io_mode=='bind-both'
        return outputs,result
    def inference_raw(self,inputs,data_format=None):
        np.copyto(self.input_arrays[0],inputs[0])
        outputs=self.output_arrays[0] if self.output_arrays else [output_array(s,np.float16,n) for s,n in zip(self.shapes,self.output_capacities)]
        return [a.copy() for a in self.run_into(self.input_arrays[0],outputs)[0]]
    def release(self):
        if self.bound:self.lib.nr_bound_destroy(self.bound);self.bound=None
        super().release()


if __name__ == '__main__':
    print(json.dumps(build(),ensure_ascii=False))
