# SPDX-License-Identifier: AGPL-3.0-only
import os
from pathlib import Path
import sys
import tempfile
import threading
import unittest
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1]/'projects/04-rknn-vision'))
try:
    import numpy as np
    import media_backends as media
except ImportError:
    media = None


@unittest.skipIf(media is None or os.name != 'posix', 'Linux pipe tests require NumPy')
class MediaTests(unittest.TestCase):
    def script(self, root, body):
        path = root/'fake-gst'
        path.write_text('#!'+sys.executable+'\nimport os,sys,time,json\n'+body)
        path.chmod(0o755)
        return str(path)

    def test_fragmented_frame_clean_eof_truncation_and_timeout(self):
        read, write = media.raw_socket()
        def producer():
            write.sendall(b'ab')
            write.sendall(b'cdef')
            write.close()
        thread = threading.Thread(target=producer)
        thread.start()
        try:
            self.assertEqual(media.read_socket_exact(read, 6), b'abcdef')
            self.assertIsNone(media.read_socket_exact(read, 6))
        finally:
            read.close()
            thread.join()
        read, write = media.raw_socket()
        write.sendall(b'abc')
        write.close()
        try:
            with self.assertRaisesRegex(RuntimeError, 'Truncated'):
                media.read_socket_exact(read, 6)
        finally:
            read.close()
        read, write = media.raw_socket(timeout=.02)
        try:
            with self.assertRaises(TimeoutError):
                media.read_socket_exact(read, 6)
        finally:
            read.close()
            write.close()

    def test_decoder_separates_library_stdout_and_restarts_at_eof(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            executable = self.script(root,
                "fd=int(next(a.split('=')[1] for a in sys.argv[sys.argv.index('fdsink')+1:] if a.startswith('fd=')))\n"
                "os.write(1,b'Library diagnostic on stdout\\n')\n"
                "for i in range(3):\n p=bytes([16+16*i])*32+bytes([128])*16\n os.write(fd,p[:7]); time.sleep(.002); os.write(fd,p[7:])\n")
            info = {'fps': 25., 'frames': 3, 'width': 8, 'height': 4, 'color_space': 'bt709'}
            with mock.patch.object(media, 'probe', return_value=info), mock.patch.object(media, 'require_plugins', return_value=executable):
                reader = media.MppVideoReader(root/'source.mp4', loop=True, log_path=root/'decode.log')
                try:
                    rows = [reader.read() for _ in range(4)]
                    self.assertEqual([(r['source_frame'], r['cycle']) for r in rows], [(0,0),(1,0),(2,0),(0,1)])
                    values = [int(r['image'][0,0,0]) for r in rows]
                    self.assertLess(values[0], values[1])
                    self.assertLess(values[1], values[2])
                    self.assertEqual(values[0], values[3])
                    self.assertTrue(all(r['image'].shape == (4,8,3) for r in rows))
                finally:
                    reader.close()
                self.assertIsNotNone(reader.process.poll())
                self.assertIn('Library diagnostic', (root/'decode.log').read_text())

    def test_encoder_drains_stdin_and_preserves_bytes(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            executable = self.script(root,
                "out=json.loads(next(a.split('=',1)[1] for a in sys.argv if a.startswith('location=')))\n"
                "data=sys.stdin.buffer.read()\nopen(out,'wb').write(data)\n")
            image = np.arange(96, dtype=np.uint8).reshape(4,8,3)
            with mock.patch.object(media, 'require_plugins', return_value=executable):
                encoder = media.MppEncoder(root/'video.mp4', image, 30)
                encoder.write(image)
                encoder.write(image)
                encoder.close()
                encoder.close()
                self.assertEqual((root/'video.mp4').read_bytes(), image.tobytes()*2)
                self.assertEqual(encoder.evidence['frames_written'], 2)
                self.assertEqual(encoder.process.poll(), 0)

    def test_decoder_failure_propagates_eof_and_reaps_color_worker(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            executable = self.script(root,
                "fd=int(next(a.split('=')[1] for a in sys.argv[sys.argv.index('fdsink')+1:] if a.startswith('fd=')))\n"
                "os.write(fd,b'bad');sys.exit(7)\n")
            info = {'fps': 25., 'frames': 3, 'width': 8, 'height': 4}
            with mock.patch.object(media, 'probe', return_value=info), mock.patch.object(media, 'require_plugins', return_value=executable):
                reader = media.MppVideoReader(root/'source.mp4', loop=False, log_path=root/'decode.log')
                try:
                    with self.assertRaisesRegex(RuntimeError, 'Early MPP decoder EOF'):
                        reader.read()
                finally:
                    reader.close()
                self.assertEqual(reader.process.poll(), 7)
                self.assertIsNotNone(reader.color_process.poll())
                self.assertIn('Truncated raw frame', (root/'decode.log').read_text())

    def test_hardware_proof_requires_plugin_and_codec_device(self):
        import bench_support
        self.assertFalse(bench_support.hardware_proven({'runtime': [{'library_maps': ['libgstrockchipmpp.so']}]}))
        self.assertFalse(bench_support.hardware_proven({'runtime': [{'device_fds': ['/dev/rga']}]}))
        self.assertTrue(bench_support.hardware_proven({'runtime': [{'library_maps': ['libgstrockchipmpp.so'],
                                                               'device_fds': ['/dev/mpp_service']}]}))

    def test_encoder_error_and_missing_plugin_are_not_fallbacks(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            executable = self.script(root, 'sys.stdin.buffer.read()\nsys.exit(9)\n')
            image = np.zeros((4,8,3), np.uint8)
            with mock.patch.object(media, 'require_plugins', return_value=executable):
                encoder = media.MppEncoder(root/'video.mp4', image, 30)
                encoder.write(image)
                with self.assertRaisesRegex(RuntimeError, 'exited 9'):
                    encoder.close()
                self.assertTrue(encoder.log.closed)
                self.assertEqual(encoder.process.poll(), 9)
            with mock.patch.object(media, 'require_plugins', side_effect=RuntimeError('plugin missing')), \
                 mock.patch.object(media.subprocess, 'Popen') as popen:
                with self.assertRaisesRegex(RuntimeError, 'plugin missing'):
                    media.MppEncoder(root/'other.mp4', image, 30)
                popen.assert_not_called()


if __name__ == '__main__':
    unittest.main()
