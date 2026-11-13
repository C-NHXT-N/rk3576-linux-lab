#!/usr/bin/env python3
# SPDX-License-Identifier: AGPL-3.0-only
# Copyright (c) 2026 C-NHXT-N and contributors
"""One-Hz background file sampler. Only a fixed debugfs cat may use sudo."""
import argparse
import csv
import json
from pathlib import Path
import re
import signal
import subprocess
import time

import psutil


def sensors():
    values = {}
    for zone in Path('/sys/class/thermal').glob('thermal_zone*'):
        try:
            values[zone.joinpath('type').read_text().strip()] = float(zone.joinpath('temp').read_text())/1000
        except (OSError, ValueError):
            pass
    return values


def npu_load():
    path = '/sys/kernel/debug/rknpu/load'
    try:
        try:
            raw = Path(path).read_text()
        except PermissionError:
            raw = subprocess.check_output(['sudo', '-n', 'cat', path], text=True, stderr=subprocess.DEVNULL, timeout=2)
        return raw.strip(), {int(i):int(value) for i, value in re.findall(r'Core(\d+):\s*(\d+)%', raw)}
    except (OSError, subprocess.SubprocessError):
        return '', {}


def read_frequencies():
    values = {}
    for device in Path('/sys/class/devfreq').glob('*'):
        if 'npu' in device.name or device.name == 'dmc':
            try:
                values[device.name] = int((device/'cur_freq').read_text())
            except (OSError, ValueError):
                pass
    for cpu in Path('/sys/devices/system/cpu').glob('cpu[0-9]*'):
        try:
            values[cpu.name] = int((cpu/'cpufreq/scaling_cur_freq').read_text())*1000
        except (OSError, ValueError):
            pass
    return values


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--pid', type=int)
    parser.add_argument('--duration', type=float, default=0)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    stop = False
    def end(*_):
        nonlocal stop
        stop = True
    signal.signal(signal.SIGTERM, end)
    signal.signal(signal.SIGINT, end)
    root = psutil.Process(args.pid) if args.pid else None
    known = {}
    psutil.cpu_percent(percpu=True)
    started = time.monotonic()
    deadline = started
    args.output.parent.mkdir(parents=True, exist_ok=True)
    fields = ['timestamp', 'monotonic', 'elapsed_s', 'cpu_percent', 'npu_percent', 'npu_raw',
              'mem_total_bytes', 'mem_available_bytes', 'mem_used_percent', 'process_rss_bytes',
              'process_cpu_percent', 'temperatures_c', 'frequencies_hz']
    with args.output.open('w', newline='') as file:
        writer = csv.DictWriter(file, fieldnames=fields)
        writer.writeheader()
        while not stop and (not args.duration or time.monotonic()-started < args.duration):
            if root and (not root.is_running() or root.status() == psutil.STATUS_ZOMBIE):
                break
            processes = []
            if root:
                try:
                    processes = [root]+root.children(recursive=True)
                except psutil.Error:
                    pass
            rss = cpu = 0
            for proc in processes:
                try:
                    identity = (proc.pid, proc.create_time())
                    if identity not in known:
                        known[identity] = proc
                        proc.cpu_percent()
                    rss += known[identity].memory_info().rss
                    cpu += known[identity].cpu_percent()
                except psutil.Error:
                    pass
            mem = psutil.virtual_memory()
            raw, load = npu_load()
            writer.writerow({'timestamp':time.time(), 'monotonic':time.monotonic(),
                'elapsed_s':time.monotonic()-started,
                'cpu_percent':json.dumps(psutil.cpu_percent(percpu=True)),
                'npu_percent':json.dumps(load), 'npu_raw':raw,
                'mem_total_bytes':mem.total, 'mem_available_bytes':mem.available,
                'mem_used_percent':100*(1-mem.available/mem.total),
                'process_rss_bytes':rss, 'process_cpu_percent':cpu,
                'temperatures_c':json.dumps(sensors()), 'frequencies_hz':json.dumps(read_frequencies())})
            file.flush()
            deadline += 1
            time.sleep(max(0, deadline-time.monotonic()))


if __name__ == '__main__':
    main()
