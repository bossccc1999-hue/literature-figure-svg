#!/usr/bin/env python3
"""Assemble a candidate native PPTX from a controlled, normalized SVG redraw.

This is NOT an arbitrary SVG/PDF decoder. Input artwork must contain only global
filled paths and semantic groups, plus resolved userSpaceOnUse gradients. Bake
strokes, clipping, rounded corners, markers and transforms with the normalizer
first. Unsupported constructs fail explicitly. The text base must have been
exported by @oai/artifact-tool, with one single-line textbox per texts.json id.

Example:
  python build_native_pptx.py --svg artwork.svg --texts texts.json \
    --base base.pptx --output candidate.pptx --report native_report.json

Candidate output still requires the presentations skill finalizer, package/font
checks, render inspection and a native ungrouping appearance check before delivery.
"""
from __future__ import annotations
import argparse
import json
import math
import re
from pathlib import Path
from zipfile import ZipFile, ZIP_DEFLATED
from lxml import etree as ET
from pptx_paths import (SvgShapeBuilder, NS, svg_viewbox, parse_path, IDENTITY,
                        inspect_editability, _style, _el, _fill, _color)
from native_gradients import apply_gradient

SVG_NS='http://www.w3.org/2000/svg'
PAINT=re.compile(r'url\(#([^)]*)\)')

def fail(message):
    raise ValueError(message)

def check_normalized(root):
    """Reject effects that the native writer cannot reproduce faithfully."""
    if ET.QName(root).localname!='svg':fail('Expected SVG root.')
    gradients={};ids=set()
    allowed={'svg','g','path','defs','linearGradient','radialGradient','stop','title','desc','metadata'}
    for e in root.iter():
        if not isinstance(e.tag,str):continue
        tag=ET.QName(e).localname
        if tag not in allowed:fail(f'<{tag}> is not normalized; convert it explicitly before assembly.')
        eid=e.get('id')
        if eid:
            if eid in ids:fail('Duplicate SVG id: '+eid)
            ids.add(eid)
        attrs=dict(e.attrib)
        for term in e.get('style','').split(';'):
            if ':' in term:
                k,v=term.split(':',1);attrs[k.strip()]=v.strip()
        if tag in ('svg','g','path'):
            if 'class' in attrs:fail(f'{eid or tag}: resolve CSS classes into explicit presentation attributes first.')
            if tag in ('svg','g') and float(attrs.get('opacity',1))!=1:fail(f'{eid or tag}: group opacity is a compositing operation; resolve it explicitly during redraw.')
            for k in ('clip-path','mask','filter','marker-start','marker-mid','marker-end','transform','vector-effect','stroke-dasharray','stroke-dashoffset'):
                if k in attrs and attrs[k] not in ('none',''):fail(f'{eid or tag}: unbaked {k}.')
            if attrs.get('stroke','none') not in ('none','transparent'):fail(f'{eid or tag}: stroke must be baked to a filled path.')
            if attrs.get('fill-rule','nonzero')!='nonzero':fail(f'{eid or tag}: resolve evenodd fills to nonzero contours first.')
            if attrs.get('display')=='none' or attrs.get('visibility')=='hidden':fail('Remove hidden elements during normalization.')
            for term in e.get('style','').split(';'):
                if ':' in term and term.split(':',1)[0].strip() not in ('fill','fill-opacity','opacity','stroke','fill-rule'):
                    fail(f'{eid or tag}: unsupported style property {term.split(":",1)[0]}.')
        if tag in ('linearGradient','radialGradient'):
            if not eid:fail('Gradient ids are required.')
            if e.get('gradientUnits')!='userSpaceOnUse':fail(eid+': normalize gradient coordinates to userSpaceOnUse first.')
            if any(ET.QName(k).localname=='href' for k in e.attrib):fail(eid+': resolve inherited gradient href first.')
            if e.get('spreadMethod','pad')!='pad':fail(eid+': only pad gradient spread is supported.')
            gradients[eid]=e
        if tag=='path':
            if not e.get('d'):fail(f'{eid or tag}: empty geometry.')
            list(parse_path(e.get('d')))
    for e in root.iter():
        if isinstance(e.tag,str) and ET.QName(e).localname in ('svg','g','path'):
            paint=_style(e,{}).get('fill','black')
            m=PAINT.fullmatch(paint)
            if m and m.group(1) not in gradients:fail('Unresolved gradient '+m.group(1))
            if paint.startswith('url(') and not m:fail('Only local gradient paint references are supported.')
    return gradients

def read_texts(path):
    items=json.loads(Path(path).read_text())
    if not isinstance(items,list):fail('texts.json must contain an array.')
    result={}
    for t in items:
        if not isinstance(t,dict) or not isinstance(t.get('id'),str) or not t['id'] or t['id'] in result:fail('Text ids must be nonempty and unique.')
        ident=t['id']
        if not isinstance(t.get('text'),str) or re.search(r'[\r\n]',t['text']):fail(ident+': only single-line text is supported.')
        for k in ('x','baseline','font_size'):
            if not isinstance(t.get(k),(int,float)) or not math.isfinite(t[k]):fail(ident+': invalid '+k)
        if t['font_size']<=0:fail(ident+': font_size must be positive.')
        if t.get('text_anchor','start') not in ('start','middle','end'):fail(ident+': unsupported text anchor.')
        runs=t.get('runs') or [{**t,'baseline_shift':'baseline'}]
        if not isinstance(runs,list) or ''.join(r.get('text','') for r in runs)!=t['text']:fail(ident+': runs must concatenate to text.')
        for run in runs:
            if any(k in run for k in ('dx','dy','rotate')) or ('runs' in t and any(k in run for k in ('x','y'))):fail(ident+': positioned or rotated runs are unsupported.')
            if run.get('baseline_shift','baseline') not in ('baseline','sub','super'):fail(ident+': unsupported baseline_shift.')
            size=run.get('font_size',t['font_size'])
            if not isinstance(size,(int,float)) or not math.isfinite(size) or size<=0:fail(ident+': invalid run font_size.')
            opacity=run.get('opacity',t.get('opacity',1))
            if not isinstance(opacity,(int,float)) or not 0<=opacity<=1:fail(ident+': opacity must be in [0,1].')
        t['_runs']=runs;result[ident]=t
    return result

def set_native_runs(shape,text):
    """Preserve artifact-authored textbox layout; set explicit native runs."""
    body=shape.find('p:txBody',NS)
    if body is None:fail(text['id']+': base shape is not a native textbox.')
    paragraphs=body.findall('a:p',NS)
    if len(paragraphs)!=1:fail(text['id']+': expected a single-line paragraph in base.')
    p=paragraphs[0]
    existing=''.join(node.text or '' for node in p.findall('.//a:t',NS))
    if existing!=text['text']:fail(text['id']+': base text differs from texts.json; regenerate base.')
    for child in list(p):
        if ET.QName(child).localname!='pPr':p.remove(child)
    ppr=p.find('a:pPr',NS)
    if ppr is None:ppr=_el('a:pPr');p.insert(0,ppr)
    ppr.set('algn',{'start':'l','middle':'ctr','end':'r'}[text.get('text_anchor','start')])
    for item in text['_runs']:
        run=_el('a:r',parent=p);size=item.get('font_size',text['font_size'])
        pr=_el('a:rPr',{'lang':'en-US','sz':str(round(size*75)),
             'b':'1' if item.get('bold',text.get('bold',False)) else '0',
             'baseline':str({'baseline':0,'sub':-25000,'super':35000}[item.get('baseline_shift','baseline')])},run)
        _fill(pr,_color(item.get('color',text['color'])),item.get('opacity',text.get('opacity',1)))
        for tag in ('a:latin','a:ea','a:cs'):_el(tag,{'typeface':item.get('font_family',text['font_family'])},pr)
        val=_el('a:t',parent=run);val.text=item['text']
        if item['text']!=item['text'].strip():val.set('{http://www.w3.org/XML/1998/namespace}space','preserve')
    bodypr=body.find('a:bodyPr',NS)
    if bodypr is not None:
        for child in list(bodypr):
            if ET.QName(child).localname in ('normAutofit','spAutoFit','noAutofit'):bodypr.remove(child)
        _el('a:noAutofit',parent=bodypr)

def tighten(group):
    """Tight editing rectangles with identity mapping: off==chOff, ext==chExt."""
    boxes=[]
    for child in group:
        tag=ET.QName(child).localname
        if tag=='grpSp':boxes.append(tighten(child))
        elif tag=='sp':
            xf=child.find('p:spPr/a:xfrm',NS)
            if xf is None or any(k in xf.attrib for k in ('rot','flipH','flipV')):fail('Base shapes must have unrotated explicit transforms.')
            off=xf.find('a:off',NS);ext=xf.find('a:ext',NS)
            boxes.append((int(off.get('x')),int(off.get('y')),int(ext.get('cx')),int(ext.get('cy'))))
    if not boxes:fail('Unexpected empty native group.')
    x=min(b[0] for b in boxes);y=min(b[1] for b in boxes)
    w=max(1,max(b[0]+b[2] for b in boxes)-x);h=max(1,max(b[1]+b[3] for b in boxes)-y)
    xf=group.find('p:grpSpPr/a:xfrm',NS)
    for tag in ('off','chOff'):xf.find('a:'+tag,NS).attrib.update({'x':str(x),'y':str(y)})
    for tag in ('ext','chExt'):xf.find('a:'+tag,NS).attrib.update({'cx':str(w),'cy':str(h)})
    return x,y,w,h

def build(svg_path,texts_path,base_path,output_path):
    parser=ET.XMLParser(resolve_entities=False,no_network=True)
    root=ET.parse(str(svg_path),parser).getroot()
    gradients=check_normalized(root);viewbox=svg_viewbox(root);textmap=read_texts(texts_path);diags=[]
    class NativeBuilder(SvgShapeBuilder):
        def path(self,el,transform,style):
            fill=style.get('fill','black');m=PAINT.fullmatch(fill)
            if not m:return super().path(el,transform,style)
            shape=super().path(el,transform,{**style,'fill':'#000000'})
            if shape is None:fail('Empty gradient path: '+el.get('id',''))
            pts=[p for _,ps in parse_path(el.get('d')) for p in ps]
            x=min(p[0] for p in pts);y=min(p[1] for p in pts)
            bbox=(x,y,max(max(p[0] for p in pts)-x,.001),max(max(p[1] for p in pts)-y,.001))
            apply_gradient(shape.find('p:spPr',NS),gradients[m.group(1)],bbox,IDENTITY,
                 style.get('_opacity',1)*float(style.get('fill-opacity',1)),bbox_target=bbox,viewport=viewbox,diagnostics=diags)
            return shape
    output_path=Path(output_path);base_path=Path(base_path)
    if output_path.resolve()==base_path.resolve():fail('Output must differ from the artifact-tool base deck.')
    with ZipFile(base_path) as z:
        slide_names=[n for n in z.namelist() if re.fullmatch(r'ppt/slides/slide\d+\.xml',n)]
        if slide_names!=['ppt/slides/slide1.xml']:fail('This controlled writer expects a single-slide text base.')
        pres=ET.fromstring(z.read('ppt/presentation.xml'),parser);sz=pres.find('p:sldSz',NS)
        canvas=tuple(int(sz.get(x)) for x in ('cx','cy'))
        expected=tuple(round(x*9525) for x in viewbox[2:])
        if canvas!=expected:fail(f'Base canvas {canvas} does not match SVG {expected}; regenerate the base.')
        slide=ET.fromstring(z.read(slide_names[0]),parser);tree=slide.find('p:cSld/p:spTree',NS)
        seen=set()
        for shape in list(tree)[2:]:
            if ET.QName(shape).localname!='sp':fail('Base must contain only the native textboxes from texts.json.')
            nv=shape.find('p:nvSpPr/p:cNvPr',NS);name=nv.get('name')
            if name not in textmap or name in seen:fail('Unexpected or duplicate base shape '+name)
            set_native_runs(shape,textmap[name]);seen.add(name)
        if seen!=set(textmap):fail('Base is missing text ids: '+', '.join(sorted(set(textmap)-seen)))
        first=max([int(e.get('id')) for e in slide.findall('.//p:cNvPr',NS)] or [1])+1
        builder=NativeBuilder(first,viewbox,canvas)
        shapes=builder.visit(root)
        for i,shape in enumerate(shapes,2):tree.insert(i,shape)
        groups={}
        for group in tree.findall('.//p:grpSp',NS):
            name=group.find('p:nvGrpSpPr/p:cNvPr',NS).get('name')
            if name in groups:fail('Duplicate semantic group '+name)
            groups[name]=group
        text_only_groups=[]
        for panel in sorted({t['panel'] for t in textmap.values() if t.get('panel')} - set(groups)):
            # The artwork-only normalizer omits groups that contain only text.
            # Recreate their declared semantic container before assigning labels.
            group=builder.group(panel,[]);tree.append(group);groups[panel]=group;text_only_groups.append(panel)
        for sp in list(tree.findall('p:sp',NS)):
            t=textmap.get(sp.find('p:nvSpPr/p:cNvPr',NS).get('name'))
            if t and t.get('panel'):
                tree.remove(sp);groups[t['panel']].append(sp)
        for group in tree.findall('p:grpSp',NS):tighten(group)
        compact=ET.Element(slide.tag,slide.attrib,nsmap={**slide.nsmap,**NS});compact.extend(list(slide));ET.cleanup_namespaces(compact,top_nsmap=NS)
        xml=ET.tostring(compact,xml_declaration=True,encoding='UTF-8',standalone=True)
        output_path.parent.mkdir(parents=True,exist_ok=True)
        with ZipFile(output_path,'w',ZIP_DEFLATED) as out:
            for item in z.infolist():out.writestr(item,xml if item.filename==slide_names[0] else z.read(item.filename))
    return {**inspect_editability(output_path),'output':str(output_path.resolve()),'status':'candidate_requires_finalization',
        'text_boxes':len(textmap),'native_text_runs':sum(len(t['_runs']) for t in textmap.values()),
        'paths_inserted':builder.count,'gradients':len(compact.findall('.//a:gradFill',NS)),
        'groups':len(groups),'text_only_groups':text_only_groups,'slide_xml_bytes':len(xml),'group_mapping':'identity_with_tight_bounds',
        'gradient_approximations':diags,'requires':['presentations skill finalizer','font and package integrity checks','rendered visual inspection','native ungrouping appearance check'],
        'limitations':['Controlled normalized SVG redraw subset; unsupported effects fail explicitly.',
          'SVG elliptical radial gradients use native circular gradient approximations.',
          'Single-line baseline placement and sub/super offsets require rendered visual review.']}

def main():
    p=argparse.ArgumentParser(description=__doc__,formatter_class=argparse.RawDescriptionHelpFormatter)
    for name in ('svg','texts','base','output','report'):p.add_argument('--'+name,required=True,type=Path)
    opt=p.parse_args()
    protected={opt.svg.resolve(),opt.texts.resolve(),opt.base.resolve()}
    if opt.output.resolve() in protected or opt.report.resolve() in protected or opt.report.resolve()==opt.output.resolve():p.error('Output and report must be distinct from one another and from every input file.')
    try:report=build(opt.svg,opt.texts,opt.base,opt.output)
    except (ValueError,KeyError,TypeError,ET.XMLSyntaxError) as exc:p.error(str(exc))
    opt.report.parent.mkdir(parents=True,exist_ok=True);opt.report.write_text(json.dumps(report,indent=2,ensure_ascii=False)+'\n')
    print(json.dumps({k:v for k,v in report.items() if k!='gradient_approximations'},indent=2,ensure_ascii=False))

if __name__=='__main__':main()
