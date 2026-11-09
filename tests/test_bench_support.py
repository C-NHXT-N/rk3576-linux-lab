# SPDX-License-Identifier: AGPL-3.0-only
from pathlib import Path
import subprocess
import sys
import tempfile
import time
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]/'04-rknn-vision'))
import bench_support


class RankingTests(unittest.TestCase):
    def row(self, name, fps, status='complete'):
        return {'config_id': name, 'config': {'batch': 1, 'contexts': 2},
                'fps': fps, 'status': status, 'once': False}

    def test_median_and_screening_do_not_rank_a_single_lucky_run(self):
        rows = [self.row('a', fps) for fps in (30, 31, 80)] + [self.row('b', 90)]
        self.assertEqual(bench_support.rank(rows)[0]['config_id'], 'a')
        self.assertEqual(bench_support.rank(rows)[0]['median_fps'], 31)
        self.assertEqual(bench_support.rank(rows, minimum=1)[0]['config_id'], 'b')

    def test_failed_configuration_and_once_run_are_excluded(self):
        rows = [self.row('a', fps) for fps in (30, 31, 32)]
        rows += [self.row('a', None, 'failed')]
        self.assertEqual(bench_support.rank(rows), [])
        rows = [dict(self.row('clip', 100), once=True)]*3
        self.assertEqual(bench_support.rank(rows), [])


@unittest.skipUnless(sys.platform == 'linux', 'Linux process groups')
class ShutdownTests(unittest.TestCase):
    def test_shutdown_reaps_a_child_after_the_group_leader_exits(self):
        with tempfile.TemporaryDirectory() as temporary:
            pid_file = Path(temporary)/'child.pid'
            code = ('import subprocess,sys; from pathlib import Path; '
                    'p=subprocess.Popen([sys.executable,"-c","import time; time.sleep(30)"]); '
                    'Path(sys.argv[1]).write_text(str(p.pid))')
            parent = subprocess.Popen([sys.executable, '-c', code, str(pid_file)], start_new_session=True)
            try:
                parent.wait(timeout=5)
                child = int(pid_file.read_text())
                bench_support.stop_process_group(parent)
                limit = time.monotonic()+3
                while time.monotonic() < limit:
                    stat = Path(f'/proc/{child}/stat')
                    if not stat.exists() or stat.read_text().split(') ', 1)[1].startswith('Z '):
                        break
                    time.sleep(.02)
                else:
                    self.fail('Encoder-like descendant survived group shutdown')
            finally:
                bench_support.stop_process_group(parent)


if __name__ == '__main__':
    unittest.main()
