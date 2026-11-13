# SPDX-License-Identifier: AGPL-3.0-only
"""One explicit CPU role policy, kept separate from the automatic baseline."""
import os
import threading

_policy = 'auto'
_initial = None
_rows = []
_lock = threading.Lock()
MASKS = {'reader': {4, 5}, 'prepare': {6}, 'postprocess': {7},
         'npu_caller': {0, 1, 2, 3}, 'producer': {0, 1, 2, 3},
         'mpp_submit': {0, 1, 2, 3}, 'main_output': {4, 5, 6, 7},
         'encoder': {4, 5}}


def begin(policy):
    global _policy, _initial, _rows
    _policy, _rows = policy, []
    _initial = set(os.sched_getaffinity(0)) if hasattr(os, 'sched_getaffinity') else None
    if policy == 'roles' and (_initial is None or not set(range(8)).issubset(_initial)):
        raise RuntimeError('The role comparison requires access to CPU0..7')


def apply(role, tid=0):
    if _policy == 'auto':
        return
    mask = MASKS[role]
    os.sched_setaffinity(tid, mask)
    with _lock:
        _rows.append(dict(role=role, tid=tid or threading.get_native_id(), cpus=sorted(mask)))


def report():
    return dict(policy=_policy, assignments=list(_rows))


def restore():
    if _initial is not None and hasattr(os, 'sched_setaffinity'):
        os.sched_setaffinity(0, _initial)
