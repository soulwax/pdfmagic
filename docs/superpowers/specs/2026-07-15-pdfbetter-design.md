# pdfbetter — design spec

Date: 2026-07-15 (revised same day after API verification)

## Problem

Given an arbitrary PDF, produce a faithful, printer-friendly version of it: same
page layout and pagination, same text/images/line content, but with ink-heavy
decorative backgrounds (flat color fills, textures, full-bleed background
images) stripped to plain white. Real content — body text, illustrations,
photos, maps, separator/rule lines, table borders — must be preserved exactly,
not approximated.

Motivating example: `input/DND5.5e.pdf`, a large modern RPG rulebook with
heavy colored/dark full-bleed page backgrounds and white/light text, which is
expensive and impractical to print as-is.

## Revision note

The first draft of this spec (extract structured elements with `pdfplumber`,
rebuild the page from scratch with `reportlab`, re-embedding extracted fonts)
was tested against real synthetic PDFs before writing the implementation
plan. That testing found `reportlab`'s built-in TTF font embedding uses a
legacy, hand-rolled font parser that fails on real, valid, already-subsetted
fonts (reproducible `IndexError`/`could not find a suitable cmap encoding`
failures unrelated to font correctness — verified by loading the same bytes
successfully with `fontTools`). This meant "best-effort font fidelity" would
in practice degrade to fallback far more often than intended, undermining the
"very precise" requirement.

Testing also confirmed a better alternative: `pikepdf` can parse a page's
content stream into individual operators (`parse_content_stream`) and
reassemble an edited one (`unparse_content_stream`). This makes it possible
to edit the original content stream **surgically** — keep every original
operator (text-showing, font references, image painting, vector strokes)
completely untouched, and only remove the operators that paint background
fills/images, plus rewrite color operators for low-contrast text/strokes.
This was prototyped end-to-end (see below) and gives *exact* — not
best-effort — position, font, and color fidelity for all kept content, since
nothing kept is ever reinterpreted or redrawn. It also removes `reportlab`,
`fontTools`, and `pdfplumber` from the runtime dependency list entirely — the
whole runtime implementation needs only `pikepdf`.

This is the architecture described below, replacing the original
extract-and-rebuild design.

## Non-goals

- OCR of scanned image-only pages (no text/vector content to operate on — a
  scanned page is typically one full-page image; see Classification for how
  that's still handled).
- Reflowing or resizing content for different paper sizes — page geometry
  (`/MediaBox`) is untouched.
- General-purpose PDF editing tool — this does one transformation
  (background-strip + contrast-correct), not arbitrary edits.
- Content-aware classification (distinguishing "a large decorative photo the
  author intended to keep" from "a full-bleed background texture" by meaning,
  not just size). The keep/drop decision is a deterministic, threshold-based
  geometry heuristic. This is a known ceiling on classification precision
  (see Classification below) and is accepted as such — not solvable without
  content understanding (e.g. an LLM), which is explicitly out of scope.

## Architecture

Pipeline, per page: **parse → walk & classify → edit → reassemble**.

```text
source.pdf ──parse──> operator list ──walk──> per-op device-space bbox  ──edit──> new operator list ──reassemble──> output.pdf
              (pikepdf.parse_          + running graphics state            (drop background        (pikepdf.unparse_
               content_stream)         (CTM stack, fill/stroke              paint ops + their        content_stream,
                                        color, text-object flag)            XObject resource         page.Contents = ...)
                                                                             entries; wrap low-
                                                                             contrast paint ops
                                                                             in q/black-color/Q)
```

All non-content parts of the document (fonts, font programs, non-dropped
images, metadata, page structure, page count, `/MediaBox`) are untouched,
because they're never parsed into an intermediate representation and
reconstructed — they're the same PDF objects, saved back as-is.

### Parsing

`pikepdf.parse_content_stream(page)` (Apache-2.0/MPL-2.0) returns the page's
content stream as a flat list of `ContentStreamInstruction` (operator +
operands), in original stream order. This is the only parsing step; there is
no separate "extraction" phase producing a different data model.

### Walking & classification

A single forward pass over the instruction list maintains:

- A CTM stack: pushed/popped on `q`/`Q`, updated by `cm` (3×2 matrix, applied
  in PDF's row-vector convention).
- Current fill and stroke color + colorspace: updated by `rg`/`g`/`k`/`sc`/
  `scn` (fill) and `RG`/`G`/`K`/`SC`/`SCN` (stroke).
- Whether we're inside a `BT`...`ET` text object.

For each complete path-construction-then-paint sequence (`re`/`m`/`l`/`c`/`v`/
`y`/`h` ending in `f`/`f*`/`b`/`b*`/`B`/`B*`/`S`/`s`/`n`), the path's control
points are transformed through the current CTM to get a device-space bbox,
which is compared against the page's `/MediaBox` dimensions.

**Classification (background candidate → drop):** a *fill* operation (`f`/
`f*`/`b`/`b*`/`B`/`B*` with a fill component) whose device-space bbox covers
≥ a configurable threshold of both page width and height (default: 80%).
Stroke-only paints (`S`/`s`) are never classified as background regardless of
size — separator lines and table borders are always kept.

**Images:** each `Do` invoking an image XObject (not a form XObject) has its
bbox computed the same way (unit square transformed by current CTM). Same
80%-of-page-in-both-dimensions default threshold → drop.

This is a deterministic geometry heuristic — it cannot distinguish "a large
decorative photo the author intended to keep" from "a full-bleed background
texture" beyond size. Mitigated by:

- Conservative default threshold (80%), configurable via CLI/API.
- The audit mode (below), so misclassifications are visible and the
  threshold can be adjusted per document rather than discovered after the
  fact.

**Scanned/image-only pages:** if the page's only content is one full-page
image with no other operators, the same size-threshold rule applies — it is
dropped like any other oversized background image, and the resulting blank
page is flagged in the CLI/audit output (there is no text/vector content to
preserve on that page).

### Contrast correction

For a paint operation that is **kept** (not dropped as background), if its
active color (fill color for a text-show or vector fill; stroke color for a
stroke) has luminance above a configurable threshold (default 0.6, i.e. it
would be low-contrast against white), the specific operator(s) for that one
paint operation are wrapped:

```text
q
<black in the same colorspace: `0 g` / `0 0 0 rg` / `0 0 0 1 k`>
<original operator(s), unchanged>
Q
```

This changes color for exactly that paint operation without touching the
color-setting operator that established it (which may still apply,
correctly, to other later content) and without affecting graphics state
outside the inserted `q`/`Q` pair. Normal-contrast colors are left completely
unchanged, in their original colorspace — no RGB/CMYK round-tripping, because
the original operator is never rewritten, only optionally wrapped.

### Editing

Building the output instruction list from the walk's classification results:

- Dropped fill: keep the color-setting operator (harmless — it's simply
  never used for a paint), keep any `n`/state-reset operator, but omit the
  path-construction operators and the paint operator itself.
- Dropped image: omit only the `Do` operator; leave any surrounding `q`/`cm`/
  `Q` untouched (they become inert but harmless). Additionally remove the
  corresponding entry from the page's `/Resources/XObject` dictionary so the
  now-unused image data doesn't remain in the output file.
- Low-contrast kept paint: wrap as described above.
- Everything else: copied through unchanged, in order.

This targeted approach — never deleting `q`/`Q`/`cm`/color-setting operators,
only path/paint operators for drops and operand-preserving wraps for
recolors — means graphics-state balance can never be broken by an edit.

### Reassembly

`pikepdf.unparse_content_stream(instructions)` serializes the edited
instruction list; it's assigned back as the page's `/Contents`. The `Pdf`
object (with all untouched pages/resources/fonts/images) is saved as the
output PDF via `pdf.save(output_path)`.

### Audit mode

`--audit` produces, alongside the output PDF, a JSON report: every
drop/recolor decision made during the walk, with the page number, operation
type (fill/image/stroke-recolor/text-recolor), computed bbox and page
coverage fraction (for drops), and the reason. An optional debug PDF
duplicates the output with colored outline annotations over dropped-element
regions, so classification can be visually checked against the source before
trusting a full run — important given the classifier is a threshold
heuristic, not content-aware.

## Verification performed during design

Before writing the implementation plan, this architecture was prototyped
end-to-end against a synthetic PDF built with `reportlab` (one page: a
full-bleed dark background rect, white text in a custom *embedded* TrueType
font, a thin separator line, a small inline image):

- `pikepdf.parse_content_stream`/`unparse_content_stream` round-trip verified.
- Background rect correctly identified (100% page coverage) and removed;
  confirmed absent from the output (re-parsed with `pdfplumber`, used here
  only as an independent verification tool, not as a dependency).
- White text color operator correctly wrapped to render black; confirmed via
  re-extracted character color `(0.0, 0.0, 0.0)`.
- Separator line, inline image, and the embedded custom font reference all
  confirmed present and unchanged in the output.

This is materially stronger evidence than the original design had (which was
based on library documentation, not hands-on testing) — the original
extract-and-rebuild approach's font-embedding failure was only discovered by
building and running real fixtures.

## Components

| Module | Responsibility |
| --- | --- |
| `pdfbetter.geometry` | Pure functions: 3×2 PDF matrix composition, applying a matrix to a set of points, computing a bbox, computing page-coverage fraction. No PDF I/O. |
| `pdfbetter.walk` | Walks a page's parsed instruction list; yields `PaintOp` records (kind: fill/stroke/image/text-show, device-space bbox where applicable, active color+colorspace, instruction index range). Pure function of the instruction list + initial state. |
| `pdfbetter.classify` | Pure function: `PaintOp` + `Thresholds` → decision (keep/drop) + reason string (for fills/images), or contrast decision (recolor/leave) + reason (for kept paints). |
| `pdfbetter.edit` | Pure function: original instruction list + classified `PaintOp`s → new instruction list (drops applied, low-contrast wraps inserted) + set of XObject resource names to remove. |
| `pdfbetter.audit` | Turns classification results into the JSON report and (optionally) a debug overlay PDF. |
| `pdfbetter.pipeline` | Orchestrates parse → walk → classify → edit → reassemble for every page of a document; removes dropped XObject resource entries; writes the output PDF (+ audit artifacts). Public API: `process(input_path, output_path, **options)`. |
| `pdfbetter.cli` | Thin CLI over `pipeline` (e.g. `pdfbetter input.pdf -o output.pdf [--bg-threshold 0.8] [--audit]`). |

`pipeline` is the only module that touches `pikepdf.Pdf`/page objects
directly for I/O; `geometry`/`walk`/`classify`/`edit` operate on plain data
(instruction lists, dataclasses) and have no I/O, so they're independently
unit-testable without constructing PDF files.

## Data flow

1. CLI or API caller invokes `pipeline.process(input_path, output_path, **options)`.
2. `pipeline` opens the source with `pikepdf.open`.
3. For each page: `pikepdf.parse_content_stream` → `walk` (produces `PaintOp`
   records with bboxes/colors) → `classify` (tags each `PaintOp` keep/drop or
   recolor/leave) → `edit` (produces the new instruction list + XObject names
   to drop).
4. `pipeline` removes the dropped XObject resource entries from the page's
   `/Resources`, reassembles the content stream with
   `pikepdf.unparse_content_stream`, and assigns it to `page.Contents`.
5. After all pages are processed, `pipeline` saves the `Pdf` object to
   `output_path`.
6. If `--audit`, `audit` writes the JSON report and (optionally) the debug
   overlay PDF alongside the output, from the classification results
   accumulated across all pages.

## Error handling

- Encrypted/corrupt source PDFs: fail fast with an error naming the file and
  cause (raised by `pikepdf.open`; not caught, surfaces directly). No
  partial/silent output.
- A page whose content stream contains operators this walker doesn't
  recognize (rare, non-standard operators): those operators are passed
  through unchanged (never dropped or rewritten) — the walker only acts on
  the specific operators it explicitly recognizes for classification, so
  unrecognized content is always preserved, never lost.
- A page that becomes fully blank after dropping (scanned image-only page
  whose single image was classified as background): reported as a warning
  with the page number, not a hard failure.
- Any single-page processing failure is reported with the page number and
  does not abort processing of the remaining pages; the run ends with a
  non-zero exit code and a summary if any page failed.

## Testing

- Unit tests for `geometry` (matrix composition, point transforms, bbox/
  coverage math) using plain numeric fixtures — no PDF involved.
- Unit tests for `walk` and `classify` using hand-built instruction lists
  (lists of `pikepdf.ContentStreamInstruction` constructed directly in the
  test) — no PDF file needed for these either.
- Unit tests for `edit` given a classified `PaintOp` list — asserting the
  produced instruction list has the expected operators removed/wrapped.
- End-to-end test: a small synthetic PDF built with `reportlab` (dev/test-only
  dependency — never imported by the package itself) in the test suite: one
  page with a full-bleed dark background rect, white text in a custom
  embedded TrueType font, a thin separator line, and a small inline image.
  Run through the full pipeline; assert (via `pikepdf`, re-parsing the
  output's content stream, and via `pdfplumber`, a dev/test-only dependency,
  for convenient readback) that: the background fill is gone, the text is
  black at its original position, the separator line and image are
  unchanged, and the embedded font's `FontFile2` bytes are byte-identical
  between source and output.
- `input/DND5.5e.pdf` is used for manual/integration smoke-testing only (too
  large for CI); not committed to git (already excluded via `.gitignore`).

## Packaging

- `src/pdfbetter/` layout.
- `pyproject.toml`, hatchling build backend, managed via `uv`.
- Console-script entry point: `pdfbetter`.
- Runtime dependency: `pikepdf` only.
- Dev dependencies: `pytest`, `reportlab` and `pillow` (building synthetic
  test-fixture PDFs), `pdfplumber` (convenient readback assertions in tests).
- `requirements.txt` (runtime) and `requirements.dev.txt` (dev, includes
  runtime + dev deps) generated alongside `pyproject.toml` for users who
  prefer plain pip installs over `uv`/PEP 621 resolution.
- Distribution name and import package: `pdfbetter`.
- `README.md` doubles as project documentation and an in-repo, TODO-list-
  bearing guidance document in the spirit of a `CLAUDE.md` — descriptive on
  its face, but structured so an agentic coding tool reading it finds
  current status/next steps without a separate file.
