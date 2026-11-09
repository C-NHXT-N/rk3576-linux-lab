#!/usr/bin/env python3
# SPDX-License-Identifier: AGPL-3.0-only
"""Verify the retained RK3576 video pipeline."""
import argparse
import signal
from pathlib import Path

import verify_delivery


def stop(*_):
    raise KeyboardInterrupt("Verification terminated")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest='command', required=True)
    verify = sub.add_parser('verify', help='Verify the retained day and night clips')
    verify.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    signal.signal(signal.SIGTERM, stop)
    verify_delivery.run(args.output)
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
