#!/usr/bin/env python3
"""Create a reproducible project for literature-figure SVG redraw work."""

from __future__ import annotations

import argparse
import copy
import json
import re
from pathlib import Path


PRESETS = {
    "diagram": {
        "title": "Editable diagram redraw package",
        "script": "draw_diagram_svg.py",
        "outputs": ["outputs/svg/figure_diagram.svg", "outputs/pdf/figure_diagram.pdf", "outputs/png_600dpi/figure_diagram_600dpi.png"],
        "data": ["data/panel_inventory.json"],
        "boundary": "Use vector primitives for mechanisms, workflows, topology, circuits, model blocks, or CNN structures.",
    },
    "plot": {
        "title": "Editable plot reconstruction package",
        "script": "draw_plot.py",
        "outputs": ["outputs/svg/figure_plot.svg", "outputs/pdf/figure_plot.pdf", "outputs/png_600dpi/figure_plot_600dpi.png"],
        "data": ["data/plot_data.csv", "data/data_source.json"],
        "boundary": "Use original, digitized, or clearly marked synthetic/demo data; never invent source data silently.",
    },
    "multi-panel": {
        "title": "Editable multi-panel literature figure package",
        "script": "draw_multi_panel.py",
        "outputs": ["outputs/svg/figure_multi_panel.svg", "outputs/pdf/figure_multi_panel.pdf", "outputs/png_600dpi/figure_multi_panel_600dpi.png", "outputs/preview/figure_multi_panel_preview.png"],
        "data": ["data/panel_inventory.json", "data/data_source.json"],
        "boundary": "Map every panel first, then rebuild each as vector, code-generated plot, or raster-with-vector-annotation.",
    },
    "raster-annotated": {
        "title": "Raster evidence with editable SVG annotations package",
        "script": "annotate_raster_panels.py",
        "outputs": ["outputs/svg/annotated_panels.svg", "outputs/pdf/annotated_panels.pdf", "outputs/png_600dpi/annotated_panels_600dpi.png"],
        "data": ["data/panel_inventory.json", "source_images/README.md"],
        "boundary": "Keep microscopy, pathology, Western blot, gel, or photo evidence as raster panels; rebuild labels, arrows, masks, and scale bars as vectors.",
    },
}


def slugify(value: str) -> str:
    value = value.strip().lower()
    value = re.sub(r"[^a-z0-9_-]+", "_", value)
    value = re.sub(r"_+", "_", value).strip("_")
    return value or "literature_figure_svg"


def write_text(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def build_readme(name: str, preset: dict[str, str | list[str]]) -> str:
    outputs = "\n".join(f"- `{item}`" for item in preset["outputs"])
    data = "\n".join(f"- `{item}`" for item in preset["data"])
    return f"""# {preset["title"]}

Project: `{name}`

This folder is for redraw-based reconstruction of literature figures into editable SVG and directly editable native PPTX graphics (unless SVG-only is requested).

## Boundary

{preset["boundary"]}

## Expected outputs

{outputs}

## Data and documentation

{data}
- `assumptions.md`
- `STYLE_GUIDE.md`
- `manifest.json`

## Acceptance checklist

- Source figure, paper, page, or screenshot is recorded.
- Editable vector objects are separated from raster evidence.
- Text remains editable in SVG when technically possible.
- Data source is marked as original-data, digitized, synthetic/demo, or unknown.
- Pure schematic content is semantic vector artwork; actual scientific image evidence stays raster.
- When PPTX is requested, native PPTX uses native shapes/text; it does not require SVG conversion in PowerPoint.
- Clipping, rounded corners, arrowheads, text/subscripts and gradients are checked.
- When PPTX is requested, an ungrouped temporary copy is compared with the grouped file.
- Only checks actually performed are marked passed in verification.json.
- Source citation and any required attribution or permission are recorded.
"""


def build_assumptions(name: str, figure_type: str) -> str:
    return f"""# assumptions

Project: `{name}`
Type: `{figure_type}`

## Source

- Paper / DOI / URL:
- Figure number:
- Source file or screenshot:
- Source creator / publisher:
- Known source license:
- Permission / citation note:
- Intended use:

## Data status

Choose one for each plot panel:

- original-data
- digitized
- synthetic/demo
- unknown

## Editable boundary

- Fully vector-redrawn elements:
- Raster elements intentionally retained:
- Labels or symbols needing human confirmation:
- Native gradient/shading approximations:
- Unsupported source features and explicit handling:
- Actual PowerPoint verification performed (or not performed):

## Do not change

- Scientific object:
- Panel order:
- Axes / variables / units:
- Topology / mechanism / flow direction:
"""


def build_style_guide() -> str:
    return """# STYLE_GUIDE

- Prefer white background and restrained journal styling.
- Use low-saturation colors and distinguish groups without relying only on color.
- Keep labels short inside the figure; put long explanations in captions or README.
- Preserve original panel labels and scientific relationships.
- Use SVG and native PPTX as editable outputs; PNG is preview only. Inspect PDF exports for intentional or renderer-created raster content.
- For Matplotlib, keep text editable with `svg.fonttype = "none"` and PDF text as TrueType.
"""


def build_common_style() -> str:
    return '''"""Shared style helpers for editable literature-figure redraws."""

from __future__ import annotations

import matplotlib.pyplot as plt


COLORS = {
    "blue": "#2F6B9A",
    "orange": "#D97732",
    "green": "#2E7D59",
    "red": "#B94A48",
    "purple": "#76569A",
    "gray": "#777777",
    "light_gray": "#D9D9D9",
}


def apply_editable_svg_style() -> None:
    plt.rcParams.update(
        {
            "figure.facecolor": "white",
            "axes.facecolor": "white",
            "font.family": ["Arial", "Helvetica", "DejaVu Sans", "sans-serif"],
            "font.size": 8,
            "svg.fonttype": "none",
            "pdf.fonttype": 42,
            "ps.fonttype": 42,
            "savefig.bbox": "tight",
            "savefig.dpi": 300,
        }
    )
'''


def build_script_stub(figure_type: str, preset: dict[str, str | list[str]]) -> str:
    return f'''#!/usr/bin/env python3
"""Generate editable SVG outputs for a {figure_type} literature figure package."""

from __future__ import annotations

from pathlib import Path

from common_style import apply_editable_svg_style


ROOT = Path(__file__).resolve().parent
OUTPUTS = {preset["outputs"]!r}


def main() -> None:
    apply_editable_svg_style()
    for folder in ["outputs/svg", "outputs/pdf", "outputs/png_600dpi", "outputs/preview"]:
        (ROOT / folder).mkdir(parents=True, exist_ok=True)
    print("Implement the redraw here, then write:")
    for output in OUTPUTS:
        print(" -", ROOT / output)


if __name__ == "__main__":
    main()
'''


def create_project(output_dir: Path, name: str, figure_type: str, force: bool, svg_only: bool = False) -> Path:
    if figure_type not in PRESETS:
        raise SystemExit(f"Unknown type: {figure_type}. Valid types: {', '.join(sorted(PRESETS))}")

    preset = copy.deepcopy(PRESETS[figure_type])
    if not svg_only:
        preset["outputs"].append("outputs/pptx/figure_native.pptx")
    preset["outputs"].append("outputs/preview/verification.json")
    project_dir = output_dir / slugify(name)
    if project_dir.exists() and any(project_dir.iterdir()) and not force:
        raise SystemExit(f"Output directory already exists and is not empty: {project_dir}")

    for folder in ["data", "source_images", "outputs/svg", "outputs/pdf", "outputs/png_600dpi", "outputs/preview", "outputs/pptx"]:
        (project_dir / folder).mkdir(parents=True, exist_ok=True)

    write_text(project_dir / "README.md", build_readme(name, preset))
    write_text(project_dir / "assumptions.md", build_assumptions(name, figure_type))
    write_text(project_dir / "STYLE_GUIDE.md", build_style_guide())
    write_text(project_dir / "common_style.py", build_common_style())
    write_text(project_dir / preset["script"], build_script_stub(figure_type, preset))

    write_text(
        project_dir / "data" / "panel_inventory.json",
        json.dumps(
            {
                "project": name,
                "figure_type": figure_type,
                "panels": [
                    {
                        "panel": "a",
                        "source": "",
                        "route": "vector | plot | raster-annotated",
                        "data_status": "original-data | digitized | synthetic/demo | unknown",
                        "notes": "",
                    }
                ],
            },
            ensure_ascii=False,
            indent=2,
        )
        + "\n",
    )
    write_text(
        project_dir / "data" / "data_source.json",
        json.dumps(
            {
                "data_status": "unknown",
                "allowed_values": ["original-data", "digitized", "synthetic/demo", "unknown"],
                "note": "Record the data source for each plot panel before making scientific claims.",
            },
            ensure_ascii=False,
            indent=2,
        )
        + "\n",
    )
    write_text(project_dir / "data" / "plot_data.csv", "x,y,series,data_status\n")
    write_text(project_dir / "source_images" / "README.md", "Place source screenshots or raster panels here when permitted.\n")

    manifest = {
        "project": name,
        "figure_type": figure_type,
        "script": preset["script"],
        "outputs": preset["outputs"],
        "editable_boundary": "Vector-redraw editable objects must be distinguished from retained raster evidence.",
    }
    manifest["native_pptx_requested"] = not svg_only
    manifest["status"] = "planned; scaffold only"
    write_text(project_dir / "outputs" / "preview" / "verification.json", json.dumps({
        "status": "pending",
        "source_inventory": "pending",
        "svg_text_geometry_visual_check": "pending",
        "native_pptx_structure_check": "not-requested" if svg_only else "pending",
        "native_pptx_render_check": "not-requested" if svg_only else "pending",
        "ungrouped_copy_comparison": "not-requested" if svg_only else "pending",
        "powerpoint_ui_check": "not-performed",
        "retained_raster_content": [],
        "known_approximations": []
    }, ensure_ascii=False, indent=2) + "\n")
    write_text(project_dir / "manifest.json", json.dumps(manifest, ensure_ascii=False, indent=2) + "\n")
    return project_dir


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", default="outputs", help="Root output directory.")
    parser.add_argument("--name", default="literature_figure_svg", help="Project name.")
    parser.add_argument("--type", choices=sorted(PRESETS), default="multi-panel", help="Figure package type.")
    parser.add_argument("--svg-only", action="store_true", help="Exclude the default native PPTX companion when requested.")
    parser.add_argument("--force", action="store_true", help="Overwrite files in an existing package directory.")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    project_dir = create_project(Path(args.output_dir), args.name, args.type, args.force, args.svg_only)
    print(project_dir)


if __name__ == "__main__":
    main()
