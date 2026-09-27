#!/usr/bin/env python3
"""Inspect actual PDF page content without mistaking a PDF container for vectors.

Usage: python inspect_pdf.py figure.pdf --output inspection.json
Requires PyMuPDF (pip install pymupdf). The report contains layout/geometry
metadata and text character counts, not extracted article body text.
"""
from __future__ import annotations

import argparse
from collections import Counter
import json
from pathlib import Path
import sys


def union_area(rectangles):
    """Exact union area for axis-aligned bounding boxes (an upper-bound proxy)."""
    if not rectangles:
        return 0.0
    xs = sorted({x for r in rectangles for x in (r[0], r[2])})
    area = 0.0
    for left, right in zip(xs, xs[1:]):
        ys = sorted((r[1], r[3]) for r in rectangles if r[0] < right and r[2] > left)
        if not ys:
            continue
        lo, hi = ys[0]
        height = 0.0
        for y0, y1 in ys[1:]:
            if y0 > hi:
                height += hi - lo
                lo, hi = y0, y1
            else:
                hi = max(hi, y1)
        area += (right - left) * (height + hi - lo)
    return area


def inspect(path):
    try:
        import pymupdf as fitz
    except ImportError:
        try:
            import fitz
        except ImportError as exc:
            raise RuntimeError("PyMuPDF is required: install pymupdf in the chosen Python runtime") from exc
    result = {
        "source": str(Path(path).resolve()),
        "format": "PDF",
        "container_is_not_evidence_of_vector_content": True,
        "classification_is_heuristic": True,
        "limitations": [
            "Image coverage uses clipped image bounding-box unions; rotated images, masks and occlusion can overstate actual visible coverage.",
            "Extractable text can be an invisible OCR layer. Text presence alone does not prove that the illustrated objects are editable vectors.",
            "Vector paths can be clipping/background objects or outlined lettering. Counts do not establish semantic editability or scientific image type.",
            "Microscopy, gels, histology and other empirical image evidence must be identified visually and preserved as raster even in mixed PDFs.",
        ],
        "pages": [],
    }
    with fitz.open(path) as doc:
        if doc.needs_pass:
            raise RuntimeError("PDF is encrypted and requires a password")
        result["page_count"] = len(doc)
        for page in doc:
            # Disable image payload extraction: get_image_info supplies metadata.
            text_dict = page.get_text("dict", flags=fitz.TEXTFLAGS_DICT & ~fitz.TEXT_PRESERVE_IMAGES)
            spans = []
            for block in text_dict.get("blocks", []):
                for line in block.get("lines", []):
                    for span in line.get("spans", []):
                        spans.append({
                            "bbox": list(span["bbox"]), "font": span.get("font"),
                            "size_pt": span.get("size"), "flags": span.get("flags"),
                            "character_count": len(span.get("text", "")),
                        })
            drawings = page.get_drawings()
            paths = [{
                "bbox": list(d["rect"]), "paint_type": d.get("type"),
                "operator_counts": dict(Counter(item[0] for item in d.get("items", []))),
                "stroke_width": d.get("width"), "fill_opacity": d.get("fill_opacity"),
                "stroke_opacity": d.get("stroke_opacity"),
            } for d in drawings]
            images = []
            boxes = []
            for info in page.get_image_info(xrefs=True):
                bbox = fitz.Rect(info["bbox"])
                clipped = bbox & page.rect
                if not clipped.is_empty:
                    boxes.append(tuple(clipped))
                images.append({key: list(info[key]) if key in ("bbox", "transform") else info.get(key)
                               for key in ("xref", "bbox", "transform", "width", "height", "bpc", "colorspace", "cs-name")})
            area = page.rect.width * page.rect.height
            coverage = min(1.0, union_area(boxes) / area) if area else 0.0
            chars = sum(s["character_count"] for s in spans)
            if images and not paths and not chars:
                classification = "raster_only_candidate"
            elif images and coverage >= 0.9:
                classification = "raster_dominant_candidate_with_text_or_vectors"
            elif images and (paths or chars):
                classification = "mixed_raster_text_vector_candidate"
            elif paths:
                classification = "vector_paths_present_no_raster_detected"
            elif chars:
                classification = "text_only_no_raster_detected"
            else:
                classification = "blank_or_unresolved_content"
            result["pages"].append({
                "page": page.number + 1, "size_pt": [page.rect.width, page.rect.height],
                "rotation_degrees": page.rotation,
                "classification": classification,
                "text_span_count": len(spans), "text_character_count": chars,
                "vector_path_count": len(paths), "image_occurrence_count": len(images),
                "image_bbox_coverage_fraction": round(coverage, 6),
                "text_spans": spans, "vector_paths": paths, "images": images,
            })
    result["classification_counts"] = dict(Counter(p["classification"] for p in result["pages"]))
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("pdf", type=Path)
    parser.add_argument("--output", required=True, type=Path, help="JSON report path")
    args = parser.parse_args()
    try:
        report = inspect(args.pdf)
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    except Exception as exc:
        print(f"inspect_pdf: {exc}", file=sys.stderr)
        return 1
    print(json.dumps({"report": str(args.output), "page_count": report["page_count"],
                      "classification_counts": report["classification_counts"]}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
