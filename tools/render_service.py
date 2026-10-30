#!/usr/bin/env python3
# SPDX-License-Identifier: AGPL-3.0-only
# Copyright (c) 2026 C-NHXT-N and contributors
"""Render a unit to stdout; never install or start a service."""
import argparse
import getpass
from pathlib import Path
import re
import sys

ROOT = Path(__file__).resolve().parents[1]

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--project', choices=['monitor', 'vision'], default='monitor')
    parser.add_argument('--user', default=getpass.getuser())
    args = parser.parse_args()
    if not re.fullmatch(r'[a-z_][a-z0-9_-]*[$]?', args.user):
        parser.error('Use a normal Linux account name.')
    folder, name = ('02-systemd-monitor', 'rk3576-monitor') if args.project == 'monitor' else ('04-rknn-vision', 'rk3576-vision')
    project = ROOT / folder
    if not re.fullmatch(r'/[A-Za-z0-9_./-]+', str(project)):
        parser.error('For this lab, use an absolute repository path without spaces, %, or shell metacharacters.')
    text = (project / (name + '.service')).read_text(encoding='utf-8')
    sys.stdout.write(text.replace('@USER@', args.user).replace('@PROJECT_DIR@', str(project)))
    return 0

if __name__ == '__main__':
    raise SystemExit(main())
