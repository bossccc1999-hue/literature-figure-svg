# Data Plot Reconstruction

Use this reference for literature plots that need editable SVG output: bar charts, line charts, scatter plots, survival curves, heatmaps, forest plots, radar charts, stacked areas, and multi-panel statistical figures.

## Data Boundary

Classify the data source before plotting:

- `original-data`: user supplied raw data, table, CSV, spreadsheet, or extracted source data.
- `digitized`: values manually or programmatically digitized from a published plot; report expected uncertainty.
- `synthetic/demo`: illustrative reconstruction used only to match structure or style; never describe as original experimental data.
- `unknown`: source data unavailable; avoid numeric claims and ask for data if exact values matter.

The output must not silently replace missing data with invented values.

## Reconstruction Routes

- If raw data are available, rebuild the plot from the raw data and export SVG/PDF/PNG.
- If only a screenshot is available and approximate visual reuse is acceptable, digitize visible points or bars and mark the result as `digitized`.
- If only the structure matters, use synthetic/demo values and state that the plot is a structural template.
- If the plot contains microscopy/photo panels plus charts, split the package: charts are code-generated, images remain raster with vector annotations.

## Plotting Requirements

- Keep graph text editable in SVG. For Matplotlib:

```python
import matplotlib.pyplot as plt

plt.rcParams["svg.fonttype"] = "none"
plt.rcParams["pdf.fonttype"] = 42
plt.rcParams["ps.fonttype"] = 42
```

- Preserve axis labels, units, legend semantics, group order, and error-bar meaning.
- Distinguish SD, SEM, CI, IQR, and range. If unclear, mark `[needs confirmation]`.
- Keep panel labels outside data-dense regions.
- Export a preview PNG so the user can inspect the figure quickly.

## Common Pitfalls

- Screenshot-to-SVG tracing produces many meaningless paths and non-editable text; use it only as a rough visual aid, not as a scholarly redraw.
- Digitized curves can be useful for visual reconstruction but should not be used as verified source data unless the user accepts that limitation.
- Do not use AI image generation for axes, tick labels, equations, curves, p-values, or circuit symbols.
- Do not remove uncertainty bands, risk tables, colorbars, legends, or sample-size labels just to make the figure cleaner.

## Validation Checklist

- Data source class is recorded in `assumptions.md`.
- Script, data file, and output file names match the manifest.
- SVG text remains editable.
- PDF does not convert all text to paths unless the user specifically requested outlined fonts.
- Preview matches the intended journal width and remains readable at 50% scale.
- Synthetic/demo labels are removed from the formal figure canvas but retained in assumptions and metadata.
