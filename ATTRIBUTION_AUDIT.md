# Attribution and Provenance Audit

## Current review: 2026-09-27

Scope: the source-tree update adding PDF inspection, controlled SVG normalization, native PowerPoint assembly, editability audits, documentation, and regression fixtures. External runtime installations and future user-supplied figures are outside this file-content review. The historical archive hash below identifies the earlier package, not this update.

No blocking attribution issue was identified in the reviewed source files and fixture metadata. This is a bounded file-content finding, not proof of authorship, chain of title, or a comprehensive dependency-license audit.

### Included material

- Reusable skill instructions and helper code remain under the repository's unchanged [0BSD license](LICENSE). Its existing contributors copyright notice is retained.
- The small fixtures in `evals/fixtures/` were created as original synthetic test documents for this update. They are not the user's mechanism figure, publisher figures, source papers, or experimental evidence.
- The three fixture PDFs intentionally exercise raster-only, vector/text, and mixed-content inspection. Their PDF author/creator metadata does not contain personal names or local paths. The mixed fixture is explicitly synthetic and is not microscopy.
- `circleclip.svg` is a small original geometry fixture for validating actual curved clipping rather than a bounding-box shortcut.
- The genuine-microscopy evaluation is a scenario requiring separately supplied, user-authorized images; no empirical microscopy data are bundled and no completed microscopy visual test is claimed.

### Dependencies and technical references

This update **does have external dependencies and technical references**. The earlier package's “no dependency” and “no external repository URL” observations must not be applied to the current tree.

- Python helpers use `lxml` and, for PDF inspection, PyMuPDF. Plotting stubs may use Matplotlib.
- Geometry operations use Node.js and `@napi-rs/canvas`; presentation text/base authoring uses `@oai/artifact-tool` supplied by a compatible host.
- `@oai/artifact-tool` is not bundled and is not represented as a public npm dependency available in every environment. Its runtime availability and the host's presentations workflow govern use of the native PPTX helpers.
- Optional render/application checks use separately provided tools, such as LibreOffice, Poppler, or PowerPoint.
- The helpers retain the SVG arc-method reference and the Microsoft DrawingML documentation links used to explain their implementation. These are technical references, not a claim of authorship of the underlying standards or documentation.
- No third-party library source, installed dependency directory, runtime binary, or dependency license is vendored in this source tree. External components retain their own licenses and terms; the repository's 0BSD license does not replace them.

### Source and privacy boundaries

- Existing requirements to record source citations, data provenance, and reuse permissions in generated projects remain in place.
- No user's source figure, paper PDF, publisher artwork, email address, credential, private key, or absolute personal filesystem path was identified in the reviewed release files. The public repository URL, XML namespace URIs, and documentation URLs are intentional references.
- The workflow distinguishes retained raster evidence from reconstructed vector objects. It does not acquire rights to source literature or make user-supplied material subject to this repository's license.

## Historical review: 2026-08-23

Reviewed archive SHA-256: `4efd58bc1528bd2d2160279fd3a1c813618355a6b3df3ffa4f4d3a2c5ebcb735`

The original report recorded no blocking attribution or authorship issue in that submitted package and reviewed release copy. Its scope was the earlier instructions/scaffold release, before the native PowerPoint helpers and synthetic PDF fixtures were added. The archived package has not been re-audited as part of this update.

The historical findings were:

- No named author, personal credit line, or third-party attribution claim was embedded in the skill files.
- No local user path, WeChat path, protected project path, or temporary source-project identifier was embedded in the release copy.
- No paper PDF, extracted published figure, or article image asset was bundled.
- No dependency, vendored library, copied code header, external repository URL, credential, or private key was reported present.
- Copyright-related guidance concerned source copying, citation, and permission boundaries.
- The package was a focused literature-figure SVG workflow rather than a copy of a broader research-mentor project.
- The public release used 0BSD without naming an individual author.

These statements describe the old review only. They do not imply that the current repository has no dependencies, URLs, copyright notice, or PDF files.

## Continuing release boundary

The repository contains reusable instructions, helper scripts, and explicitly identified original synthetic fixtures. It does not bundle source literature, publisher figures, or user-owned visual assets. Publication assumes the uploader is entitled to release the submitted material. Later contributions incorporating third-party material must retain applicable notices and comply with the relevant licenses.
