#!/usr/bin/env python3
# SPDX-License-Identifier: AGPL-3.0-only
# Copyright (c) 2026 C-NHXT-N and contributors
"""Fetch pinned official SDK assets, validating recorded SHA256; no installation."""
import argparse
import hashlib
from pathlib import Path
import shutil
import urllib.request

BASE = 'https://raw.githubusercontent.com/airockchip/rknn-toolkit2/v2.5.0/'
ASSETS = {
    'host': [('rknn-toolkit2/packages/x86_64/rknn_toolkit2-2.5.0-cp310-cp310-manylinux_2_17_x86_64.manylinux2014_x86_64.whl', '7dead4048d60f9cf29dc6017cf0f1dbb30f5f1d4f227c5e2e6739d9fe3e5eec6')],
    'board': [('rknn-toolkit-lite2/packages/rknn_toolkit_lite2-2.5.0-cp310-cp310-manylinux_2_17_aarch64.manylinux2014_aarch64.whl', '57a5a1f967ff88a1f933abc15a64cf11db37fb406c00cb610f20a566ec231161'),
              ('rknpu2/runtime/Linux/librknn_api/aarch64/librknnrt.so', '4b6cc575bedf8952b13db4b1190fa3b3d2ac213f00be774ff6ccd19d651970c0')],
}

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--role', choices=ASSETS, required=True)
    parser.add_argument('--output', type=Path, default=Path('runtime'))
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=True)
    for source, expected in ASSETS[args.role]:
        target = args.output / Path(source).name
        if not target.exists():
            temporary = target.with_suffix(target.suffix + '.download')
            with urllib.request.urlopen(BASE + source, timeout=60) as response, temporary.open('wb') as output:
                shutil.copyfileobj(response, output)
            if hashlib.sha256(temporary.read_bytes()).hexdigest() != expected:
                raise ValueError(f'SHA256 mismatch for {temporary}; no installation was performed.')
            temporary.replace(target)
        if hashlib.sha256(target.read_bytes()).hexdigest() != expected:
            raise ValueError(f'Existing asset hash differs: {target}; inspect it before replacing.')
        print(f'{target.name} SHA256={expected}')

if __name__ == '__main__':
    main()
