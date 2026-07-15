# pdfbetter — design spec

Date: 2026-07-15

## Problem

Given an arbitrary PDF, produce a faithful, printer-friendly version of it: same
page layout and pagination, same text/images/line content, but with ink-heavy
decorative backgrounds (flat color fills, textures, full-bleed background
images) stripped to plain white. Real content — body text, illustrations,
photos, maps, separator/rule lines, table borders — must be preserved, not
approximated.

Motivating example: `input/DND5.5e.pdf`, a large modern RPG rulebook with
heavy colored/dark full-bleed page backgrounds and white/light text, which is
expensive and impractical to print as-is.

## Non-goals

- OCR of scanned image-only pages (no text layer to extract).
- Reflowing or resizing content for different paper sizes — page geometry is
  preserved exactly.
- General-purpose PDF editing tool — this does one transformation
  (background-strip + faithful rebuild), not arbitrary edits.
- 100%-guaranteed font fidelity for every exotic font type (see Fonts below) —
  best effort with explicit, itemized reporting when it isn't achieved.
- Using an LLM to make classification judgment calls. The keep/drop and
  contrast decisions are deterministic, threshold-based heuristics, not model
  inference. This is a known ceiling on classification precision (see
  Classification below) and is accepted as such.

## Architecture

Pipeline, per page: **extract → classify → recolor → rebuild**.

```
source.pdf ──extract──> page elements ──classify──> tagged elements ──rebuild──> output.pdf
                (text runs,              (keep/drop +                 (white page,
                 images,                  contrast fix)                 kept elements
                 vector shapes,                                         at original
                 fonts, colors)                                         position)
```

### Extraction

- `pdfplumber` (MIT, built on `pdfminer.six`): per-page layout extraction —
  character/text runs (font name, size, position, native color), image
  elements (bbox, position in page z-order), vector shapes (rects, lines,
  curves; fill/stroke color, width, bbox).
- `pikepdf` (Apache-2.0/MPL-2.0 dual): structural access `pdfplumber` doesn't
  expose — embedded font program streams
  (`/Resources/Font/.../FontDescriptor/FontFile*`) and raw colorspace objects
  per element (RGB / Gray / CMYK / Indexed), so color reproduction doesn't
  round-trip through a single lossy internal representation.
- Coordinates and color values are carried through as extracted — no
  rounding, no reflow.

### Classification

A page element (vector fill or image) is a **background candidate** — dropped
— if its bbox covers a large fraction of the page (default threshold: ≥80% of
both page width and height), configurable via CLI/API. Everything else (thin
lines, table borders, small-to-medium rects, inline images, illustrations,
maps, icons) is **kept** unchanged.

This is a deterministic size/position heuristic, not content-aware
classification — it cannot distinguish "a large decorative photo the author
intended to keep" from "a full-bleed background texture" beyond size and
z-order. This is the known ceiling mentioned in Non-goals. Mitigated by:

- Conservative default threshold (80%) tuned against real samples.
- The audit mode (below), so misclassifications are visible and threshold can
  be adjusted per document rather than discovered after the fact.

### Contrast recoloring

Any **kept** text or stroke whose original color would be low-contrast against
white (light/pale/white colors, luminance above a configurable threshold) is
recolored to black. Elements that already have reasonable contrast against
white are left at their original color, in their original colorspace (RGB
stays RGB, CMYK stays CMYK — no forced conversion).

### Font handling

For each distinct font used in the document:

1. Extract the embedded font program via `pikepdf` (reads the
   `FontDescriptor`'s `FontFile`/`FontFile2`/`FontFile3` stream).
2. Validate/normalize it with `fontTools` (MIT) into a form `reportlab` can
   register (TTF/OTF).
3. Register with `reportlab` (`pdfmetrics.registerFont`) and use it for all
   text runs in that font.

If extraction or re-embedding fails for a given font (Type 3 bitmap fonts,
some CID-keyed or DRM'd fonts, corrupt font streams), fall back to the closest
standard font **and record the fallback** in the audit report — this must
never happen silently. This is the highest-risk, highest-effort part of the
system; the goal is best-effort exact match with full transparency when it
isn't achieved, not a guarantee of 100% coverage.

### Rebuild

`reportlab` (BSD) constructs the output PDF: one white page per source page,
same dimensions/orientation, with kept elements drawn at their original
(unrounded) position:

- Text runs: original font (via the registered font from step above, or
  fallback), size, position, and color (original or contrast-corrected).
- Images: unchanged, original position/size.
- Vector shapes: original position, stroke width, and color (or
  contrast-corrected) — including redrawn separator/rule lines and table
  borders.

### Audit mode

`--audit` produces, alongside the output PDF:

- A JSON report: every extracted element, its keep/drop classification and
  the reason (e.g. "dropped: covers 94% of page, z-order 0"), and every font
  fallback that occurred with the reason.
- An optional debug PDF: a copy of the output with colored outlines over
  dropped-element regions, so classification can be visually checked against
  the source before trusting a full run — important given the classifier is a
  threshold heuristic, not content-aware.

## Components

| Module | Responsibility |
|---|---|
| `pdfbetter.extract` | Wrap `pdfplumber` + `pikepdf`; produce structured per-page data: `TextRun`, `ImageElement`, `VectorElement`, each carrying native colorspace and unrounded geometry. |
| `pdfbetter.classify` | Pure functions: element + `Thresholds` config → tagged (keep/drop) element, with reason string. No I/O. |
| `pdfbetter.contrast` | Pure function: color + colorspace → corrected color (black) if low-contrast against white, else unchanged. |
| `pdfbetter.fonts` | Extract embedded font programs (`pikepdf`), normalize (`fontTools`), register with `reportlab`; track fallbacks. |
| `pdfbetter.build` | Wrap `reportlab`; take filtered/recolored per-page data + registered fonts, write output PDF. |
| `pdfbetter.audit` | Produce the JSON report and debug overlay PDF from classification/font-fallback results. |
| `pdfbetter.pipeline` | Orchestrate extract → classify → contrast → build (+ audit) for a whole document. Public API: `process(input_path, output_path, **options)`. |
| `pdfbetter.cli` | Thin CLI over `pipeline` (e.g. `pdfbetter input.pdf -o output.pdf [--bg-threshold 0.8] [--audit]`). |

`pipeline` is the only module the CLI depends on; `extract`/`classify`/
`contrast`/`fonts`/`build`/`audit` are independently testable and have no
dependency on each other beyond the data types they pass.

## Data flow

1. CLI or API caller invokes `pipeline.process(input_path, output_path, **options)`.
2. `extract` reads the source PDF once, yields a list of per-page structured
   elements (`TextRun`/`ImageElement`/`VectorElement`) plus the set of fonts
   used.
3. `fonts` resolves each used font to a registered reportlab font (or
   fallback + reason).
4. `classify` tags each element keep/drop with a reason.
5. `contrast` recolors kept text/stroke elements where needed.
6. `build` writes the output PDF from kept, recolored elements + resolved
   fonts.
7. If `--audit`, `audit` writes the JSON report and (optionally) the debug
   overlay PDF alongside the output.

## Error handling

- Encrypted/corrupt source PDFs: fail fast with an error naming the file and
  cause. No partial/silent output.
- A page with no extractable text (pure scanned image): passed through with
  only the oversized-image background rule applied; flagged in CLI output
  (not a hard failure) since there's no text layer to reposition.
- A font that can't be extracted/re-embedded: fallback + audit record (see
  Font handling), never a hard crash for one bad font in a large document.
- Any single-page processing failure is reported with the page number and
  does not abort processing of the remaining pages; the run ends with a
  non-zero exit code and a summary if any page failed.

## Testing

- Unit tests for `classify` and `contrast` (pure functions) using small
  synthetic fixtures — no large PDF dependency.
- Unit tests for `fonts` fallback behavior using a deliberately broken/
  unsupported embedded font fixture.
- End-to-end test: a small synthetic PDF built with `reportlab` in the test
  suite itself (one page: a large dark background rect, white text on top,
  a thin separator line, a small inline image, one embedded custom font) run
  through the full pipeline, asserting the output has a white background,
  black (contrast-corrected) text at the original position, the separator
  line preserved, and the image preserved.
- `input/DND5.5e.pdf` is used for manual/integration smoke-testing only (too
  large for CI); not committed to git (already excluded via `.gitignore`).

## Packaging

- `src/pdfbetter/` layout.
- `pyproject.toml`, hatchling build backend, managed via `uv`.
- Console-script entry point: `pdfbetter`.
- Runtime dependencies: `pdfplumber`, `pikepdf`, `fonttools`, `reportlab`.
- Dev dependencies: `pytest`.
- Distribution name and import package: `pdfbetter`.
