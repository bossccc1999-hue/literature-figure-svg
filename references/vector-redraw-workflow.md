# Vector Redraw Workflow

Use this reference for literature diagrams that should become editable vector graphics: mechanisms, workflows, topology diagrams, equivalent circuits, model blocks, CNN architectures, process diagrams, and schematic multi-panel summaries.

## Redraw Boundary

The target is a clean scholarly reconstruction, not pixel copying.

Preserve:

- figure purpose and scientific object;
- panel order and major layout;
- modules, arrows, labels, variables, coordinate meanings, and legend logic;
- topology, circuit direction, physical connection, or model flow.

Improve:

- font consistency, alignment, line width, grayscale hierarchy, crowded labels, low-resolution artifacts, and export quality.

Do not:

- replace the original scientific structure with a generic illustration;
- allow image generation to invent circuits, axes, equations, labels, or data;
- convert all text to outlines when editable text is requested.

## Practical Steps

1. Make a panel map before drawing: `panel`, `source crop`, `editable vector objects`, `raster objects`, `must-preserve text`, `uncertain text`.
2. Choose a vector method:
   - SVG primitives for flowcharts, block diagrams, topology, and simple mechanisms.
   - Matplotlib patches for diagrams that benefit from code and publication export.
   - draw.io/PowerPoint/Illustrator-style construction when the user needs manual editing outside code.
3. Use a restrained journal style:
   - white background;
   - low-saturation colors;
   - consistent line width;
   - short labels inside the figure;
   - long explanations in README, caption, or manuscript text.
4. Export SVG with editable text plus native PPTX and PNG preview by default (respect an explicit SVG-only request). Read [native PowerPoint workflow](native-powerpoint-workflow.md); normalize clipping/rounded paths/markers and build native shapes/text instead of embedding an SVG and relying on Convert to Shape.
5. Compare against the source figure for missing modules, wrong arrows, changed labels, or accidental layout drift.

## Figure-Type Notes

- Flowcharts: preserve branch conditions, loopbacks, error paths, and step order.
- Mechanism diagrams: preserve material layers, reaction/process order, arrows, and scale relationships where meaningful.
- Topology/circuit figures: preserve node identity, component orientation, buses, phase symmetry, feedback loops, and variables.
- CNN/model structures: preserve input, repeated blocks, pooling/attention layers, skip paths, output head, and legend.
- Multi-panel summaries: first rebuild the panel grid; only then fill each panel.

## SVG Quality Checklist

- Text is selectable/editable in SVG where possible.
- Lines and arrows are vector strokes, not embedded screenshots.
- Elements are grouped or named clearly enough for later editing.
- No clipped labels or overlapping legends.
- Black-and-white print remains understandable through line style, marker shape, or hierarchy.
- Raster components are intentionally embedded and documented, not accidental low-resolution leftovers.

- Compare grouped and fully expanded temporary PPTX copies after checking identity group transforms.
- Record which renderers/applications were checked and any native shading approximation.
