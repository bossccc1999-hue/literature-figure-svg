"""SVG gradient -> native DrawingML fill, with no SVG or image objects.

Call ``apply_gradient(spPr, svg_gradient, bbox_local, transform, opacity,
                      bbox_target=actual_shape_bbox)``.
Both bboxes are (x, y, width, height); transform is SVG (a,b,c,d,e,f).
The local bbox MUST be measured before flattening the SVG transform and before
clipping. bbox_target is the exact bounding rectangle used by native a:xfrm.
If the geometry is already flattened, carry its original bbox and transform as
sidecar metadata. gradientTransform and element transforms are composed here.

Linear gradients are mapped by their affine scalar field (inverse transpose),
not just by rotating endpoint vectors. Stops outside the new bounding rectangle
are correctly trimmed and colors/alpha interpolated at the new endpoints.
Radial gradients use native circle path fills. Focus and opacity are retained.
SVG elliptical radius is approximated by an equal-area circular radius, with
stops resampled to native circle shading's half-diagonal extent. This avoids
tileRect, whose rendering differs across PowerPoint and LibreOffice versions.
Diagnostics identify that approximation; no geometry is changed.

DrawingML references (accessed 2026-09-27):
https://learn.microsoft.com/en-us/dotnet/api/documentformat.openxml.drawing.lineargradientfill.scaled
https://learn.microsoft.com/en-us/dotnet/api/documentformat.openxml.drawing.filltorectangle
https://learn.microsoft.com/en-us/dotnet/api/documentformat.openxml.drawing.tilerectangle
https://learn.microsoft.com/en-us/dotnet/api/documentformat.openxml.drawing.pathgradientfill
"""
from __future__ import annotations

import math
import re
from lxml import etree as ET

A = 'http://schemas.openxmlformats.org/drawingml/2006/main'
IDENTITY = (1., 0., 0., 1., 0., 0.)
NUM = r'[-+]?(?:\d*\.\d+|\d+\.?\d*)(?:[eE][-+]?\d+)?'


def _el(name, attrs=None, parent=None):
    result = ET.Element('{%s}%s' % (A, name), attrs or {})
    if parent is not None:
        # CT_ShapeProperties requires its fill before line/effect properties.
        if name in ('gradFill','solidFill','noFill'):
            for i,child in enumerate(parent):
                if ET.QName(child).namespace==A and ET.QName(child).localname in ('ln','effectLst','effectDag','scene3d','sp3d','extLst'):
                    parent.insert(i,result)
                    break
            else:
                parent.append(result)
        else:
            parent.append(result)
    return result


def _mul(m, n):
    a,b,c,d,e,f = m; g,h,i,j,k,l = n
    return (a*g+c*h, b*g+d*h, a*i+c*j, b*i+d*j,
            a*k+c*l+e, b*k+d*l+f)


def _point(m, p):
    a,b,c,d,e,f = m; x,y = p
    return (a*x+c*y+e, b*x+d*y+f)


def _transform(raw):
    m = IDENTITY
    for name, args in re.findall(r'([A-Za-z]+)\s*\(([^)]*)\)', raw or ''):
        v = [float(x) for x in re.findall(NUM, args)]
        if name == 'matrix' and len(v) == 6:
            n = tuple(v)
        elif name == 'translate' and len(v) in (1, 2):
            n = (1,0,0,1,v[0],v[1] if len(v)>1 else 0)
        elif name == 'scale' and len(v) in (1, 2):
            n = (v[0],0,0,v[1] if len(v)>1 else v[0],0,0)
        elif name == 'rotate' and len(v) in (1, 3):
            t = math.radians(v[0]); co,si = math.cos(t),math.sin(t)
            n = (co,si,-si,co,0,0)
            if len(v)==3:
                n = _mul((1,0,0,1,v[1],v[2]), _mul(n,(1,0,0,1,-v[1],-v[2])))
        elif name in ('skewX','skewY') and len(v)==1:
            t = math.tan(math.radians(v[0]))
            n = (1,0,t,1,0,0) if name=='skewX' else (1,t,0,1,0,0)
        else:
            raise ValueError('Unsupported gradient transform: '+name+'('+args+')')
        m = _mul(m,n)
    return m


def _fraction(value):
    text = str(value).strip()
    return float(text[:-1])/100 if text.endswith('%') else float(text)


def _rgb(value):
    value = value.strip().lower()
    names = {'black':'000000','white':'ffffff','red':'ff0000',
             'green':'008000','blue':'0000ff','transparent':'000000'}
    value = names.get(value,value)
    if value.startswith('#'):
        value = value[1:]
    if len(value)==3 and re.fullmatch('[0-9a-f]{3}',value):
        value = ''.join(x*2 for x in value)
    if re.fullmatch('[0-9a-f]{6}',value):
        return tuple(int(value[i:i+2],16) for i in (0,2,4))
    m = re.fullmatch(r'rgb\(\s*(\d+)\s*[, ]\s*(\d+)\s*[, ]\s*(\d+)\s*\)',value)
    if m:
        return tuple(max(0,min(255,int(x))) for x in m.groups())
    raise ValueError('Unsupported gradient stop color: '+value)


def read_stops(gradient, opacity=1.0):
    """Return SVG stops as (offset, RGB tuple, opacity), preserving duplicates."""
    result = []; previous = 0.
    for child in gradient:
        if ET.QName(child).localname != 'stop':
            continue
        attrs = dict(child.attrib)
        for item in child.get('style','').split(';'):
            if ':' in item:
                key,value = item.split(':',1); attrs[key.strip()] = value.strip()
        pos = max(previous,min(1.,max(0.,_fraction(attrs.get('offset','0')))))
        color = attrs.get('stop-color','#000000')
        alpha = _fraction(attrs.get('stop-opacity',1))*opacity
        if color == 'transparent':
            alpha = 0.
        result.append((pos,_rgb(color),max(0.,min(1.,alpha))))
        previous = pos
    if not result:
        raise ValueError('Gradient has no inline stops; resolve SVG href first')
    if result[0][0]>0:
        result.insert(0,(0.,result[0][1],result[0][2]))
    if result[-1][0]<1:
        result.append((1.,result[-1][1],result[-1][2]))
    return result


def _sample(stops, t):
    if t<=stops[0][0]:
        return stops[0][1:]
    if t>=stops[-1][0]:
        return stops[-1][1:]
    for left,right in zip(stops,stops[1:]):
        if left[0]<=t<right[0]:
            f = (t-left[0])/(right[0]-left[0])
            rgb = tuple(x+(y-x)*f for x,y in zip(left[1],right[1]))
            return (rgb,left[2]+(right[2]-left[2])*f)
    return stops[-1][1:]


def _write_stops(fill, stops):
    seq = _el('gsLst',parent=fill)
    for pos,rgb,alpha in stops:
        gs = _el('gs',{'pos':str(round(max(0,min(1,pos))*100000))},seq)
        color = _el('srgbClr',{'val':''.join(f'{max(0,min(255,round(c))):02X}' for c in rgb)},gs)
        if alpha<.999999:
            _el('alpha',{'val':str(round(max(0,min(1,alpha))*100000))},color)


def _bbox_corners(bbox):
    x,y,w,h = bbox
    return [(x,y),(x+w,y),(x,y+h),(x+w,y+h)]


def _target_bbox(bbox, transform):
    points = [_point(transform,p) for p in _bbox_corners(bbox)]
    x = min(p[0] for p in points); y = min(p[1] for p in points)
    return x,y,max(p[0] for p in points)-x,max(p[1] for p in points)-y


def _coordinate(gradient,name,default,axis,object_bbox,viewport):
    raw = gradient.get(name,str(default))
    val = _fraction(raw)
    if str(raw).strip().endswith('%') and not object_bbox:
        if viewport is None:
            raise ValueError('userSpaceOnUse percentage requires viewport=(x,y,w,h)')
        vx,vy,vw,vh = viewport
        if axis == 'x': val = vx+val*vw
        elif axis == 'y': val = vy+val*vh
        else: val = val*math.hypot(vw,vh)/math.sqrt(2)
    return val


def apply_gradient(props, gradient_element, bbox_local, transform=IDENTITY,
                   opacity=1.0, *, bbox_target=None, viewport=None,
                   diagnostics=None):
    """Append and return one a:gradFill (or degenerate solidFill).

    Existing fill nodes are removed. Geometry and line nodes remain unchanged.
    Gradient definition must already have href inheritance resolved. Source uses
    only spreadMethod=pad; unsupported reflect/repeat raises rather than silently
    misrepresenting its color pattern. Optional diagnostics receives dictionaries.
    """
    g = gradient_element
    kind = ET.QName(g).localname
    if kind not in ('linearGradient','radialGradient'):
        raise ValueError('Expected SVG linearGradient or radialGradient')
    if g.get('spreadMethod','pad') != 'pad':
        raise ValueError('Only SVG spreadMethod=pad is supported')
    for child in list(props):
        if ET.QName(child).namespace==A and ET.QName(child).localname in ('noFill','solidFill','gradFill','blipFill','pattFill','grpFill'):
            props.remove(child)
    stops = read_stops(g,opacity)
    object_bbox = g.get('gradientUnits','objectBoundingBox') == 'objectBoundingBox'
    x,y,w,h = bbox_local
    if object_bbox and (w<=0 or h<=0):
        return _el('noFill',parent=props)
    basis = (w,0,0,h,x,y) if object_bbox else IDENTITY
    matrix = _mul(transform,_mul(basis,_transform(g.get('gradientTransform'))))
    bbox_target = bbox_target or _target_bbox(bbox_local,transform)
    bx,by,bw,bh = bbox_target
    if bw<=0 or bh<=0:
        return _el('noFill',parent=props)
    get = lambda n,d,a: _coordinate(g,n,d,a,object_bbox,viewport)
    if kind=='linearGradient':
        p1 = (get('x1','0%','x'),get('y1','0%','y'))
        p2 = (get('x2','100%','x'),get('y2','0%','y'))
        dx,dy = p2[0]-p1[0],p2[1]-p1[1]
        length2 = dx*dx+dy*dy
        a,b,c,d,e,f = matrix; det = a*d-b*c
        if length2<1e-20 or abs(det)<1e-20:
            fill = _el('solidFill',parent=props)
            color = _el('srgbClr',{'val':''.join(f'{round(v):02X}' for v in stops[-1][1])},fill)
            if stops[-1][2]<1: _el('alpha',{'val':str(round(stops[-1][2]*100000))},color)
            return fill
        # SVG scalar field transforms as a covector: n = M^-T(v/|v|^2).
        nx = (d*dx-b*dy)/(det*length2)
        ny = (-c*dx+a*dy)/(det*length2)
        origin = _point(matrix,p1)
        ts = [nx*(px-origin[0])+ny*(py-origin[1]) for px,py in _bbox_corners(bbox_target)]
        lo,hi = min(ts),max(ts); span = hi-lo
        mapped = [(0.,*_sample(stops,lo))]
        mapped += [((pos-lo)/span,rgb,alpha) for pos,rgb,alpha in stops if lo<pos<hi]
        mapped.append((1.,*_sample(stops,hi)))
        fill = _el('gradFill',{'rotWithShape':'1','flip':'none'},props)
        _write_stops(fill,mapped)
        angle = math.degrees(math.atan2(ny,nx))%360
        _el('lin',{'ang':str(round(angle*60000)%21600000),'scaled':'0'},fill)
        return fill

    cx,cy = get('cx','50%','x'),get('cy','50%','y')
    fx,fy = get('fx',cx,'x'),get('fy',cy,'y')
    radius = get('r','50%','r')
    if radius<=0:
        raise ValueError('SVG radialGradient must have positive radius')
    center = _point(matrix,(cx,cy)); focus = _point(matrix,(fx,fy))
    a,b,c,d,_,_ = matrix
    rx = radius*math.hypot(a,c); ry = radius*math.hypot(b,d)
    effective_radius = radius*math.sqrt(abs(a*d-b*c))
    if effective_radius<1e-12:
        raise ValueError('Degenerate radial gradient transform')
    native_radius = math.hypot(bw,bh)/2
    radial_scale = native_radius/effective_radius
    circularity = math.hypot(a*a+c*c-b*b-d*d,2*(a*b+c*d))/max(1e-20,a*a+b*b+c*c+d*d)
    if diagnostics is not None and circularity>1e-5:
        diagnostics.append({'gradient':g.get('id'),'approximation':'elliptical radial shading represented by equal-area native circle','circularity_error':round(circularity,6)})
    if diagnostics is not None and (abs(fx-cx)>1e-8 or abs(fy-cy)>1e-8):
        diagnostics.append({'gradient':g.get('id'),'approximation':'SVG radial focal offset represented by DrawingML focus point'})
    # Verified with native PPTX -> bundled LibreOffice -> PDF rendering:
    # DrawingML circle stop 0 is the focus; stop 1 lies half a diagonal away.
    radial_stops = [(0.,*_sample(stops,0.))]
    radial_stops += [(pos/radial_scale,rgb,alpha) for pos,rgb,alpha in stops if 0<pos<radial_scale]
    radial_stops.append((1.,*_sample(stops,radial_scale)))
    fill = _el('gradFill',{'rotWithShape':'1','flip':'none'},props)
    _write_stops(fill,radial_stops)
    path = _el('path',{'path':'circle'},fill)
    _el('fillToRect',{
        'l':str(round((focus[0]-bx)/bw*100000)),
        't':str(round((focus[1]-by)/bh*100000)),
        'r':str(round((bx+bw-focus[0])/bw*100000)),
        'b':str(round((by+bh-focus[1])/bh*100000)),
    },path)
    return fill
