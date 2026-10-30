#!/usr/bin/env python3
# SPDX-License-Identifier: AGPL-3.0-only
# Copyright (c) 2026 C-NHXT-N and contributors
# Adapted from Rockchip RKNN Model Zoo (Apache-2.0); see THIRD_PARTY_NOTICES.md.
"""Convert YOLO26n to the Rockchip two-output contract, for RK3576 only."""
import argparse
import json
from pathlib import Path
import sys

OUTPUTS = ['/model.23/Sigmoid_output_0', '/model.23/Mul_2_output_0']


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--onnx', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--dataset', type=Path, help='One absolute calibration image path per line; enables INT8.')
    args = parser.parse_args()
    if not args.onnx.is_file():
        parser.error(f'ONNX file not found: {args.onnx}')
    try:
        import onnx
        from rknn.api import RKNN
    except ImportError:
        print('Use the host RKNN Toolkit2 2.5.0 conversion virtual environment.', file=sys.stderr)
        return 1
    graph = onnx.load(str(args.onnx))
    nodes = {name for node in graph.graph.node for name in node.output}
    if not set(OUTPUTS).issubset(nodes):
        parser.error('YOLO26 one-to-one output nodes are missing. Use the recorded exporter/version; do not silently substitute another detection head.')
    shape = [d.dim_value for d in graph.graph.input[0].type.tensor_type.shape.dim]
    if shape != [1, 3, 640, 640]:
        parser.error(f'Expected fixed input [1, 3, 640, 640], found {shape}. Export batch=1, imgsz=640, dynamic=False.')
    if args.dataset is not None:
        if not args.dataset.is_file():
            parser.error(f'Calibration list missing: {args.dataset}')
        images = [line.strip() for line in args.dataset.read_text().splitlines() if line.strip()]
        if not images or any(not Path(p).is_absolute() or not Path(p).is_file() for p in images):
            parser.error('Calibration list must contain existing absolute image paths.')
    rknn = RKNN()
    try:
        # Toolkit 2.5.0's SDPA fusion raises IndexError on this pinned YOLO26n
        # graph; the SDK diagnostic recommends disabling this single rule.
        if rknn.config(target_platform='rk3576', mean_values=[[0, 0, 0]], std_values=[[255, 255, 255]],
                       disable_rules=['fuse_exmatmul_add_mul_exsoftmax13_exmatmul_to_sdpa']) != 0:
            raise RuntimeError('RKNN preprocessing configuration failed.')
        if rknn.load_onnx(model=str(args.onnx.resolve()), outputs=OUTPUTS) != 0:
            raise RuntimeError('ONNX load failed.')
        kwargs = {'do_quantization': args.dataset is not None}
        if args.dataset is not None:
            kwargs['dataset'] = str(args.dataset.resolve())
        if rknn.build(**kwargs) != 0:
            raise RuntimeError('RKNN build failed.')
        args.output.parent.mkdir(parents=True, exist_ok=True)
        if rknn.export_rknn(str(args.output.resolve())) != 0:
            raise RuntimeError('RKNN export failed.')
        print(json.dumps({'output': str(args.output), 'target': 'rk3576', 'precision': 'int8' if args.dataset else 'fp16', 'outputs': OUTPUTS}))
        return 0
    except (RuntimeError, ValueError, OSError) as error:
        print(f'ERROR: {error}', file=sys.stderr)
        return 1
    finally:
        rknn.release()


if __name__ == '__main__':
    raise SystemExit(main())
