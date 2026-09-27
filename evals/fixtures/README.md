# Small regression fixtures

These are small original/synthetic test documents, not scientific evidence and not the user's mechanism figure.

- `mechanism_raster.pdf`: image-only PDF; inspection should not classify it as native vector content.
- `vector_figure.pdf`: 5 extractable text spans, 7 vector paths, no raster image.
- `mixed_content_synthetic.pdf`: synthetic image + labels/vector; tests object classification only. It is not microscopy.
- `circleclip.svg`: a circle wider than 100 user units whose bounding box contains geometry outside the actual circle. The normalizer must remove the outside rectangle, preserve curved intersections, and eliminate the clip reference. This guards against an unsafe bounding-box clipping shortcut.

The genuine-microscopy scenario in `../evals.json` needs separate user-authorized empirical images. Do not substitute this synthetic mixed fixture and claim a real microscopy workflow has been visually validated.
