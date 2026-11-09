# SPDX-License-Identifier: AGPL-3.0-only
"""Video/RKNN primitives used by fast_bench; experiment.py is the suite entry."""
import math
from pathlib import Path
import queue
import subprocess
import threading
import time
import cv2
import numpy as np
import detector
import vision
import thread_schedule

def distribution(values):
    return {name: float(np.percentile(values, percentile)) if values else None
            for name, percentile in [('min', 0), ('p5', 5), ('p50', 50), ('p95', 95), ('max', 100)]}

def summarize(records, elapsed, target=0):
    times = [r['completed_s'] for r in records]
    windows = [0] * int(elapsed)
    for t in times:
        if 0 <= int(t) < len(windows):
            windows[int(t)] += 1
    fps = len(records) / elapsed if elapsed else 0
    good = sum(n >= target*.9 for n in windows) / len(windows) if windows else 0
    return {'frames': len(records), 'elapsed_s': elapsed, 'fps': fps,
            'second_fps': windows, 'second_fps_distribution': distribution(windows),
            'target_fps': target, 'good_windows_fraction': good if target else None,
            'stable': bool(target and fps >= target*.99 and good >= .95),
            'stage_ms': {key: distribution([r[key] for r in records]) for key in
                         ['decode_ms', 'preprocess_ms', 'inference_ms', 'postprocess_ms', 'output_ms', 'latency_ms']}}

class VideoReader:
    def __init__(self, path, loop=True, decode_threads=1):
        if decode_threads not in (1, 2, 4):
            raise ValueError('Decode threads must be 1, 2 or 4.')
        self.decode_threads = decode_threads
        self.path, self.loop = str(path), loop
        self.cap = cv2.VideoCapture(self.path, cv2.CAP_FFMPEG, [cv2.CAP_PROP_N_THREADS, self.decode_threads])
        if not self.cap.isOpened():
            raise RuntimeError('Video open/decode failed: ' + self.path)
        self.fps = self.cap.get(cv2.CAP_PROP_FPS)
        self.count = int(self.cap.get(cv2.CAP_PROP_FRAME_COUNT))
        self.index, self.cycle = 0, 0
        if not math.isfinite(self.fps) or self.fps <= 0 or self.count <= 0:
            self.close()
            raise ValueError('Expected a seekable video with valid FPS and frame count.')

    def read(self):
        started = time.perf_counter()
        if self.index >= self.count:
            if not self.loop:
                return None
            self.cap.release()
            self.cap = cv2.VideoCapture(self.path, cv2.CAP_FFMPEG, [cv2.CAP_PROP_N_THREADS, self.decode_threads])
            self.index = 0
            self.cycle += 1
        grab_begin = time.perf_counter()
        cpu_begin = time.thread_time()
        ok = self.cap.grab()
        grabbed = time.perf_counter()
        ok, image = self.cap.retrieve() if ok else (False, None)
        retrieved = time.perf_counter()
        if not ok:
            raise RuntimeError(f'Video decode failed before declared EOF at frame {self.index}.')
        item = {'image': image, 'source_frame': self.index, 'cycle': self.cycle,
                'decode_started': started, 'decode_ms': (retrieved-started)*1000,
                'decode_grab_ms': (grabbed-grab_begin)*1000,
                'decode_retrieve_ms': (retrieved-grabbed)*1000,
                'decode_cpu_ms': (time.thread_time()-cpu_begin)*1000}
        self.index += 1
        return item

    def close(self):
        self.cap.release()

def release_image(item):
    prepared=item.pop('prepared_lease',None)
    if prepared:prepared.release()
    lease=item.pop('image_lease',None)
    if lease:lease.release()
    item.pop('image',None)


class Prefetch:
    def __init__(self, reader, phase=None):
        self.reader = reader
        self.items = queue.Queue(2)
        self.stop = threading.Event()
        self.thread = threading.Thread(target=phase.wrap('reader',self.produce) if phase else self.produce,
                                       name='video-reader',daemon=True)
        self.thread.start()

    def produce(self):
        try:
            thread_schedule.apply('reader')
            while not self.stop.is_set():
                item = self.reader.read()
                queued=False
                while not self.stop.is_set():
                    try:
                        self.items.put(item, timeout=.1)
                        queued=True
                        break
                    except queue.Full:
                        pass
                if not queued and isinstance(item,dict):release_image(item)
                if item is None:
                    break
        except Exception as error:
            while not self.stop.is_set():
                try:
                    self.items.put(error, timeout=.1)
                    break
                except queue.Full:
                    pass

    def read(self):
        item = self.items.get(timeout=30)
        if isinstance(item, Exception):
            raise item
        return item

    def cancel(self):
        self.stop.set()
        if hasattr(self.reader,'cancel'):self.reader.cancel()

    def close(self):
        self.cancel()
        self.thread.join(timeout=30)
        if self.thread.is_alive():
            raise RuntimeError('Decoder did not stop.')
        while not self.items.empty():
            item=self.items.get_nowait()
            if isinstance(item,dict):release_image(item)
        self.reader.close()

class Engine:
    def __init__(self, model, cores):
        _, _, RKNNLite, _ = vision.dependencies()
        expected = vision.select_runtime()
        vision.bind_runtime(expected)
        self.runtimes = []
        try:
            for core in cores:
                runtime = RKNNLite()
                self.runtimes.append(runtime)
                if runtime.load_rknn(str(model)) != 0:
                    raise RuntimeError('load_rknn failed')
                mask = getattr(RKNNLite, 'NPU_CORE_'+core.upper())
                if runtime.init_runtime(core_mask=mask) != 0:
                    raise RuntimeError('init_runtime failed for core mask ' + core)
                if str(expected) not in vision.mapped_runtime():
                    raise RuntimeError('Expected project Runtime is not mapped.')
        except Exception:
            self.close()
            raise



    def close(self):
        for runtime in self.runtimes:
            runtime.release()

def decorate(image, detections, detail):
    # A separate header preserves every source pixel and every detection label.
    rendered = cv2.copyMakeBorder(detector.annotate(image, detections), 70, 0, 0, 0,
                                  cv2.BORDER_CONSTANT, value=(23, 18, 15))
    cv2.putText(rendered, 'RK3576  /  YOLO26n FP16  /  640 x 640', (20, 28),
                cv2.FONT_HERSHEY_SIMPLEX, .7, (240, 245, 250), 1, cv2.LINE_AA)
    cv2.putText(rendered, detail, (20, 54), cv2.FONT_HERSHEY_SIMPLEX, .53,
                (220, 210, 40), 1, cv2.LINE_AA)
    return rendered

class Encoder:
    def __init__(self, path, image, fps, preset='veryfast', threads=2):
        h, w = image.shape[:2]
        self.log = path.with_suffix('.ffmpeg.log').open('wb')
        self.process = subprocess.Popen(['ffmpeg', '-hide_banner', '-loglevel', 'error', '-y',
            '-f', 'rawvideo', '-pix_fmt', 'bgr24', '-s', f'{w}x{h}', '-r', str(fps), '-i', '-',
            '-an', '-c:v', 'libx264', '-threads', str(threads), '-preset', preset, '-crf', '20',
            '-pix_fmt', 'yuv420p', '-movflags', '+faststart', str(path)], stdin=subprocess.PIPE, stderr=self.log)

    def write(self, image):
        self.process.stdin.write(memoryview(image).cast('B'))

    def close(self):
        self.process.stdin.close()
        code = self.process.wait(timeout=60)
        self.log.close()
        if code:
            raise RuntimeError(f'Video encoder failed with exit code {code}')
