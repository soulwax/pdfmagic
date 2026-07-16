# pdfbetter — rasterize/upscale mode design

Date: 2026-07-16

## Problem

The existing `pdfbetter` pipeline (content-stream surgery via `pikepdf`) only
helps PDFs that have real vector/text content to separate from a background —
it explicitly cannot improve a fully rasterized PDF (one full-page image per
page, no text layer), which is exactly what the project's own real sample
file (`input/DND5.5e.pdf`) turned out to be (see
`docs/superpowers/specs/2026-07-15-pdfbetter-design.md`'s Task 11 finding).

For that class of PDF, the only way to actually improve output quality is
"the old-fashioned way": rasterize each page to an image, run it through an
image super-resolution model, and reassemble the upscaled images into a new
PDF. This spec adds that as a second, independent mode.

## Non-goals

- Blending this with the existing surgery pipeline — the two modes are
  mutually exclusive and never combined on the same run.
- Bundling, vendoring, or auto-downloading the `realesrgan-ncnn-vulkan`
  binary — it remains an external prerequisite the user installs themselves
  (scoop on Windows; the upstream project's own release archives on
  macOS/Linux).
- OCR or text-layer reconstruction — output pages are images, exactly like
  the input in this mode; there is no selectable text, by design (matching
  what the user asked for).
- Supporting arbitrary Real-ESRGAN models beyond the two named here — model
  selection is a fixed default (`realesrgan-x4plus`) with an escape hatch to
  name a different model file, not a curated model library.

## Architecture

A second pipeline, selected by a CLI mode flag, entirely separate from the
existing one:

```text
source.pdf ──rasterize──> page images (PNG, per-page, temp dir)
                              │
                          ──crop── (trim fixed margins, in-place, optional)
                              │
                          ──upscale── (one batch realesrgan-ncnn-vulkan call)
                              │
                          upscaled images (temp dir)
                              │
                          ──reassemble── (pikepdf: one full-page image per page)
                              │
                            output.pdf
```

This design was revised after reviewing the user's own prior, hand-built
version of this exact workflow (`inspiration/cut.py`, `inspiration/upscale.py`
— informative precedent, not treated as binding truth). Two concrete changes
came from that review: a margin-cropping step exists in the validated prior
workflow and was missing from the first draft of this spec entirely, and the
prior workflow's validated upscale scale factor is `2`, not `4` (see
Upscale below).

### Crop

`pdfbetter/crop.py` (new module) trims a fixed margin off each rendered page
image before upscaling — the prior workflow used this to remove scanner-bed
white borders so the upscaler doesn't spend resolution on blank margin and
the final page is tightly cropped to content. Unlike the prior script (which
hardcoded raw pixel counts tied to whatever DPI it happened to render at),
margins are specified in **points** (1/72 inch — the same unit PDF page
geometry already uses throughout `pdfbetter`), converted to pixels
internally using the actual `--render-dpi` in effect, so a given margin
means the same physical trim regardless of render resolution. Symmetric per
axis (one horizontal margin trimmed from both left and right, one vertical
margin trimmed from both top and bottom), matching the prior script's shape
rather than four independent per-side values — real scanned-page borders are
typically even. Default: no cropping (`0pt` both axes) — opt-in, since not
every source PDF has a border to trim.

### Rasterize

`pdfbetter/rasterize.py` (new module) uses `pypdfium2` (BSD/Apache-2,
permissive, ships prebuilt wheels for Windows/macOS/Linux — no external
system binary needed for this step) to render each page of the source PDF
to a PNG file at a configurable DPI (default: 300), written into a temporary
directory, one file per page, named so page order is preserved by a simple
lexicographic sort (zero-padded page index).

### Upscale

`pdfbetter/upscale.py` (new module) locates the `realesrgan-ncnn-vulkan`
executable — first an explicit `--realesrgan-path` CLI argument, then a
`PDFBETTER_REALESRGAN_PATH` environment variable, then a PATH lookup
(`shutil.which`) — and, if none resolve, raises immediately with a clear,
per-OS-aware message pointing at how to install it (scoop on Windows; the
upstream project's release page for macOS/Linux) **before any rasterization
work happens**, so a missing binary never wastes time rendering pages first.

If found, it's invoked **once**, as a single batch subprocess call over the
whole staged input directory (`-i <in_dir> -o <out_dir> -n realesrgan-x4plus
-s 2 -t <tile> -j <threads> [-x]`), rather than once per page — this is both
faster (one process startup/model load instead of hundreds) and matches how
the tool is designed to be used. The model name is configurable via
`--realesrgan-model` for users who want a different bundled model (e.g. the
anime variant), but `realesrgan-x4plus` is the default and the one this
feature was built around ("optimised for text" in practice means: not the
anime-tuned variants, which distort fine linework/text) — this matches the
prior workflow's own validated choice.

**Scale factor is `2`, not `4`**, again matching the prior workflow — even
though `realesrgan-x4plus` is a 4x-trained model, `-s 2` requests a lower
output multiplier than the model's native scale (the binary still runs the
model internally and downsamples to the requested output scale). With the
default `--render-dpi 300`, effective output resolution is ~600 DPI —
comfortably above standard print quality (300 DPI) without the impractical
file size/processing time of a full 4x (~1200 DPI-equivalent) multiplier on
a large multi-hundred-page book.

Three more tuning flags are exposed, matching tunables the prior workflow
already found necessary in practice: `--realesrgan-tile` (tile size passed
as `-t`; `0` = auto, the default; raising it can reduce per-tile overhead on
a GPU with enough VRAM headroom), `--realesrgan-threads` (load:proc:save
thread counts passed as `-j`; default `1:2:2`), and `--realesrgan-tta`
(passes `-x`, enabling test-time augmentation — marginally cleaner output at
roughly 8x the processing time; off by default, since the prior workflow's
own assessment was "usually not worth it for text").

### Reassemble

Folded into the orchestrating module (`pdfbetter/rasterize_upscale_pipeline.py`,
new): builds a fresh `pikepdf.Pdf`, one page per upscaled image, page size
matching the image's pixel dimensions at the target DPI, image embedded as a
single full-page XObject. No new dependency for this step — `pikepdf` is
already a dependency of the core package.

## CLI integration

New flags on the existing `pdfbetter` command (not a new command):

- `--mode {surgery,rasterize}` (default: `surgery`, today's unchanged
  behavior).
- `--render-dpi` (default: `300`) — only meaningful in `rasterize` mode;
  the pre-upscale render resolution. With the default scale of `2`, the
  effective final resolution is 2x this value (300 → ~600 DPI-equivalent).
  This is still a real speed/size/quality tradeoff on a large book; the
  flag exists precisely so it can be lowered (e.g. `150` or `96`) per-file
  without changing the tool's default.
- `--crop-x` / `--crop-y` (default: `0` both — no cropping) — margin, in
  points, trimmed from both left+right (`--crop-x`) and both top+bottom
  (`--crop-y`) of every rendered page before upscaling.
- `--realesrgan-path` (default: none, falls back to env var then PATH
  lookup as described above).
- `--realesrgan-model` (default: `realesrgan-x4plus`).
- `--realesrgan-tile` (default: `0`, auto).
- `--realesrgan-threads` (default: `1:2:2`).
- `--realesrgan-tta` (default: off).

`--mode rasterize` is incompatible with `--bg-threshold`/
`--contrast-luminance`/`--audit` (those are surgery-mode-only); passing them
together with `--mode rasterize` is a usage error, reported clearly, not
silently ignored.

## Dependencies

`pypdfium2` and `pillow` (needed to bridge `pypdfium2`'s rendered bitmap to
a PNG file, and already a dev-only dependency of the existing test suite)
become an **optional** runtime dependency group: `pip install
pdfbetter[rasterize]`. The default install (`pip install pdfbetter`) stays
`pikepdf`-only, unchanged — only users who invoke `--mode rasterize` need
the extra installed; `cli.py` gives a clear, actionable error naming the
extra to install if `--mode rasterize` is selected but `pypdfium2`/`pillow`
aren't importable, rather than an ugly `ImportError` traceback.

`realesrgan-ncnn-vulkan` is never a Python dependency at all — it's an
external binary the user installs themselves, located at runtime.

## Error handling

- Missing `realesrgan-ncnn-vulkan` binary: fail before any rasterization,
  clear message with install pointers.
- Missing `pypdfium2`/`pillow` when `--mode rasterize` is selected: fail
  immediately with a message naming `pip install pdfbetter[rasterize]`.
- Subprocess failure (non-zero exit from the upscaler): the run fails as a
  whole, surfacing the subprocess's stderr in the error message. This mode
  does not attempt the existing surgery pipeline's per-page failure
  isolation — it processes the whole document as one batch for speed, so a
  failure means "this run didn't produce output," reported plainly rather
  than left silently partial.
- Incompatible flag combinations (surgery-only flags passed with `--mode
  rasterize`): usage error before any processing begins.

## Testing

- Unit tests for `rasterize.py` using a small synthetic PDF (built with
  `reportlab`, already a dev dependency), asserting the expected number of
  PNG files are produced with roughly the expected pixel dimensions for a
  given DPI.
- Unit tests for `crop.py`: points-to-pixels conversion at a given DPI, and
  the crop itself against a synthetic image, including the "margins too
  large for this image" error case.
- Unit tests for `upscale.py` with the subprocess call mocked/stubbed (no
  dependency on the real binary or a GPU in CI) — asserting the correct
  command-line arguments are constructed (including `-t`/`-j`/`-x`), and
  that binary-not-found / subprocess-failure cases raise the expected clear
  errors.
- Unit tests for the reassembly step building a PDF from a couple of
  synthetic PNGs and asserting page count/dimensions.
- An end-to-end test that actually shells out to `realesrgan-ncnn-vulkan`
  is out of scope for the automated suite (same reasoning as the existing
  `input/DND5.5e.pdf` smoke test — needs a real binary and, here, a real
  GPU) — covered by a manual smoke-test step instead, run once against the
  real sample file.

## Packaging

- `pyproject.toml` gains `[project.optional-dependencies].rasterize =
  ["pypdfium2>=4.0", "pillow>=10.0"]`.
- `requirements.txt`/`requirements.dev.txt` are unaffected (the core
  install stays `pikepdf`-only); a note is added to the README on how to
  install the `rasterize` extra.
