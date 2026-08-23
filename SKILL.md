---
name: literature-figure-svg
description: Reconstruct literature, paper, PDF, or screenshot figures as editable SVG/PDF figure projects for scholarly use. Use when users ask to redraw paper images, diagrams, plots, mechanisms, flowcharts, topology figures, or multi-panel figures as editable vector graphics; do not use for ordinary photo editing, decorative image generation, or unsupported claims of exact source-data recovery.
metadata:
  short-description: Literature figures to editable SVG
---

# Literature Figure SVG

Use this skill when the user wants figures from papers, PDFs, screenshots, or literature reviews turned into editable SVG-style scholarly graphics.

The default task is **redraw-based vector reconstruction**, not one-click bitmap tracing. Preserve the figure's scientific role, panel structure, labels, axes, variables, and visual grammar, while rebuilding the editable parts as SVG, PDF, and high-resolution PNG.

## Core Rules

1. Record the source figure, DOI/URL or file reference, figure number, intended use, and any known license or permission before rebuilding externally published material. Preserve required attribution. Never imply that the user, the assistant, or this skill authored the source figure or its underlying data.
2. Do not claim that a screenshot has been faithfully converted into editable objects unless it has been manually or programmatically rebuilt as vector elements and checked against the source.
3. Do not copy a published figure pixel-for-pixel. Reconstruct the structure, visual logic, and scholarly expression while respecting copyright, citation, license, and permission boundaries.
4. Do not invent source data. If graph data are unavailable, either digitize with an explicit caveat, ask for data, or mark any generated values as `synthetic/demo/illustrative`.
5. Keep text editable in SVG whenever possible. For Matplotlib output, set `svg.fonttype = "none"` and avoid converting all labels to paths.
6. For microscopy, pathology, Western blot, gel images, animal photos, and other real images, keep the raw image as raster content and add editable vector labels, arrows, scale bars, masks, and panel layout. Do not pretend the photograph itself is fully vectorized.
7. Deliver a reproducible package when the user asks for multiple figures, future editing, scripts, assumptions, SVG/PDF/PNG, or a project-like handoff.

## Fast Routing

- Flowchart, mechanism diagram, model diagram, topology, equivalent circuit, CNN architecture, process diagram: read [references/vector-redraw-workflow.md](references/vector-redraw-workflow.md), then rebuild as editable SVG using SVG primitives, draw.io-style logic, Matplotlib patches, or another vector-first method.
- Plots, bar charts, line charts, Kaplan-Meier curves, heatmaps, statistical panels: read [references/data-plot-reconstruction.md](references/data-plot-reconstruction.md), then use code-based plotting and preserve the data source boundary.
- Multi-panel paper figures: read both references, first make a panel map and assumptions file, then rebuild each panel according to its type.
- Photos, microscopy, histology, immunofluorescence, Western blot, animal wound photos: create an editable SVG wrapper with raster panels plus vector annotations; do not trace the image as if it were quantitative vector data.

## Default Workflow

1. Inspect the source figure, PDF page, or screenshot and classify each panel.
2. Create a panel inventory: panel label, figure type, source evidence, editable elements, raster elements, uncertain text, and data status.
3. Choose the reconstruction route:
   - Pure vector redraw for diagrams and flowcharts.
   - Code-generated plot for charts and statistical panels.
   - Raster base plus vector annotations for scientific images.
4. Build or update a reproducible project. For a new package, prefer running `scripts/scaffold_svg_project.py`.
5. Export at least SVG and a preview PNG; add PDF and 600 dpi PNG when the user needs publication-ready output.
6. Verify: editable text, no missing labels, no overlapping annotations, white background unless intentionally transparent, and assumptions clearly recorded.

## Package Helper

Use the helper when the user wants a reusable output folder:

```bash
python scripts/scaffold_svg_project.py --output-dir outputs --name my_literature_figure --type multi-panel
```

Supported package types:

- `diagram`: mechanisms, workflows, model diagrams, topology, equivalent circuits.
- `plot`: bar charts, line charts, KM curves, heatmaps, statistical panels.
- `multi-panel`: mixed paper figures with multiple subpanels.
- `raster-annotated`: microscopy, pathology, Western blot, animal photos, or any figure that must retain raster image evidence.

## Delivery Language

When delivering results, state:

- Which parts are fully editable vector elements.
- Which parts remain raster because they are source images.
- Whether graph values came from original data, digitization, or synthetic/demo reconstruction.
- Which source citation, license, or permission note applies.
- Where the SVG/PDF/PNG outputs and assumptions file are located.

If the user only asks whether a paper image can be converted, answer with the practical route and limitations instead of promising a perfect automatic conversion.
