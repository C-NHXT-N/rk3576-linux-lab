#!/usr/bin/env python3
# SPDX-License-Identifier: AGPL-3.0-only
# Copyright (c) 2026 C-NHXT-N and contributors
"""Fetch the pinned Rockchip COCO20 subset and letterbox it for INT8 calibration."""
import argparse
import hashlib
import json
from pathlib import Path
import shutil
import urllib.request

SOURCE_COMMIT = '837db8e992815ff8647eadb709f07067f4bc3a71'
SOURCE_BASE = f'https://raw.githubusercontent.com/airockchip/rknn_model_zoo/{SOURCE_COMMIT}/datasets/COCO/'


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, default=Path('calibration'))
    args = parser.parse_args()
    import cv2
    from detector import preprocess
    root = args.output.resolve()
    (root / 'raw').mkdir(parents=True, exist_ok=True)
    (root / 'letterbox').mkdir(exist_ok=True)
    with urllib.request.urlopen(SOURCE_BASE + 'coco_subset_20.txt', timeout=30) as response:
        entries = response.read().decode().splitlines()
    images, manifest = [], []
    for entry in entries:
        relative = entry.strip().removeprefix('./')
        if not relative:
            continue
        if not relative.startswith('subset/') or '..' in Path(relative).parts:
            raise ValueError('Unexpected calibration source path.')
        raw = root / 'raw' / Path(relative).name
        if not raw.exists():
            with urllib.request.urlopen(SOURCE_BASE + relative, timeout=60) as response, raw.open('wb') as destination:
                shutil.copyfileobj(response, destination)
        image = cv2.imread(str(raw))
        if image is None:
            raise ValueError(f'Calibration source is not a readable image: {raw}')
        batch, _ = preprocess(image)
        target = root / 'letterbox' / (raw.stem + '.png')
        # Image codecs store normal BGR images; Toolkit reads RGB from disk.
        if not cv2.imwrite(str(target), cv2.cvtColor(batch[0], cv2.COLOR_RGB2BGR)):
            raise OSError(f'Could not write calibration image: {target}')
        images.append(str(target))
        manifest.append({'source': SOURCE_BASE + relative, 'sha256': hashlib.sha256(raw.read_bytes()).hexdigest(),
                         'prepared_sha256': hashlib.sha256(target.read_bytes()).hexdigest()})
        print(f'Prepared {len(images)}: {raw.name}', flush=True)
    if len(images) != 20:
        raise ValueError('The pinned lesson expects exactly 20 calibration images.')
    (root / 'dataset.txt').write_text('\n'.join(images) + '\n', encoding='utf-8')
    (root / 'manifest.json').write_text(json.dumps({'commit': SOURCE_COMMIT, 'images': manifest}, indent=2), encoding='utf-8')
    print(f'Calibration list: {root / "dataset.txt"}')


if __name__ == '__main__':
    raise SystemExit(main())
