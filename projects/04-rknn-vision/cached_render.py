# SPDX-License-Identifier: AGPL-3.0-only
"""Pixel-compatible original drawing with reusable canvas and bounded labels."""
from collections import OrderedDict
import cv2
import numpy as np


class Renderer:
    def __init__(self, limit=512, labels=None):
        self.limit = limit
        self.labels = labels if labels is not None else OrderedDict()
        self.canvas = self.header = None
        self.hits = self.misses = 0

    def draw(self, image, detections, detail, canvas=None):
        height, width = image.shape[:2]
        if canvas is not None:
            if canvas.shape!=(height+70,width,3) or not np.shares_memory(canvas[70:],image):
                raise ValueError('Inplace rendering needs its original leased canvas')
            self.canvas=canvas
        elif self.canvas is None or self.canvas.shape != (height+70, width, 3):
            self.canvas = np.empty((height+70, width, 3), np.uint8)
        if self.header is None or self.header.shape!=(70,width,3):
            self.header = np.full((70, width, 3), (23, 18, 15), np.uint8)
            cv2.putText(self.header, 'RK3576  /  YOLO26n FP16  /  640 x 640', (20, 28),
                cv2.FONT_HERSHEY_SIMPLEX, .7, (240, 245, 250), 1, cv2.LINE_AA)
        self.canvas[:70] = self.header
        rendered = self.canvas[70:]
        if canvas is None:np.copyto(rendered, image)
        palette = [(220, 210, 40), (90, 210, 245), (100, 190, 255),
                   (220, 120, 200), (130, 220, 120), (100, 125, 250)]
        thickness = max(2, round(width/640))
        scale = max(.45, width/1800)
        for item in detections:
            x1, y1, x2, y2 = (int(round(v)) for v in item['xyxy'])
            color = palette[item['class_id'] % len(palette)]
            cv2.rectangle(rendered, (x1, y1), (min(width-1, x2), min(height-1, y2)),
                          color, thickness, cv2.LINE_AA)
            label = f"{item['name']} {item['confidence']:.2f}"
            key = (label, scale, color)
            cached = self.labels.pop(key, None)
            if cached is None:
                self.misses += 1
                (tw, th), baseline = cv2.getTextSize(label, cv2.FONT_HERSHEY_SIMPLEX, scale, 1)
                tile = np.full((th+baseline+8, tw+10, 3), color, np.uint8)
                cv2.putText(tile, label, (4, th+4), cv2.FONT_HERSHEY_SIMPLEX, scale,
                            (18, 24, 32), 1, cv2.LINE_AA)
                cached = (tile, tw, th, baseline)
            else:
                self.hits += 1
            self.labels[key] = cached
            if len(self.labels) > self.limit:
                self.labels.popitem(last=False)
            tile, tw, th, baseline = cached
            lx = max(0, min(x1, width-tw-10))
            ly = max(th+10, min(height-baseline-1, y1-4))
            y = ly-th-7
            h, w = min(tile.shape[0], height-y), min(tile.shape[1], width-lx)
            if h > 0 and w > 0:
                rendered[y:y+h, lx:lx+w] = tile[:h, :w]
        cv2.putText(self.canvas, detail, (20, 54), cv2.FONT_HERSHEY_SIMPLEX, .53,
                    (220, 210, 40), 1, cv2.LINE_AA)
        # Borrowed storage; caller must finish synchronous encoding before next draw.
        return self.canvas
