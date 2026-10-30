#!/usr/bin/env python3
# SPDX-License-Identifier: AGPL-3.0-only
# Copyright (c) 2026 C-NHXT-N and contributors
"""Headless YOLO26n static-image detector. RKNN Lite is the only inference backend."""
import argparse
import importlib
import json
import math
import os
from pathlib import Path
import signal
import sys
import time

PROJECT = Path(__file__).resolve().parent


def load_config(path):
    path = path.resolve()
    config = json.loads(path.read_text(encoding='utf-8'))
    if not isinstance(config, dict):
        raise ValueError('Configuration must be a JSON object.')
    if 'labels' in config or 'camera' in config:
        raise ValueError('Migrate the old classification/camera configuration: use YOLO26n, one image and built-in COCO80 labels; remove labels and camera.')
    allowed = {'model', 'image', 'frames', 'interval', 'health', 'score_threshold', 'topk', 'output_dir'}
    if set(config) - allowed:
        raise ValueError(f'Unknown configuration keys: {sorted(set(config) - allowed)}')
    for required in ['model', 'image']:
        if not isinstance(config.get(required), str) or not config[required]:
            raise ValueError(f'{required} must be a non-empty path string.')
    for name in ['model', 'image', 'health', 'output_dir']:
        if name in config:
            if not isinstance(config[name], str) or not config[name]:
                raise ValueError(f'{name} must be a non-empty path string.')
            value = Path(config[name]).expanduser()
            config[name] = value if value.is_absolute() else path.parent / value
    config.setdefault('frames', 1)
    config.setdefault('interval', 1.0)
    config.setdefault('health', path.parent / 'run/health.json')
    config.setdefault('output_dir', path.parent / 'run/vision')
    config.setdefault('score_threshold', 0.25)
    config.setdefault('topk', 300)
    if type(config['frames']) is not int or not 0 <= config['frames'] <= 1000000:
        raise ValueError('frames must be an integer in 0..1000000; 0 means continuous.')
    if type(config['interval']) not in (int, float) or not math.isfinite(config['interval']) or not 0 < config['interval'] <= 60:
        raise ValueError('interval must be finite and > 0 and <= 60 seconds.')
    if type(config['score_threshold']) not in (int, float) or not math.isfinite(config['score_threshold']) or not 0 <= config['score_threshold'] <= 1:
        raise ValueError('score_threshold must be finite and in 0..1.')
    if type(config['topk']) is not int or not 1 <= config['topk'] <= 8400:
        raise ValueError('topk must be an integer in 1..8400.')
    for name in ['model', 'image']:
        if not config[name].is_file():
            raise ValueError(f'{name}: file not found: {config[name]}')
    return config


def select_runtime():
    library = Path(os.environ.get('LIBRKNNRT_PATH', PROJECT / 'runtime/librknnrt.so')).resolve()
    if not library.is_file():
        raise RuntimeError(f'Project Runtime missing: {library}. Follow docs/07-rknn/00-environment.md; do not replace the system Runtime.')
    # This is the course launcher's setting. Lite 2.5 itself uses a module
    # constant rather than reading this environment variable (see bind_runtime).
    os.environ['LIBRKNNRT_PATH'] = str(library)
    return library


def bind_runtime(library):
    # Process-local override of the pinned Lite 2.5 path resolver. No installed
    # SDK file or system shared library is modified. Verify /proc maps below.
    module = importlib.import_module('rknnlite.api.rknn_runtime')
    if not hasattr(module, 'LIBRKNNRT_PATH'):
        raise RuntimeError('This lesson requires the pinned RKNN Lite2 2.5.0 path interface.')
    # Assigning LIBRKNNRT_PATH alone is ineffective in the compiled extension.
    module.RKNNRuntime._get_rknn_api_lib_path = lambda self: str(library)


def dependencies():
    try:
        return (importlib.import_module('cv2'), importlib.import_module('numpy'),
                importlib.import_module('rknnlite.api').RKNNLite,
                importlib.import_module('detector'))
    except ImportError as error:
        raise RuntimeError(f'Missing dependency: {error}. Follow docs/07-rknn/00-environment.md with the project Python.') from error


def atomic_json(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + '.tmp')
    temporary.write_text(json.dumps(data, ensure_ascii=False, allow_nan=False) + '\n', encoding='utf-8')
    temporary.replace(path)


def write_health(path, status, frames):
    atomic_json(path, {'status': status, 'backend': 'rknn', 'model_family': 'yolo26',
                       'frames': frames, 'timestamp': time.time()})


def mapped_runtime():
    try:
        return sorted({line.split()[-1] for line in Path('/proc/self/maps').read_text().splitlines() if 'librknnrt.so' in line})
    except OSError:
        return []


def save_result(cv2, detector, image, result, output):
    output.mkdir(parents=True, exist_ok=True)
    ok, encoded = cv2.imencode('.jpg', detector.annotate(image, result['detections']))
    if not ok:
        raise RuntimeError('Could not encode the annotated result image.')
    temporary = output / 'result.jpg.tmp'
    temporary.write_bytes(encoded.tobytes())
    temporary.replace(output / 'result.jpg')
    atomic_json(output / 'result.json', result)


def run(config):
    cv2, np, RKNNLite, detector = dependencies()
    expected_library = select_runtime()
    bind_runtime(expected_library)
    runtime = RKNNLite()
    frames = 0
    stopped = False
    state = 'error'
    old_handlers = {}

    def request_stop(signum, frame):
        nonlocal stopped
        stopped = True

    try:
        for number in (signal.SIGINT, signal.SIGTERM):
            old_handlers[number] = signal.signal(number, request_stop)
        write_health(config['health'], 'starting', frames)
        if runtime.load_rknn(str(config['model'])) != 0:
            raise RuntimeError('load_rknn failed: verify the rk3576 YOLO26 model and SDK compatibility.')
        if runtime.init_runtime(core_mask=RKNNLite.NPU_CORE_0) != 0:
            raise RuntimeError('init_runtime failed: inspect the driver, project Runtime and device permissions.')
        loaded = mapped_runtime()
        if str(expected_library) not in loaded:
            raise RuntimeError(f'Wrong Runtime mapped: {loaded}; expected {expected_library}.')
        print(f'Runtime mapped: {loaded}', file=sys.stderr)
        while not stopped and (config['frames'] == 0 or frames < config['frames']):
            started = time.perf_counter()
            image = cv2.imread(str(config['image']))
            if image is None:
                raise RuntimeError('OpenCV could not decode the input image.')
            batch, transform = detector.preprocess(image)
            before_inference = time.perf_counter()
            outputs = runtime.inference(inputs=[batch], data_format=['nhwc'])
            after_inference = time.perf_counter()
            detections = detector.postprocess(outputs, transform, config['score_threshold'], config['topk'])
            frames += 1
            ended = time.perf_counter()
            result = {
                'frame': frames, 'backend': 'rknn', 'model_family': 'yolo26',
                'timestamp': time.time(), 'image': str(config['image']),
                'image_size': [image.shape[1], image.shape[0]],
                'preprocess_ms': round((before_inference - started) * 1000, 3),
                'inference_ms': round((after_inference - before_inference) * 1000, 3),
                'pipeline_ms': round((ended - started) * 1000, 3),
                'detections': detections,
            }
            save_result(cv2, detector, image, result, config['output_dir'])
            print(json.dumps(result, ensure_ascii=False, allow_nan=False), flush=True)
            write_health(config['health'], 'running', frames)
            if config['frames'] and frames >= config['frames']:
                break
            deadline = time.monotonic() + max(0, config['interval'] - (time.perf_counter() - started))
            while not stopped and time.monotonic() < deadline:
                time.sleep(min(0.1, max(0, deadline - time.monotonic())))
        state = 'stopped'
        return 0
    finally:
        try:
            runtime.release()
        finally:
            try:
                write_health(config['health'], state, frames)
            finally:
                for number, previous in old_handlers.items():
                    signal.signal(number, previous)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--config', type=Path, required=True)
    parser.add_argument('--check', action='store_true', help='Check paths, imports and project Runtime file; never initializes the NPU.')
    args = parser.parse_args()
    config = None
    try:
        config = load_config(args.config)
        if args.check:
            dependencies()
            print(f'Project Runtime: {select_runtime()}')
            print('Preflight passed. Real model initialization and inference are still required.')
            return 0
        write_health(config['health'], 'starting', 0)
        return run(config)
    except (OSError, ValueError, RuntimeError) as error:
        if config is not None and not args.check:
            try:
                write_health(config['health'], 'error', 0)
            except OSError:
                pass
        print(f'ERROR: {error}', file=sys.stderr)
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
