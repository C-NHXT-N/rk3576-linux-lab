# SPDX-License-Identifier: AGPL-3.0-only
"""Shared FFmpeg headers, library identity and bounded frame leases."""
import ctypes as ct
import hashlib
import json
import os
from pathlib import Path
import queue
import subprocess
import tarfile
import threading
import time
import urllib.request

import cv2
import numpy as np
import media_backends
import vision
import thread_accounting

ROOT=Path(__file__).resolve().parent
ARCHIVE_SHA256='f428a08942b609cd9dfc3faab610db809705eed908c0c9b5d0fcbe70eb3134aa'
SOURCE_URL='https://codeload.github.com/FFmpeg/FFmpeg/tar.gz/refs/tags/n5.1.6'


def digest(path):return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def reference_libraries():
    maps=Path('/proc/self/maps').read_text().splitlines();result=[]
    for name in ('libavformat-','libavcodec-','libavutil-','libswscale-'):
        paths=sorted({line.split()[-1] for line in maps if name in line and 'opencv' in line})
        if len(paths)!=1:raise RuntimeError('Expected exactly one OpenCV FFmpeg library: '+name)
        result.append(paths[0])
    return result


def ensure_headers():
    cache=ROOT/'build';cache.mkdir(exist_ok=True)
    archive=cache/'ffmpeg-n5.1.6.tar.gz'
    if not archive.exists():
        with urllib.request.urlopen(SOURCE_URL,timeout=60) as response:archive.write_bytes(response.read())
    if digest(archive)!=ARCHIVE_SHA256:raise RuntimeError('FFmpeg source archive hash mismatch')
    headers=cache/'FFmpeg-n5.1.6'
    if not (headers/'libavutil/avconfig.h').exists():
        with tarfile.open(archive) as tar:
            # Fixed official source, reject links and extraction outside the cache.
            members=[m for m in tar.getmembers() if m.isfile() or m.isdir()]
            if any(not (cache/m.name).resolve().is_relative_to(cache.resolve()) for m in members):
                raise RuntimeError('Unsafe FFmpeg archive member')
            tar.extractall(cache,members=members)
        subprocess.run(['sh','configure','--disable-everything','--disable-x86asm','--disable-doc',
                        '--disable-programs','--disable-autodetect'],cwd=headers,check=True,
                       stdout=subprocess.DEVNULL,timeout=90)
    return {'source_url':SOURCE_URL,'archive_sha256':ARCHIVE_SHA256}


class FrameLease:
    def __init__(self,pool,slot):
        self.pool,self.slot,self.image,self.released=pool,slot,slot.image,False
        self.canvas=slot.canvas
    def release(self):
        with self.pool.lock:
            if not self.released:
                self.released=True;self.pool.active.pop(id(self),None);self.pool.free.put_nowait(self.slot)


class FrameSlot:
    def __init__(self,canvas=False):
        rows=800 if canvas else 720
        storage=np.empty(rows*1280*3+96,np.uint8)
        offset=(-storage.ctypes.data)%32
        pixels=storage[offset:offset+rows*1280*3].reshape(rows,1280,3)
        self.canvas=pixels[:790] if canvas else None
        self.image=self.canvas[70:] if canvas else pixels


class FramePool:
    def __init__(self,count,canvas=False):
        self.free=queue.Queue(count);self.lock=threading.Lock();self.active={}
        self.slots=[];self.closed=False
        for _ in range(count):
            slot=FrameSlot(canvas);self.slots.append(slot);self.free.put(slot)
    def acquire(self,stop):
        while not stop.is_set():
            try:slot=self.free.get(timeout=.1)
            except queue.Empty:continue
            lease=FrameLease(self,slot)
            with self.lock:self.active[id(lease)]=lease
            return lease
        return None
    def reclaim(self):
        for lease in list(self.active.values()):lease.release()
    def close(self):
        if self.closed:return
        self.reclaim();self.closed=True
