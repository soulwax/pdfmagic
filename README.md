# pdfbetter

Strip ink-heavy backgrounds out of a PDF and get back a faithful,
printer-friendly copy: full-bleed dark fills and background images are
removed, low-contrast text/lines are recolored to black, and everything
else — real images, separator lines, table borders, exact text position,
exact fonts, non-background colors — is carried through byte-for-byte. No
page is ever redrawn from scratch: the original content stream is edited in
place, so fonts and positions are never approximated.

## Install

```bash
uv pip install -e ".[dev]"
```

## Use

```bash
pdfbetter input.pdf -o output.pdf
pdfbetter input.pdf -o output.pdf --bg-threshold 0.7   # more aggressive background stripping
pdfbetter input.pdf -o output.pdf --audit              # also writes output.pdf.audit.json + output.pdf.debug.pdf
```

Or as a library:

```python
from pdfbetter.pipeline import process
process("input.pdf", "output.pdf")
```

## Rasterize/upscale mode

For PDFs with no text/vector layer to preserve (fully rasterized/scanned
PDFs — one full-page image per page, the surgery mode's target case doesn't
apply), a second mode renders each page to an image, optionally trims fixed
margins, upscales it with
[Real-ESRGAN](https://github.com/xinntao/Real-ESRGAN) (`realesrgan-ncnn-vulkan`,
an external prerequisite you install yourself — `scoop install
realesrgan-ncnn-vulkan` on Windows, the upstream project's own release
archives on macOS/Linux), and reassembles the result into a new PDF.
Requires the `rasterize` extra:

```bash
uv pip install -e ".[rasterize]"
uv run pdfbetter input.pdf --mode rasterize
uv run pdfbetter input.pdf --mode rasterize --render-dpi 150       # faster/smaller than the 300 default
uv run pdfbetter input.pdf --mode rasterize --crop-x 20 --crop-y 40 # trim a 20pt/40pt scanner-bed border
uv run pdfbetter input.pdf --mode rasterize --realesrgan-path /custom/path/to/realesrgan-ncnn-vulkan
```

Output pages are images (no selectable text) — this mode trades text
selectability for the only real quality improvement available when there's
no text layer to begin with. Default upscale factor is 2x (not
realesrgan-x4plus's native 4x) — at the default 300 DPI render, that's
~600 DPI-equivalent output, well above standard print quality without the
impractical processing time/file size of a full 4x pass on a large book.

## How it works

See `docs/superpowers/specs/2026-07-15-pdfbetter-design.md` for the full
design (content-stream surgery via `pikepdf`: parse the page's operators,
walk them tracking graphics state, classify each fill/image as
background-or-not by page-coverage fraction, drop the background ones,
recolor low-contrast kept text/strokes in place, reassemble -- kept fills
are never recolored, only dropped or left as-is). The implementation
plan with task-by-task status is
`docs/superpowers/plans/2026-07-15-pdfbetter-implementation.md`.

## Status / next up

- [x] Geometry (matrix math, bbox coverage) — `src/pdfbetter/geometry.py`
- [x] Color model + luminance + black-operator construction — `src/pdfbetter/color.py`
- [x] Content-stream walker — `src/pdfbetter/walk.py`
- [x] Classification against configurable thresholds — `src/pdfbetter/classify.py`
- [x] Instruction-list editing — `src/pdfbetter/edit.py`
- [x] Audit JSON report + debug overlay — `src/pdfbetter/audit.py`
- [x] Pipeline orchestration + end-to-end test — `src/pdfbetter/pipeline.py`
- [x] CLI — `src/pdfbetter/cli.py`
- [x] Manual smoke test against `input/DND5.5e.pdf` — found the file is fully rasterized (one full-page image per page, no text layer), which was dropping every page to blank; led directly to the Task 11 safety rule (never drop content that would leave a page blank)
- [x] Fixed: dropping a background image no longer mutates `page.Resources.XObject` in place — real PDFs can share one Resources object across pages, so a page-scoped copy is built before removing anything (see `pipeline.py`)
- [x] Rasterize/upscale mode (`--mode rasterize`) — `src/pdfbetter/rasterize.py`, `src/pdfbetter/crop.py`, `src/pdfbetter/upscale.py`, `src/pdfbetter/rasterize_upscale_pipeline.py`
- [ ] Manual smoke test of `--mode rasterize` against `input/DND5.5e.pdf` at the full 300 DPI default (only tested at 96 DPI so far, for turnaround time) — confirm the default is actually practical on a 387-page file, or reconsider it
- [ ] Decide whether combined fill+stroke operators (`B`/`B*`/`b`/`b*`) need independent stroke-recolor handling — currently they're only ever treated as fills (see `walk.py` note); revisit if real-world testing finds a case where this drops a border that should have stayed
- [ ] `walk.py`'s CTM stack is saved/restored across `q`/`Q`, but the active fill/stroke color is not — a PDF that sets a light color inside a balanced `q ... Q` and relies on the outer color afterward could see a stale color used for later contrast decisions. Bounded to missed-recolor (never background-dropping or content loss); low real-world frequency. Fix would be to stack `(fill_color, stroke_color)` alongside the CTM in `walk_page`.
- [ ] Consider a `--dry-run` mode that only writes the audit report/overlay, no output PDF, for faster iteration on threshold tuning against a large file
- [ ] Consider whether `/Resources` inherited from a parent `/Pages` node (rather than set directly on the page) needs explicit resolution — current code assumes `page.Resources`/`page.mediabox` are directly accessible, which pikepdf's `.mediabox` property already handles; a page with inherited-only Resources currently lands in `failed_pages` rather than being silently mishandled, which is safe but not ideal

Whoever picks this up next: read the design spec first, then the plan above
— the plan has exact function signatures for every module, so cross-module
changes should update both this file's checklist and the relevant module's
docstring-level intent, not just the code.
