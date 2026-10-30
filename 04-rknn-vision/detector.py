# SPDX-License-Identifier: AGPL-3.0-only
# Copyright (c) 2026 C-NHXT-N and contributors
# Adapted from Rockchip RKNN Model Zoo (Apache-2.0); see THIRD_PARTY_NOTICES.md.
"""YOLO26 one-to-one output contract; no inference backend lives in this module."""
import cv2
import numpy as np

SIZE = 640
SCORE_NODE = '/model.23/Sigmoid_output_0'
BOX_NODE = '/model.23/Mul_2_output_0'
OUTPUT_NODES = [SCORE_NODE, BOX_NODE]
CLASSES = (
    'person', 'bicycle', 'car', 'motorcycle', 'airplane', 'bus', 'train', 'truck',
    'boat', 'traffic light', 'fire hydrant', 'stop sign', 'parking meter', 'bench',
    'bird', 'cat', 'dog', 'horse', 'sheep', 'cow', 'elephant', 'bear', 'zebra',
    'giraffe', 'backpack', 'umbrella', 'handbag', 'tie', 'suitcase', 'frisbee',
    'skis', 'snowboard', 'sports ball', 'kite', 'baseball bat', 'baseball glove',
    'skateboard', 'surfboard', 'tennis racket', 'bottle', 'wine glass', 'cup',
    'fork', 'knife', 'spoon', 'bowl', 'banana', 'apple', 'sandwich', 'orange',
    'broccoli', 'carrot', 'hot dog', 'pizza', 'donut', 'cake', 'chair', 'couch',
    'potted plant', 'bed', 'dining table', 'toilet', 'tv', 'laptop', 'mouse',
    'remote', 'keyboard', 'cell phone', 'microwave', 'oven', 'toaster', 'sink',
    'refrigerator', 'book', 'clock', 'vase', 'scissors', 'teddy bear',
    'hair drier', 'toothbrush',
)


def preprocess(image):
    if image is None or image.ndim != 3 or image.shape[2] != 3:
        raise ValueError('Expected a decoded three-channel BGR image.')
    height, width = image.shape[:2]
    if width < 1 or height < 1:
        raise ValueError('Image dimensions must be positive.')
    ratio = min(SIZE / width, SIZE / height)
    resized_width, resized_height = round(width * ratio), round(height * ratio)
    resized_width = max(1, resized_width)
    resized_height = max(1, resized_height)
    horizontal = (SIZE - resized_width) / 2
    vertical = (SIZE - resized_height) / 2
    left, right = round(horizontal - 0.1), round(horizontal + 0.1)
    top, bottom = round(vertical - 0.1), round(vertical + 0.1)
    resized = cv2.resize(image, (resized_width, resized_height))
    padded = cv2.copyMakeBorder(resized, top, bottom, left, right, cv2.BORDER_CONSTANT, value=(0, 0, 0))
    batch = np.expand_dims(cv2.cvtColor(padded, cv2.COLOR_BGR2RGB), 0)
    # Actual rounded scales and integer padding make inverse mapping unambiguous.
    transform = {'width': width, 'height': height, 'scale_x': resized_width / width,
                 'scale_y': resized_height / height, 'left': left, 'top': top}
    return np.ascontiguousarray(batch, dtype=np.uint8), transform


def postprocess(outputs, transform, threshold=0.25, topk=300):
    if not isinstance(outputs, (list, tuple)) or len(outputs) != 2:
        raise ValueError('YOLO26 requires two truncated outputs: class scores and xyxy boxes.')
    score_output = box_output = None
    for output in outputs:
        array = np.asarray(output)
        if array.ndim != 3 or array.shape[0] != 1:
            raise ValueError('Expected batch-one outputs shaped (1, 80, N) and (1, 4, N).')
        if array.shape[1] == 80 and score_output is None:
            score_output = array[0].T
        elif array.shape[1] == 4 and box_output is None:
            box_output = array[0].T
        else:
            raise ValueError('Wrong output channels: use the matching YOLO26 conversion contract.')
    if score_output is None or box_output is None or score_output.shape[0] != box_output.shape[0]:
        raise ValueError('Score and box candidate counts must match.')
    if not np.isfinite(score_output).all() or not np.isfinite(box_output).all():
        raise ValueError('Model outputs contain non-finite values.')
    if np.any(score_output < -0.001) or np.any(score_output > 1.001):
        raise ValueError('Expected post-sigmoid class probabilities, not classification logits.')
    if score_output.shape[0] == 0:
        return []
    classes = np.argmax(score_output, axis=1)
    scores = np.max(score_output, axis=1)
    candidates = np.flatnonzero(scores > threshold)
    order = candidates[np.argsort(-scores[candidates], kind='stable')[:topk]]
    results = []
    for index in order:
        box = np.asarray(box_output[index], dtype=np.float64).copy()
        box[[0, 2]] = (box[[0, 2]] - transform['left']) / transform['scale_x']
        box[[1, 3]] = (box[[1, 3]] - transform['top']) / transform['scale_y']
        box[[0, 2]] = np.clip(box[[0, 2]], 0, transform['width'])
        box[[1, 3]] = np.clip(box[[1, 3]], 0, transform['height'])
        if box[2] <= box[0] or box[3] <= box[1]:
            continue
        class_id = int(classes[index])
        results.append({'class_id': class_id, 'name': CLASSES[class_id],
                        'confidence': float(scores[index]), 'xyxy': [round(float(x), 3) for x in box]})
    return results


def annotate(image, detections):
    rendered = image.copy()
    for item in detections:
        x1, y1, x2, y2 = (int(round(value)) for value in item['xyxy'])
        cv2.rectangle(rendered, (x1, y1), (x2, y2), (0, 200, 0), 2)
        label = f"{item['name']} {item['confidence']:.2f}"
        cv2.putText(rendered, label, (x1, max(15, y1 - 5)), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 200, 0), 1)
    return rendered
