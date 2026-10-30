#!/usr/bin/env python3
# SPDX-License-Identifier: AGPL-3.0-only
# Copyright (c) 2026 C-NHXT-N and contributors
"""Export the pinned official YOLO26n weights on the x86_64 conversion host."""
import argparse
import hashlib
import os
from pathlib import Path
import shutil
import sys
import urllib.request

WEIGHTS_URL = 'https://github.com/ultralytics/assets/releases/download/v8.4.0/yolo26n.pt'
WEIGHTS_SHA256 = '9b09cc8bf347f0fc8a5f7657480587f25db09b34bf33b0652110fb03a8ad4fef'


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--weights', type=Path, default=Path('models/yolo26n.pt'))
    parser.add_argument('--output', type=Path, default=Path('models/yolo26n.onnx'))
    args = parser.parse_args()
    args.weights.parent.mkdir(parents=True, exist_ok=True)
    if not args.weights.exists():
        with urllib.request.urlopen(WEIGHTS_URL, timeout=60) as response, args.weights.open('wb') as destination:
            shutil.copyfileobj(response, destination)
    digest = hashlib.sha256(args.weights.read_bytes()).hexdigest()
    if digest != WEIGHTS_SHA256:
        parser.error(f'Weight SHA256 mismatch: {digest}. This lesson uses the recorded official YOLO26n weights only.')
    os.environ['YOLO_AUTOINSTALL'] = 'false'
    try:
        import ultralytics
        from ultralytics import YOLO
        if ultralytics.__version__ != '8.4.192':
            parser.error('Use ultralytics==8.4.192; output node names are version-specific.')
        output = Path(YOLO(str(args.weights.resolve())).export(
            format='onnx', imgsz=640, batch=1, opset=17, dynamic=False,
            simplify=False, device='cpu', nms=False))
        args.output.parent.mkdir(parents=True, exist_ok=True)
        if output.resolve() != args.output.resolve():
            shutil.copyfile(output, args.output)
        print(f'ONNX: {args.output}; SHA256={hashlib.sha256(args.output.read_bytes()).hexdigest()}')
        return 0
    except (ImportError, OSError, RuntimeError, ValueError) as error:
        print(f'ERROR: {error}', file=sys.stderr)
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
