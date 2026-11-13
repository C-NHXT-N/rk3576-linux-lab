#!/usr/bin/env python3
# SPDX-License-Identifier: AGPL-3.0-only
"""Explicit ctypes C++ postprocessor; Python retains public record formatting."""
import ctypes as ct
import hashlib
import json
from pathlib import Path
import platform
import subprocess
import time

import numpy as np
import detector

ROOT = Path(__file__).resolve().parent
LIBRARY = ROOT/'build/native_post.so'


def build():
    LIBRARY.parent.mkdir(exist_ok=True)
    source = ROOT/'native_post.cpp'
    flags = ['-std=c++17', '-O3', '-fPIC', '-shared', '-fno-fast-math', '-ffp-contract=off']
    command = ['g++', *flags, str(source), '-o', str(LIBRARY)]
    subprocess.run(command, check=True, timeout=120)
    manifest = {'compiler': subprocess.check_output(['g++', '--version'], text=True).splitlines()[0],
                'flags': flags, 'platform': platform.machine(),
                'source_sha256': hashlib.sha256(source.read_bytes()).hexdigest(),
                'binary_sha256': hashlib.sha256(LIBRARY.read_bytes()).hexdigest()}
    LIBRARY.with_suffix('.json').write_text(json.dumps(manifest, indent=2)+'\n')
    return manifest


class Postprocessor:
    def __init__(self, comparison_dtype=None):
        self.comparison_dtype=comparison_dtype
        manifest = json.loads(LIBRARY.with_suffix('.json').read_text())
        if manifest['source_sha256'] != hashlib.sha256((ROOT/'native_post.cpp').read_bytes()).hexdigest() or manifest['binary_sha256'] != hashlib.sha256(LIBRARY.read_bytes()).hexdigest():
            raise RuntimeError('Native build/source hash mismatch; rebuild explicitly.')
        self.manifest = manifest
        self.lib = ct.CDLL(str(LIBRARY))
        self.lib.post_create.restype = ct.c_void_p
        self.lib.post_destroy.argtypes = [ct.c_void_p]
        self.lib.post_run.argtypes = [ct.c_void_p, ct.c_void_p, ct.c_void_p, ct.c_int64,
            ct.c_double, ct.c_double, ct.c_double, ct.c_int64,
            ct.c_double, ct.c_double, ct.c_double, ct.c_double,
            ct.c_int, ct.c_int, ct.c_void_p, ct.c_int]
        self.lib.post_run_half.argtypes=self.lib.post_run.argtypes
        if self.lib.post_abi_version() != 2:
            raise RuntimeError('Unsupported native postprocessor ABI.')
        self.handle = self.lib.post_create()
        if not self.handle:
            raise MemoryError('Native workspace allocation failed.')
        self.storage = np.empty((300, 6), np.float64)
        self.last_timing = {}

    def close(self):
        if self.handle:
            self.lib.post_destroy(self.handle)
            self.handle = None

    def batch(self, outputs, transforms, batch_size, threshold=.25, topk=300):
        if not isinstance(outputs, (list, tuple)) or len(outputs) != 2:
            raise ValueError('Expected two complete batched outputs.')
        arrays = [np.asarray(a) for a in outputs]
        if not 0 < len(transforms) <= batch_size or any(a.ndim != 3 or a.shape[0] != batch_size for a in arrays):
            raise ValueError('Model output batch does not match the requested batch.')
        scores = next((a for a in arrays if a.shape[1] == 80), None)
        boxes = next((a for a in arrays if a.shape[1] == 4), None)
        if scores is None or boxes is None or scores.shape[2] != boxes.shape[2]:
            raise ValueError('Wrong output channels or candidate count.')
        if any(a.dtype not in (np.dtype('float16'), np.dtype('float32')) for a in arrays):
            raise ValueError('Native output dtype must be FP16 or FP32.')
        totals = dict(post_convert_ms=0., post_native_ms=0., post_pack_ms=0.)
        result = []
        for i, transform in enumerate(transforms):
            begin = time.perf_counter()
            dtype=np.float16 if scores.dtype==boxes.dtype==np.dtype('float16') else np.float32
            score = np.ascontiguousarray(scores[i], dtype=dtype)
            box = np.ascontiguousarray(boxes[i], dtype=dtype)
            n = score.shape[1]
            capacity = min(n, max(0, topk) if topk >= 0 else n)
            if len(self.storage) < capacity:
                self.storage = np.empty((capacity, 6), np.float64)
            # NumPy casts scalar comparisons to the source score dtype.
            low, high, cutoff = [float(np.asarray(v, dtype=self.comparison_dtype or scores.dtype)) for v in (-.001, 1.001, threshold)]
            native_begin = time.perf_counter()
            call=self.lib.post_run_half if dtype==np.float16 else self.lib.post_run
            count = call(self.handle, score.ctypes.data, box.ctypes.data, n,
                low, high, cutoff, topk, transform['left'], transform['top'],
                transform['scale_x'], transform['scale_y'], transform['width'], transform['height'],
                self.storage.ctypes.data, capacity)
            pack_begin = time.perf_counter()
            if count < 0:
                raise ValueError({-1: 'Model outputs contain non-finite values.',
                                  -2: 'Expected post-sigmoid class probabilities, not classification logits.'}.get(count, 'Invalid native postprocessor arguments or allocation failure.'))
            records = []
            for row in self.storage[:count]:
                cls = int(row[0])
                records.append({'class_id': cls, 'name': detector.CLASSES[cls],
                    'confidence': float(row[1]), 'xyxy': [round(float(x), 3) for x in row[2:]]})
            end = time.perf_counter()
            totals['post_convert_ms'] += (native_begin-begin)*1000
            totals['post_native_ms'] += (pack_begin-native_begin)*1000
            totals['post_pack_ms'] += (end-pack_begin)*1000
            result.append(records)
        self.last_timing = totals
        return result


if __name__ == '__main__':
    import argparse
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--build', action='store_true', required=True)
    parser.parse_args()
    print(json.dumps(build()))
