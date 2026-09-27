#!/usr/bin/env python3
"""Audit SVG/PPTX editability and optionally make an identity-group-flattened PPTX.

Usage: python audit_editability.py --svg drawing.svg --pptx drawing.pptx --report audit.json
       python audit_editability.py --pptx drawing.pptx --report audit.json --flattened-pptx scratch/ungrouped.pptx

Requires lxml (pip install lxml), which preserves PowerPoint namespace prefixes
and mc:Ignorable declarations during a scratch rewrite. Raster content is
allowed and explicitly reported; its presence is not an error for empirical
images. This structural audit does not replace a visual roundtrip test.
"""
from __future__ import annotations

import argparse
from collections import Counter
import json
import posixpath
from pathlib import Path
import re
import sys
from zipfile import ZipFile, ZIP_DEFLATED
from urllib.parse import unquote

try:
    from lxml import etree as ET
except ImportError:
    raise SystemExit("audit_editability: lxml is required; install lxml in the chosen Python runtime")

NS = {"p": "http://schemas.openxmlformats.org/presentationml/2006/main",
      "a": "http://schemas.openxmlformats.org/drawingml/2006/main",
      "r": "http://schemas.openxmlformats.org/officeDocument/2006/relationships"}
P = "{" + NS["p"] + "}"
A = "{" + NS["a"] + "}"
R = "{" + NS["r"] + "}"
SVG_PATH_COMMANDS = set("MmLlHhVvCcSsQqTtAaZz")


def parse_xml(data):
    return ET.fromstring(data, parser=ET.XMLParser(resolve_entities=False, no_network=True,
                                                 remove_comments=True, remove_pis=True))


def local(tag):
    return tag.rsplit("}", 1)[-1]


def duplicates(values):
    return {key: count for key, count in Counter(values).items() if count > 1}


def svg_audit(path):
    root = parse_xml(path.read_bytes())
    counts = Counter(local(e.tag) for e in root.iter())
    ids = [e.get("id") for e in root.iter() if e.get("id")]
    known = set(ids)
    broken, external, risky, images, arc_paths, unsupported = [], [], Counter(), [], 0, []
    for e in root.iter():
        attrs = dict(e.attrib)
        for item in e.get("style", "").split(";"):
            if ":" in item:
                k, v = item.split(":", 1)
                attrs[k.strip()] = v.strip()
        for k, value in attrs.items():
            if local(k) in {"clip-path", "mask", "filter", "marker-start", "marker-mid", "marker-end",
                            "transform", "gradientTransform", "patternTransform", "opacity", "mix-blend-mode",
                            "vector-effect", "textLength", "lengthAdjust", "baseline-shift"} and value not in ("none", ""):
                risky[local(k)] += 1
            for target in re.findall(r"url\(\s*['\"]?([^)'\"]+)['\"]?\s*\)", value):
                target = target.strip()
                if target.startswith("#") and target[1:] not in known:
                    broken.append({"element": e.get("id"), "attribute": local(k), "target": target})
                elif not target.startswith("#"):
                    external.append(target)
            if local(k) == "href":
                if value.startswith("#") and value[1:] not in known:
                    broken.append({"element": e.get("id"), "attribute": "href", "target": value})
                elif not value.startswith(("#", "data:")):
                    external.append(value)
        if local(e.tag) == "path":
            commands = set(re.findall(r"[A-DF-Za-df-z]", e.get("d", "")))
            arc_paths += int(bool(commands & set("Aa")))
            if commands - SVG_PATH_COMMANDS:
                unsupported.append({"id": e.get("id"), "commands": sorted(commands - SVG_PATH_COMMANDS)})
        if local(e.tag) == "image":
            href = e.get("href", e.get("{http://www.w3.org/1999/xlink}href", ""))
            if href.startswith("data:image/svg+xml") or href.lower().split("?")[0].endswith(".svg"):
                kind = "nested_svg_picture"
            elif href.startswith("data:image/") or re.search(r"\.(png|jpe?g|gif|bmp|tiff?|webp)(?:[?#]|$)", href, re.I):
                kind = "raster_picture"
            else:
                kind = "picture_type_unknown"
            images.append({"id": e.get("id"), "kind": kind, "embedded": href.startswith("data:"),
                           "source": "embedded_data_omitted" if href.startswith("data:") else href})
    rounded = sum(local(e.tag) == "rect" and (e.get("rx") is not None or e.get("ry") is not None) for e in root.iter())
    return {
        "source": str(path.resolve()), "element_counts": dict(counts), "text_elements": counts["text"],
        "duplicate_ids": duplicates(ids), "broken_local_references": broken,
        "external_references": sorted(set(external)), "images": images,
        "raster_image_count": sum(i["kind"] == "raster_picture" for i in images),
        "picture_type_unknown_count": sum(i["kind"] == "picture_type_unknown" for i in images),
        "powerpoint_svg_import_risk_attributes": dict(risky),
        "powerpoint_svg_import_risk_elements": {k: counts[k] for k in ("clipPath", "mask", "filter", "marker", "use", "foreignObject", "style", "pattern") if counts[k]},
        "rounded_rectangles": rounded, "paths_with_arc_commands": arc_paths,
        "unsupported_path_commands": unsupported,
        "interpretation": "Valid SVG features such as gradients, clipping and rounded rects can still change in PowerPoint Convert to Shape. Structural presence is a risk signal, not proof of a visual failure. Use native editable PPTX and render/roundtrip checks when PPT editing is required.",
    }


def group_identity(group):
    """Return blockers; flatten only proven identity transforms with no effects."""
    reasons = []
    props = group.find("p:grpSpPr", NS)
    xfrm = props.find("a:xfrm", NS) if props is not None else None
    if xfrm is None:
        return ["group transform missing; identity not proven"]
    try:
        off, ext, choff, chext = [xfrm.find("a:" + n, NS) for n in ("off", "ext", "chOff", "chExt")]
        if any(v is None for v in (off, ext, choff, chext)):
            reasons.append("incomplete group transform")
        else:
            if any(k not in e.attrib for e, keys in ((off, ("x", "y")), (choff, ("x", "y")),
                                                    (ext, ("cx", "cy")), (chext, ("cx", "cy"))) for k in keys):
                reasons.append("missing required group coordinates")
            if any(int(off.get(k, "0")) != int(choff.get(k, "0")) for k in ("x", "y")):
                reasons.append("off differs from chOff")
            if any(int(ext.get(k, "0")) != int(chext.get(k, "0")) for k in ("cx", "cy")):
                reasons.append("ext differs from chExt")
            if any(int(ext.get(k, "0")) <= 0 for k in ("cx", "cy")):
                reasons.append("nonpositive extent; identity scale not proven")
        if int(xfrm.get("rot", "0")) % 21600000:
            reasons.append("nonzero rotation")
        if any(xfrm.get(k, "false").lower() not in ("0", "false") for k in ("flipH", "flipV")):
            reasons.append("group flip")
    except (ValueError, TypeError):
        reasons.append("invalid numeric transform")
    if props is not None:
        extras = [local(e.tag) for e in props if e.tag != A + "xfrm"]
        if extras:
            reasons.append("group appearance/extension properties: " + ", ".join(extras))
    return reasons


def slide_audit(root, name):
    groups = root.findall(".//p:grpSp", NS)
    ids = [e.get("id") for e in root.findall(".//p:cNvPr", NS)]
    blocks = []
    for group in groups:
        reasons = group_identity(group)
        if reasons:
            meta = group.find("p:nvGrpSpPr/p:cNvPr", NS)
            blocks.append({"id": meta.get("id") if meta is not None else None,
                           "name": meta.get("name") if meta is not None else None, "reasons": reasons})
    return {"part": name, "shape_count": len(root.findall(".//p:sp", NS)), "group_count": len(groups),
            "text_box_count": len(root.findall(".//p:txBody", NS)), "text_run_count": len(root.findall(".//a:t", NS)),
            "gradient_count": len(root.findall(".//a:gradFill", NS)), "picture_count": len(root.findall(".//p:pic", NS)),
            "custom_geometry_count": len(root.findall(".//a:custGeom", NS)),
            "duplicate_nonvisual_ids": duplicates(ids), "missing_nonvisual_ids": sum(i is None for i in ids),
            "flatten_blockers": blocks,
            "identity_groups": len(groups) - len(blocks)}


def flatten_groups(parent):
    for child in list(parent):
        if child.tag == P + "grpSp":
            flatten_groups(child)
            index = list(parent).index(child)
            for item in list(child):
                if item.tag not in (P + "nvGrpSpPr", P + "grpSpPr", P + "extLst"):
                    parent.insert(index, item)
                    index += 1
            parent.remove(child)


def pptx_audit(path, flattened=None):
    report = {"source": str(path.resolve()), "slides": [], "missing_relationship_targets": [],
              "broken_slide_relationship_ids": [], "media": [], "flattened_pptx": None}
    replacements = {}
    with ZipFile(path) as package:
        names = set(package.namelist())
        report["missing_required_parts"] = sorted({"[Content_Types].xml", "_rels/.rels", "ppt/presentation.xml"} - names)
        for name in sorted(names):
            if name.endswith(".rels"):
                base = name.split("/_rels/")[0] if "/_rels/" in name else ""
                for rel in parse_xml(package.read(name)):
                    if rel.get("TargetMode") == "External":
                        continue
                    target = rel.get("Target", "")
                    target_path = unquote(target.split("#", 1)[0])
                    resolved = target_path.lstrip("/") if target_path.startswith("/") else posixpath.normpath(posixpath.join(base, target_path))
                    if resolved not in names:
                        report["missing_relationship_targets"].append({"part": name, "id": rel.get("Id"), "target": target})
            if name.startswith("ppt/media/") and not name.endswith("/"):
                suffix = Path(name).suffix.lower()
                report["media"].append({"part": name, "bytes": package.getinfo(name).file_size,
                                        "kind": "raster" if suffix in (".png", ".jpg", ".jpeg", ".gif", ".bmp", ".tif", ".tiff", ".webp") else "vector_picture" if suffix in (".svg", ".emf", ".wmf") else "unknown"})
            if re.fullmatch(r"ppt/slides/slide\d+\.xml", name):
                root = parse_xml(package.read(name))
                slide = slide_audit(root, name)
                report["slides"].append(slide)
                relpath = "ppt/slides/_rels/" + name.rsplit("/", 1)[-1] + ".rels"
                relids = {e.get("Id") for e in parse_xml(package.read(relpath))} if relpath in names else set()
                for e in root.iter():
                    for key, value in e.attrib.items():
                        if key.startswith(R) and value not in relids:
                            report["broken_slide_relationship_ids"].append({"part": name, "id": value})
                replacements[name] = root
        report["raster_media_count"] = sum(m["kind"] == "raster" for m in report["media"])
        report["vector_picture_media_count"] = sum(m["kind"] == "vector_picture" for m in report["media"])
        report["all_groups_proven_identity"] = all(not s["flatten_blockers"] for s in report["slides"])
        report["structural_errors"] = bool(report["missing_required_parts"] or not report["slides"] or
                                           report["missing_relationship_targets"] or report["broken_slide_relationship_ids"] or
                                           any(s["duplicate_nonvisual_ids"] or s["missing_nonvisual_ids"] for s in report["slides"]))
        if flattened is not None:
            if flattened.resolve() == path.resolve():
                report["flatten_error"] = "Output must be a separate scratch file; source overwrite refused"
            elif not report["all_groups_proven_identity"]:
                report["flatten_error"] = "Flatten refused: not every group is proven identity and free of inherited group appearance properties"
            elif report["structural_errors"]:
                report["flatten_error"] = "Flatten refused: package has structural errors"
            else:
                # Reparenting only: element attributes, paint and path data stay intact.
                for root in replacements.values():
                    before = [ET.tostring(e) for e in root.findall(".//p:sp", NS)]
                    tree = root.find("p:cSld/p:spTree", NS)
                    if tree is None:
                        raise ValueError("Slide shape tree missing")
                    flatten_groups(tree)
                    assert before == [ET.tostring(e) for e in root.findall(".//p:sp", NS)], "Shape XML changed while flattening"
                flattened.parent.mkdir(parents=True, exist_ok=True)
                with ZipFile(flattened, "w", ZIP_DEFLATED) as output:
                    for info in package.infolist():
                        data = ET.tostring(replacements[info.filename], encoding="utf-8", xml_declaration=True) if info.filename in replacements else package.read(info.filename)
                        output.writestr(info, data)
                report["flattened_pptx"] = str(flattened.resolve())
                report["flattened_shape_xml_unchanged"] = True
    report["interpretation"] = "Counts establish object presence, not visual fidelity. Compare original and scratch flattened renders, and test a real PowerPoint ungroup/save roundtrip when available. A vector image inside p:pic remains a picture, not native editable shapes. Raster media may be intentional empirical imagery."
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--svg", type=Path)
    parser.add_argument("--pptx", type=Path)
    parser.add_argument("--report", required=True, type=Path)
    parser.add_argument("--flattened-pptx", type=Path, help="Optional separate scratch PPTX for render comparison")
    args = parser.parse_args()
    if not args.svg and not args.pptx:
        parser.error("provide --svg and/or --pptx")
    if args.flattened_pptx and not args.pptx:
        parser.error("--flattened-pptx requires --pptx")
    try:
        report = {"audit_scope": "structural_editability_not_visual_fidelity", "raster_is_allowed_when_intentional": True}
        if args.svg:
            report["svg"] = svg_audit(args.svg)
        if args.pptx:
            report["pptx"] = pptx_audit(args.pptx, args.flattened_pptx)
        args.report.parent.mkdir(parents=True, exist_ok=True)
        args.report.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    except Exception as exc:
        print(f"audit_editability: {exc}", file=sys.stderr)
        return 1
    failed = bool(report.get("pptx", {}).get("flatten_error") or report.get("pptx", {}).get("structural_errors") or
                  report.get("svg", {}).get("duplicate_ids") or report.get("svg", {}).get("broken_local_references"))
    print(json.dumps({"report": str(args.report), "status": "needs_attention" if failed else "structural_audit_complete",
                      "flattened_pptx": report.get("pptx", {}).get("flattened_pptx")}, ensure_ascii=False))
    return 2 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
