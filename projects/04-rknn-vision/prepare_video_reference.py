# SPDX-License-Identifier: AGPL-3.0-only
"""Create references for local clips using OpenCV decode and the RKNN Lite path."""
from contextlib import closing

from bench_support import digest
import detector
from fast_bench import infer
from verify_delivery import MODEL, ROOT, SCENES, SOURCE, check_source
from video_bench import Engine, VideoReader
from vision import atomic_json


def main():
    inputs = ROOT/'run/video-input'
    output = ROOT/'run/reference'
    pending = [(inputs/clip, output/reference) for clip,reference in SCENES.values()
               if not (output/reference).exists()]
    if not pending:
        print('Both references already exist. Keep them with the original clips and model.')
        return
    for source, _ in pending:
        check_source(source)
    output.mkdir(parents=True, exist_ok=True)
    model_sha = digest(MODEL)
    with closing(Engine(MODEL, ['0'])) as engine:
        for source, target in pending:
            frames = []
            with closing(VideoReader(source, loop=False)) as reader:
                for index in range(SOURCE['count']):
                    item = reader.read()
                    if item is None or item['source_frame'] != index:
                        raise RuntimeError(f'Source frame sequence ended early: {source}')
                    batch, transforms = detector.preprocess_batch([item['image']])
                    outputs, _ = infer(engine.runtimes[0], batch)
                    frames.extend(detector.postprocess_batch(outputs, transforms, 1))
            atomic_json(target, dict(frames=frames, verification_clip_sha256=digest(source),
                                     verification_model_sha256=model_sha, backend='opencv+rknn-lite'))
            print(target)


if __name__ == '__main__':
    main()
