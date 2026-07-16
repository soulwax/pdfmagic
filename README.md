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
- [ ] Decide whether combined fill+stroke operators (`B`/`B*`/`b`/`b*`) need independent stroke-recolor handling — currently they're only ever treated as fills (see `walk.py` note); revisit if real-world testing finds a case where this drops a border that should have stayed
- [ ] `walk.py`'s CTM stack is saved/restored across `q`/`Q`, but the active fill/stroke color is not — a PDF that sets a light color inside a balanced `q ... Q` and relies on the outer color afterward could see a stale color used for later contrast decisions. Bounded to missed-recolor (never background-dropping or content loss); low real-world frequency. Fix would be to stack `(fill_color, stroke_color)` alongside the CTM in `walk_page`.
- [ ] Consider a `--dry-run` mode that only writes the audit report/overlay, no output PDF, for faster iteration on threshold tuning against a large file
- [ ] Consider whether `/Resources` inherited from a parent `/Pages` node (rather than set directly on the page) needs explicit resolution — current code assumes `page.Resources`/`page.mediabox` are directly accessible, which pikepdf's `.mediabox` property already handles; a page with inherited-only Resources currently lands in `failed_pages` rather than being silently mishandled, which is safe but not ideal

Whoever picks this up next: read the design spec first, then the plan above
— the plan has exact function signatures for every module, so cross-module
changes should update both this file's checklist and the relevant module's
docstring-level intent, not just the code.
