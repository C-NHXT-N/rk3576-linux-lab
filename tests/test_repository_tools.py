# SPDX-License-Identifier: AGPL-3.0-only
# Copyright (c) 2026 C-NHXT-N and contributors
"""Regression checks for course navigation and relocated service projects."""
from configparser import ConfigParser
from contextlib import redirect_stderr, redirect_stdout
import importlib.util
import io
from pathlib import Path
import sys
import tempfile
import unittest
from unittest import mock


ROOT = Path(__file__).resolve().parents[1]
LESSON = '''# 第一课

## 这课完成什么
## 自己完成一次
## 完成标准
## 清理与回顾
上一课：[课程总目录](../README.md)
下一课：[课程总目录](../README.md)
'''


def load_tool(name):
    spec = importlib.util.spec_from_file_location(name, ROOT / 'tools' / (name + '.py'))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class DocumentationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tool = load_tool('check_docs')

    def setUp(self):
        parent = ROOT / 'build/test-tmp'
        parent.mkdir(parents=True, exist_ok=True)
        temporary = tempfile.TemporaryDirectory(dir=parent)
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name).resolve()
        self.write('README.md', '# 课程总目录\n')
        self.write('00-start/01-connect.md', LESSON)

    def write(self, name, text):
        path = self.root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding='utf-8')

    def check(self):
        output, errors = io.StringIO(), io.StringIO()
        with mock.patch.object(self.tool, 'ROOT', self.root), \
                redirect_stdout(output), redirect_stderr(errors):
            result = self.tool.main()
        return result, errors.getvalue()

    def test_root_lessons_pass_without_treating_projects_or_templates_as_lessons(self):
        self.write('projects/02-systemd-monitor/README.md', '# 监控项目\n')
        self.write('docs/maintenance/lesson-template.md', '# 课件模板\n')
        self.write('build/generated.md', '[ignored](missing.md)\n')
        self.write('projects/04-rknn-vision/.venv-convert/README.md', '[ignored](missing.md)\n')
        result, errors = self.check()
        self.assertFalse(result, errors)
        self.assertEqual(errors, '')

    def test_missing_lesson_section_is_reported_after_moving_chapters(self):
        self.write('00-start/01-connect.md', LESSON.replace('## 完成标准\n', ''))
        result, errors = self.check()
        self.assertTrue(result)
        self.assertIn('00-start/01-connect.md: missing lesson element: ## 完成标准', errors)

    def test_broken_links_and_heading_fragments_are_reported(self):
        self.write('projects/01-system-inspector/README.md', '# 系统巡检\n')
        for target, expected in [
            ('../projects/missing/README.md', 'missing target'),
            ('../projects/01-system-inspector/README.md#missing', 'missing heading'),
        ]:
            with self.subTest(target=target):
                self.write('00-start/01-connect.md', LESSON + f'\n[项目]({target})\n')
                result, errors = self.check()
                self.assertTrue(result)
                self.assertIn(expected, errors)
                self.assertIn(target, errors)


@unittest.skipUnless(sys.platform.startswith('linux'), 'Service rendering requires a Linux repository path')
class ServiceRenderingTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tool = load_tool('render_service')

    def test_service_paths_follow_relocated_projects(self):
        for project, folder, executable in [
            ('monitor', '02-systemd-monitor', 'rk3576-monitor.sh'),
            ('vision', '04-rknn-vision', 'vision.py'),
        ]:
            with self.subTest(project=project):
                output = io.StringIO()
                arguments = ['render_service.py', '--project', project, '--user', 'student']
                with mock.patch.object(sys, 'argv', arguments), redirect_stdout(output):
                    self.assertEqual(self.tool.main(), 0)
                text = output.getvalue()
                self.assertNotIn('@USER@', text)
                self.assertNotIn('@PROJECT_DIR@', text)
                # systemd permits repeated directives such as Environment.
                config = ConfigParser(interpolation=None, strict=False)
                config.read_string(text)
                service = config['Service']
                directory = ROOT / 'projects' / folder
                self.assertEqual(service['User'], 'student')
                self.assertEqual(service['WorkingDirectory'], str(directory))
                if project == 'monitor':
                    self.assertEqual(service['ExecStart'], f'/usr/bin/bash {directory / executable}')
                else:
                    self.assertEqual(service['ExecStart'],
                                     f'{directory}/.venv/bin/python {directory / executable} --config {directory}/config.json')
                    self.assertIn(f'LIBRKNNRT_PATH={directory}/runtime/librknnrt.so', service['Environment'])


if __name__ == '__main__':
    unittest.main()
