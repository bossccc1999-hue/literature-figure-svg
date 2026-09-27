"""Bake an explicit SVG diagram into editable Office-compatible vector paths.

CLI: python normalize_svg.py input.svg --output-dir normalized
Outputs compatible.svg, artwork.svg (without text), texts.json and
normalization.json. Canvas units follow the source viewBox, translated to 0,0.

Supported: explicit primitive/path geometry, affine transforms, solid/linear/
radial paint, per-paint alpha, curve boolean clipping, outlined strokes with
one on/off dash pair, simple start/end markers, and explicitly positioned
single-line text with baseline/sub/super runs. Arc geometry becomes cubics.
All clipping is an actual Skia boolean operation, never a bounds shortcut.

Fails explicitly on CSS sheets/classes, external references, use/image,
filter/mask/pattern, group opacity, blend modes, nonuniform viewport scaling,
complex/clipped/transformed text, complex marker viewports, and unsupported
attributes. Resolve these through native authoring; do not silently rasterize.
Requires lxml, sibling geometry modules, Node.js and @napi-rs/canvas. Set
PPT_COMPAT_NODE and PPT_COMPAT_CANVAS_MODULE or RUNTIME_NODE_MODULES as needed.
"""
from __future__ import annotations

import argparse
import copy
import json
import math
from pathlib import Path
import re

from lxml import etree as E
from pptx_paths import parse_path, parse_transform, transform_point, multiply, IDENTITY
from svg_geometry import primitive_to_path
from clip_bake import (intersect_paths, union_paths, difference_paths,
                       stroke_to_path, path_bounds, normalize_path)

S = 'http://www.w3.org/2000/svg'
NUM = r'[-+]?(?:\d*\.\d+|\d+\.?\d*)(?:[eE][-+]?\d+)?'
GEOMETRY = {'path', 'rect', 'circle', 'ellipse', 'polygon', 'polyline', 'line'}
INHERITED = {'fill', 'stroke', 'stroke-width', 'fill-opacity', 'stroke-opacity',
             'stroke-linecap', 'stroke-linejoin', 'stroke-miterlimit',
             'stroke-dasharray', 'stroke-dashoffset', 'fill-rule', 'clip-rule',
             'marker-start', 'marker-end', 'font-family', 'font-size',
             'font-weight', 'font-style', 'text-anchor'}
COMMON = INHERITED | {'id', 'style', 'transform', 'opacity', 'clip-path'}
SPECIFIC = {
    'svg': {'width', 'height', 'viewBox', 'version', 'preserveAspectRatio'},
    'g': set(), 'defs': set(), 'path': {'d'},
    'rect': {'x', 'y', 'width', 'height', 'rx', 'ry'},
    'circle': {'cx', 'cy', 'r'}, 'ellipse': {'cx', 'cy', 'rx', 'ry'},
    'line': {'x1', 'y1', 'x2', 'y2'}, 'polygon': {'points'}, 'polyline': {'points'},
    'text': {'x', 'y'}, 'tspan': {'baseline-shift'},
    'clipPath': {'clipPathUnits'},
    'linearGradient': {'x1', 'y1', 'x2', 'y2', 'gradientUnits', 'gradientTransform', 'spreadMethod'},
    'radialGradient': {'cx', 'cy', 'r', 'fx', 'fy', 'gradientUnits', 'gradientTransform', 'spreadMethod'},
    'stop': {'offset', 'stop-color', 'stop-opacity'},
    'marker': {'markerUnits', 'markerWidth', 'markerHeight', 'refX', 'refY', 'orient', 'overflow'},
}
DEFAULTS = {'fill': '#000000', 'stroke': 'none', 'stroke-width': '1',
            'fill-opacity': '1', 'stroke-opacity': '1', 'fill-rule': 'nonzero',
            'clip-rule': 'nonzero', 'stroke-linecap': 'butt', 'stroke-linejoin': 'miter',
            'font-family': 'Arial', 'font-size': '16', 'font-weight': '400',
            'font-style': 'normal', 'text-anchor': 'start'}


def tag(e):
    return E.QName(e).localname


def fail(e, message):
    raise ValueError(f"<{tag(e)}> id={e.get('id', '(none)')}: {message}; use explicit native authoring for this feature")


def attrs(e):
    result = dict(e.attrib)
    for item in e.get('style', '').split(';'):
        if item.strip():
            if ':' not in item:
                fail(e, 'malformed inline style')
            name, value = (x.strip() for x in item.split(':', 1))
            if '!important' in value:
                fail(e, '!important is unsupported')
            result[name] = value
    return result


def number(value, label='number'):
    text = str(value).strip()
    if not re.fullmatch(NUM + r'(?:px)?', text):
        raise ValueError(f'{label} must be one explicit numeric user-unit value, got {value!r}')
    result = float(text.removesuffix('px'))
    if not math.isfinite(result):
        raise ValueError(f'Nonfinite {label}')
    return result


def viewport_length(value):
    """Resolve a root viewport length to CSS px; geometry remains user units."""
    match = re.fullmatch('(' + NUM + r')(px|pt|pc|in|cm|mm|q)?', str(value).strip())
    if not match:
        raise ValueError(f'Root width/height must use explicit absolute lengths, got {value!r}')
    factor = {None: 1, 'px': 1, 'pt': 96 / 72, 'pc': 16, 'in': 96,
              'cm': 96 / 2.54, 'mm': 96 / 25.4, 'q': 96 / 101.6}[match.group(2)]
    return number(match.group(1)) * factor


def alpha(value):
    result = number(value, 'opacity')
    if not 0 <= result <= 1:
        raise ValueError('Opacity must be between 0 and 1')
    return result


def matrix(value):
    if value and re.sub(r'[A-Za-z]+\s*\([^)]*\)', '', value).strip(' ,\t\r\n'):
        raise ValueError(f'Malformed SVG transform: {value}')
    for raw in re.findall(r'[A-Za-z]+\s*\(([^)]*)\)', value or ''):
        if re.sub(NUM, '', raw).strip(' ,\t\r\n'):
            raise ValueError(f'Malformed transform numbers: {raw}')
    result = parse_transform(value)
    if not all(math.isfinite(v) for v in result):
        raise ValueError('Nonfinite SVG transform')
    return result


def ref(value):
    if value in (None, '', 'none'):
        return None
    match = re.fullmatch(r'url\(\s*[\'\"]?#([^\s\)\'\"]+)[\'\"]?\s*\)', value)
    if not match:
        raise ValueError(f'Only local url(#id) references are supported, got {value!r}')
    return match.group(1)


def color(value):
    value = value.strip()
    named = {'black': '#000000', 'white': '#ffffff', 'red': '#ff0000',
             'green': '#008000', 'blue': '#0000ff', 'yellow': '#ffff00',
             'gray': '#808080', 'grey': '#808080', 'purple': '#800080', 'orange': '#ffa500'}
    if value in ('none', 'transparent'):
        return value
    if value.lower() in named:
        return named[value.lower()]
    if re.fullmatch(r'#[\da-fA-F]{3}', value):
        return '#' + ''.join(c * 2 for c in value[1:])
    if re.fullmatch(r'#[\da-fA-F]{6}', value):
        return value
    match = re.fullmatch(r'rgb\(\s*(\d+)\s*,\s*(\d+)\s*,\s*(\d+)\s*\)', value)
    if match and all(int(c) <= 255 for c in match.groups()):
        return '#' + ''.join(f'{int(c):02x}' for c in match.groups())
    raise ValueError(f'Unsupported color {value!r}; resolve to #RRGGBB and explicit opacity')


def transform_d(d, m):
    return ' '.join(cmd + (' '.join(f'{v:.9f}'.rstrip('0').rstrip('.') or '0'
                         for p in points for v in transform_point(m, p)) if points else '')
                    for cmd, points in parse_path(d))


class Normalizer:
    def __init__(self, source):
        parser = E.XMLParser(resolve_entities=False, no_network=True)
        document = E.parse(str(source), parser)
        if document.docinfo.doctype:
            raise ValueError('SVG DOCTYPE/entity declarations are unsupported')
        if document.xpath('//processing-instruction("xml-stylesheet")'):
            raise ValueError('External XML stylesheets are unsupported')
        self.src = document.getroot()
        if tag(self.src) != 'svg':
            raise ValueError('Input must be an SVG document')
        self.byid = {}
        self.preflight(self.src)
        viewbox = self.src.get('viewBox')
        if viewbox:
            values = [number(v) for v in re.split(r'[\s,]+', viewbox.strip())]
            if len(values) != 4:
                raise ValueError('viewBox requires exactly four numbers')
            x, y, self.width, self.height = values
        else:
            x = y = 0
            self.width, self.height = viewport_length(self.src.get('width')), viewport_length(self.src.get('height'))
        if self.width <= 0 or self.height <= 0:
            raise ValueError('Canvas dimensions must be positive')
        if self.src.get('width') and self.src.get('height'):
            ratio = viewport_length(self.src.get('width')) / viewport_length(self.src.get('height'))
            if abs(ratio - self.width / self.height) > 1e-6:
                fail(self.src, 'viewport and viewBox aspect ratios must match')
        self.origin_matrix = (1, 0, 0, 1, -x, -y)
        self.out = E.Element(f'{{{S}}}svg', nsmap={None: S}, width=f'{self.width:g}',
                             height=f'{self.height:g}', viewBox=f'0 0 {self.width:g} {self.height:g}', version='1.1')
        self.defs = E.SubElement(self.out, f'{{{S}}}defs')
        self.records, self.texts = [], []
        self.serial = self.gserial = 0
        self.stats = {'clipped_fills': 0, 'clipped_strokes': 0, 'markers': 0, 'opacity_partitions': 0}

    def preflight(self, e):
        t = tag(e)
        if t in ('title', 'desc', 'metadata'):
            return
        if t not in SPECIFIC:
            fail(e, f'unsupported SVG element {t}')
        if t == 'svg' and e is not self.src:
            fail(e, 'nested svg viewport')
        a = attrs(e)
        for key, value in a.items():
            if key.startswith('{'):
                if E.QName(key).localname in ('href', 'base'):
                    fail(e, 'external or inherited references')
                continue  # Inkscape labels and nonrendering editor metadata.
            if key.startswith(('aria-', 'data-')) or key in ('role',):
                continue
            if key not in COMMON | SPECIFIC[t]:
                fail(e, f'unsupported attribute/style {key}')
            if 'url(' in value and not re.fullmatch(r'url\(\s*[\'\"]?#[^\s\)\'\"]+[\'\"]?\s*\)', value):
                fail(e, 'external, fallback or multiple paint references')
        ident = e.get('id')
        if ident:
            if ident in self.byid:
                fail(e, 'duplicate id')
            self.byid[ident] = e
        if 'transform' in a:
            matrix(a['transform'])
        if t in ('svg', 'g', 'defs', 'clipPath', 'marker') and alpha(a.get('opacity', 1)) != 1:
            fail(e, 'group opacity requires compositing and cannot be distributed over children')
        if t in ('linearGradient', 'radialGradient'):
            if a.get('spreadMethod', 'pad') != 'pad':
                fail(e, 'only gradient spreadMethod=pad is supported')
            if a.get('gradientUnits', 'objectBoundingBox') not in ('objectBoundingBox', 'userSpaceOnUse'):
                fail(e, 'unknown gradientUnits')
            matrix(a.get('gradientTransform'))
        if t == 'clipPath' and a.get('clipPathUnits', 'userSpaceOnUse') != 'userSpaceOnUse':
            fail(e, 'only clipPathUnits=userSpaceOnUse is currently supported')
        if t == 'marker' and (a.get('transform') or a.get('clip-path')):
            fail(e, 'transform or clip-path on the marker definition')
        for child in e:
            if isinstance(child.tag, str):
                self.preflight(child)

    def style(self, e, inherited):
        a = attrs(e)
        st = dict(inherited)
        st.update({k: v for k, v in a.items() if k in INHERITED})
        st['opacity'] = alpha(a.get('opacity', 1))
        for key in ('fill-rule', 'clip-rule'):
            if st.get(key, 'nonzero') not in ('nonzero', 'evenodd'):
                fail(e, f'unsupported {key}')
        return st

    def lookup(self, value, expected):
        ident = ref(value)
        if ident is None:
            return None
        if ident not in self.byid or tag(self.byid[ident]) not in expected:
            raise ValueError(f'Missing or incorrect SVG reference {ident!r}; expected {expected}')
        return self.byid[ident]

    def clip_for(self, e, m):
        cp = self.lookup(attrs(e).get('clip-path'), {'clipPath'})
        if cp is None:
            return None
        cm = multiply(m, matrix(attrs(cp).get('transform')))
        st = self.style(cp, DEFAULTS)
        result = ''
        for child in cp:
            if tag(child) not in GEOMETRY:
                fail(child, 'clipPath children must be explicit primitives')
            if attrs(child).get('clip-path'):
                fail(child, 'nested clipPath on clip geometry')
            cs = self.style(child, st)
            d = normalize_path(primitive_to_path(child), fill_rule=cs.get('clip-rule', 'nonzero'))
            d = transform_d(d, multiply(cm, matrix(attrs(child).get('transform'))))
            result = union_paths(result, d)
        return result

    def clipped(self, d, clips, kind):
        for clip in clips:
            if not d:
                break
            d = intersect_paths(d, clip)
            self.stats['clipped_' + kind] += 1
        return d

    def gradient(self, original, bbox, m, pid):
        g = copy.deepcopy(original)
        g.attrib.clear()
        original_attrs = attrs(original)
        gid = pid + '_gradient'
        g.set('id', gid)
        x, y, w, h = bbox
        object_units = original_attrs.get('gradientUnits', 'objectBoundingBox') == 'objectBoundingBox'
        if object_units and (w <= 0 or h <= 0):
            fail(original, 'objectBoundingBox gradient on a zero-area shape')
        defaults = {'x1': '0', 'y1': '0', 'x2': '1', 'y2': '0'} if tag(g) == 'linearGradient' else {'cx': '.5', 'cy': '.5', 'r': '.5'}
        keys = ('x1', 'x2', 'y1', 'y2') if tag(g) == 'linearGradient' else ('cx', 'cy', 'r', 'fx', 'fy')
        for key in keys:
            value = original_attrs.get(key, defaults.get(key))
            if value is None:
                continue
            if value.endswith('%'):
                fraction = number(value[:-1]) / 100
                if object_units:
                    value = str(fraction)
                else:
                    base = self.width if key in ('x1', 'x2', 'cx', 'fx') else self.height
                    if key == 'r':
                        base = math.hypot(self.width, self.height) / math.sqrt(2)
                    value = str(fraction * base)
            g.set(key, str(number(value)))
        # Default userSpaceOnUse linear endpoint is 100% of the viewport width.
        if not object_units and tag(g) == 'linearGradient' and 'x2' not in original_attrs:
            g.set('x2', str(self.width))
        if not object_units and tag(g) == 'radialGradient':
            for key, base in [('cx', self.width), ('cy', self.height), ('r', math.hypot(self.width, self.height) / math.sqrt(2))]:
                if key not in original_attrs:
                    g.set(key, str(base * .5))
        gm = matrix(original_attrs.get('gradientTransform'))
        if object_units:
            gm = multiply((w, 0, 0, h, x, y), gm)
        gm = multiply(m, gm)
        g.set('gradientUnits', 'userSpaceOnUse')
        g.set('gradientTransform', 'matrix(' + ' '.join(f'{v:.12g}' for v in gm) + ')')
        last_offset = -1
        for stop in g:
            if tag(stop) != 'stop':
                fail(stop, 'gradient children must be explicit stops')
            a = attrs(stop)
            value = a.get('offset', '0')
            offset = number(value[:-1]) / 100 if value.endswith('%') else number(value)
            if not 0 <= offset <= 1 or offset < last_offset:
                fail(stop, 'gradient stop offsets must be sorted within [0,1]')
            last_offset = offset
            stop.attrib.clear()
            stop.set('offset', str(offset))
            stop_color = color(a.get('stop-color', '#000000'))
            stop_alpha = alpha(a.get('stop-opacity', 1))
            if stop_color == 'none':
                fail(stop, 'none is not a valid gradient stop-color')
            if stop_color == 'transparent':
                stop_color, stop_alpha = '#000000', 0
            stop.set('stop-color', stop_color)
            stop.set('stop-opacity', str(stop_alpha))
        if not len(g):
            fail(original, 'gradient requires explicit stops')
        self.defs.append(g)
        return f'url(#{gid})'

    def paint(self, parent, d, paint, opacity, bbox, m, sid, kind, clips):
        if paint in ('none', 'transparent') or not d or opacity <= 0:
            return
        d = self.clipped(transform_d(d, m), clips, kind)
        if not d:
            return
        self.serial += 1
        pid = f'{sid}_{kind}_{self.serial:05d}'
        p = E.SubElement(parent, f'{{{S}}}path', id=pid, d=d)
        if paint.startswith('url('):
            gradient = self.lookup(paint, {'linearGradient', 'radialGradient'})
            p.set('fill', self.gradient(gradient, bbox, m, pid))
        else:
            p.set('fill', color(paint))
        if opacity < 1:
            p.set('fill-opacity', f'{opacity:.9g}')
        self.records.append({'id': pid, 'source_id': sid, 'kind': kind, 'group': parent.get('id')})

    def draw_shape(self, e, parent, m, st, clips, sid=None):
        d = primitive_to_path(e)
        if not d:
            return
        bbox = path_bounds(d)
        sid = sid or e.get('id') or f'shape_{len(self.records)+1:05d}'
        fill = normalize_path(d, fill_rule=st.get('fill-rule', 'nonzero'))
        stroke = ''
        stroke_alpha = alpha(st.get('stroke-opacity', 1))
        if st.get('stroke', 'none') not in ('none', 'transparent') and number(st.get('stroke-width', 1)) > 0:
            stroke = stroke_to_path(d, number(st.get('stroke-width', 1)),
                                    cap=st.get('stroke-linecap', 'butt'), join=st.get('stroke-linejoin', 'miter'),
                                    dash=st.get('stroke-dasharray'), dash_offset=number(st.get('stroke-dashoffset', 0)),
                                    miter_limit=number(st.get('stroke-miterlimit', 4)))
        if st['opacity'] < 1 and stroke and st.get('fill', '#000000') not in ('none', 'transparent'):
            # Element opacity applies after its fill+stroke composite. Removing
            # the fill under an opaque solid stroke preserves this semantics;
            # merely multiplying both paint alphas would darken the overlap.
            if stroke_alpha != 1 or st['stroke'].startswith('url('):
                fail(e, 'element opacity with overlapping fill and translucent/gradient stroke')
            fill = difference_paths(fill, stroke)
            self.stats['opacity_partitions'] += 1
        self.paint(parent, fill, st.get('fill', '#000000'), alpha(st.get('fill-opacity', 1)) * st['opacity'], bbox, m, sid, 'fills', clips)
        self.paint(parent, stroke, st.get('stroke', 'none'), stroke_alpha * st['opacity'], bbox, m, sid, 'strokes', clips)
        if st.get('marker-start', 'none') != 'none' or st.get('marker-end', 'none') != 'none':
            if st['opacity'] != 1:
                fail(e, 'marker with element opacity needs composite authoring')
            self.markers(e, parent, d, m, st, clips)

    def markers(self, e, parent, d, m, st, clips):
        commands = list(parse_path(d))
        if sum(cmd == 'M' for cmd, _ in commands) != 1:
            fail(e, 'marker paths must have a single subpath')
        pen = start = (0, 0)
        first = last = None
        def tangent(points):
            for p in points[1:]:
                t = p[0] - points[0][0], p[1] - points[0][1]
                if abs(t[0]) + abs(t[1]) > 1e-12:
                    return t
            return None
        for cmd, pts in commands:
            if cmd == 'M':
                pen = start = pts[0]
                continue
            points = [pen] + (list(pts) if cmd != 'Z' else [start])
            a, b = tangent(points), tangent(list(reversed(points)))
            first = first or a
            if b:
                last = (-b[0], -b[1])
            pen = points[-1]
        if first is None or last is None:
            fail(e, 'marker tangent is undefined on a zero-length path')
        for position, point, direction in [('start', start, first), ('end', pen, last)]:
            marker = self.lookup(st.get('marker-' + position), {'marker'})
            if marker is None:
                continue
            a = attrs(marker)
            orient = a.get('orient', '0')
            angle = math.atan2(direction[1], direction[0]) if orient in ('auto', 'auto-start-reverse') else math.radians(number(orient.removesuffix('deg')))
            if position == 'start' and orient == 'auto-start-reverse':
                angle += math.pi
            scale = number(st.get('stroke-width', 1)) if a.get('markerUnits', 'strokeWidth') == 'strokeWidth' else 1
            if a.get('markerUnits', 'strokeWidth') not in ('strokeWidth', 'userSpaceOnUse'):
                fail(marker, 'unknown markerUnits')
            c, s = math.cos(angle), math.sin(angle)
            mm = multiply(m, multiply((c, s, -s, c, point[0], point[1]), multiply((scale, 0, 0, scale, 0, 0), (1, 0, 0, 1, -number(a.get('refX', 0)), -number(a.get('refY', 0))))))
            marker_clips = clips
            if a.get('overflow', 'hidden') == 'hidden':
                rect = E.Element('rect', width=str(number(a.get('markerWidth', 3))), height=str(number(a.get('markerHeight', 3))))
                marker_clips += (transform_d(primitive_to_path(rect), mm),)
            elif a.get('overflow') != 'visible':
                fail(marker, 'unsupported marker overflow')
            mst = self.style(marker, DEFAULTS)
            for j, child in enumerate(marker):
                if tag(child) not in GEOMETRY:
                    fail(child, 'marker children must be explicit primitives without nested groups')
                cst = self.style(child, mst)
                if cst.get('marker-start', 'none') != 'none' or cst.get('marker-end', 'none') != 'none':
                    fail(child, 'recursive marker')
                cm = multiply(mm, matrix(attrs(child).get('transform')))
                cp = self.clip_for(child, cm)
                self.draw_shape(child, parent, cm, cst, marker_clips + ((cp,) if cp is not None else ()), (e.get('id') or 'marker') + f'_{position}_{j}')
                self.stats['markers'] += 1

    def text(self, e, parent, m, st, clips, panel):
        if m != self.origin_matrix or clips:
            fail(e, 'transformed or clipped text requires native textbox authoring')
        if st.get('stroke', 'none') != 'none' or st.get('font-style', 'normal') != 'normal':
            fail(e, 'text stroke or nonnormal font-style')
        anchor = st.get('text-anchor', 'start')
        if anchor not in ('start', 'middle', 'end'):
            fail(e, 'unsupported text-anchor')
        x, y = transform_point(m, (number(e.get('x')), number(e.get('y'))))
        runs = []
        def add_run(value, rst, shift='baseline', opacity=1):
            if not value or not value.strip():
                return
            if '\n' in value.strip() or '\r' in value.strip():
                fail(e, 'multiline text content')
            weight = rst.get('font-weight', '400')
            if weight not in ('400', '700', 'normal', 'bold'):
                fail(e, 'only normal/400 and bold/700 font weights are supported')
            run_color = color(rst['fill'])
            run_alpha = opacity * alpha(rst.get('fill-opacity', 1))
            if run_color in ('none', 'transparent'):
                run_color, run_alpha = '#000000', 0
            runs.append({'text': value.strip('\r\n'), 'font_size': number(rst['font-size']),
                         'font_family': rst['font-family'], 'bold': weight in ('700', 'bold'),
                         'color': run_color, 'opacity': run_alpha,
                         'baseline_shift': shift})
        add_run(e.text, st, opacity=st['opacity'])
        for child in e:
            if tag(child) != 'tspan' or len(child):
                fail(child, 'text children must be simple leaf tspans')
            ca = attrs(child)
            if ca.get('transform') or ca.get('clip-path') or ca.get('stroke', 'none') != 'none':
                fail(child, 'transformed, stroked or clipped tspan')
            shift = ca.get('baseline-shift', 'baseline')
            if shift not in ('baseline', 'sub', 'super'):
                fail(child, 'only baseline/sub/super baseline shifts are supported')
            cs = self.style(child, st)
            if cs.get('font-style', 'normal') != 'normal' or cs.get('text-anchor', 'start') != anchor:
                fail(child, 'tspan font-style or changed text-anchor')
            add_run(child.text, cs, shift, st['opacity'] * cs['opacity'])
            add_run(child.tail, st, opacity=st['opacity'])
        if not runs:
            return
        text = ''.join(r['text'] for r in runs)
        t = E.SubElement(parent, f'{{{S}}}text', id=e.get('id') or f'text_{len(self.texts)+1:04}', x=str(x), y=str(y), **{'text-anchor': anchor})
        for run in runs:
            child = E.SubElement(t, f'{{{S}}}tspan', **{'font-family': run['font_family'], 'font-size': f"{run['font_size']:g}px", 'font-weight': '700' if run['bold'] else '400', 'fill': run['color']})
            if run['baseline_shift'] != 'baseline':
                child.set('baseline-shift', run['baseline_shift'])
            if run['opacity'] < 1:
                child.set('fill-opacity', str(run['opacity']))
            child.text = run['text']
        self.texts.append({'id': t.get('id'), 'text': text, 'x': x, 'baseline': y,
                           'font_size': number(st['font-size']), 'font_family': st['font-family'],
                           'bold': st['font-weight'] in ('700', 'bold'), 'color': color(st['fill']),
                           'opacity': st['opacity'] * alpha(st.get('fill-opacity', 1)),
                           'text_anchor': anchor, 'panel': panel, 'runs': runs})

    def walk(self, e, parent, m, inherited, clips=(), panel=None):
        t = tag(e)
        if t in ('defs', 'title', 'desc', 'metadata'):
            return
        st = self.style(e, inherited)
        m = multiply(m, matrix(attrs(e).get('transform')))
        cp = self.clip_for(e, m)
        if cp is not None:
            clips += (cp,)
        if t in ('svg', 'g'):
            p = parent
            if t == 'g':
                self.gserial += 1
                gid = e.get('id') or f'group_{self.gserial:05d}'
                p = E.SubElement(parent, f'{{{S}}}g', id=gid)
                panel = panel or gid
            for child in e:
                if isinstance(child.tag, str):
                    self.walk(child, p, m, st, clips, panel)
            if t == 'g' and not len(p):
                parent.remove(p)
        elif t == 'text':
            self.text(e, parent, m, st, clips, panel)
        elif t in GEOMETRY:
            self.draw_shape(e, parent, m, st, clips)
        else:
            fail(e, f'{t} cannot render directly in the artwork tree')

    def write(self, output_dir):
        self.walk(self.src, self.out, self.origin_matrix, DEFAULTS)
        output_dir = Path(output_dir)
        output_dir.mkdir(parents=True, exist_ok=True)
        E.ElementTree(self.out).write(str(output_dir / 'compatible.svg'), encoding='utf-8', xml_declaration=True)
        art = copy.deepcopy(self.out)
        for t in art.findall(f'.//{{{S}}}text'):
            t.getparent().remove(t)
        E.ElementTree(art).write(str(output_dir / 'artwork.svg'), encoding='utf-8', xml_declaration=True)
        (output_dir / 'texts.json').write_text(json.dumps(self.texts, ensure_ascii=False, indent=2))
        report = {'canvas': {'width': self.width, 'height': self.height}, 'stats': self.stats,
                  'objects': len(self.records), 'texts': len(self.texts), 'records': self.records,
                  'geometry_backend': 'Skia PathKit; vector boolean clipping and stroke outlining',
                  'text_model': 'explicit single-line runs; baseline_shift=baseline/sub/super; resolved run opacity'}
        (output_dir / 'normalization.json').write_text(json.dumps(report, ensure_ascii=False, indent=2))
        return {k: v for k, v in report.items() if k != 'records'}


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('source', type=Path, help='Explicit SVG diagram to normalize')
    parser.add_argument('--output-dir', type=Path, required=True)
    args = parser.parse_args()
    try:
        print(json.dumps(Normalizer(args.source).write(args.output_dir), ensure_ascii=False))
    except (ValueError, RuntimeError, OSError) as exc:
        parser.exit(2, f'Normalization refused: {exc}\n')


if __name__ == '__main__':
    main()
