# SPDX-License-Identifier: AGPL-3.0-only
"""Run one complete video check per scene using the accepted B configuration."""
import json
import os
from pathlib import Path
import platform
import shutil
import sys
from types import SimpleNamespace

import bench_support as support
import fast_bench
import media_backends as media
import native_mpp
import vision

ROOT = Path(__file__).resolve().parent
MODEL = ROOT/'models/yolo26n-rk3576-fp16.rknn'
SCENES = {'night': ('test-720p30.mp4', 'golden.json'),
          'day': ('day-720p30.mp4', 'day-golden.json')}
SOURCE = dict(count=1050, fps=30, width=1280, height=720)

def check_source(source):
    meta = media.probe(source)
    if (meta['frames'], meta['width'], meta['height']) != (1050,1280,720) or abs(meta['fps']-30)>.001:
        raise ValueError(f'Expected a 1050-frame 720p30 clip: {source}')


def other_experiments():
    result = []
    for entry in Path('/proc').glob('[0-9]*/cmdline'):
        try:
            args = entry.read_bytes().decode(errors='replace').split('\0')
        except OSError:
            continue
        if int(entry.parent.name) != os.getpid() and any(
                Path(arg).name in ('experiment.py', 'fast_bench.py', 'sample_resources.py')
                for arg in args[:3]):
            result.append(int(entry.parent.name))
    return result


def validate(row, golden):
    integrity = support.check_run(row, SOURCE)
    output = Path(row['command'][row['command'].index('--output')+1])
    with (output/'frames.jsonl').open(encoding='utf-8') as stream:
        for index, line in enumerate(stream):
            actual = json.loads(line)['detections']
            try:
                fast_bench.compare_detections(golden[index], actual)
            except ValueError as error:
                raise ValueError(f'Source frame {index}: {error}') from error
    decoder = row['media']['decoder']
    if row['completed'] != SOURCE['count'] or not native_mpp.hardware_proven(decoder, SOURCE['count']):
        raise ValueError('MPP decoder did not drain the complete source')
    encoder = row['media']['encoder']['encoder']
    if (not encoder.get('eos_received') or encoder['free_buffers'] != 3
            or any(encoder[key]!=SOURCE['count'] for key in ('submitted', 'completed', 'frames'))):
        raise ValueError('MPP encoder did not drain and return all buffers')
    proof = json.loads((output/'measurement-media.json').read_text())
    if proof['decoder'].get('active_frame_leases_after_close') != 0:
        raise ValueError('Source frame lease remains active')
    return dict(integrity, golden=True, decoder_eos=True, encoder_eos=True, buffers_released=True)


def run(output):
    output = output.resolve()
    if not output.is_relative_to((ROOT/'run').resolve()):
        raise ValueError('Verification output must be inside the project run directory')
    if sys.platform != 'linux' or platform.machine() != 'aarch64':
        raise RuntimeError('Use the RK3576 board environment')
    busy = other_experiments()
    if busy:
        raise RuntimeError(f'Existing experiment processes: {busy}')
    if shutil.disk_usage(ROOT).free < 512*1024**2:
        raise RuntimeError('Verification requires 512 MiB free')
    output.mkdir(parents=True, exist_ok=False)
    config = dict(model=MODEL, mode='display', batch=1, contexts=4, queue_batches=8,
                  decode_backend='mpp-fused', decode_threads=4, post_backend='cpp',
                  inference_backend='native-prealloc', input_mode='fp16-ready',
                  output_mode='fp16', io_mode='bind-both', preprocess_backend='cpu-fused',
                  feed_path='fused', render_backend='cached', encode_backend='mpp-native',
                  display_pipeline='async', render_storage='inplace', reuse_padding=True,
                  validation_frames=8, encoder_bitrate=14000000)
    result = dict(status='running', scenes={})
    try:
        for scene, (clip, reference) in SCENES.items():
            source = ROOT/'run/video-input'/clip
            check_source(source)
            reference_path = ROOT/'run/reference'/reference
            if not reference_path.is_file():
                raise FileNotFoundError(f'Missing {reference_path}. Run prepare_video_reference.py first.')
            reference_data = json.loads(reference_path.read_text(encoding='utf-8'))
            golden = reference_data['frames']
            if len(golden) != SOURCE['count']:
                raise ValueError(f'Expected 1050 reference frames for {scene}')
            for key, path in [('verification_clip_sha256',source), ('verification_model_sha256',MODEL)]:
                if key in reference_data and reference_data[key] != support.digest(path):
                    raise ValueError(f'Reference belongs to a different clip or model: {reference_path}')
            suite = support.Suite(SimpleNamespace(output=output, reference_model=MODEL,
                                  video=source, warmup=5, duration=3600, frames=1050, quiet=True))
            row = suite.run(scene, config, once=True, timeout=150)
            if row['status']!='complete':
                raise RuntimeError(f'{scene} failed. See {row.get("log")}')
            result['scenes'][scene] = dict(fps=row['fps'], **validate(row,golden))
            vision.atomic_json(output/'final.json', result)
            print(f'{scene}: {row["fps"]:.2f} FPS, 1050 frames, EOS and leases verified', flush=True)
        result['status'] = 'complete'
    except BaseException as error:
        result.update(status='failed', error=str(error))
        raise
    finally:
        vision.atomic_json(output/'final.json', result)
