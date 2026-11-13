# SPDX-License-Identifier: AGPL-3.0-only
"""Shared experiment execution, integrity and resource summaries."""
import csv
import json
import os
import signal
import hashlib
import shutil
from pathlib import Path
import statistics
import subprocess
import sys
import time
import video_bench as video
import vision
PROJECT = Path(__file__).resolve().parent

def digest(path):
    h = hashlib.sha256()
    with Path(path).open('rb') as stream:
        for block in iter(lambda: stream.read(1024*1024), b''):
            h.update(block)
    return h.hexdigest()


def stop_process_group(process):
    """Bounded shutdown, including an encoder left behind by a failed worker."""
    if os.name == 'posix':
        try:
            os.killpg(process.pid, signal.SIGTERM)
        except ProcessLookupError:
            return
    elif process.poll() is None:
        process.terminate()
    try:
        process.wait(timeout=8)
    except subprocess.TimeoutExpired:
        if os.name == 'posix':
            try:
                os.killpg(process.pid, signal.SIGKILL)
            except ProcessLookupError:
                pass
        else:
            process.kill()
        process.wait(timeout=5)
    # The group leader can exit before a descendant responds to TERM.
    if os.name == 'posix':
        try:
            os.killpg(process.pid, signal.SIGKILL)
        except ProcessLookupError:
            pass


def rank(results, minimum=3):
    failed = {row['config_id'] for row in results if row.get('status') != 'complete'}
    groups = {}
    for row in results:
        if row.get('status') == 'complete' and (not row.get('once') or row.get('fixed_workload')) and row['config_id'] not in failed:
            groups.setdefault(row['config_id'], []).append(row)
    ranking = []
    for name, rows in groups.items():
        if len(rows) < minimum:
            continue
        ranking.append({'config_id': name, 'config': rows[0]['config'],
                        'fps': [r['fps'] for r in rows],
                        'median_fps': statistics.median(r['fps'] for r in rows),
                        'peak_rss_bytes': max((r.get('peak_rss_bytes') or 0 for r in rows), default=0),
                        'correctness': 'reference validation passed'})
    return sorted(ranking, key=lambda row: (-row['median_fps'], row['config_id']))

class Suite:
    def __init__(self, args):
        self.args, self.results, self.configs = args, [], {}

    def report(self):
        vision.atomic_json(self.args.output/'runs.json', self.results)
        ranking = rank(self.results, minimum=1)
        vision.atomic_json(self.args.output/'ranking.json', ranking)
        lines = ['# Fixed-workload results (one round is screening only)', '', '| Config | Batch | Contexts | FPS rounds | Median FPS | Peak RSS MiB | Correctness |',
                 '|---|---:|---:|---|---:|---:|---|']
        for row in ranking:
            c = row['config']
            fps = ', '.join(f'{v:.3f}' for v in row['fps'])
            lines.append(f"| {row['config_id']} | {c['batch']} | {c['contexts']} | {fps} | {row['median_fps']:.3f} | {row['peak_rss_bytes']/1024**2:.1f} | {row['correctness']} |")
        lines += ['', 'Only actual board measurements belong in this table. Stage times in fast_bench are per batch.',
                  'RSS excludes some device allocations; no long-term stability or absolute chip limit is claimed.']
        (self.args.output/'comparison.md').write_text('\n'.join(lines)+'\n', encoding='utf-8')

    def run(self, name, config, once=False, timeout=150):
        self.configs[name] = config
        index = sum(row['config_id'] == name for row in self.results)+1
        label = f'{name}-{index}'
        output = self.args.output/label
        while output.exists():
            index += 1
            label, output = f'{name}-{index}', self.args.output/f'{name}-{index}'
        command = [sys.executable, str(PROJECT/'fast_bench.py'), '--model', str(config['model']),
                       '--reference-model', str(self.args.reference_model), '--batch', str(config['batch']),
                       '--contexts', str(config['contexts']), '--core-policy', config.get('core_policy', 'split'),
                       '--queue-batches', str(config.get('queue_batches', 4)),
                       '--max-inflight',str(config.get('max_inflight',config.get('queue_batches',4))),
                       '--post-workers', str(config.get('post_workers', 1)),
                       '--encoder-preset', config.get('encoder_preset', 'veryfast'),
                       '--encoder-threads', str(config.get('encoder_threads', 2)),
                       '--decode-backend', config.get('decode_backend', 'opencv'),
                       '--decode-threads', str(config.get('decode_threads', 1)),
                       '--post-backend', config.get('post_backend', 'python'),
                       '--inference-backend', config.get('inference_backend', 'lite'),
                       '--input-mode',config.get('input_mode','uint8'),
                       '--output-mode',config.get('output_mode','fp32'),
                       '--io-mode',config.get('io_mode','copy'),
                       '--binding-mode',config.get('binding_mode','dynamic'),
                       '--input-source',config.get('input_source','video'),
                       '--preprocess-backend',config.get('preprocess_backend','cpu'),
                       '--feed-path',config.get('feed_path','standard'),
                       '--pre-workers',str(config.get('pre_workers',1)),
                       '--render-backend', config.get('render_backend', 'original'),
                       '--encode-backend', config.get('encode_backend', 'x264'),
                       '--encoder-bitrate', str(config.get('encoder_bitrate', 14000000))]
        command += ['--display-pipeline',config.get('display_pipeline','serial'),
                    '--cpu-policy',config.get('cpu_policy','auto'),
                    '--validation-frames',str(config.get('validation_frames',32)),
                    '--render-storage',config.get('render_storage','copy')]
        if config.get('reuse_padding'):command.append('--reuse-padding')
        if not config.get('reuse_inputs', True):
            command.append('--allocate-inputs')
        if config.get('profile_device', False):
            command.append('--profile-device')
        if config.get('thread_accounting',False):command.append('--thread-accounting')
        command += ['--video', str(self.args.video), '--output', str(output),
                    '--warmup', str(self.args.warmup), '--duration', str(3600 if once else self.args.duration),
                    '--max-frames', str(getattr(self.args, 'frames', 0)),
                    '--mode', config.get('mode', 'detect')]
        if once:
            command.append('--once')
        vision.atomic_json(self.args.output/'status.json', {'test': label, 'command': command, 'started': time.time()})
        child_started=time.monotonic()
        with (self.args.output/(label+'.log')).open('w') as log:
            process = subprocess.Popen(command, stdout=log, stderr=subprocess.STDOUT,
                                       start_new_session=os.name == 'posix')
            sampler = None
            try:
                sampler = subprocess.Popen([sys.executable, str(PROJECT/'sample_resources.py'),
                    '--pid', str(process.pid), '--output', str(self.args.output/(label+'-resources.csv'))],
                    stdout=log, stderr=subprocess.STDOUT)
                code = process.wait(timeout=timeout)
            except BaseException:
                stop_process_group(process)
                raise
            finally:
                if sampler:
                    sampler.terminate()
                    try:
                        sampler.wait(timeout=5)
                    except subprocess.TimeoutExpired:
                        sampler.kill()
                        sampler.wait(timeout=5)
                stop_process_group(process)
        row = {'config_id': name, 'config': {**config, 'model': str(config['model'])}, 'once': once, 'fixed_workload': bool(getattr(self.args, 'frames', 0))}
        summary = output/'summary.json'
        if code or not summary.exists():
            row.update(status='failed', exit_code=code, log=str(self.args.output/(label+'.log')))
        else:
            row.update(json.loads(summary.read_text(encoding='utf-8')))
            if row['status'] == 'complete':
                csv_path = self.args.output/(label+'-resources.csv')
                with csv_path.open() as stream:
                    samples = [r for r in csv.DictReader(stream) if
                               row['measurement_start_monotonic'] <= float(r['monotonic']) <= row['measurement_end_monotonic']]
                row['peak_rss_bytes'] = max((int(r['process_rss_bytes']) for r in samples), default=None)
        row['child_wall_s']=time.monotonic()-child_started
        self.results.append(row)
        self.report()
        if not getattr(self.args,'quiet',False):
            print(json.dumps({'test': label, 'status': row['status'], 'fps': row.get('fps')}, ensure_ascii=False), flush=True)
        return row



def hardware_proven(evidence):
    runs = evidence.get('runtime', [])
    return any(any('libgstrockchipmpp' in name for name in run.get('library_maps', [])) and
               any(any(word in name for word in ('mpp_service', 'rkvdec', 'rkvenc', 'vpu_service', 'hevc_service'))
                   for name in run.get('device_fds', [])) for run in runs)

def resource_summary(folder, results):
    summary = {}
    for row in results:
        if row.get('status') != 'complete' or (row.get('once') and not row.get('fixed_workload')):
            continue
        command = row['command']
        run = Path(command[command.index('--output')+1])
        path = folder/(run.name+'-resources.csv')
        with path.open() as stream:
            samples = [sample for sample in csv.DictReader(stream) if
                       row['measurement_start_monotonic'] <= float(sample['monotonic']) <= row['measurement_end_monotonic']]
        group = summary.setdefault(row['config_id'], {'fps': [], 'samples': [], 'stage_ms': []})
        group['fps'].append(row['fps'])
        group['samples'].extend(samples)
        group['stage_ms'].append({name: data['p50'] for name, data in row['stage_ms'].items()})
    for group in summary.values():
        samples = group.pop('samples')
        group['rounds'] = len(group['fps'])
        group['median_fps'] = statistics.median(group['fps'])
        group['sample_count'] = len(samples)
        if not samples:
            continue
        npu = [json.loads(sample['npu_percent']) for sample in samples]
        cpu = [json.loads(sample['cpu_percent']) for sample in samples]
        group['npu_mean_percent'] = {str(core): statistics.mean(row[str(core)] for row in npu if str(core) in row)
                                     for core in (0, 1) if any(str(core) in row for row in npu)}
        group['cpu_each_mean_percent'] = [statistics.mean(row[i] for row in cpu) for i in range(len(cpu[0]))]
        group['peak_rss_mib'] = max(int(row['process_rss_bytes']) for row in samples)/1024**2
        group['min_available_gib'] = min(int(row['mem_available_bytes']) for row in samples)/1024**3
        frequencies = [json.loads(row.get('frequencies_hz') or '{}') for row in samples]
        temperatures = [json.loads(row.get('temperatures_c') or '{}') for row in samples]
        group['mean_frequencies_hz'] = {key: statistics.mean(r[key] for r in frequencies if key in r)
            for key in sorted({key for r in frequencies for key in r})}
        group['max_temperature_c'] = max((v for r in temperatures for v in r.values()),default=None)
        group['stage_p50_ms'] = {name: statistics.median(row[name] for row in group['stage_ms'])
                                for name in group['stage_ms'][0]}
        group['stage_time_unit'] = 'legacy raw batch times for pre/infer/post; normalized per-image times are in diagnostics'
        del group['stage_ms']
    return summary

def check_run(row, source):
    if row.get('status') != 'complete' or not row['validation']['passed']:
        raise RuntimeError('Boundary run failed: '+row['config_id'])
    if row['submitted'] != row['completed'] or row['frames'] != row['completed']:
        raise RuntimeError('Submitted/completed frame counts differ.')
    if row['mode'] == 'infer':
        if row['infer_pool_frames'] != 32:
            raise RuntimeError('Pure inference must use 32 preprocessed source frames.')
        return {'passed': True, 'frames': row['completed'], 'kind': 'repeated-input diagnostic'}
    path = Path(row['command'][row['command'].index('--output')+1])
    with (path/'frames.jsonl').open() as stream:
        records = [json.loads(line) for line in stream]
    if len(records) != row['completed'] or any(
            r['frame'] != i or r['source_frame'] != i % source['count'] or
            r['cycle'] != i // source['count'] for i, r in enumerate(records)):
        raise RuntimeError('Source/JSON frame continuity failed.')
    result = {'passed': True, 'frames': len(records), 'kind': 'real-video sequential'}
    if row['mode'] == 'display':
        stream = json.loads(subprocess.check_output(['ffprobe', '-v', 'error', '-select_streams', 'v:0',
            '-count_frames', '-show_entries', 'stream=width,height,nb_read_frames,avg_frame_rate,duration,bit_rate',
            '-of', 'json', str(path/'annotated.mp4')], text=True, timeout=120))['streams'][0]
        n, d = map(int, stream['avg_frame_rate'].split('/'))
        if (int(stream['nb_read_frames']) != len(records) or
                (stream['width'], stream['height']) != (source['width'], source['height']+70) or
                abs(n/d-source['fps']) > .001 or
                abs(float(stream['duration'])-len(records)/source['fps']) > 1/source['fps']+.001):
            raise RuntimeError('Encoded count, geometry or timeline failed.')
        result['encoded_stream'] = stream
    return result
