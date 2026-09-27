# SVG and native PowerPoint workflow

Use this route for editable figure delivery and especially when PowerPoint changes imported SVG after conversion or ungrouping. SVG and PPTX are separate exports of the same figure. Native PPTX bypasses Office's SVG importer; an embedded SVG picture is not a native reconstruction.

## Inspect and reconstruct

Inspect a PDF's rendering and its text/path/image inventory. Counts inform routing but do not prove every component is editable: outlined letters are paths, not text; one image may be a whole screenshot or only a microscopy panel. Preserve usable vectors, recover verified labels, and inspect PDF clipping/transparency/fonts.

Extract source images at original resolution if a PDF wraps a screenshot. Rebuild schematic content with semantic vectors and live labels. Retain genuine scientific images and annotate them. Keep source evidence and scientific meaning separate from editable presentation choices.

## Stable representations

| Feature | Editing representation |
| --- | --- |
| Rounded rect/capsule/ellipse | Explicit Bézier curves where importers lose primitive parameters |
| SVG arc command | Verified cubic segments |
| Clip path | Curve intersection in shared coordinates; clip fill and outlined stroke separately |
| Stroke/dash | Outline locally before affine transformation; avoid stroking the new clipping boundary |
| Arrow marker | Explicit arrowhead path using marker coordinates and endpoint tangent |
| Nested transform | Bake the complete affine mapping into geometry |
| Compound hole | Preserve fill rule; normalize winding before native freeform export |
| Text | Native text box/runs with explicit font, size, color, baseline and sub/superscript |
| Gradient | Native DrawingML fill with transformed SVG gradient basis, stops and alpha |
| Group | Tight bounds and identity mapping (`off=chOff`, `ext=chExt`), named objects, unchanged z-order |
| Micrograph/photo | Original raster evidence plus native annotations |

Bounding-box containment is insufficient for clipping an ellipse or rounded corner. Preserve composited group opacity: multiplying opacity into overlapping children changes appearance. Unsupported constructs need deliberate handling rather than silent omission.

The supplied linear-gradient converter preserves the affine scalar field. Its elliptical radial shading is approximated with an equal-area native circular gradient; brightness/highlight shape may differ slightly. Inspect and disclose material differences. If shading fidelity requires more work, construct a better native fill or explicit editable vector shading. Do not silently add a bitmap fallback to a claimed pure-vector result.

## Dependencies and commands

Locate Python/Node/libraries through the host's workspace dependency loader. Read the installed presentations skill for its required artifact-tool authoring, operation marker and finalizer. Avoid fixed user paths, runtime versions, figure names or slide sizes.

- Python: `lxml`; PDF inspection: `PyMuPDF`.
- Node: `@oai/artifact-tool` for base/text, `@napi-rs/canvas` for curve booleans and stroke expansion.
- Rendering: bundled LibreOffice/Poppler or another supported renderer. Use approved GUI tools for actual PowerPoint operations.

Set `PPT_COMPAT_NODE` to the discovered Node executable when necessary. Set `RUNTIME_NODE_MODULES` to the discovered dependency directory, or explicitly set `PPT_COMPAT_CANVAS_MODULE` for the canvas module. Run scripts in a project intermediate directory, not inside the installed skill. Read `--help` for exact options. Typical sequence (variables refer to discovered paths):

```bash
"$FIGURE_PYTHON" "$FIGURE_SKILL/scripts/inspect_pdf.py" source.pdf --output work/pdf_inventory.json
"$FIGURE_PYTHON" "$FIGURE_SKILL/scripts/normalize_svg.py" source_redraw.svg --output-dir work/normalized
"$FIGURE_NODE" "$FIGURE_SKILL/scripts/build_native_base.mjs" --svg work/normalized/artwork.svg --texts work/normalized/texts.json --output work/base.pptx
"$FIGURE_PYTHON" "$FIGURE_SKILL/scripts/build_native_pptx.py" --svg work/normalized/artwork.svg --texts work/normalized/texts.json --base work/base.pptx --output work/candidate.pptx --report work/native_report.json
"$FIGURE_PYTHON" "$FIGURE_SKILL/scripts/audit_editability.py" --svg work/normalized/compatible.svg --pptx work/candidate.pptx --report work/editability.json --flattened-pptx work/ungrouped_check.pptx
```

The normalizer exports compatible SVG, artwork-only SVG, text metadata and a report. The native builder injects geometry into an artifact-tool base. These are candidate files: use the presentations skill's finalizer to validate the deliverable, with fresh final/receipt paths. ZIP/XML validity alone is insufficient.

### Supported-subset boundary

These scripts are building blocks for controlled semantic redraws. Unimplemented constructs should raise a diagnostic. CSS classes/stylesheets, `use`/external references, masks, filters, patterns, complex text positioning, some marker/dash configurations and group opacity can require preprocessing or native authoring. Do not assume an arbitrary PDF-exported SVG is supported. Read helper diagnostics and docstrings.

For rich text beyond the helper, measure and author native runs/text boxes preserving baseline relationships. For mixed raster figures, place source images using the presentation authoring runtime and layer native annotations. The strict path normalizer need not accept image nodes.

## Verification

1. Audit XML, unique SVG IDs, references, live labels, meaningful groups and intentional raster objects.
2. Render semantic and normalized SVG at the same dimensions/background/renderer. Inspect changed areas as well as aggregate pixel differences; edge antialiasing is distinct from missing shapes.
3. Render native PPTX. Check rounded corners, clip boundaries, holes, arrows, text/subscripts, overlaps, stacking and gradients at useful zoom.
4. Flatten a **temporary** copy only after proving group coordinate mappings are identity. Compare object content/order and rendered pixels. For nonidentity mappings, compute transforms before flattening instead of deleting wrappers.
5. Where available, open a separate copy in PowerPoint, select intended groups, ungroup/save, and recheck object counts and render. Preserve grouping in the main deliverable. Do not claim all nested groups were interactively tested if only the top level was ungrouped.
6. Use the presentations finalizer. State which checks ran: an XML audit, a LibreOffice rendering and an actual PowerPoint check provide different evidence.

Deliver SVG + native PPTX + preview with short usage notes: “PPTX 内已经是原生形状和文本，直接打开编辑，无需转换为形状。” State retained raster evidence and material shading approximations. Do not recommend SVG conversion/ungrouping as the main editing route.

## Motivating regression

The 2026-09-27 six-panel schematic exposed rounded-rectangle loss, clip overflow, marker loss and text-size changes after Office SVG conversion. Its native reconstruction retained 2,105 freeforms, 117 text boxes and 271 gradients with no pictures. PowerPoint top-level ungroup/save preserved object counts and the re-rendered result. A separate full expansion of 479 identity groups also rendered identically. These are regression results for that figure, not target counts or universal guarantees.
