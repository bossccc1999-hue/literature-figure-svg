"""Low-level editable DrawingML path primitives for the controlled redraw pipeline.

The source deck must first be authored/exported with @oai/artifact-tool.
This module only post-processes its ZIP package. It never embeds raster images
or SVG picture objects. SVG C/Q commands remain native Bézier path commands.

Use build_native_pptx.py as the supported assembly CLI: it validates normalized
SVG input, integrates native_gradients.py, updates native text runs and assigns
tight identity group bounds. This low-level module is not an arbitrary SVG/PDF
decoder. Candidate PPTX files require the presentations skill finalizer and
rendered inspection before delivery.

Supported SVG: paths with M/L/H/V/C/S/Q/T/Z (absolute and relative), affine
transforms, inherited solid fill/stroke/opacity, and nested groups. Arc commands
fail explicitly rather than changing appearance. Existing PPTX text is retained.
"""

from __future__ import annotations

import argparse
import json
import math
import re
from pathlib import Path
from zipfile import ZipFile, ZIP_DEFLATED

from lxml import etree as ET


NS = {
    "p": "http://schemas.openxmlformats.org/presentationml/2006/main",
    "a": "http://schemas.openxmlformats.org/drawingml/2006/main",
}
EMU_PER_PX = 9525
PATH_SCALE = 1000
NUM = r"[-+]?(?:\d*\.\d+|\d+\.?\d*)(?:[eE][-+]?\d+)?"
TOKEN_RE = re.compile(r"[A-Za-z]|" + NUM)
IDENTITY = (1.0, 0.0, 0.0, 1.0, 0.0, 0.0)


def _el(name, attrs=None, parent=None):
    prefix, local = name.split(":")
    element = ET.Element(f"{{{NS[prefix]}}}{local}", attrs or {})
    if parent is not None:
        parent.append(element)
    return element


def _int(value):
    return str(round(value))


def multiply(m, n):
    """Affine composition m(n(point))."""
    a, b, c, d, e, f = m
    g, h, i, j, k, l = n
    return (a*g+c*h, b*g+d*h, a*i+c*j, b*i+d*j,
            a*k+c*l+e, b*k+d*l+f)


def transform_point(m, point):
    x, y = point
    a, b, c, d, e, f = m
    return (a*x+c*y+e, b*x+d*y+f)


def parse_transform(value):
    result = IDENTITY
    for name, raw in re.findall(r"([A-Za-z]+)\s*\(([^)]*)\)", value or ""):
        v = [float(x) for x in re.findall(NUM, raw)]
        if name == "matrix" and len(v) == 6:
            matrix = tuple(v)
        elif name == "translate" and len(v) in (1, 2):
            matrix = (1, 0, 0, 1, v[0], v[1] if len(v) == 2 else 0)
        elif name == "scale" and len(v) in (1, 2):
            matrix = (v[0], 0, 0, v[1] if len(v) == 2 else v[0], 0, 0)
        elif name == "rotate" and len(v) in (1, 3):
            rad = math.radians(v[0]); c = math.cos(rad); s = math.sin(rad)
            matrix = (c, s, -s, c, 0, 0)
            if len(v) == 3:
                matrix = multiply((1, 0, 0, 1, v[1], v[2]),
                                  multiply(matrix, (1, 0, 0, 1, -v[1], -v[2])))
        elif name in ("skewX", "skewY") and len(v) == 1:
            t = math.tan(math.radians(v[0]))
            matrix = (1, 0, t, 1, 0, 0) if name == "skewX" else (1, t, 0, 1, 0, 0)
        else:
            raise ValueError(f"Unsupported SVG transform: {name}({raw})")
        result = multiply(result, matrix)
    return result


def parse_path(d):
    """Yield (M/L/C/Q/Z, points), resolving relative and smooth commands."""
    tokens = TOKEN_RE.findall(d)
    i = 0
    command = None
    current = (0.0, 0.0)
    start = current
    last_c = last_q = None
    arity = {"M": 2, "L": 2, "H": 1, "V": 1, "C": 6, "S": 4, "Q": 4, "T": 2}
    while i < len(tokens):
        if tokens[i].isalpha():
            command = tokens[i]
            i += 1
            if command.upper() == "Z":
                yield "Z", []
                current = start
                last_c = last_q = None
                command = None
                continue
        if not command or command.upper() not in arity:
            raise ValueError(f"Unsupported or malformed SVG path command {command!r}")
        upper = command.upper()
        count = arity[upper]
        if i + count > len(tokens) or any(x.isalpha() for x in tokens[i:i+count]):
            raise ValueError(f"Missing coordinates for SVG path command {command}")
        values = [float(x) for x in tokens[i:i+count]]
        i += count
        relative = command.islower()
        def point(x, y):
            return (x+current[0], y+current[1]) if relative else (x, y)
        if upper == "H":
            points = [(values[0]+current[0] if relative else values[0], current[1])]
            out = "L"
        elif upper == "V":
            points = [(current[0], values[0]+current[1] if relative else values[0])]
            out = "L"
        else:
            points = [point(values[j], values[j+1]) for j in range(0, count, 2)]
            out = upper
        if upper == "S":
            reflected = (2*current[0]-last_c[0], 2*current[1]-last_c[1]) if last_c else current
            points.insert(0, reflected)
            out = "C"
        elif upper == "T":
            reflected = (2*current[0]-last_q[0], 2*current[1]-last_q[1]) if last_q else current
            points.insert(0, reflected)
            out = "Q"
        last_c = points[-2] if out == "C" else None
        last_q = points[-2] if out == "Q" else None
        current = points[-1]
        if upper == "M":
            start = current
            command = "l" if relative else "L"
        yield out, points


def _color(value):
    if value is None or value == "none":
        return None
    value = value.strip()
    if value.startswith("#"):
        v = value[1:]
        if len(v) == 3:
            v = "".join(x*2 for x in v)
        if len(v) != 6:
            raise ValueError(f"Unsupported SVG color {value}")
        return v.upper()
    rgb = re.fullmatch(r"rgb\(\s*(\d+)\s*[, ]\s*(\d+)\s*[, ]\s*(\d+)\s*\)", value)
    if rgb:
        return "".join(f"{int(x):02X}" for x in rgb.groups())
    names = {"black": "000000", "white": "FFFFFF", "red": "FF0000",
             "green": "008000", "blue": "0000FF", "transparent": None}
    if value.lower() in names:
        return names[value.lower()]
    raise ValueError(f"Unsupported SVG color {value}; convert gradients to solid paths first")


def _fill(parent, color, opacity=1.0):
    if color is None:
        return _el("a:noFill", parent=parent)
    fill = _el("a:solidFill", parent=parent)
    rgb = _el("a:srgbClr", {"val": color}, fill)
    if opacity < 1:
        _el("a:alpha", {"val": _int(max(0, opacity)*100000)}, rgb)
    return fill


def _style(element, inherited):
    result = dict(inherited)
    attrs = dict(element.attrib)
    for item in element.get("style", "").split(";"):
        if ":" in item:
            k, v = item.split(":", 1)
            attrs[k.strip()] = v.strip()
    for key in ("fill", "stroke", "stroke-width", "fill-opacity", "stroke-opacity", "fill-rule"):
        if key in attrs:
            result[key] = attrs[key]
    result["_opacity"] = float(inherited.get("_opacity", 1)) * float(attrs.get("opacity", 1))
    result["_hidden"] = inherited.get("_hidden", False) or attrs.get("display") == "none" or attrs.get("visibility") == "hidden"
    return result


class SvgShapeBuilder:
    def __init__(self, first_id, viewbox, canvas_emu, bounds_px=None, preserve_groups=True):
        self.next_id = first_id
        self.viewbox = viewbox
        self.canvas_emu = canvas_emu
        self.preserve_groups = preserve_groups
        self.count = 0
        vx, vy, vw, vh = viewbox
        if bounds_px is None:
            x = y = 0
            w, h = canvas_emu
        else:
            x, y, w, h = [v * EMU_PER_PX for v in bounds_px]
        self.to_emu = (w/vw, 0, 0, h/vh, x-vx*w/vw, y-vy*h/vh)

    def new_id(self):
        value = self.next_id
        self.next_id += 1
        return value

    def group(self, name, children):
        group = _el("p:grpSp")
        nv = _el("p:nvGrpSpPr", parent=group)
        _el("p:cNvPr", {"id": str(self.new_id()), "name": name}, nv)
        _el("p:cNvGrpSpPr", parent=nv)
        _el("p:nvPr", parent=nv)
        props = _el("p:grpSpPr", parent=group)
        xfrm = _el("a:xfrm", parent=props)
        w, h = self.canvas_emu
        for tag, attrs in (("a:off", {"x": "0", "y": "0"}),
                           ("a:ext", {"cx": str(w), "cy": str(h)}),
                           ("a:chOff", {"x": "0", "y": "0"}),
                           ("a:chExt", {"cx": str(w), "cy": str(h)})):
            _el(tag, attrs, xfrm)
        group.extend(children)
        return group

    def path(self, element, transform, style):
        # Coordinates are normalized only after applying every SVG transform.
        commands = [(cmd, [transform_point(transform, p) for p in points])
                    for cmd, points in parse_path(element.get("d", ""))]
        points = [p for _, pts in commands for p in pts]
        if not points:
            return None
        min_x = min(x for x, _ in points); min_y = min(y for _, y in points)
        max_x = max(x for x, _ in points); max_y = max(y for _, y in points)
        width = max(max_x-min_x, 0.001); height = max(max_y-min_y, 0.001)
        ident = self.new_id()
        shape = _el("p:sp")
        nv = _el("p:nvSpPr", parent=shape)
        _el("p:cNvPr", {"id": str(ident), "name": element.get("id", f"Vector path {self.count+1}")}, nv)
        _el("p:cNvSpPr", parent=nv)
        _el("p:nvPr", parent=nv)
        props = _el("p:spPr", parent=shape)
        xfrm = _el("a:xfrm", parent=props)
        top_left = transform_point(self.to_emu, (min_x, min_y))
        _el("a:off", {"x": _int(top_left[0]), "y": _int(top_left[1])}, xfrm)
        _el("a:ext", {"cx": _int(width*self.to_emu[0]), "cy": _int(height*self.to_emu[3])}, xfrm)
        geom = _el("a:custGeom", parent=props)
        for tag in ("a:avLst", "a:gdLst", "a:ahLst", "a:cxnLst"):
            _el(tag, parent=geom)
        _el("a:rect", {"l": "0", "t": "0", "r": "r", "b": "b"}, geom)
        path_list = _el("a:pathLst", parent=geom)
        native_path = _el("a:path", {"w": _int(width*PATH_SCALE), "h": _int(height*PATH_SCALE),
                                     "fill": "norm", "stroke": "1", "extrusionOk": "0"}, path_list)
        tags = {"M": "a:moveTo", "L": "a:lnTo", "C": "a:cubicBezTo", "Q": "a:quadBezTo", "Z": "a:close"}
        for command, pts in commands:
            node = _el(tags[command], parent=native_path)
            for x, y in pts:
                _el("a:pt", {"x": _int((x-min_x)*PATH_SCALE), "y": _int((y-min_y)*PATH_SCALE)}, node)
        opacity = style.get("_opacity", 1)
        _fill(props, _color(style.get("fill", "black")), opacity*float(style.get("fill-opacity", 1)))
        # Geometric scaling approximates width if an SVG uses non-uniform scaling.
        a, b, c, d, _, _ = transform
        geometric_scale = math.sqrt(abs(a*d-b*c))
        stroke_width = float(style.get("stroke-width", 1)) * geometric_scale * math.sqrt(abs(self.to_emu[0]*self.to_emu[3]))
        line = _el("a:ln", {"w": _int(stroke_width)}, props)
        _fill(line, _color(style.get("stroke", "none")), opacity*float(style.get("stroke-opacity", 1)))
        self.count += 1
        return shape

    def visit(self, element, transform=IDENTITY, inherited=None):
        style = _style(element, inherited or {})
        if style["_hidden"]:
            return []
        transform = multiply(transform, parse_transform(element.get("transform")))
        tag = ET.QName(element).localname
        if tag == "path":
            shape = self.path(element, transform, style)
            return [shape] if shape is not None else []
        if tag in ("svg", "g"):
            children = []
            for child in element:
                children.extend(self.visit(child, transform, style))
            if tag == "g" and self.preserve_groups and children:
                label = element.get("{http://www.inkscape.org/namespaces/inkscape}label") or element.get("id", "Vector group")
                return [self.group(label, children)]
            return children
        if tag in ("metadata", "defs", "title", "desc"):
            return []
        raise ValueError(f"SVG element <{tag}> needs conversion to path before PPTX insertion")


def svg_viewbox(root):
    if root.get("viewBox"):
        viewbox = tuple(float(v) for v in re.findall(NUM, root.get("viewBox")))
        if len(viewbox) != 4 or viewbox[2] <= 0 or viewbox[3] <= 0:
            raise ValueError("Invalid SVG viewBox")
        return viewbox
    width = float(re.match(NUM, root.get("width", "0"))[0])
    height = float(re.match(NUM, root.get("height", "0"))[0])
    if width <= 0 or height <= 0:
        raise ValueError("SVG requires a positive viewBox or width/height")
    return (0, 0, width, height)


def inject_svg_into_pptx(base_pptx, svg_path, output_pptx, *, slide_number=1,
                         behind_existing=True, preserve_groups=True,
                         outer_group="Editable vector artwork", bounds_px=None):
    """Add native paths to one existing slide, retaining text and package parts.

    bounds_px optionally specifies (left, top, width, height) at 96 DPI in deck
    coordinates. By default, the SVG viewBox fills the entire slide. Behind=True
    inserts vector artwork behind text already authored with artifact-tool.
    """
    svg_root = ET.parse(str(svg_path)).getroot()
    with ZipFile(base_pptx) as archive:
        presentation = ET.fromstring(archive.read("ppt/presentation.xml"))
        size = presentation.find("p:sldSz", NS)
        canvas = (int(size.get("cx")), int(size.get("cy")))
        slide_path = f"ppt/slides/slide{slide_number}.xml"
        slide = ET.fromstring(archive.read(slide_path))
        tree = slide.find("p:cSld/p:spTree", NS)
        first_id = max([int(e.get("id")) for e in slide.findall(".//p:cNvPr", NS)] or [1])+1
        builder = SvgShapeBuilder(first_id, svg_viewbox(svg_root), canvas, bounds_px, preserve_groups)
        shapes = builder.visit(svg_root)
        if outer_group and shapes:
            shapes = [builder.group(outer_group, shapes)]
        if behind_existing:
            # Required nvGrpSpPr and grpSpPr are the first two children.
            for index, shape in enumerate(shapes, start=2):
                tree.insert(index, shape)
        else:
            tree.extend(shapes)
        # Hoist shared namespace prefixes instead of redeclaring them on every
        # freeform property. This preserves geometry and makes large figures
        # considerably smaller in the uncompressed Office package.
        compact = ET.Element(slide.tag, slide.attrib, nsmap={**slide.nsmap, **NS})
        compact.extend(list(slide))
        ET.cleanup_namespaces(compact, top_nsmap=NS)
        xml = ET.tostring(compact, xml_declaration=True, encoding="UTF-8", standalone=True)
        output_pptx = Path(output_pptx)
        output_pptx.parent.mkdir(parents=True, exist_ok=True)
        if Path(base_pptx).resolve() == output_pptx.resolve():
            raise ValueError("Use a distinct output file; never overwrite the base deck")
        with ZipFile(output_pptx, "w", compression=ZIP_DEFLATED) as output:
            for item in archive.infolist():
                output.writestr(item, xml if item.filename == slide_path else archive.read(item.filename))
    return {"paths_inserted": builder.count, "output": str(output_pptx), **inspect_editability(output_pptx)}


def inspect_editability(pptx):
    counts = {"slides": 0, "native_freeforms": 0, "editable_text_runs": 0,
              "cubic_segments": 0, "quadratic_segments": 0, "picture_objects": 0}
    with ZipFile(pptx) as archive:
        for name in archive.namelist():
            if re.fullmatch(r"ppt/slides/slide\d+\.xml", name):
                root = ET.fromstring(archive.read(name))
                counts["slides"] += 1
                for key, xpath in (("native_freeforms", ".//a:custGeom"),
                                   ("editable_text_runs", ".//a:t"),
                                   ("cubic_segments", ".//a:cubicBezTo"),
                                   ("quadratic_segments", ".//a:quadBezTo"),
                                   ("picture_objects", ".//p:pic")):
                    counts[key] += len(root.findall(xpath, NS))
    return counts


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("base_pptx")
    parser.add_argument("svg")
    parser.add_argument("output_pptx")
    parser.add_argument("--slide", type=int, default=1)
    parser.add_argument("--front", action="store_true", help="Place paths in front of existing shapes")
    parser.add_argument("--ungrouped", action="store_true")
    args = parser.parse_args()
    print(json.dumps(inject_svg_into_pptx(args.base_pptx, args.svg, args.output_pptx,
                      slide_number=args.slide, behind_existing=not args.front,
                      preserve_groups=not args.ungrouped,
                      outer_group=None if args.ungrouped else "Editable vector artwork"), indent=2))
