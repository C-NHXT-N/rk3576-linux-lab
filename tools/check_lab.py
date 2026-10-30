#!/usr/bin/env python3
# SPDX-License-Identifier: AGPL-3.0-only
# Copyright (c) 2026 C-NHXT-N and contributors
"""Read-only checks of observable lab results; this does not grade understanding."""
import argparse
import json
from pathlib import Path
import re
import shutil
import subprocess
import sys
import time

ROOT = Path(__file__).resolve().parents[1]

def command(*args):
    try:
        return subprocess.run(args, capture_output=True, text=True, timeout=15)
    except (OSError, subprocess.TimeoutExpired) as error:
        return subprocess.CompletedProcess(args, 127, '', str(error))

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('lab', choices=['environment', 'files', 'inspector', 'monitor', 'programming', 'vision'])
    parser.add_argument('--workspace', type=Path, default=Path.home() / 'rk3576-practice' / 'files')
    parser.add_argument('--unit', default='rk3576-monitor-lab.service')
    parser.add_argument('--health', type=Path, default=ROOT / '04-rknn-vision/run/health.json')
    args = parser.parse_args()
    checks = []
    def check(ok, label, hint):
        checks.append(bool(ok))
        print(f'{"PASS" if ok else "FAIL"}: {label}')
        if not ok: print(f'  Next: {hint}')

    if args.lab == 'environment':
        for name in ['bash', 'python3', 'git', 'uname', 'ip', 'ss', 'findmnt', 'free', 'g++', 'strace']:
            check(shutil.which(name), name, f'查看 docs/environment.md，安装或定位 {name}。')
        check(sys.platform.startswith('linux'), 'Linux host', '请在开发板终端执行。')
    elif args.lab == 'files':
        root = args.workspace.expanduser()
        source = root / 'notes' / 'hello.txt'
        copied = root / 'archive' / 'hello-copy.txt'
        link = root / 'hello-link'
        check(source.is_file(), 'source file', f'创建 {source} 并写入 hello linux。')
        check(copied.is_file() and source.is_file() and copied.read_bytes() == source.read_bytes(), 'copy matches', '重新检查 cp 的源和目标；移动、删除实验请使用临时副本。')
        check(link.is_symlink() and link.resolve() == source.resolve() and link.exists(), 'symbolic link', '在练习根目录运行 ln -s notes/hello.txt hello-link。')
        check(source.is_file() and (source.stat().st_mode & 0o777) == 0o640, 'mode 640', '对练习文件执行 chmod 640，随后用 ls -l 检查。')
    elif args.lab == 'inspector':
        result = command('bash', str(ROOT / '01-system-inspector/system_report.sh'))
        check(result.returncode == 0, 'report exits successfully', result.stderr or '先运行报告，查看哪个必需命令失败。')
        for title in ['SYSTEM', 'CPU', 'MEMORY', 'STORAGE', 'NETWORK', 'PROCESS', 'DEVICES']:
            check(f'========== {title} ==========' in result.stdout, f'{title} section', '从项目源码入口对照检查报告结构。')
    elif args.lab == 'monitor':
        check(bool(re.fullmatch(r'rk3576-monitor(?:-lab|-check)?\.service', args.unit)), 'course unit name', '仅检查课程服务：rk3576-monitor-lab.service。')
        if not checks[-1]: return 1
        state = command('systemctl', 'is-active', args.unit)
        check(state.returncode == 0, 'service active', f'systemctl status {args.unit} --no-pager')
        info = command('systemctl', 'show', args.unit, '-p', 'MainPID', '--value')
        pid = info.stdout.strip()
        check(info.returncode == 0 and pid.isdigit() and int(pid) > 0 and Path('/proc', pid).exists(), 'live main process', f'journalctl -u {args.unit} -n 20 --no-pager')
        enabled = command('systemctl', 'is-enabled', args.unit)
        print(f'INFO: boot relationship={enabled.stdout.strip() or "unknown"}; enabled is separate from active.')
    elif args.lab == 'programming':
        for name, expected in [('write_lab', 'Hello via write()'), ('pipe_lab', 'hello through pipe'), ('mmap_lab', 'shared value after child exit: 42')]:
            result = command(str(ROOT / 'build' / name))
            check(result.returncode == 0 and expected in result.stdout, name, '按系统编程课程把源码编译到 build/ 后再检查。')
    elif args.lab == 'vision':
        try:
            data = json.loads(args.health.read_text(encoding='utf-8'))
            age = time.time() - data['timestamp']
            valid = data.get('status') == 'running' and data.get('backend') == 'rknn' and data.get('model_family') == 'yolo26' and data.get('frames', 0) > 0 and 0 <= age < 30
        except (OSError, ValueError, KeyError, TypeError):
            valid = False
        check(valid, 'recent RKNN inference heartbeat', '前台运行真实 RKNN 推理；该检查只验证心跳，不证明识别准确率。')
    print(f'{sum(checks)}/{len(checks)} checks passed. 自评与独立挑战仍需自己完成。')
    return 0 if checks and all(checks) else 1

if __name__ == '__main__':
    raise SystemExit(main())
