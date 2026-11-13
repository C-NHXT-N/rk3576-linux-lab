#!/usr/bin/env python3
# SPDX-License-Identifier: AGPL-3.0-only
"""Explicit GStreamer MPP bridges. Raw frames use a separate, bounded OS pipe."""
from fractions import Fraction
from functools import lru_cache
import ctypes
import json
import os
from pathlib import Path
import shutil
import signal
import socket
import struct
import subprocess
import sys
import tempfile
import time

import numpy as np


def probe(path):
    path = Path(path).resolve()
    if not path.is_file():
        raise ValueError(f'Expected a local video file: {path}')
    command = ['ffprobe', '-v', 'error', '-select_streams', 'v:0', '-show_entries',
               'stream=codec_name,pix_fmt,width,height,avg_frame_rate,r_frame_rate,nb_frames,color_range,color_space',
               '-of', 'json', str(path)]
    data = json.loads(subprocess.check_output(command, text=True, timeout=30))['streams'][0]
    if data['codec_name'] != 'h264':
        raise ValueError('The MPP bridge currently supports local H.264 MP4 input only.')
    rate = Fraction(data['avg_frame_rate'])
    if rate <= 0 or min(data['width'], data['height']) < 1:
        raise ValueError('Invalid source dimensions/framerate.')
    count = data.get('nb_frames')
    if count in (None, 'N/A'):
        count = json.loads(subprocess.check_output(['ffprobe', '-v', 'error', '-select_streams', 'v:0',
            '-count_frames', '-show_entries', 'stream=nb_read_frames', '-of', 'json', str(path)],
            text=True, timeout=120))['streams'][0]['nb_read_frames']
    if int(count) < 1:
        raise ValueError('Source must contain frames.')
    return {**data, 'frames': int(count), 'rate': str(rate), 'fps': float(rate)}


class LegacyColorConverter:
    """Use OpenCV's already-loaded swscale and SWS_BICUBIC conversion settings.

    OpenCV 4.10 VideoCapture uses default swscale coefficients rather than
    applying stream colorimetry. Preserve that input contract instead of silently
    changing model pixels with GStreamer's metadata-aware BGR conversion.
    """
    def __init__(self, width, height, pixel_format='yuv420p'):
        import cv2  # Ensure the same video libraries as the reference are loaded.
        paths = sorted({line.split()[-1] for line in Path('/proc/self/maps').read_text().splitlines()
                        if 'libswscale' in line})
        paths.sort(key=lambda p: 'opencv' not in p)
        if not paths or width % 2 or height % 2 or pixel_format not in ('yuv420p', 'yuvj420p'):
            raise RuntimeError('Legacy-compatible conversion requires OpenCV swscale and even 8-bit 4:2:0 input.')
        self.path, self.width, self.height = paths[0], width, height
        self.lib = ctypes.CDLL(self.path)
        self.lib.av_get_pix_fmt.argtypes = [ctypes.c_char_p]
        self.lib.av_get_pix_fmt.restype = ctypes.c_int
        self.lib.sws_getContext.argtypes = [ctypes.c_int]*7+[ctypes.c_void_p]*3
        self.lib.sws_getContext.restype = ctypes.c_void_p
        self.lib.sws_scale.argtypes = [ctypes.c_void_p, ctypes.POINTER(ctypes.c_void_p),
            ctypes.POINTER(ctypes.c_int), ctypes.c_int, ctypes.c_int,
            ctypes.POINTER(ctypes.c_void_p), ctypes.POINTER(ctypes.c_int)]
        self.lib.sws_scale.restype = ctypes.c_int
        self.lib.sws_freeContext.argtypes = [ctypes.c_void_p]
        self.context = self.lib.sws_getContext(width, height, self.lib.av_get_pix_fmt(pixel_format.encode()),
            width, height, self.lib.av_get_pix_fmt(b'bgr24'), 4, None, None, None)
        if not self.context:
            raise RuntimeError('Could not initialize the OpenCV-compatible color converter.')
        self.y_stride = (width+3)//4*4
        self.uv_stride = (width//2+3)//4*4
        self.y_bytes = self.y_stride*height
        self.uv_bytes = self.uv_stride*(height//2)
        self.frame_bytes = self.y_bytes+2*self.uv_bytes

    def convert(self, payload):
        if len(payload) != self.frame_bytes:
            raise ValueError('Packed I420 size mismatch.')
        # Padding protects swscale's SIMD reads, matching AVFrame allocation rules.
        source = np.zeros(self.frame_bytes+96, np.uint8)
        offset = (-source.ctypes.data) % 32
        source[offset:offset+self.frame_bytes] = np.frombuffer(payload, np.uint8)
        address = source.ctypes.data+offset
        stride = (self.width*3+31)//32*32
        storage = np.empty(self.height*stride+31, np.uint8)
        out_offset = (-storage.ctypes.data) % 32
        target = storage[out_offset:out_offset+self.height*stride].reshape(self.height, stride)
        pointers = (ctypes.c_void_p*4)(address, address+self.y_bytes, address+self.y_bytes+self.uv_bytes, None)
        strides = (ctypes.c_int*4)(self.y_stride, self.uv_stride, self.uv_stride, 0)
        destinations = (ctypes.c_void_p*4)(target.ctypes.data, None, None, None)
        destination_strides = (ctypes.c_int*4)(stride, 0, 0, 0)
        rows = self.lib.sws_scale(self.context, pointers, strides, 0, self.height, destinations, destination_strides)
        if rows != self.height:
            raise RuntimeError('Color conversion returned an incomplete frame.')
        return np.ascontiguousarray(target[:, :self.width*3].reshape(self.height, self.width, 3))

    def close(self):
        if self.context:
            self.lib.sws_freeContext(self.context)
            self.context = None


@lru_cache(maxsize=None)
def require_plugins(*plugins):
    if os.name != 'posix':
        raise RuntimeError('MPP media bridges require the Linux board.')
    executable = shutil.which('gst-launch-1.0')
    inspector = shutil.which('gst-inspect-1.0')
    if not executable or not inspector:
        raise RuntimeError('GStreamer launcher/inspector missing; no software fallback.')
    for plugin in plugins:
        result = subprocess.run([inspector, plugin], stdout=subprocess.DEVNULL,
                                stderr=subprocess.PIPE, timeout=15)
        if result.returncode:
            raise RuntimeError(f'GStreamer plugin unavailable: {plugin}: {result.stderr.decode(errors="replace")}')
    return executable


def gst_property(name, value):
    value = str(value).replace('\\', '\\\\').replace('"', '\\"')
    return f'{name}="{value}"'


def _log(path):
    if path is None:
        return tempfile.TemporaryFile()
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    return path.open('ab', buffering=0)


def runtime_evidence(pid):
    result = {'pid': pid, 'device_fds': [], 'library_maps': []}
    try:
        for fd in Path(f'/proc/{pid}/fd').iterdir():
            try:
                target = os.readlink(fd)
                if target.startswith('/dev/') and target != '/dev/null':
                    result['device_fds'].append(target)
            except OSError:
                pass
        result['library_maps'] = sorted({line.split()[-1] for line in
            Path(f'/proc/{pid}/maps').read_text().splitlines()
            if any(word in line for word in ['libgstrockchipmpp', 'librockchip_mpp', 'librga'])})
    except OSError as error:
        result['unprivileged_unavailable'] = str(error)
        # Some BSP media executables are non-dumpable. Inspect only this child,
        # using noninteractive, read-only sudo; never run the pipeline as root.
        try:
            maps = subprocess.check_output(['sudo', '-n', 'cat', f'/proc/{int(pid)}/maps'],
                                           text=True, stderr=subprocess.DEVNULL, timeout=2)
            fds = subprocess.check_output(['sudo', '-n', 'ls', '-l', f'/proc/{int(pid)}/fd'],
                                          text=True, stderr=subprocess.DEVNULL, timeout=2)
            result['library_maps'] = sorted({line.split()[-1] for line in maps.splitlines()
                if any(word in line for word in ['libgstrockchipmpp', 'librockchip_mpp', 'librga'])})
            result['device_fds'] = [line.split(' -> ', 1)[1] for line in fds.splitlines()
                                    if ' -> /dev/' in line and not line.endswith(' -> /dev/null')]
            result['inspection'] = 'read-only sudo of child maps/fd'
        except (OSError, subprocess.SubprocessError) as unavailable:
            result['unavailable'] = str(unavailable)
    result['device_fds'] = sorted(set(result['device_fds']))
    return result


def raw_socket(timeout=10):
    a, b = socket.socketpair()
    seconds = int(timeout)
    microseconds = int((timeout-seconds)*1000000)
    for endpoint in (a, b):
        endpoint.setsockopt(socket.SOL_SOCKET, socket.SO_RCVTIMEO, struct.pack('ll', seconds, microseconds))
        endpoint.setsockopt(socket.SOL_SOCKET, socket.SO_SNDTIMEO, struct.pack('ll', seconds, microseconds))
    return a, b


def read_socket_exact(stream, size):
    # One blocking C recv avoids repeated Python/GIL handoffs for every pipe chunk.
    try:
        payload = stream.recv(size, socket.MSG_WAITALL)
    except BlockingIOError as error:
        raise TimeoutError('Timed out receiving an MPP frame.') from error
    if not payload:
        return None
    if len(payload) != size:
        raise RuntimeError(f'Truncated raw frame: {len(payload)}/{size} bytes.')
    return payload


def terminate(process):
    if process is None:
        return
    if process.poll() is None:
        process.terminate()
    try:
        process.wait(timeout=5)
    except subprocess.TimeoutExpired:
        process.kill()
        process.wait(timeout=5)


class MppVideoReader:
    def __init__(self, path, loop=True, log_path=None):
        self.info = probe(path)
        self.path, self.loop = str(Path(path).resolve()), loop
        self.fps, self.count = self.info['fps'], self.info['frames']
        self.width, self.height = self.info['width'], self.info['height']
        self.stride = (self.width*3+3)//4*4
        self.index, self.cycle = 0, 0
        self.process, self.fd, self.stream = None, None, None
        self.color_process, self.color_input = None, None
        self.log_path, self.log = log_path, _log(log_path)
        self.closed = False
        self.eof = False
        self.converter = None
        self.evidence = {'backend': 'mpp', 'input': self.info, 'commands': [], 'runtime': [],
                         'frames_read': 0, 'log': str(log_path) if log_path else None,
                         'transport': 'MPP I420 -> isolated legacy BGR converter -> Unix stream; not zero-copy',
                         'color_workers': []}
        try:
            self.converter = LegacyColorConverter(self.width, self.height, self.info.get('pix_fmt', 'yuv420p'))
            self.evidence['color_converter'] = {'library': self.converter.path, 'flags': 'SWS_BICUBIC',
                                              'contract': 'match current OpenCV conversion'}
            self.converter.close()
            self.executable = require_plugins('qtdemux', 'h264parse', 'mppvideodec', 'videoconvert', 'fdsink')
            self._open()
        except BaseException:
            self.close()
            raise

    def _open(self):
        color_read, self.color_input = raw_socket()
        self.stream, color_write = raw_socket()
        stats = str(Path(self.log_path).with_name(Path(self.log_path).stem+f'-color-{self.cycle}.json')) if self.log_path else '-'
        command = [sys.executable, str(Path(__file__).resolve()), '--color-worker',
                   str(self.width), str(self.height), self.info.get('pix_fmt', 'yuv420p'),
                   str(color_read.fileno()), str(color_write.fileno()), stats]
        try:
            self.color_process = subprocess.Popen(command, stdout=self.log, stderr=self.log,
                                                  pass_fds=(color_read.fileno(), color_write.fileno()))
        finally:
            color_read.close()
            color_write.close()
        if read_socket_exact(self.stream, 5) != b'READY':
            raise RuntimeError('Color conversion worker did not initialize.')
        self.evidence['color_workers'].append({'pid': self.color_process.pid, 'argv': command, 'stats': stats})
        write_stream = self.color_input
        write_fd = write_stream.fileno()
        # fd=1/2 remain logs, preventing MPP library printf from corrupting pixel bytes.
        color = 'bt709' if self.info.get('color_space') == 'bt709' else 'bt601'
        command = [self.executable, '-q', 'filesrc', gst_property('location', self.path), '!',
                   'qtdemux', '!', 'h264parse', '!', 'mppvideodec', 'format=I420', 'qos=false',
                   'ignore-error=false', 'discard-corrupted-frames=false', 'arm-afbc=false', '!',
                   f'video/x-raw,format=I420,colorimetry={color}', '!',
                   'fdsink', f'fd={write_fd}', 'sync=false']
        try:
            self.process = subprocess.Popen(command, stdout=self.log, stderr=self.log, pass_fds=(write_fd,))
        except BaseException:
            self.stream.close()
            self.stream = None
            raise
        finally:
            write_stream.close()
            self.color_input = None
        self.fd = self.stream.fileno()
        self.evidence['commands'].append({'cycle': self.cycle, 'pid': self.process.pid, 'argv': command})

    def _finish(self):
        code = self.process.wait(timeout=10)
        if self.color_input:
            self.color_input.close()
            self.color_input = None
        extra = read_socket_exact(self.stream, 1)
        if extra is not None:
            raise RuntimeError('MPP decoded more frames/bytes than source metadata; check stride.')
        color_code = self.color_process.wait(timeout=10)
        self.stream.close()
        self.stream = None
        self.fd = None
        if code or color_code:
            raise RuntimeError(f'MPP decoder/color worker exited {code}/{color_code}; see {self.log_path}.')

    def read(self):
        if self.closed:
            raise RuntimeError('Decoder already closed.')
        if self.eof:
            return None
        started = time.perf_counter()
        if self.index == self.count:
            self._finish()
            if not self.loop:
                self.eof = True
                return None
            self.cycle += 1
            self.index = 0
            self._open()
        payload = read_socket_exact(self.stream, self.width*self.height*3)
        if payload is None:
            code = self.process.wait(timeout=10)
            color_code = self.color_process.wait(timeout=10)
            raise RuntimeError(f'Early MPP decoder EOF at frame {self.index}/{self.count}, exit={code}/{color_code}; see {self.log_path}.')
        image = np.frombuffer(payload, np.uint8).reshape(self.height, self.width, 3)
        if self.index == 0:
            self.evidence['runtime'].append(runtime_evidence(self.process.pid))
        item = {'image': image, 'source_frame': self.index, 'cycle': self.cycle,
                'decode_started': started, 'decode_ms': (time.perf_counter()-started)*1000}
        self.index += 1
        self.evidence['frames_read'] += 1
        return item

    def close(self):
        if self.closed:
            return
        self.closed = True
        try:
            if self.process:
                self.evidence['cancelled_before_eof'] = self.process.poll() is None
                terminate(self.process)
                self.evidence['returncode'] = self.process.returncode
        finally:
            if self.color_input:
                self.color_input.close()
                self.color_input = None
            terminate(self.color_process)
            if self.color_process:
                self.evidence['color_worker_returncode'] = self.color_process.returncode
            if self.stream is not None:
                self.stream.close()
                self.stream = None
                self.fd = None
            self.log.close()
            if self.converter:
                self.converter.close()


class MppEncoder:
    def __init__(self, path, image, fps, bitrate=14000000):
        self.height, self.width = image.shape[:2]
        self.stride = (self.width*3+3)//4*4
        rate = Fraction(str(fps)).limit_denominator(100000)
        if bitrate <= 0 or rate <= 0 or self.width % 2 or self.height % 2:
            raise ValueError('MPP H.264 requires positive rate/bitrate and even output dimensions.')
        self.closed, self.process, self.frames, self.stream = False, None, 0, None
        self.log_path = Path(path).with_suffix('.gst.log')
        self.log = _log(self.log_path)
        self.evidence = {'backend': 'mpp', 'bitrate': bitrate, 'rc_mode': 'cbr',
                         'gop': round(fps), 'frames_written': 0, 'runtime': [],
                         'transport': 'BGR Unix stream; not zero-copy'}
        try:
            executable = require_plugins('fdsrc', 'rawvideoparse', 'videoconvert', 'mpph264enc', 'h264parse', 'mp4mux', 'filesink')
            command = [executable, '-q', 'fdsrc', 'fd=0', f'blocksize={self.stride*self.height}', '!', 'rawvideoparse', 'format=bgr',
                       f'width={self.width}', f'height={self.height}',
                       f'framerate={rate.numerator}/{rate.denominator}', '!', 'videoconvert', '!',
                       'video/x-raw,format=NV12,colorimetry=bt601', '!', 'mpph264enc',
                       'rc-mode=cbr', f'bps={bitrate}', f'gop={round(fps)}', '!', 'h264parse',
                       '!', 'mp4mux', '!', 'filesink', gst_property('location', Path(path).resolve()), 'sync=false']
            self.evidence['command'] = command
            self.stream, child_stream = raw_socket()
            try:
                self.process = subprocess.Popen(command, stdin=child_stream, stdout=self.log, stderr=self.log, bufsize=0)
            finally:
                child_stream.close()
            self.evidence['pid'] = self.process.pid
        except BaseException:
            self.abort()
            raise

    def write(self, image):
        if self.closed or image.shape != (self.height, self.width, 3) or image.dtype != np.uint8:
            raise ValueError('Encoder frame must retain its original BGR uint8 dimensions.')
        image = np.ascontiguousarray(image)
        if self.stride != self.width*3:
            padded = np.zeros((self.height, self.stride), np.uint8)
            padded[:, :self.width*3] = image.reshape(self.height, self.width*3)
            image = padded
        self.stream.sendall(memoryview(image).cast('B'))
        self.frames += 1
        self.evidence['frames_written'] = self.frames
        if self.frames in (1, 3):
            self.evidence['runtime'].append(runtime_evidence(self.process.pid))

    def close(self):
        if self.closed:
            return
        self.closed = True
        try:
            self.evidence['runtime'].append(runtime_evidence(self.process.pid))
            self.stream.shutdown(socket.SHUT_WR)  # EOF drives GStreamer EOS/MP4 finalization.
            self.stream.close()
            self.stream = None
            code = self.process.wait(timeout=30)
            self.evidence['returncode'] = code
            if code:
                raise RuntimeError(f'MPP encoder exited {code}; see {self.log_path}.')
        finally:
            terminate(self.process)
            if self.stream:
                self.stream.close()
                self.stream = None
            self.log.close()

    def abort(self):
        self.closed = True
        try:
            if self.stream:
                self.stream.close()
                self.stream = None
            terminate(self.process)
        finally:
            self.log.close()


def color_worker(width, height, pixel_format, read_fd, write_fd, stats_path):
    """Isolate conversion from inference's Python/GIL scheduling contention."""
    def stopped(*_):
        raise SystemExit(0)
    signal.signal(signal.SIGTERM, stopped)
    source = socket.socket(fileno=read_fd)
    target = socket.socket(fileno=write_fd)
    converter = LegacyColorConverter(width, height, pixel_format)
    stats = {'frames': 0, 'read_ms': 0., 'convert_ms': 0., 'write_ms': 0., 'library': converter.path}
    try:
        target.sendall(b'READY')
        while True:
            begin = time.perf_counter()
            payload = read_socket_exact(source, converter.frame_bytes)
            read = time.perf_counter()
            if payload is None:
                break
            image = converter.convert(payload)
            converted = time.perf_counter()
            target.sendall(memoryview(image).cast('B'))
            end = time.perf_counter()
            stats['frames'] += 1
            stats['read_ms'] += (read-begin)*1000
            stats['convert_ms'] += (converted-read)*1000
            stats['write_ms'] += (end-converted)*1000
    finally:
        converter.close()
        source.close()
        target.close()
        if stats_path != '-':
            Path(stats_path).write_text(json.dumps(stats)+'\n', encoding='utf-8')


if __name__ == '__main__':
    if len(sys.argv) != 8 or sys.argv[1] != '--color-worker':
        raise SystemExit('Internal color-worker entrypoint; use fast_bench.py for experiments.')
    color_worker(int(sys.argv[2]), int(sys.argv[3]), sys.argv[4], int(sys.argv[5]), int(sys.argv[6]), sys.argv[7])
