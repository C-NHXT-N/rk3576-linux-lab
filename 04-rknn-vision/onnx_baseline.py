#!/usr/bin/env python3
# SPDX-License-Identifier: AGPL-3.0-only
# Copyright (c) 2026 C-NHXT-N and contributors
"""Host-only CPU reference for the same YOLO26 two-output contract; not NPU evidence."""
import argparse
import json
from pathlib import Path
import tempfile
import time


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--onnx', type=Path, required=True)
    parser.add_argument('--image', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    import cv2
    import numpy as np
    import onnx
    import onnxruntime as ort
    from detector import OUTPUT_NODES, preprocess, postprocess
    image = cv2.imread(str(args.image))
    batch, transform = preprocess(image)
    # Keep scratch extraction in the explicitly selected output directory.
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(dir=args.output.parent) as directory:
        truncated = str(Path(directory) / 'reference.onnx')
        graph = onnx.load(str(args.onnx))
        onnx.utils.extract_model(str(args.onnx), truncated, [graph.graph.input[0].name], OUTPUT_NODES)
        session = ort.InferenceSession(truncated, providers=['CPUExecutionProvider'])
        tensor = batch.transpose(0, 3, 1, 2).astype(np.float32) / 255
        started = time.perf_counter()
        values = session.run(OUTPUT_NODES, {session.get_inputs()[0].name: tensor})
        result = {'backend': 'onnx-cpu-reference', 'inference_ms': (time.perf_counter() - started) * 1000,
                  'image_size': [image.shape[1], image.shape[0]], 'detections': postprocess(values, transform)}
    args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    print(f'CPU reference saved: {args.output}; detections={len(result["detections"])}')


if __name__ == '__main__':
    main()
