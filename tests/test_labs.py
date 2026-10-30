# SPDX-License-Identifier: AGPL-3.0-only
# Copyright (c) 2026 C-NHXT-N and contributors
import importlib.util
import contextlib
import io
import json
import os
from pathlib import Path
import signal
import subprocess
import sys
import tempfile
import time
import unittest
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
MONITOR = ROOT / '02-systemd-monitor/rk3576-monitor.sh'


def temporary_directory():
    parent = (ROOT / 'build/test-tmp').resolve()
    if not parent.is_relative_to(ROOT):
        raise RuntimeError('Temporary test data must stay inside the workspace.')
    parent.mkdir(parents=True, exist_ok=True)
    return tempfile.TemporaryDirectory(dir=parent)


def execute(*args, env=None):
    return subprocess.run(args, text=True, capture_output=True, timeout=15, env=env)


@unittest.skipUnless(sys.platform.startswith('linux'), 'Board/Bash integration tests require Linux')
class MonitorTests(unittest.TestCase):
    def test_finite_sampling_and_arguments(self):
        result = execute('bash', str(MONITOR), '--samples', '02', '--interval', '1')
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout.count('Temperature:'), 2)
        for arguments in [('--samples',), ('--samples', 'abc'), ('--interval', '0'), ('--interval', '-1'), ('--bad',)]:
            self.assertEqual(execute('bash', str(MONITOR), *arguments).returncode, 2)

    def test_sensor_lookup_missing_invalid_zero_and_negative(self):
        with temporary_directory() as temporary:
            env = dict(os.environ, RK3576_THERMAL_ROOT=temporary)
            result = execute('bash', str(MONITOR), '--once', env=env)
            self.assertIn('NPU=N/A (not found)', result.stdout)
            zone = Path(temporary) / 'thermal_zone73'
            zone.mkdir()
            (zone / 'type').write_text('npu-thermal\n')
            for raw, expected in [('42000', '42.0 C'), ('0', '0.0 C'), ('-1500', '-1.5 C'), ('broken', 'N/A (invalid reading)')]:
                (zone / 'temp').write_text(raw + '\n')
                result = execute('bash', str(MONITOR), '--once', env=env)
                self.assertEqual(result.returncode, 0, result.stderr)
                self.assertIn('NPU=' + expected, result.stdout)
            (zone / 'temp').unlink()
            self.assertIn('NPU=N/A (unreadable)', execute('bash', str(MONITOR), '--once', env=env).stdout)

    def test_term_is_prompt_and_cleans_sleep(self):
        process = subprocess.Popen(['bash', str(MONITOR), '--interval', '30'], stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        child = None
        try:
            deadline = time.monotonic() + 5
            while time.monotonic() < deadline:
                info = execute('ps', '--ppid', str(process.pid), '-o', 'pid=,comm=')
                for line in info.stdout.splitlines():
                    if line.strip().endswith('sleep'):
                        child = int(line.split()[0])
                if child is not None:
                    break
                time.sleep(0.05)
            self.assertIsNotNone(child, 'monitor did not start its sampling wait')
            process.send_signal(signal.SIGTERM)
            output, error = process.communicate(timeout=5)
            self.assertEqual(process.returncode, 0, error)
            self.assertIn('Monitor stopping...', output)
            self.assertFalse(Path('/proc', str(child)).exists(), 'sampling child leaked after stop')
        finally:
            if process.poll() is None:
                process.kill()
                process.communicate()

    def test_report_sections_and_errors(self):
        report = str(ROOT / '01-system-inspector/system_report.sh')
        result = execute('bash', report, '--section', 'identity')
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn('Architecture:', result.stdout)
        self.assertNotIn('========== NETWORK', result.stdout)
        self.assertEqual(execute('bash', report, '--section', 'unknown').returncode, 2)
        self.assertEqual(execute('bash', report, '--section').returncode, 2)


class VisionConfigurationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        spec = importlib.util.spec_from_file_location('vision', ROOT / '04-rknn-vision/vision.py')
        cls.module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(cls.module)

    def test_paths_are_relative_to_config_not_working_directory(self):
        with temporary_directory() as temporary:
            folder = Path(temporary)
            (folder / 'model.rknn').write_bytes(b'configuration fixture only')
            (folder / 'input.jpg').write_bytes(b'configuration fixture only')
            path = folder / 'config.json'
            path.write_text(json.dumps({'model': 'model.rknn', 'image': 'input.jpg'}))
            config = self.module.load_config(path)
            self.assertEqual(config['model'], folder / 'model.rknn')
            self.assertEqual(config['image'], folder / 'input.jpg')
            self.assertEqual(config['health'], folder / 'run/health.json')

    def test_reject_invalid_sources_intervals_and_missing_models(self):
        with temporary_directory() as temporary:
            folder = Path(temporary)
            path = folder / 'config.json'
            (folder / 'a').write_bytes(b'configuration fixture only')
            for values in [[], {}, {'model': 'missing.rknn', 'image': 'missing.jpg'},
                           {'model': 'a', 'image': 'a', 'camera': '/dev/video0'},
                           {'model': 'a', 'camera': '/dev/video0', 'frames': -1},
                           {'model': 'a', 'camera': '/dev/video0', 'interval': 0},
                           {'model': 'a', 'camera': '/dev/video0', 'interval': True},
                           {'model': 'a', 'camera': '/dev/video0', 'interval': float('nan')},
                           {'model': 'a', 'camera': '/dev/video0', 'unknown': 1}]:
                path.write_text(json.dumps(values))
                with self.assertRaises(ValueError, msg=values):
                    self.module.load_config(path)

    def test_missing_runtime_invalidates_previous_healthy_state(self):
        with temporary_directory() as temporary:
            folder = Path(temporary)
            (folder / 'model.rknn').write_bytes(b'configuration fixture only')
            (folder / 'input.jpg').write_bytes(b'configuration fixture only')
            config = folder / 'config.json'
            config.write_text(json.dumps({'model': 'model.rknn', 'image': 'input.jpg'}))
            health = folder / 'run/health.json'
            self.module.write_health(health, 'running', 20)
            errors = io.StringIO()
            with mock.patch.object(sys, 'argv', ['vision.py', '--config', str(config)]), \
                    mock.patch.object(self.module, 'dependencies', side_effect=RuntimeError('Missing dependency fixture')), \
                    contextlib.redirect_stderr(errors):
                self.assertEqual(self.module.main(), 1)
            self.assertIn('Missing dependency', errors.getvalue())
            self.assertEqual(json.loads(health.read_text())['status'], 'error')

    def test_health_failure_does_not_look_running(self):
        with temporary_directory() as temporary:
            path = Path(temporary) / 'health.json'
            self.module.write_health(path, 'running', 3)
            self.module.write_health(path, 'error', 3)
            data = json.loads(path.read_text())
            self.assertEqual(data['status'], 'error')
            self.assertEqual(data['frames'], 3)
            self.assertFalse(path.with_suffix('.tmp').exists())


if __name__ == '__main__':
    unittest.main()
