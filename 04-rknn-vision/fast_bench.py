#!/usr/bin/env python3
# SPDX-License-Identifier: AGPL-3.0-only
"""Bounded batch pipeline and short real-NPU benchmarks; no CPU fallback."""
import argparse
import hashlib
import json
import math
import os
from pathlib import Path
import queue
import signal
import threading
import time

import cv2
import numpy as np
import detector
import video_bench as video
import vision
import media_backends as media
import native_post
import cached_render
import native_rknn
import cpu_preprocess
import thread_accounting
import native_mpp
import media_support
import native_output
import output_pipeline
import thread_schedule


def make_reader(path, loop=True, backend='opencv', log_path=None, decode_threads=1, pool_size=11,keep_image=True,reuse_padding=False,render_storage='copy'):
    if backend == 'mpp-fused':
        return native_mpp.FusedReader(path,loop=loop,decode_threads=decode_threads,pool_size=pool_size,keep_image=keep_image,reuse_padding=reuse_padding,
            frame_canvas=render_storage=='inplace')
    if backend == 'mpp-native':
        return native_mpp.VideoReader(path,loop=loop,decode_threads=decode_threads,pool_size=pool_size)
    if backend == 'mpp':
        return media.MppVideoReader(path, loop=loop, log_path=log_path)
    if backend == 'opencv':
        return video.VideoReader(path, loop=loop, decode_threads=decode_threads)
    raise ValueError('Unknown decoder backend: '+backend)


def core_list(policy, contexts):
    return [str(i % 2) if policy == 'split' else policy for i in range(contexts)]


def check_model(model, batch):
    manifest = model.with_suffix('.json')
    if not manifest.exists():
        if batch != 1:
            raise ValueError('Batched models require the conversion .json manifest.')
        return
    data = json.loads(manifest.read_text(encoding='utf-8'))
    if data.get('batch') != batch or data.get('precision') != 'fp16':
        raise ValueError('Model manifest must match batch and FP16 precision.')
    if data.get('model_sha256') != hashlib.sha256(model.read_bytes()).hexdigest():
        raise ValueError('Model hash differs from the conversion manifest.')


def infer(runtime, batch):
    started = time.perf_counter()
    outputs = runtime.inference(inputs=[batch], data_format=['nhwc'])
    # Own the arrays before this context starts another inference.
    if not isinstance(outputs, (list, tuple)) or len(outputs) != 2:
        raise RuntimeError('RKNN did not return both complete outputs.')
    outputs = [np.array(output, copy=True) for output in outputs]
    channels = sorted(array.shape[1] for array in outputs if array.ndim == 3)
    if channels != [4, 80] or any(array.shape[0] != len(batch) for array in outputs):
        raise RuntimeError('RKNN output dimensions do not match the batch contract.')
    if outputs[0].shape[2] != outputs[1].shape[2]:
        raise RuntimeError('RKNN candidate counts differ.')
    return outputs, (time.perf_counter()-started)*1000


def compare_detections(reference, actual):
    if len(reference) != len(actual):
        raise ValueError('Detection count differs from batch-one reference.')
    if any(actual[i]['confidence'] < actual[i+1]['confidence'] for i in range(len(actual)-1)):
        raise ValueError('Detection output is not sorted by descending confidence.')
    unmatched = set(range(len(actual)))
    for left in reference:
        matches = []
        for index in unmatched:
            right = actual[index]
            if left['class_id'] != right['class_id']:
                continue
            a, b = np.array(left['xyxy']), np.array(right['xyxy'])
            intersection = np.maximum(0, np.minimum(a[2:], b[2:])-np.maximum(a[:2], b[:2])).prod()
            union = (a[2:]-a[:2]).prod()+(b[2:]-b[:2]).prod()-intersection
            iou = intersection/union if union > 0 else 0
            if iou >= .99 and abs(left['confidence']-right['confidence']) <= .02:
                matches.append((iou, index))
        if not matches:
            raise ValueError(f'No unused same-class match with IoU>=0.99 and score difference<=0.02: {left}')
        unmatched.remove(max(matches)[1])


def save_input_failure(output, batch, expected, actual, details, reference_rgb=None):
    """Keep one witness; validation may hold batched complete outputs."""
    target=Path(output)/'input-failure.npz'
    if target.exists():
        return
    values={'rgb':batch}
    if reference_rgb is not None:values['reference_rgb']=reference_rgb
    for prefix,arrays in [('reference',expected),('actual',actual)]:
        for array in arrays:
            values[prefix+('_scores' if array.shape[1]==80 else '_boxes')]=array
    np.savez_compressed(target,**values)
    vision.atomic_json(target.with_suffix('.json'),details)


def validate(engine, reference_model, path, batch_size, count=32, decode_backend='opencv', output=None,
             decode_threads=1, post_backend='python', renderer=None, preprocessor=None):
    check_model(reference_model, 1)
    reference = reader = candidate_reader = native = peer = None
    render_checks = native_checks = 0
    preprocess_diffs=[]
    try:
        if post_backend == 'cpp':
            native = native_post.Postprocessor(comparison_dtype=np.float32 if getattr(engine,'output_mode','fp32')=='fp16' else None)
        reference = video.Engine(reference_model, ['0'])
        reader = video.VideoReader(path, loop=True)
        reference_items = [reader.read() for _ in range(count)]
        images = [item['image'] for item in reference_items]
        candidate_images = images
        pixel_diffs = []
        fused_inputs=[]
        if decode_backend in ('mpp','mpp-native','mpp-fused') or decode_threads != 1:
            if decode_backend == 'mpp':
                candidate_reader = make_reader(path, loop=True, backend='mpp',
                    log_path=output/'validation-decoder.gst.log' if output else None)
            else:
                candidate_reader = make_reader(path, loop=True, backend=decode_backend,
                                               decode_threads=decode_threads)
            candidate_images = []
            for index, image in enumerate(images):
                if decode_backend=='mpp-fused':
                    prepared_input=np.empty((1,640,640,3),np.float16)
                    item=candidate_reader.read_prepared(prepared_input)
                    fused_inputs.append(prepared_input)
                else:item = candidate_reader.read()
                if (item['source_frame'], item['cycle']) != (reference_items[index]['source_frame'], reference_items[index]['cycle']) or item['image'].shape != image.shape:
                    raise ValueError('Candidate decoder frame dimensions/order differ.')
                diff = np.abs(item['image'].astype(np.int16)-image.astype(np.int16))
                candidate_images.append(item['image'].copy() if decode_backend in ('mpp-native','mpp-fused') else item['image'])
                if decode_backend in ('mpp-native','mpp-fused'):
                    video.release_image(item)
                    if diff.max()!=0 and decode_backend!='mpp-fused':raise ValueError(f'Native decoder pixels differ at source frame {index}')
                pixel_diffs.append({'source_frame': index, 'mean_absolute_error': float(diff.mean()),
                                    'max_absolute_error': int(diff.max())})
            candidate_reader.close()
            if output:
                vision.atomic_json(output/'decoder-validation.json', {'backend': decode_backend,
                    'decode_threads': decode_threads, 'pixel_differences': pixel_diffs,
                    'evidence': getattr(candidate_reader, 'evidence', {'backend': decode_backend})})
        expected = []
        for image in images:
            batch, transforms = detector.preprocess_batch([image])
            outputs, _ = infer(reference.runtimes[0], batch)
            expected.extend(detector.postprocess_batch(outputs, transforms, 1))
        # Validate every context before performance ranking.
        for worker,runtime in enumerate(engine.runtimes):
            if getattr(engine,'output_mode','fp32')=='fp16':
                peer=native_rknn.Runtime(runtime.lib,reference_model,Path(engine.info['library']),str(worker%2),
                                         True,runtime.input_mode,'fp32')
            for offset in range(0, count, batch_size):
                group = candidate_images[offset:offset+batch_size]
                if fused_inputs:
                    batch=fused_inputs[offset]
                    _,transforms=detector.preprocess_batch(group,batch_size)
                else:
                    batch, transforms = (preprocessor.batch(group,batch_size) if preprocessor else
                                          detector.preprocess_batch(group, batch_size))
                if preprocessor and worker==0:
                    reference_rgb,reference_transforms=detector.preprocess_batch(group,batch_size)
                    if transforms!=reference_transforms:raise ValueError('RGA letterbox transforms differ')
                    expected_input=((reference_rgb.astype(np.float32)/np.float32(255)).astype(np.float16)
                                    if preprocessor.fused else reference_rgb)
                    delta=np.abs(batch.astype(np.float32)-expected_input.astype(np.float32))
                    preprocess_diffs.append({'source_frame':offset,'max_error':float(delta.max()),
                        'mean_error':float(delta.mean()),'tensor_bit_exact':bool(np.array_equal(batch,expected_input))})
                    if not np.array_equal(batch.view(np.uint8),expected_input.view(np.uint8)) and decode_backend!='mpp-fused':
                        raise ValueError(f'Prepared input bits differ at source frame {offset}')
                if peer:
                    outputs=runtime.inference_raw([batch])
                    old_outputs=peer.inference([batch])
                    if any(not np.array_equal(a.astype(np.float32).view(np.uint32),b.view(np.uint32)) for a,b in zip(outputs,old_outputs)):
                        if output:save_input_failure(output,batch,old_outputs,outputs,{'worker':worker,'source_frame':offset,
                            'error':'Native FP16 outputs differ from FP32 retrieval','kind':'validation raw output witness'})
                        raise ValueError(f'Native FP16 output differs at source frame {offset}')
                else:outputs, _ = infer(runtime, batch)
                python_actual = detector.postprocess_batch([a.astype(np.float32,copy=False) for a in outputs], transforms, batch_size)
                actual = native.batch(outputs, transforms, batch_size) if native else python_actual
                if native:
                    if actual != python_actual:
                        raise ValueError('Native postprocessing differs on identical raw outputs.')
                    native_checks += len(group)
                for index, result in enumerate(actual):
                    try:
                        compare_detections(expected[offset+index], result)
                    except ValueError as error:
                        if output and (preprocessor or getattr(runtime,'info',{}).get('input_mode')=='fp16-pass'):
                            reference_rgb,_=detector.preprocess_batch([images[offset+index]])
                            reference_outputs,_=infer(reference.runtimes[0],reference_rgb)
                            save_input_failure(output,batch,reference_outputs,outputs,
                                {'source_frame':reference_items[offset+index]['source_frame'],
                                 'worker':worker,'error':str(error),'transform':transforms[index],
                                 'native_input':getattr(runtime,'info',{}),'kind':'original validation output witness',
                                 'preprocess_evidence':preprocessor.evidence() if preprocessor else None},
                                reference_rgb=reference_rgb if preprocessor else None)
                        raise ValueError(f'Validation frame {offset+index}: {error}') from error
                    if renderer is not None:
                        detail = f'Validation {offset+index}'
                        if not np.array_equal(video.decorate(group[index], result, detail),
                                              renderer.draw(group[index], result, detail)):
                            raise ValueError('Cached renderer is not pixel-identical.')
                        render_checks += 1
            if peer:peer.release();peer=None
        return {'passed': True, 'frames': count, 'contexts': len(engine.runtimes),
                'decode_backend': decode_backend, 'decode_threads': decode_threads,
                'pixel_differences': pixel_diffs,
                'native_exact_checks': native_checks, 'render_exact_checks': render_checks,
                'preprocess_pixel_differences':preprocess_diffs,
                'preprocess_evidence':preprocessor.evidence() if preprocessor else None,
                'reference_sha256': hashlib.sha256(reference_model.read_bytes()).hexdigest()}
    finally:
        if peer:peer.release()
        if native:
            native.close()
        if candidate_reader:
            candidate_reader.close()
        if reader:
            reader.close()
        if reference:
            reference.close()


def execute(engine, args, seconds, output=None, stop=None):
    """Independent producer/NPU/postprocess stages; ordered, bounded output."""
    stop = stop or threading.Event()
    abort = threading.Event()
    inflight_limit=getattr(args,'max_inflight',None) or args.queue_batches
    slots = threading.Semaphore(inflight_limit)
    prepared, raw, completed = (queue.Queue(args.queue_batches) for _ in range(3))
    unprepared=queue.Queue(args.queue_batches)
    errors, records = [], []
    counts = {'submitted': 0, 'batches': 0, 'inference_done': 0,'preparation_done':0}
    wait_totals = {'slot_wait_ms': 0., 'raw_put_wait_ms': 0., 'completed_put_wait_ms': 0.}
    lock = threading.Lock()
    log_dir = output or getattr(args, 'output', None)
    phase = 'measurement' if output else 'warmup'
    direct=getattr(args,'decode_backend','opencv')=='mpp-fused'
    thread_schedule.begin(getattr(args,'cpu_policy','auto'))
    ledger=thread_accounting.Phase() if getattr(args,'thread_accounting',False) and not direct else None
    cache=None
    bound=getattr(engine,'io_mode','copy')!='copy'
    if bound:prepared=native_rknn.PreparedQueues(len(engine.runtimes),args.queue_batches)
    reader = make_reader(args.video, loop=not args.once,
                         backend=getattr(args, 'decode_backend', 'opencv'),
                         decode_threads=getattr(args, 'decode_threads', 1),
                         pool_size=args.queue_batches*args.batch+3,
                         keep_image=args.mode=='display',
                         reuse_padding=getattr(args,'reuse_padding',False),
                         render_storage=getattr(args,'render_storage','copy'),
                         log_path=log_dir/(phase+'-decoder.gst.log') if log_dir else None)
    source = native_mpp.DirectSource(reader) if direct else video.Prefetch(reader,phase=ledger)
    pool = []
    if args.mode == 'infer':
        # All preprocessing is outside the timed region in inference-only mode.
        try:
            for _ in range(max(2, math.ceil(32/args.batch))):
                items = [source.read() for _ in range(args.batch)]
                if any(item is None for item in items):
                    raise ValueError('Inference pool needs 32 frames; use looping input.')
                batch, transforms = detector.preprocess_batch([item['image'] for item in items])
                pool.append((items,batch,transforms))
        finally:
            source.close()
    input_buffers = queue.Queue(args.queue_batches)
    reuse_inputs = not getattr(args, 'allocate_inputs', False)
    if not bound and not pool and reuse_inputs:
        for _ in range(args.queue_batches):
            input_buffers.put(np.empty((args.batch, 640, 640, 3),
                dtype=np.float16 if getattr(args,'input_mode','uint8')=='fp16-ready' else np.uint8))
    encoder = None
    encoder_evidence = None
    log = None
    threads = []
    encoder_drain_ms = 0.
    json_drain_ms = 0.
    started = time.perf_counter()
    process_cpu_started = time.process_time()
    child_times = os.times()
    children_cpu_started = child_times.children_user + child_times.children_system
    preprocessor=getattr(args,'preprocessor',None)
    pre_workers=getattr(args,'pre_workers',1)
    parallel_prepare=not direct and (getattr(args,'feed_path','standard')=='fused' or pre_workers>1)
    processors=getattr(args,'preprocessors',None) or [preprocessor]*pre_workers
    hardware_calls_started=sum(p.calls for p in processors if p)

    def put(target, item):
        begin = time.perf_counter()
        while not abort.is_set():
            try:
                target.put(item, timeout=.1)
                key = 'raw_put_wait_ms' if target is raw else 'completed_put_wait_ms' if target is completed else None
                if key:
                    with lock:
                        wait_totals[key] += (time.perf_counter()-begin)*1000
                return True
            except queue.Full:
                pass
        return False

    def get(target):
        while not abort.is_set():
            try:
                return target.get(timeout=.1)
            except queue.Empty:
                pass
        return None

    def guarded(function,role):
        def wrapped():
            try:
                thread_schedule.apply(role)
                function()
            except BaseException as error:
                errors.append(error)
                abort.set()
        return wrapped

    def produce():
        sequence = 0
        while not abort.is_set() and not stop.is_set() and time.perf_counter()-started < seconds:
            limit = getattr(args, 'max_frames', 0)
            if limit and counts['submitted'] >= limit:
                break
            slot_begin = time.perf_counter()
            acquired = slots.acquire(timeout=.1)
            wait_totals['slot_wait_ms'] += (time.perf_counter()-slot_begin)*1000
            if not acquired:
                continue
            if stop.is_set() or time.perf_counter()-started >= seconds:
                slots.release()
                break
            begin = time.perf_counter()
            direct_lease=None
            if direct:
                slot_begin=time.perf_counter();direct_lease=engine.input_pool.acquire(abort)
                if direct_lease is None:slots.release();break
                input_wait=(time.perf_counter()-slot_begin)*1000
                try:item=reader.read_prepared(direct_lease.arrays[0])
                except BaseException:direct_lease.release();slots.release();raise
                if item is None:direct_lease.release();slots.release();break
                items=[item];decode_wait_ms=0.
            elif pool:
                originals, batch, transforms = pool[sequence % len(pool)]
                items = [dict(item, decode_started=begin, decode_ms=0) for item in originals]
                if limit:
                    items = items[:limit-counts['submitted']]
                pre_ms = 0
                decode_wait_ms = 0.
            else:
                items = []
                decode_wait_begin = time.perf_counter()
                for _ in range(args.batch):
                    if limit and counts['submitted']+len(items) >= limit:
                        break
                    item = source.read()
                    if item is None:
                        break
                    items.append(item)
                decode_wait_ms = (time.perf_counter()-decode_wait_begin)*1000
                if not items:
                    slots.release()
                    break
            task = {'sequence': sequence, 'first_frame': counts['submitted'], 'items': items,
                    'decode_wait_ms': decode_wait_ms}
            if direct:
                task.update(batch=item.pop('prepared'),transforms=item.pop('transforms'),input_lease=direct_lease,
                    target_context=direct_lease.worker,input_owner='bound',preprocess_ms=item['fused_prepare_ms'],
                    preprocess_cpu_ms=item['fused_prepare_cpu_ms'],pre_parts={'cpu_fused_kernel_wall_ms':item['fused_prepare_ms'],
                    'cpu_fused_kernel_cpu_ms':item['fused_prepare_cpu_ms']},preparation_worker=0,prepare_queue_wait_ms=0.,input_slot_wait_ms=input_wait,
                    ready_queue_depth=prepared.qsize())
            elif pool:
                task.update(batch=batch,transforms=transforms,preprocess_ms=0.,preprocess_cpu_ms=0.,
                    pre_parts={},preparation_worker=-1,prepare_queue_wait_ms=0.,input_slot_wait_ms=0.)
                task['ready_queue_depth']=prepared.qsize()
            elif not parallel_prepare:
                task=prepare_task(task,0,0.)
                if task is None:return
            if not put(prepared if pool or not parallel_prepare else unprepared, task):
                return
            counts['submitted'] += len(items)
            counts['batches'] += 1
            sequence += 1
            if len(items) < args.batch:
                break
        for _ in range(len(engine.runtimes) if pool or not parallel_prepare else pre_workers):
            put(prepared if pool or not parallel_prepare else unprepared, None)

    def prepare_task(task,worker,waited):
        processor=processors[worker]
        slot_begin=time.perf_counter()
        if bound:
            lease=engine.input_pool.acquire(abort)
            if lease is None:return None
            task['input_lease']=lease;task['target_context']=lease.worker
            buffer=lease.arrays[0]
        else:buffer=get(input_buffers) if reuse_inputs else None
        if reuse_inputs and buffer is None:return None
        task['input_slot_wait_ms']=(time.perf_counter()-slot_begin)*1000
        task['input_owner']='bound' if bound else 'pool' if reuse_inputs else 'allocation'
        begin,cpu_begin=time.perf_counter(),time.thread_time()
        prepare=processor.batch if processor else detector.preprocess_batch
        try:
            task['batch'],task['transforms']=prepare([i['image'] for i in task['items']],args.batch,out=buffer)
        finally:
            if args.mode=='detect':
                for item in task['items']:video.release_image(item)
        task['preprocess_cpu_ms']=(time.thread_time()-cpu_begin)*1000
        task['preprocess_ms']=(time.perf_counter()-begin)*1000
        task['pre_parts']=processor.last_timing.copy() if processor else {}
        task.update(preparation_worker=worker,prepare_queue_wait_ms=waited,ready_queue_depth=prepared.qsize())
        return task

    def preprocess(worker):
        while not abort.is_set():
            wait_begin=time.perf_counter();task=get(unprepared)
            waited=(time.perf_counter()-wait_begin)*1000
            if task is None:break
            task=prepare_task(task,worker,waited)
            if task is None:return
            if not put(prepared,task):return
        with lock:
            counts['preparation_done']+=1
            last=counts['preparation_done']==pre_workers
        if last:
            for _ in engine.runtimes:put(prepared,None)

    def inference(worker):
        while not abort.is_set():
            wait_begin = time.perf_counter()
            task = get(prepared.queues[worker] if bound else prepared)
            prepared_wait_ms = (time.perf_counter()-wait_begin)*1000
            if task is None:
                break
            task['prepared_wait_ms'] = prepared_wait_ms
            batch = task.pop('batch')
            runtime = engine.runtimes[worker]
            task['runtime_parts'] = {}
            task['output_buffer_wait_ms'] = 0.
            lease = None
            if hasattr(engine, 'output_pool'):
                begin = time.perf_counter()
                lease = engine.output_pool.acquire(abort,worker) if bound and engine.io_mode=='bind-both' else engine.output_pool.acquire(abort)
                task['output_buffer_wait_ms'] = (time.perf_counter()-begin)*1000
                if lease is None:
                    return
            begin, cpu_begin = time.perf_counter(), time.thread_time()
            try:
                if lease:
                    task['outputs'], task['runtime_parts'] = runtime.run_into(
                        batch, lease.arrays, profile=getattr(args, 'profile_device', False))
                    task['inference_ms'] = (time.perf_counter()-begin)*1000
                    task['output_lease'] = lease
                else:
                    task['outputs'], task['inference_ms'] = infer(runtime, batch)
            except BaseException:
                if lease:
                    lease.release()
                raise
            task['inference_cpu_ms'] = (time.thread_time()-cpu_begin)*1000
            if task.get('input_lease'):task.pop('input_lease').release()
            if not pool and reuse_inputs and task.pop('input_owner','pool')=='pool':
                put(input_buffers, batch)
            task['worker'] = worker
            task['raw_queue_depth']=raw.qsize()
            if not put(raw, task):
                return
        with lock:
            counts['inference_done'] += 1
            last = counts['inference_done'] == len(engine.runtimes)
        if last:
            for _ in range(args.post_workers):
                put(raw, None)

    def postprocess():
        native = native_post.Postprocessor(comparison_dtype=np.float32 if getattr(args,'output_mode','fp32')=='fp16' else None) if getattr(args, 'post_backend', 'python') == 'cpp' and not pool else None
        try:
            postprocess_loop(native)
        finally:
            if native:
                native.close()

    def postprocess_loop(native):
        while not abort.is_set():
            task = get(raw)
            if task is None:
                break
            before = time.perf_counter()
            cpu_before = time.thread_time()
            try:
                task['detections'] = ([[] for _ in task['items']] if pool else
                    (native.batch(task['outputs'], task['transforms'], args.batch) if native else
                     detector.postprocess_batch(task['outputs'], task['transforms'], args.batch)))
            finally:
                task.pop('outputs', None)
                lease = task.pop('output_lease', None)
                if lease:
                    lease.release()
            task['postprocess_ms'] = (time.perf_counter()-before)*1000
            task['postprocess_cpu_ms'] = (time.thread_time()-cpu_before)*1000
            task['post_parts'] = native.last_timing.copy() if native else dict(
                post_convert_ms=0., post_native_ms=0., post_pack_ms=0.)
            if not put(completed, task):
                return
        put(completed, None)

    def make_encoder(image):
        backend=getattr(args,'encode_backend','x264')
        if backend=='mpp-native':
            return native_output.Encoder(output/'annotated.mp4',image,reader.fps,args.encoder_bitrate)
        if backend=='mpp':return media.MppEncoder(output/'annotated.mp4',image,reader.fps,bitrate=args.encoder_bitrate)
        return video.Encoder(output/'annotated.mp4',image,reader.fps,preset=getattr(args,'encoder_preset','veryfast'),threads=getattr(args,'encoder_threads',2))

    try:
        if output and args.mode != 'infer':
            log = (output/'frames.jsonl').open('w', encoding='utf-8', buffering=1024*1024)
        functions = [('producer',produce)]+([] if pool or not parallel_prepare else [('prepare',lambda i=i:preprocess(i)) for i in range(pre_workers)])
        functions += [('npu_caller',lambda i=i:inference(i)) for i in range(len(engine.runtimes))]
        functions += [('postprocess',postprocess)]*args.post_workers
        for role,function in functions:
            function=guarded(function,role)
            thread = threading.Thread(target=ledger.wrap(role,function) if ledger else function,name=role,daemon=True)
            threads.append(thread)
            thread.start()
        if ledger:
            started,process_cpu_started=ledger.start(len(functions)+1,release=False)
            ledger.go.set()
        next_sequence, ended, waiting = 0, 0, {}
        thread_schedule.apply('main_output')
        while ended < args.post_workers:
            if errors:
                raise errors[0]
            try:
                task = completed.get(timeout=.1)
            except queue.Empty:
                continue
            if task is None:
                ended += 1
                continue
            waiting[task['sequence']] = task
            while next_sequence in waiting:
                task = waiting.pop(next_sequence)
                for index, (item, detections) in enumerate(zip(task['items'], task['detections'])):
                    before = time.perf_counter()
                    draw_cpu_begin = time.thread_time()
                    draw_cpu_ms = 0.
                    draw_ms = encoder_init_ms = encode_write_ms = 0.
                    if output and args.mode == 'display':
                        detail=f"Frame {item['source_frame']:04d} | {len(detections)} objects | batch {args.batch} | playback {reader.fps:g} FPS"
                        if getattr(args,'display_pipeline','serial')=='async':
                            inplace=getattr(args,'render_storage','copy')=='inplace'
                            if encoder is None:encoder=output_pipeline.QueuedEncoder(make_encoder,shared_cache=inplace)
                            lease=item.pop('image_lease',None) if inplace else None
                            draw_ms,draw_cpu_ms,encode_write_ms=encoder.draw_submit(item['image'],detections,detail,
                                canvas=item.get('canvas') if inplace else None,lease=lease)
                        else:
                            draw = args.renderer.draw if getattr(args, 'renderer', None) is not None else video.decorate
                            rendered=draw(item['image'],detections,detail)
                            draw_ms=(time.perf_counter()-before)*1000;draw_cpu_ms=(time.thread_time()-draw_cpu_begin)*1000
                            encoder_begin=time.perf_counter()
                            if encoder is None:encoder=make_encoder(rendered)
                            encoder_init_ms=(time.perf_counter()-encoder_begin)*1000
                            write_begin=time.perf_counter();encoder.write(rendered);encode_write_ms=(time.perf_counter()-write_begin)*1000
                    video.release_image(item)
                    now = time.perf_counter()
                    record = {'frame': task['first_frame']+index,
                              'task_sequence': task['sequence'],
                              'source_frame': item['source_frame'], 'cycle': item['cycle'],
                              'worker': task['worker'], 'batch': args.batch,
                              'batch_valid': len(task['items']), 'batch_slot': index,
                              'decode_ms': item['decode_ms'],
                              'decode_grab_ms': item.get('decode_grab_ms', 0.),
                              'decode_retrieve_ms': item.get('decode_retrieve_ms', 0.),
                              'decode_cpu_ms': item.get('decode_cpu_ms', 0.),
                              'decode_pool_wait_ms':item.get('decode_pool_wait_ms',0.),
                              'decode_convert_cpu_ms':item.get('decode_convert_cpu_ms',0.),
                              'source_pts':item.get('source_pts'),**item.get('media_parts',{}),
                              'preprocess_ms': task['preprocess_ms'],
                              'inference_ms': task['inference_ms'],
                              'postprocess_ms': task['postprocess_ms'],
                              'decode_wait_ms': task['decode_wait_ms'],
                              'prepared_wait_ms': task['prepared_wait_ms'],
                               'preparation_worker':task['preparation_worker'],
                               'prepare_queue_wait_ms':task['prepare_queue_wait_ms'],
                               'input_slot_wait_ms':task['input_slot_wait_ms'],
                               'ready_queue_depth':task['ready_queue_depth'],
                               'raw_queue_depth':task['raw_queue_depth'],
                               'output_buffer_wait_ms': task['output_buffer_wait_ms'],
                               'inference_cpu_ms': task['inference_cpu_ms'],
                               **task['runtime_parts'],
                               **task['pre_parts'],
                              'draw_ms': draw_ms, 'encoder_init_ms': encoder_init_ms,
                              'encode_write_ms': encode_write_ms,
                              'preprocess_cpu_ms': task['preprocess_cpu_ms'],
                              'postprocess_cpu_ms': task['postprocess_cpu_ms'],
                              'draw_cpu_ms': draw_cpu_ms, **task['post_parts'],
                              'output_ms': (now-before)*1000,
                              'latency_ms': (now-item['decode_started'])*1000,
                              'decode_started_monotonic':item['decode_started'],
                              'completed_s': now-started}
                    if log:
                        json_begin = time.perf_counter()
                        log.write(json.dumps({**record, 'detections': detections})+'\n')
                        record['json_write_ms'] = (time.perf_counter()-json_begin)*1000
                    else:
                        record['json_write_ms'] = 0.
                    records.append(record)
                slots.release()
                next_sequence += 1
        if waiting or len(records) != counts['submitted']:
            raise RuntimeError('Submitted/completed/order mismatch.')
        if encoder:
            current, encoder = encoder, None
            drain_begin = time.perf_counter()
            current.close()
            encoder_drain_ms = (time.perf_counter()-drain_begin)*1000
            encoder_evidence = getattr(current, 'evidence', None)
        if log:
            current, log = log, None
            drain_begin = time.perf_counter()
            current.close()
            json_drain_ms = (time.perf_counter()-drain_begin)*1000
        ledger_result=None
        if ledger:
            source.cancel()
            ledger_result,process_cpu_ms,ended=ledger.end(process_cpu_started,len(records))
            elapsed=ended-started
        else:
            process_cpu_ms = (time.process_time()-process_cpu_started)*1000
            elapsed = time.perf_counter()-started
        child_times = os.times()
        children_cpu_ms = max(0., child_times.children_user + child_times.children_system - children_cpu_started)*1000
        diagnostics = {name: {**video.distribution([r[name] for r in records]),
                              'mean': float(np.mean([r[name] for r in records])) if records else None,
                              'sum_ms': sum(r[name] for r in records)}
                       for name in ['decode_wait_ms', 'prepared_wait_ms', 'draw_ms',
                                    'encoder_init_ms', 'encode_write_ms', 'json_write_ms',
                                    'preprocess_cpu_ms', 'postprocess_cpu_ms', 'draw_cpu_ms',
                                    'post_convert_ms', 'post_native_ms', 'post_pack_ms']}
        runtime_metrics = {}
        completion={}
        encoding=encoder_evidence or {}
        if encoding.get('backend')=='async':encoding=encoding.get('encoder',{})
        if encoding.get('pipeline')=='pipelined':
            events=dict(encoding.get('completion_events',[]))
            if set(events)!=set(range(len(records))):raise RuntimeError('Encoded completion timestamps are incomplete')
            values=[(events[i]-r['decode_started_monotonic'])*1000 for i,r in enumerate(records)]
            if any(v<0 for v in values):raise RuntimeError('Encoder and source monotonic clocks differ')
            completion=dict(encoder_completion_latency_ms={**video.distribution(values),'mean':float(np.mean(values))},
                completion_note='Source read start to encoded frame completion; includes pipeline waits, excludes final MP4 mux')
        for name in ['inference_cpu_ms', 'output_buffer_wait_ms','prepare_queue_wait_ms','input_slot_wait_ms','ready_queue_depth','raw_queue_depth','decode_pool_wait_ms','decode_convert_cpu_ms'] + sorted({
                k for r in records for k in r if k.startswith(('rknn_','cpu_fused_','mpp_')) and k.endswith('_ms')}):
            values = [r[name] for r in records if name in r]
            runtime_metrics[name] = {**video.distribution(values),
                'mean': float(np.mean(values)) if values else None, 'sum': sum(values), 'count': len(values)}
        return {**video.summarize(records, elapsed), 'submitted': counts['submitted'],
                **completion,
                'render_cache':encoder_evidence.get('render_cache') if encoder_evidence else None,
                'per_frame_ms': {key: {**video.distribution(values), 'mean': float(np.mean(values)) if values else None,
                                      'sum_ms': sum(values)} for key in
                    ['preprocess_ms', 'inference_ms', 'postprocess_ms', 'preprocess_cpu_ms',
                     'postprocess_cpu_ms', 'post_convert_ms', 'post_native_ms', 'post_pack_ms',
                     'decode_wait_ms', 'prepared_wait_ms']
                    for values in [[r[key]/r['batch_valid'] for r in records]]},
                'decode_parts_ms': {key: {'mean': float(np.mean([r[key] for r in records])) if records else None,
                                         'sum_ms': sum(r[key] for r in records)}
                                    for key in ['decode_ms', 'decode_grab_ms', 'decode_retrieve_ms', 'decode_cpu_ms']},
                'stage_mean_ms': {key: float(np.mean([r[key] for r in records])) if records else None
                                  for key in ['decode_ms', 'preprocess_ms', 'inference_ms', 'postprocess_ms', 'output_ms']},
                'diagnostic_ms': diagnostics, 'encoder_drain_ms': encoder_drain_ms,
                'runtime_metrics': runtime_metrics,
                'process_cpu_ms':process_cpu_ms,
                'children_cpu_ms':children_cpu_ms,
                'family_cpu_ms_per_image':(process_cpu_ms+children_cpu_ms)/len(records) if records else None,
                'family_cpu_note':'process threads plus reaped children in this window, including the drained encoder; excludes external sampler',
                'thread_accounting':ledger_result,
                'input_source':getattr(args,'input_source','video'),
                'diagnostic_cache':cache.info if cache else None,
                'process_cpu_ms_per_image':process_cpu_ms/len(records) if records else None,
                'process_cpu_note':'all threads of this process; excludes child processes and sampler',
                'preprocess_calls':counts['submitted'] if direct else sum(p.calls for p in processors if p)-hardware_calls_started,
                'preprocess_hardware_calls':(sum(p.calls for p in processors if p)-hardware_calls_started) if getattr(args,'preprocess_backend','rga')=='rga' else 0,
                'json_drain_ms': json_drain_ms,
                'queue_wait_ms': wait_totals,
                'infer_pool_frames': sum(len(items) for items, _, _ in pool),
                'completed': len(records), 'batches': counts['batches'],
                'batch_per_s': counts['batches']/elapsed,
                'queue_bound_frames': args.queue_batches*args.batch,
                'max_inflight_batches':inflight_limit,
                'decode_prefetch_bound_frames': 3 if not pool else 0,
                'media': {'decoder': getattr(reader, 'evidence', {'backend': 'opencv'}),
                          'encoder': encoder_evidence or {'backend': 'disabled' if args.mode != 'display'
                                                         else getattr(args, 'encode_backend', 'x264')}},
                'thread_schedule':thread_schedule.report(),
                'display_pipeline':getattr(args,'display_pipeline','serial'),
                'stage_time_unit': 'preprocess/inference/postprocess are per batch; latency is per image',
                'measurement_start_monotonic': started, 'measurement_end_monotonic': started+elapsed}
    finally:
        abort.set()
        if ledger:ledger.abort()
        source.cancel()
        for thread in threads:
            thread.join(timeout=60)
        engine.workers_active = any(thread.is_alive() for thread in threads)
        if not engine.workers_active and hasattr(engine, 'output_pool'):
            engine.output_pool.reclaim()
        if not engine.workers_active and bound:engine.input_pool.reclaim()
        try:
            if encoder:encoder.close()
        finally:
            output_alive=bool(encoder and hasattr(encoder,'thread') and encoder.thread.is_alive())
            if not pool and not output_alive:source.close()
            if log:log.close()
            if output_alive:engine.workers_active=True
        if log_dir:
            vision.atomic_json(log_dir/(phase+'-media.json'),
                               {'decoder': getattr(reader, 'evidence', {'backend': 'opencv'}),
                                'encoder': encoder_evidence or getattr(encoder, 'evidence', None)})
        if engine.workers_active:
            raise RuntimeError('Worker did not stop; runtime must not be released while active.')
        thread_schedule.restore()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--model', type=Path, required=True)
    parser.add_argument('--reference-model', type=Path, required=True)
    parser.add_argument('--video', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--batch', type=int, default=1)
    parser.add_argument('--contexts', type=int, default=2)
    parser.add_argument('--core-policy', choices=['0', '1', 'auto', '0_1', 'split'], default='split')
    parser.add_argument('--queue-batches', type=int, default=4)
    parser.add_argument('--max-inflight',type=int,default=None,
                        help='Global in-flight batch limit; queue and buffer capacity remain queue-batches.')
    parser.add_argument('--post-workers', type=int, default=1)
    parser.add_argument('--allocate-inputs', action='store_true',
                        help='Disable input-buffer reuse for a controlled allocation comparison.')
    parser.add_argument('--encoder-preset', choices=['ultrafast', 'superfast', 'veryfast'], default='veryfast')
    parser.add_argument('--encoder-threads', type=int, default=2)
    parser.add_argument('--decode-backend', choices=['opencv', 'mpp','mpp-native','mpp-fused'], default='opencv')
    parser.add_argument('--decode-threads', type=int, choices=[1, 2, 4], default=1)
    parser.add_argument('--post-backend', choices=['python', 'cpp'], default='python')
    parser.add_argument('--inference-backend', choices=['lite', 'native-copy', 'native-prealloc'], default='lite')
    parser.add_argument('--input-mode',choices=['uint8','fp16-pass','fp16-ready'],default='uint8')
    parser.add_argument('--preprocess-backend',choices=['cpu','cpu-fused'],default='cpu')
    parser.add_argument('--output-mode',choices=['fp32','fp16'],default='fp32')
    parser.add_argument('--input-source',choices=['video'],default='video')
    parser.add_argument('--thread-accounting',action='store_true')
    parser.add_argument('--feed-path',choices=['standard','fused'],default='standard')
    parser.add_argument('--pre-workers',type=int,choices=[1],default=1)
    parser.add_argument('--io-mode',choices=['copy','bind-input','bind-both'],default='copy')
    parser.add_argument('--binding-mode',choices=['dynamic','fixed'],default='dynamic')
    parser.add_argument('--profile-device', action='store_true', help='SDK PERF_RUN queries; diagnostic runs only.')
    parser.add_argument('--render-backend', choices=['original', 'cached'], default='original')
    parser.add_argument('--encode-backend', choices=['x264', 'mpp','mpp-native'], default='x264')
    parser.add_argument('--display-pipeline',choices=['serial','async'],default='serial')
    parser.add_argument('--cpu-policy',choices=['auto','roles'],default='auto')
    parser.add_argument('--validation-frames',type=int,choices=[4,8,16,32],default=32)
    parser.add_argument('--reuse-padding',action='store_true')
    parser.add_argument('--render-storage',choices=['copy','inplace'],default='copy')
    parser.add_argument('--encoder-bitrate', type=int, default=14000000)
    parser.add_argument('--mode', choices=['infer', 'detect', 'display'], default='detect')
    parser.add_argument('--duration', type=float, default=30)
    parser.add_argument('--max-frames', type=int, default=0,
                        help='Stop after this many valid images; 0 retains duration/EOF behavior.')
    parser.add_argument('--warmup', type=float, default=5)
    parser.add_argument('--once', action='store_true')
    args = parser.parse_args()
    if min(args.batch, args.contexts, args.queue_batches, args.post_workers, args.encoder_threads, args.encoder_bitrate) < 1:
        parser.error('Batch, contexts, queue and worker counts must be positive.')
    if args.max_inflight is None:args.max_inflight=args.queue_batches
    if args.max_inflight<1 or args.max_inflight>args.queue_batches:parser.error('max-inflight must be between 1 and queue-batches')
    if not all(math.isfinite(v) for v in [args.duration, args.warmup]) or args.duration <= 0 or args.warmup < 0:
        parser.error('Invalid duration/warmup.')
    if args.once and args.mode == 'infer':
        parser.error('--once is for complete video detect/display modes.')
    if args.max_frames < 0:
        parser.error('max-frames must be nonnegative')
    if args.inference_backend != 'lite' and (args.batch != 1 or args.core_policy != 'split'):
        parser.error('Native experiment requires batch=1 and split core policy')
    if args.profile_device and args.inference_backend == 'lite':
        parser.error('Device profiling requires a native backend')
    if args.input_mode in ('fp16-pass','fp16-ready') and args.inference_backend!='native-prealloc':
        parser.error('FP16 pass-through experiment requires native-prealloc')
    if (args.input_mode=='fp16-ready') != (args.feed_path=='fused'):
        parser.error('FP16-ready requires fused preparation and vice versa')
    if args.feed_path=='fused' and args.preprocess_backend!='cpu-fused':parser.error('Fused requires CPU fused')
    if args.preprocess_backend=='cpu-fused' and (args.batch!=1 or args.mode not in ('detect','display')):parser.error('CPU fused requires batch one detect/display')
    if args.decode_backend in ('mpp-native','mpp-fused') and (args.batch!=1 or args.mode not in ('detect','display')):parser.error('MPP native requires batch one detect/display')
    if args.decode_backend=='mpp-fused' and args.io_mode!='bind-both':parser.error('Fused MPP requires bound FP16 I/O')
    if args.output_mode=='fp16' and (args.inference_backend!='native-prealloc' or args.post_backend!='cpp' or args.mode not in ('detect','display')):parser.error('FP16 outputs require native prealloc C++ detect/display')
    if args.io_mode=='copy' and args.binding_mode!='dynamic':parser.error('binding-mode applies only to bound I/O')
    if args.io_mode!='copy' and not (args.contexts in (2,4) and args.queue_batches==8 and args.input_mode=='fp16-ready' and args.output_mode=='fp16' and args.inference_backend=='native-prealloc' and args.decode_backend in ('mpp-native','mpp-fused') and args.mode in ('detect','display') and not args.profile_device and args.batch==1):
        parser.error('Bound I/O requires batch-one FP16 MPP detection, depth eight and two/four contexts')
    if args.binding_mode=='fixed' and args.io_mode!='bind-both':parser.error('Fixed binding requires bind-both I/O')
    if args.binding_mode=='fixed' and args.contexts!=4:parser.error('Fixed binding comparison requires four contexts')
    if args.display_pipeline=='async' and (args.mode!='display' or args.thread_accounting):parser.error('Async output requires display without thread ledger')
    if args.render_storage=='inplace' and not (args.mode=='display' and args.decode_backend=='mpp-fused' and args.display_pipeline=='async' and args.render_backend=='cached'):
        parser.error('Inplace rendering requires fused MPP display, cached drawing and async output')
    cv2.setNumThreads(1)
    check_model(args.model, args.batch)
    args.output.mkdir(parents=True, exist_ok=False)
    stop = threading.Event()
    for sig in (signal.SIGINT, signal.SIGTERM):
        signal.signal(sig, lambda *_: stop.set())
    engine = None
    args.preprocessor=None
    args.preprocessors=[]
    args.input_cache=None
    try:
        if args.thread_accounting:thread_accounting.enable()
        if args.preprocess_backend=='cpu-fused':
            args.preprocessors=[cpu_preprocess.Processor()]
            args.preprocessor=args.preprocessors[0]
        args.renderer = cached_render.Renderer() if args.render_backend == 'cached' else None
        cores = core_list(args.core_policy, args.contexts)
        engine = (video.Engine(args.model, cores) if args.inference_backend == 'lite' else
                  native_rknn.Engine(args.model, cores, args.queue_batches, args.inference_backend,args.input_mode,args.output_mode,args.io_mode,args.binding_mode))
        validation = validate(engine, args.reference_model, args.video, args.batch,
                              count=args.validation_frames,
                              decode_backend=args.decode_backend, output=args.output,
                              decode_threads=args.decode_threads, post_backend=args.post_backend,
                              renderer=args.renderer,preprocessor=args.preprocessor)
        vision.atomic_json(args.output/'validation.json', validation)
        # Validation must not populate the timed run's cache.
        args.renderer = cached_render.Renderer() if args.render_backend == 'cached' else None
        if args.warmup:
            # Warm the selected complete path, including drawing and encoding.
            # Its frames/artifacts remain separate from the measured clip.
            warmup_output = args.output/'warmup'
            warmup_output.mkdir()
            warmup = execute(engine, args, args.warmup, warmup_output, stop)
            vision.atomic_json(warmup_output/'summary.json', warmup)
        if stop.is_set():
            raise RuntimeError('Stopped before measurement.')
        result = execute(engine, args, args.duration, args.output, stop)
        if args.input_cache:
            result['cache_integrity']=args.input_cache.verify()
        result.update(status='stopped' if stop.is_set() else 'complete', mode=args.mode,
                      batch=args.batch, contexts=args.contexts, core_policy=args.core_policy,
                      reuse_inputs=not args.allocate_inputs,
                      encoder_preset=args.encoder_preset, encoder_threads=args.encoder_threads,
                      decode_backend=args.decode_backend, encode_backend=args.encode_backend,
                      decode_threads=args.decode_threads,
                      post_backend=args.post_backend, render_backend=args.render_backend,
                      inference_backend=args.inference_backend, profile_device=args.profile_device,
                      input_mode=args.input_mode,
                      output_mode=args.output_mode,
                      io_mode=args.io_mode,feed_path=args.feed_path,pre_workers=args.pre_workers,
                      binding_mode=args.binding_mode,max_inflight=args.max_inflight,
                      preprocess_backend=args.preprocess_backend,
                      preprocess_evidence=({**args.preprocessor.evidence(),
                          'workers':[p.evidence() for p in args.preprocessors]} if args.preprocessor else None),
                      native_runtime=getattr(engine, 'info', None),
                      native_build=json.loads(native_post.LIBRARY.with_suffix('.json').read_text()) if args.post_backend == 'cpp' else None,
                      render_cache=result.get('render_cache') or ({'hits': args.renderer.hits, 'misses': args.renderer.misses,
                                    'entries': len(args.renderer.labels)} if args.renderer else None),
                      render_storage=args.render_storage,
                      encoder_bitrate=args.encoder_bitrate,
                      model_sha256=hashlib.sha256(args.model.read_bytes()).hexdigest(),
                      video_sha256=hashlib.sha256(args.video.read_bytes()).hexdigest(),
                      runtime=vision.mapped_runtime(), validation=validation,
                      source_sha256={path.name: hashlib.sha256(path.read_bytes()).hexdigest()
                                     for path in [Path(__file__), Path(detector.__file__), Path(video.__file__), Path(media.__file__),
                                                  Path(native_post.__file__), Path(cached_render.__file__),
                                                  Path(native_rknn.__file__), Path(native_rknn.__file__).with_suffix('.cpp'),

                                                  Path(cpu_preprocess.__file__),Path(cpu_preprocess.__file__).with_suffix('.cpp'),
                                                  Path(media_support.__file__),
                                                  Path(thread_accounting.__file__),
                                                  Path(native_mpp.__file__),Path(native_mpp.__file__).with_suffix('.cpp'),
                                                  Path(native_post.__file__).with_suffix('.cpp')]},
                      command=__import__('sys').argv)
        vision.atomic_json(args.output/'summary.json', result)
        print(json.dumps({k:v for k,v in result.items() if k not in ['stage_ms','second_fps']}, ensure_ascii=False))
        return 0
    except Exception as error:
        vision.atomic_json(args.output/'error.json', {'error': str(error)})
        raise
    finally:
        if engine and not getattr(engine, 'workers_active', False):
            engine.close()
        if not getattr(engine,'workers_active',False):
            for processor in args.preprocessors:processor.close()
            if args.input_cache:args.input_cache.close()


if __name__ == '__main__':
    raise SystemExit(main())
