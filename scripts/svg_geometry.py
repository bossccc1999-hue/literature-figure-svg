"""Pure SVG geometry normalization for editable PowerPoint freeforms.

Only standard-library modules are required. Geometry is returned in the source
element's local coordinate system; callers remain responsible for transforms,
style inheritance, clipping and paint. Cubic arc segments are at most 45 degrees
(maximum radial error about 4.3e-6 of radius before affine transformations).
"""

from __future__ import annotations

import math
import re

_NUMBER = re.compile(r"[-+]?(?:\d*\.\d+|\d+\.?\d*)(?:[eE][-+]?\d+)?")
_COMMANDS = set("MmLlHhVvCcSsQqTtAaZz")


def _fmt(value):
    value = float(value)
    if not math.isfinite(value):
        raise ValueError("Nonfinite SVG coordinate")
    if abs(value) < 0.5e-9:
        return "0"
    return f"{value:.9f}".rstrip("0").rstrip(".")


def _emit(command, *points):
    return command + " ".join(_fmt(v) for point in points for v in point)


def _arc_cubics(start, rx, ry, rotation, large, sweep, end):
    """Endpoint-to-center SVG arc conversion, per SVG 1.1 implementation notes."""
    if start == end:
        return []  # SVG: coincident endpoints omit the arc altogether.
    rx, ry = abs(rx), abs(ry)
    if not rx or not ry:
        return [("L", (end,))]
    phi = math.radians(rotation % 360)
    cp, sp = math.cos(phi), math.sin(phi)
    dx, dy = (start[0] - end[0]) / 2, (start[1] - end[1]) / 2
    xp, yp = cp * dx + sp * dy, -sp * dx + cp * dy
    lam = (xp / rx) ** 2 + (yp / ry) ** 2
    if lam > 1:
        rx, ry = rx * math.sqrt(lam), ry * math.sqrt(lam)
    numerator = rx * rx * ry * ry - rx * rx * yp * yp - ry * ry * xp * xp
    denominator = rx * rx * yp * yp + ry * ry * xp * xp
    factor = math.sqrt(max(0.0, numerator / denominator))
    if bool(large) == bool(sweep):
        factor = -factor
    cxp, cyp = factor * rx * yp / ry, -factor * ry * xp / rx
    cx = cp * cxp - sp * cyp + (start[0] + end[0]) / 2
    cy = sp * cxp + cp * cyp + (start[1] + end[1]) / 2
    ux, uy = (xp - cxp) / rx, (yp - cyp) / ry
    vx, vy = (-xp - cxp) / rx, (-yp - cyp) / ry
    theta = math.atan2(uy, ux)
    delta = math.atan2(ux * vy - uy * vx, ux * vx + uy * vy)
    if not sweep and delta > 0:
        delta -= 2 * math.pi
    elif sweep and delta < 0:
        delta += 2 * math.pi
    count = max(1, int(math.ceil(abs(delta) / (math.pi / 4))))
    step = delta / count

    def point(angle):
        ca, sa = math.cos(angle), math.sin(angle)
        return cx + cp * rx * ca - sp * ry * sa, cy + sp * rx * ca + cp * ry * sa

    def derivative(angle):
        ca, sa = math.cos(angle), math.sin(angle)
        return -cp * rx * sa - sp * ry * ca, -sp * rx * sa + cp * ry * ca

    result = []
    for index in range(count):
        a, b = theta + index * step, theta + (index + 1) * step
        alpha = 4 / 3 * math.tan((b - a) / 4)
        p0, p3 = point(a), point(b)
        d0, d3 = derivative(a), derivative(b)
        p1 = p0[0] + alpha * d0[0], p0[1] + alpha * d0[1]
        p2 = p3[0] - alpha * d3[0], p3[1] - alpha * d3[1]
        result.append(("C", (p1, p2, end if index == count - 1 else p3)))
    return result


def arcs_to_cubics(d: str) -> str:
    """Normalize any SVG path to absolute M/L/C/Q/Z, replacing A/a with C.

    Handles repeated commands, relative coordinates, smooth shorthand and arc
    flag tokens without intervening spaces. Invalid paths fail explicitly.
    """
    position = 0
    length = len(d)
    current = (0.0, 0.0)
    start = current
    command = None
    previous = None
    cubic_control = quadratic_control = None
    output = []

    def skip():
        nonlocal position
        while position < length and d[position] in " \t\r\n,":
            position += 1

    def number(flag=False):
        nonlocal position
        skip()
        if flag:
            if position >= length or d[position] not in "01":
                raise ValueError(f"Expected arc flag at character {position}")
            result = int(d[position])
            position += 1
            return result
        match = _NUMBER.match(d, position)
        if not match:
            raise ValueError(f"Expected SVG number at character {position}")
        position = match.end()
        return float(match.group())

    while True:
        skip()
        if position == length:
            break
        if d[position] in _COMMANDS:
            command = d[position]
            position += 1
        elif command is None:
            raise ValueError(f"Expected SVG command at character {position}")
        upper = command.upper()
        relative = command.islower()

        def pair():
            x, y = number(), number()
            return (x + current[0], y + current[1]) if relative else (x, y)

        points = ()
        out = upper
        if upper == "Z":
            output.append("Z")
            current = start
            cubic_control = quadratic_control = None
            previous = "Z"
            command = None
            continue
        if upper in ("M", "L", "T"):
            points = (pair(),)
            if upper == "T":
                q = (2 * current[0] - quadratic_control[0], 2 * current[1] - quadratic_control[1]) if previous in ("Q", "T") else current
                points, out = (q, points[0]), "Q"
        elif upper == "H":
            x = number()
            points, out = (((x + current[0]) if relative else x, current[1]),), "L"
        elif upper == "V":
            y = number()
            points, out = ((current[0], (y + current[1]) if relative else y),), "L"
        elif upper == "C":
            points = pair(), pair(), pair()
        elif upper == "S":
            c = (2 * current[0] - cubic_control[0], 2 * current[1] - cubic_control[1]) if previous in ("C", "S") else current
            points, out = (c, pair(), pair()), "C"
        elif upper == "Q":
            points = pair(), pair()
        elif upper == "A":
            rx, ry, rotation = number(), number(), number()
            large, sweep = number(flag=True), number(flag=True)
            end = pair()
            for arc_command, arc_points in _arc_cubics(current, rx, ry, rotation, large, sweep, end):
                output.append(_emit(arc_command, *arc_points))
            current = end
            cubic_control = quadratic_control = None
            previous = upper
            continue
        else:
            raise ValueError(f"Unsupported SVG command {command}")
        output.append(_emit(out, *points))
        current = points[-1]
        cubic_control = points[-2] if out == "C" else None
        quadratic_control = points[-2] if out == "Q" else None
        if upper == "M":
            start = current
            command = "l" if relative else "L"
        previous = upper
    return " ".join(output)


def primitive_to_path(element) -> str:
    """Return normalized local M/L/C/Q/Z geometry for a DOM/XML primitive.

    Supported: path, rect (including rounded corners), circle, ellipse, line,
    polygon and polyline. Returns an empty string for zero-area closed shapes.
    Requires numeric user-unit attributes; percentages and CSS geometry should
    be resolved by the caller before invoking this function.
    """
    tag = element.tag.rsplit("}", 1)[-1]

    def get(name, default=0):
        return float(element.get(name, default))

    if tag == "path":
        return arcs_to_cubics(element.get("d", ""))
    if tag == "line":
        return _emit("M", (get("x1"), get("y1"))) + " " + _emit("L", (get("x2"), get("y2")))
    if tag in ("polygon", "polyline"):
        nums = [float(n.group()) for n in _NUMBER.finditer(element.get("points", ""))]
        if len(nums) % 2:
            raise ValueError("Odd number of polygon/polyline coordinates")
        if not nums:
            return ""
        pairs = list(zip(nums[::2], nums[1::2]))
        return " ".join([_emit("M", pairs[0])] + [_emit("L", p) for p in pairs[1:]] + (["Z"] if tag == "polygon" else []))
    if tag in ("circle", "ellipse"):
        cx, cy = get("cx"), get("cy")
        rx = get("r") if tag == "circle" else get("rx")
        ry = rx if tag == "circle" else get("ry")
        if rx <= 0 or ry <= 0:
            return ""
        d = f"M {_fmt(cx + rx)} {_fmt(cy)} A {_fmt(rx)} {_fmt(ry)} 0 0 1 {_fmt(cx-rx)} {_fmt(cy)} A {_fmt(rx)} {_fmt(ry)} 0 0 1 {_fmt(cx+rx)} {_fmt(cy)} Z"
        return arcs_to_cubics(d)
    if tag == "rect":
        x, y, w, h = get("x"), get("y"), get("width"), get("height")
        if w <= 0 or h <= 0:
            return ""
        rx = get("rx", element.get("ry", 0))
        ry = get("ry", element.get("rx", 0))
        rx, ry = min(max(0, rx), w / 2), min(max(0, ry), h / 2)
        if not rx or not ry:
            return " ".join((_emit("M", (x, y)), _emit("L", (x+w, y)), _emit("L", (x+w, y+h)), _emit("L", (x, y+h)), "Z"))
        f = _fmt
        d = f"M {f(x+rx)} {f(y)} L {f(x+w-rx)} {f(y)} A {f(rx)} {f(ry)} 0 0 1 {f(x+w)} {f(y+ry)} L {f(x+w)} {f(y+h-ry)} A {f(rx)} {f(ry)} 0 0 1 {f(x+w-rx)} {f(y+h)} L {f(x+rx)} {f(y+h)} A {f(rx)} {f(ry)} 0 0 1 {f(x)} {f(y+h-ry)} L {f(x)} {f(y+ry)} A {f(rx)} {f(ry)} 0 0 1 {f(x+rx)} {f(y)} Z"
        return arcs_to_cubics(d)
    raise ValueError(f"Unsupported SVG geometry element {tag}")
