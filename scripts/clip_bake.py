"""Curve-preserving SVG path boolean clipping and stroke expansion.

Uses the preinstalled @napi-rs/canvas (Skia PathKit) through a persistent Node
worker. There is no raster intermediate, sampling, polygonization, or network.
Input paths must already share a coordinate system. Returned paths use the
nonzero fill rule (including correct hole winding) and M/L/C/Q/Z commands.

Stroke outlines should be expanded in an element's original coordinate space
and then transformed, especially for nonuniform transforms. Fill and stroke
are separate visual paint layers: intersect each separately to avoid stroking
the newly introduced clip boundary. The caller resolves clipPathUnits and CTM.
"""
from __future__ import annotations

import atexit
import json
import os
from pathlib import Path
import re
import subprocess
import shutil
import threading

_worker = None
_lock = threading.RLock()
_COMMAND_RE = re.compile(r'[A-DF-Za-df-z]')  # Excludes e/E in scientific notation.


def _request(payload):
    global _worker
    with _lock:
        if _worker is None or _worker.poll() is not None:
            node = os.environ.get('PPT_COMPAT_NODE') or shutil.which('node')
            if not node:
                raise RuntimeError('Node.js was not found: set PPT_COMPAT_NODE or add node to PATH')
            _worker = subprocess.Popen(
                [node,
                 str(Path(__file__).with_name('clip_bake_worker.cjs'))],
                stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                text=True, bufsize=1,
            )
        _worker.stdin.write(json.dumps(payload, separators=(',', ':')) + '\n')
        _worker.stdin.flush()
        response = _worker.stdout.readline()
        if not response:
            raise RuntimeError('Skia PathKit worker stopped unexpectedly')
        result = json.loads(response)
        if not result['ok']:
            raise ValueError(result['error'])
        value = result['value']
        if isinstance(value, str):
            commands = set(_COMMAND_RE.findall(value))
            if not commands <= set('MLCQZ'):
                raise ValueError(f'Unexpected output path commands {commands}')
        return value


def close_worker():
    global _worker
    with _lock:
        if _worker is not None:
            if _worker.poll() is None:
                _worker.stdin.close()
                try:
                    _worker.wait(timeout=2)
                except subprocess.TimeoutExpired:
                    _worker.terminate()
                    _worker.wait(timeout=2)
            _worker = None


atexit.register(close_worker)


def intersect_paths(subject_d: str, clip_d: str, *, fill_rule='nonzero', clip_rule='nonzero') -> str:
    """Return exact Skia curve intersection as a nonzero-fill SVG d string.

    Filled contours are implicitly closed by SVG/Skia semantics. Open strokes
    must first be expanded with stroke_to_path instead of passed directly here.
    Empty intersections return an empty string.
    """
    if not subject_d or not clip_d:
        return ''
    return _request(dict(op='intersect', subject_d=subject_d, clip_d=clip_d,
                         fill_rule=fill_rule, clip_rule=clip_rule))


def union_paths(subject_d: str, other_d: str) -> str:
    """Union filled contours, preserving nonzero hole winding."""
    if not subject_d:
        return normalize_path(other_d)
    if not other_d:
        return normalize_path(subject_d)
    return _request(dict(op='union', subject_d=subject_d, clip_d=other_d))


def difference_paths(subject_d: str, other_d: str) -> str:
    """Subtract filled contours, preserving nonzero hole winding."""
    if not subject_d or not other_d:
        return subject_d
    return _request(dict(op='difference', subject_d=subject_d, clip_d=other_d))


def stroke_to_path(d: str, width: float, cap='butt', join='miter', dash=None,
                   *, dash_offset=0.0, miter_limit=4.0) -> str:
    """Expand a vector stroke into filled contours without rasterization.

    Skia retains cubic and quadratic curve segments. dash accepts a numeric
    sequence or SVG string with one on/off pair (the only patterns in this
    figure); unsupported longer patterns deliberately raise ValueError.
    """
    if not d or float(width) <= 0:
        return ''
    if isinstance(dash, str):
        dash = None if dash.strip() in ('', 'none') else [float(n) for n in re.split(r'[\s,]+', dash.strip())]
    return _request(dict(op='stroke', d=d, width=float(width), cap=cap, join=join,
                         dash=dash, dash_offset=float(dash_offset), miter_limit=float(miter_limit)))


def path_bounds(d: str):
    """Return tight (x, y, width, height) bounds from Skia curve extrema."""
    left, top, right, bottom = _request(dict(op='bounds', d=d))
    return left, top, right - left, bottom - top


def path_bounds_ltrb(d: str):
    """Return tight (left, top, right, bottom) bounds from curve extrema."""
    return tuple(_request(dict(op='bounds', d=d)))


def normalize_path(d: str, *, fill_rule='nonzero') -> str:
    """Normalize a path to absolute commands and nonzero-fill hole winding."""
    return _request(dict(op='normalize', d=d, fill_rule=fill_rule))


if __name__ == '__main__':
    import sys
    if len(sys.argv) == 3:
        print(intersect_paths(sys.argv[1], sys.argv[2]))
    else:
        print(json.dumps(_request(dict(op='ping'))))
