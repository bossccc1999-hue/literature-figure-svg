# literature-figure-svg

A Codex skill for reconstructing literature figures, screenshots, diagrams, plots, and AI-generated schematic elements as editable SVG and native PowerPoint figures.

The default deliverables are **editable SVG, directly editable native PPTX, and a PNG preview**. A current request for SVG only takes precedence. Native PPTX contains shapes and text boxes, so editing does not depend on PowerPoint's SVG “Convert to Shape” importer.

This is a vector-redraw workflow, not a one-click bitmap tracer or an arbitrary PDF converter. Diagrams and charts can be rebuilt as native vector elements; microscopy, blots, pathology, photographs, and other empirical images remain raster panels with editable annotations. A PDF extension alone does not establish that its contents are vectors.

## What it does

- Routes diagrams, mechanisms, topology figures, and workflow panels to vector-first redraw guidance.
- Routes plots and statistical panels to data-aware reconstruction guidance.
- Inspects actual PDF text spans, vector drawing paths, and embedded images before choosing a reconstruction route.
- Distinguishes fully editable vector elements from raster evidence such as microscopy, blots, pathology, or photos.
- Provides a scaffold for reproducible packages with SVG, native PPTX, previews, metadata, and assumptions; PDF and publication exports can be added when needed.
- Normalizes a controlled SVG subset into explicit geometry, with curve-based clipping, rounded shapes, arrowheads, and native PowerPoint gradients.
- Audits editability and can create a temporary ungrouped PPTX only after verifying that every group has an identity coordinate mapping and no unsupported group appearance properties.
- Records source provenance, data status, permissions, and the boundary between editable vectors and retained raster evidence.

## Install

Clone the repository into your Codex skills directory:

```bash
git clone https://github.com/bossccc1999-hue/literature-figure-svg.git ~/.codex/skills/literature-figure-svg
```

Then invoke it as `$literature-figure-svg`, or let Codex use it automatically when the request matches literature-figure SVG conversion.

Installing this repository installs the skill source, not its external runtimes. Requirements depend on the operation:

| Operation | Runtime requirements |
| --- | --- |
| Project scaffold | Python 3.10 or newer |
| PDF inventory | Python and PyMuPDF |
| SVG normalization | Python with `lxml`, Node.js, and `@napi-rs/canvas` |
| Native PPTX text base | Node.js and the host-provided `@oai/artifact-tool` runtime |
| Native geometry assembly and SVG/PPTX audit | Python with `lxml` |
| Rendering and application verification | An available renderer such as LibreOffice/Poppler; PowerPoint for an actual application roundtrip |
| Implemented plotting stubs | Matplotlib |

**`@oai/artifact-tool` is supplied by a compatible Codex host.** It is not bundled here, and this repository does not assume that it can be installed from the public npm registry. Discover the host's workspace dependencies and follow its installed presentations skill, including finalization requirements. `RUNTIME_NODE_MODULES`, `PPT_COMPAT_NODE`, and `PPT_COMPAT_CANVAS_MODULE` can point helpers to explicitly discovered runtime locations; see the [native PowerPoint workflow](references/native-powerpoint-workflow.md).

Without the host-provided presentation runtime, the independent scaffold, PDF inspection, normalization, and audit helpers can still be used when their own dependencies are available. Do not claim that the native PPTX pipeline ran in an environment where its authoring runtime is unavailable.

## Start a project

```bash
python scripts/scaffold_svg_project.py --output-dir work --name example_figure --type multi-panel
```

Add `--svg-only` to exclude the default native PPTX companion. The scaffold creates a plan and implementation stubs, not a finished figure. For PDF inspection:

```bash
python scripts/inspect_pdf.py source.pdf --output work/pdf_inventory.json
```

Follow the [native PowerPoint workflow](references/native-powerpoint-workflow.md) for normalization, native assembly, rendering, temporary ungrouping comparisons, and finalization. Helper-generated PPTX files are candidates until those checks are completed.

## Main files

- `SKILL.md`: skill entrypoint and routing rules.
- `references/vector-redraw-workflow.md`: guidance for diagrams, mechanisms, flowcharts, topology, and schematic panels.
- `references/data-plot-reconstruction.md`: guidance for plots and statistical figure panels.
- `references/native-powerpoint-workflow.md`: compatibility strategy, supported subset, runtime configuration, and verification.
- `scripts/scaffold_svg_project.py`: creates a reusable project folder for figure-redraw work.
- `scripts/inspect_pdf.py`: inventories PDF objects without dumping article body text.
- `scripts/normalize_svg.py`: prepares explicit vector geometry and text metadata.
- `scripts/build_native_base.mjs` and `scripts/build_native_pptx.py`: create an authoring-runtime text base and add native editable geometry.
- `scripts/audit_editability.py`: checks objects, references, media, and safe temporary group expansion.
- `evals/evals.json` and `evals/fixtures/`: regression scenarios and small original synthetic fixtures.
- `agents/openai.yaml`: display metadata for Codex.

## Accuracy boundary

- Exact vector recovery is only claimed for elements that are actually rebuilt and checked.
- Values reconstructed from a plot are marked `digitized`; illustrative values are marked `synthetic/demo`.
- Raw scientific images are not represented as fully vectorized evidence.
- Normalization supports an explicit subset. Unsupported constructs must be handled deliberately; they are not permission to drop objects or silently rasterize a claimed vector result.
- Native radial-gradient shading can approximate an SVG elliptical gradient. Visual checks and disclosure of material differences remain necessary.
- XML counts, renderer comparisons, and actual PowerPoint operations provide different evidence. Do not claim an application test that was not performed or guarantee identical rendering across all Office versions.
- PDF exports can contain renderer-created raster regions. Inspect the export before describing it as entirely vector.

## Rights and authorship

- This repository does not claim authorship of any source paper, published figure, dataset, or scientific result.
- No source paper PDF, publisher figure, or user's figure is included. The bundled PDF/SVG fixtures are small original synthetic test documents, not scientific evidence or third-party visual assets.
- The synthetic mixed-content fixture is not microscopy. The genuine-microscopy evaluation requires separately supplied, user-authorized empirical images.
- Source citations and license or permission notes belong in each generated project's `assumptions.md`.
- Users remain responsible for confirming whether their intended reuse, redistribution, or publication is permitted.

Repository code, instructions, and original test fixtures are released under the [0BSD license](LICENSE), which does not require attribution. Source literature and user-supplied materials are not covered by that license. External runtimes and libraries retain their own licenses and terms; they are not vendored or relicensed by this repository. See the [attribution audit](ATTRIBUTION_AUDIT.md) for the historical and current review scopes.
