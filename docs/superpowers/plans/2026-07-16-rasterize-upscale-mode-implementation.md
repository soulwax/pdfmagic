# Rasterize/Upscale Mode Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a second, independent processing mode to `pdfbetter` — `--mode rasterize` — that renders each PDF page to an image, optionally trims fixed margins, upscales it with `realesrgan-ncnn-vulkan`, and reassembles the result into a new PDF, for PDFs (like the project's own real sample file) that have no text/vector layer for the existing surgery mode to work with.

**Architecture:** Four new modules (`rasterize.py`, `crop.py`, `upscale.py`, `rasterize_upscale_pipeline.py`) mirroring the existing package's separation of concerns, plus `cli.py` integration behind a `--mode` flag. `pypdfium2` renders pages to PNG; an optional crop step trims fixed margins (specified in points, converted to pixels at the render DPI); `realesrgan-ncnn-vulkan` (external binary, located via explicit flag/env var/PATH, never bundled) upscales the whole staged folder in one batch subprocess call; `pikepdf` (already a core dependency) reassembles the upscaled images into a new PDF, one full-page image per page. Default upscale scale factor is `2` (not the model's native `4`) and default `--render-dpi` is `300`, giving ~600 DPI-equivalent output — both values, along with the `realesrgan-x4plus` model choice, come from the project owner's own prior, hand-validated version of this exact workflow (`inspiration/cut.py`, `inspiration/upscale.py` — informative precedent, used as a reference during design, not treated as binding truth or copied verbatim).

**Tech Stack:** Python ≥3.10, `pypdfium2` + `pillow` (new, optional runtime extra `pdfbetter[rasterize]`), `pikepdf` (existing core dependency, no new use beyond what's already verified working), `realesrgan-ncnn-vulkan` (external binary, invoked via `subprocess`).

## Global Constraints

- Python ≥3.10.
- `pypdfium2`/`pillow` are an **optional** runtime extra (`pdfbetter[rasterize]`) — the default `pip install pdfbetter` stays `pikepdf`-only. `cli.py` must give a clear, actionable error naming the extra if `--mode rasterize` is used without it installed, never a raw `ImportError` traceback.
- `realesrgan-ncnn-vulkan` is never a Python dependency and is never bundled/downloaded — it's an external prerequisite located at runtime (explicit `--realesrgan-path` > `PDFBETTER_REALESRGAN_PATH` env var > PATH lookup), with a clear error naming install instructions if not found.
- The binary-missing check must happen **before** any rasterization work — never render pages only to discover upscaling can't run.
- Default upscale scale factor is `2`; default model is `realesrgan-x4plus`; default `--render-dpi` is `300`.
- Crop margins (`--crop-x`/`--crop-y`) are specified in points (1/72 inch), converted to pixels internally using the actual render DPI — never raw pixels — and default to `0` (no cropping).
- `--mode rasterize` is incompatible with `--bg-threshold`/`--contrast-luminance`/`--audit` (surgery-mode-only flags) — passing them together is a usage error (exit 1, clear message), not silently ignored.
- No `Co-Authored-By: Claude` (or any AI co-author) trailer in any commit message. Commit under the repo's existing configured git identity only.
- Do NOT run `git push`, `git pull`, `git fetch`, or any command that contacts a remote during implementation — work locally only.

---

### Task 14: Rasterize — render PDF pages to images

**Files:**
- Create: `src/pdfbetter/rasterize.py`
- Test: `tests/test_rasterize.py`

**Interfaces:**
- Consumes: nothing from earlier tasks (this is the first task of this plan; the existing package's `tests/conftest.py` fixture `synthetic_pdf_path` is reused).
- Produces: `rasterize_pdf(input_path: str, output_dir: str, dpi: int = 300) -> list[str]` — renders every page of `input_path` to a PNG file in `output_dir` (filenames zero-padded by page index, e.g. `page_0000.png`), returns the sorted list of output file paths.

- [ ] **Step 1: Write the failing tests**

Create `tests/test_rasterize.py`:

```python
import pytest
from PIL import Image
from reportlab.pdfgen import canvas

from pdfbetter.rasterize import rasterize_pdf


@pytest.fixture
def two_page_pdf_path(tmp_path):
    path = tmp_path / "two_pages.pdf"
    c = canvas.Canvas(str(path), pagesize=(200, 200))
    c.drawString(50, 100, "Page One")
    c.showPage()
    c.drawString(50, 100, "Page Two")
    c.showPage()
    c.save()
    return str(path)


def test_rasterize_pdf_produces_one_png_per_page(synthetic_pdf_path, tmp_path):
    output_dir = tmp_path / "rendered"
    output_dir.mkdir()

    output_paths = rasterize_pdf(synthetic_pdf_path, str(output_dir), dpi=72)

    assert len(output_paths) == 1
    assert output_paths[0].endswith(".png")
    Image.open(output_paths[0]).verify()


def test_rasterize_pdf_scales_with_dpi(synthetic_pdf_path, tmp_path):
    output_dir_72 = tmp_path / "rendered_72"
    output_dir_72.mkdir()
    paths_72 = rasterize_pdf(synthetic_pdf_path, str(output_dir_72), dpi=72)
    image_72 = Image.open(paths_72[0])

    output_dir_144 = tmp_path / "rendered_144"
    output_dir_144.mkdir()
    paths_144 = rasterize_pdf(synthetic_pdf_path, str(output_dir_144), dpi=144)
    image_144 = Image.open(paths_144[0])

    assert image_144.width == image_72.width * 2
    assert image_144.height == image_72.height * 2


def test_rasterize_pdf_produces_correctly_ordered_pages(two_page_pdf_path, tmp_path):
    output_dir = tmp_path / "rendered"
    output_dir.mkdir()

    output_paths = rasterize_pdf(two_page_pdf_path, str(output_dir), dpi=72)

    assert len(output_paths) == 2
    assert output_paths == sorted(output_paths)
    assert "page_0000" in output_paths[0]
    assert "page_0001" in output_paths[1]
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_rasterize.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'pdfbetter.rasterize'`

- [ ] **Step 3: Write the implementation**

Create `src/pdfbetter/rasterize.py`:

```python
import os

import pypdfium2 as pdfium


def rasterize_pdf(input_path: str, output_dir: str, dpi: int = 300) -> list[str]:
    pdf = pdfium.PdfDocument(input_path)
    scale = dpi / 72
    output_paths = []
    for page_number in range(len(pdf)):
        page = pdf[page_number]
        bitmap = page.render(scale=scale)
        image = bitmap.to_pil()
        output_path = os.path.join(output_dir, f"page_{page_number:04d}.png")
        image.save(output_path)
        output_paths.append(output_path)
    return output_paths
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_rasterize.py -v`
Expected: PASS (3 passed)

- [ ] **Step 5: Commit**

```bash
git add src/pdfbetter/rasterize.py tests/test_rasterize.py
git commit -m "Add PDF page rasterization via pypdfium2"
```

---

### Task 15: Crop — trim fixed margins from rendered pages

**Files:**
- Create: `src/pdfbetter/crop.py`
- Test: `tests/test_crop.py`

**Interfaces:**
- Consumes: nothing from earlier tasks (operates on a `PIL.Image.Image`, decoupled from how it was produced).
- Produces: `points_to_pixels(points: float, dpi: int) -> int`, `crop_margins(image: Image.Image, crop_x_px: int, crop_y_px: int) -> Image.Image` (raises `ValueError` if the margins leave an empty or inverted crop box for the given image size).

- [ ] **Step 1: Write the failing tests**

Create `tests/test_crop.py`:

```python
import pytest
from PIL import Image

from pdfbetter.crop import crop_margins, points_to_pixels


def test_points_to_pixels_at_300_dpi():
    assert points_to_pixels(20, 300) == 83


def test_points_to_pixels_at_72_dpi_is_identity():
    assert points_to_pixels(20, 72) == 20


def test_crop_margins_trims_expected_amount():
    image = Image.new("RGB", (2550, 3300), (255, 255, 255))

    cropped = crop_margins(image, crop_x_px=83, crop_y_px=83)

    assert cropped.size == (2550 - 2 * 83, 3300 - 2 * 83)


def test_crop_margins_zero_is_a_no_op():
    image = Image.new("RGB", (100, 100), (255, 255, 255))

    cropped = crop_margins(image, crop_x_px=0, crop_y_px=0)

    assert cropped.size == (100, 100)


def test_crop_margins_raises_when_margins_too_large():
    image = Image.new("RGB", (100, 100), (255, 255, 255))

    with pytest.raises(ValueError, match="too large"):
        crop_margins(image, crop_x_px=60, crop_y_px=60)
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_crop.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'pdfbetter.crop'`

- [ ] **Step 3: Write the implementation**

Create `src/pdfbetter/crop.py`:

```python
from PIL import Image


def points_to_pixels(points: float, dpi: int) -> int:
    return round(points * dpi / 72)


def crop_margins(image: Image.Image, crop_x_px: int, crop_y_px: int) -> Image.Image:
    width, height = image.size
    box = (crop_x_px, crop_y_px, width - crop_x_px, height - crop_y_px)
    if box[2] <= box[0] or box[3] <= box[1]:
        raise ValueError(
            f"crop margins too large for image size {width}x{height}: "
            f"resulting box {box} is empty or inverted"
        )
    return image.crop(box)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_crop.py -v`
Expected: PASS (5 passed)

- [ ] **Step 5: Commit**

```bash
git add src/pdfbetter/crop.py tests/test_crop.py
git commit -m "Add DPI-independent margin cropping for rendered pages"
```

---

### Task 16: Upscale — locate and invoke realesrgan-ncnn-vulkan

**Files:**
- Create: `src/pdfbetter/upscale.py`
- Test: `tests/test_upscale.py`

**Interfaces:**
- Consumes: nothing from earlier tasks.
- Produces: `RealesrganNotFoundError(Exception)`, `RealesrganFailedError(Exception)`, `find_realesrgan(explicit_path: str | None = None) -> str`, `upscale_directory(input_dir: str, output_dir: str, *, binary_path: str, model: str = "realesrgan-x4plus", scale: int = 2, tile: int = 0, threads: str = "1:2:2", tta: bool = False) -> None`.

- [ ] **Step 1: Write the failing tests**

Create `tests/test_upscale.py`:

```python
import subprocess

import pytest

from pdfbetter.upscale import (
    RealesrganFailedError,
    RealesrganNotFoundError,
    find_realesrgan,
    upscale_directory,
)


def test_find_realesrgan_prefers_explicit_path():
    assert find_realesrgan(explicit_path="/custom/path/realesrgan") == "/custom/path/realesrgan"


def test_find_realesrgan_uses_env_var(monkeypatch):
    monkeypatch.setenv("PDFBETTER_REALESRGAN_PATH", "/env/path/realesrgan")
    assert find_realesrgan() == "/env/path/realesrgan"


def test_find_realesrgan_falls_back_to_path_lookup(monkeypatch):
    monkeypatch.delenv("PDFBETTER_REALESRGAN_PATH", raising=False)
    monkeypatch.setattr("shutil.which", lambda name: "/usr/local/bin/realesrgan-ncnn-vulkan")
    assert find_realesrgan() == "/usr/local/bin/realesrgan-ncnn-vulkan"


def test_find_realesrgan_raises_when_not_found(monkeypatch):
    monkeypatch.delenv("PDFBETTER_REALESRGAN_PATH", raising=False)
    monkeypatch.setattr("shutil.which", lambda name: None)
    with pytest.raises(RealesrganNotFoundError):
        find_realesrgan()


def test_upscale_directory_invokes_expected_command_with_defaults(monkeypatch):
    captured = {}

    def fake_run(cmd, capture_output, text):
        captured["cmd"] = cmd
        return subprocess.CompletedProcess(cmd, returncode=0, stdout="", stderr="")

    monkeypatch.setattr(subprocess, "run", fake_run)

    upscale_directory("in_dir", "out_dir", binary_path="/path/to/realesrgan")

    assert captured["cmd"] == [
        "/path/to/realesrgan",
        "-i",
        "in_dir",
        "-o",
        "out_dir",
        "-n",
        "realesrgan-x4plus",
        "-s",
        "2",
        "-t",
        "0",
        "-j",
        "1:2:2",
    ]


def test_upscale_directory_appends_tta_flag_when_enabled(monkeypatch):
    captured = {}

    def fake_run(cmd, capture_output, text):
        captured["cmd"] = cmd
        return subprocess.CompletedProcess(cmd, returncode=0, stdout="", stderr="")

    monkeypatch.setattr(subprocess, "run", fake_run)

    upscale_directory("in_dir", "out_dir", binary_path="/path/to/realesrgan", tta=True)

    assert captured["cmd"][-1] == "-x"


def test_upscale_directory_passes_custom_tile_and_threads(monkeypatch):
    captured = {}

    def fake_run(cmd, capture_output, text):
        captured["cmd"] = cmd
        return subprocess.CompletedProcess(cmd, returncode=0, stdout="", stderr="")

    monkeypatch.setattr(subprocess, "run", fake_run)

    upscale_directory("in_dir", "out_dir", binary_path="/path/to/realesrgan", tile=256, threads="2:4:4")

    assert "256" in captured["cmd"]
    assert "2:4:4" in captured["cmd"]


def test_upscale_directory_raises_on_failure(monkeypatch):
    def fake_run(cmd, capture_output, text):
        return subprocess.CompletedProcess(cmd, returncode=1, stdout="", stderr="boom")

    monkeypatch.setattr(subprocess, "run", fake_run)

    with pytest.raises(RealesrganFailedError, match="boom"):
        upscale_directory("in_dir", "out_dir", binary_path="/path/to/realesrgan")
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_upscale.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'pdfbetter.upscale'`

- [ ] **Step 3: Write the implementation**

Create `src/pdfbetter/upscale.py`:

```python
import os
import shutil
import subprocess


class RealesrganNotFoundError(Exception):
    pass


class RealesrganFailedError(Exception):
    pass


def find_realesrgan(explicit_path: str | None = None) -> str:
    if explicit_path:
        return explicit_path

    env_path = os.environ.get("PDFBETTER_REALESRGAN_PATH")
    if env_path:
        return env_path

    found = shutil.which("realesrgan-ncnn-vulkan")
    if found:
        return found

    raise RealesrganNotFoundError(
        "realesrgan-ncnn-vulkan not found. Install it and ensure it's on PATH, "
        "set the PDFBETTER_REALESRGAN_PATH environment variable, or pass "
        "--realesrgan-path. On Windows: 'scoop install realesrgan-ncnn-vulkan'. "
        "On macOS/Linux: download the matching release from the upstream "
        "Real-ESRGAN project's releases."
    )


def upscale_directory(
    input_dir: str,
    output_dir: str,
    *,
    binary_path: str,
    model: str = "realesrgan-x4plus",
    scale: int = 2,
    tile: int = 0,
    threads: str = "1:2:2",
    tta: bool = False,
) -> None:
    cmd = [
        binary_path,
        "-i",
        input_dir,
        "-o",
        output_dir,
        "-n",
        model,
        "-s",
        str(scale),
        "-t",
        str(tile),
        "-j",
        threads,
    ]
    if tta:
        cmd.append("-x")

    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        raise RealesrganFailedError(
            f"realesrgan-ncnn-vulkan failed (exit code {result.returncode}): {result.stderr}"
        )
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_upscale.py -v`
Expected: PASS (8 passed)

- [ ] **Step 5: Commit**

```bash
git add src/pdfbetter/upscale.py tests/test_upscale.py
git commit -m "Add realesrgan-ncnn-vulkan location and batch invocation"
```

---

### Task 17: Pipeline orchestration — rasterize, crop, upscale, reassemble

**Files:**
- Create: `src/pdfbetter/rasterize_upscale_pipeline.py`
- Test: `tests/test_rasterize_upscale_pipeline.py`

**Interfaces:**
- Consumes: `pdfbetter.rasterize.rasterize_pdf`, `pdfbetter.crop.{points_to_pixels, crop_margins}`, `pdfbetter.upscale.{find_realesrgan, upscale_directory, RealesrganNotFoundError, RealesrganFailedError}`.
- Produces: `RasterizeUpscaleResult(output_path: str, pages_processed: int)`, `process_rasterize_upscale(input_path: str, output_path: str, *, dpi: int = 300, realesrgan_path: str | None = None, model: str = "realesrgan-x4plus", scale: int = 2, crop_x: float = 0.0, crop_y: float = 0.0, tile: int = 0, threads: str = "1:2:2", tta: bool = False) -> RasterizeUpscaleResult`. This is the public entry point `cli.py` will call for `--mode rasterize` (Task 18).

- [ ] **Step 1: Write the failing tests**

Create `tests/test_rasterize_upscale_pipeline.py`:

```python
import os

import pikepdf
import pytest
from PIL import Image

import pdfbetter.rasterize_upscale_pipeline as pipeline_module
from pdfbetter.rasterize_upscale_pipeline import process_rasterize_upscale
from pdfbetter.upscale import RealesrganNotFoundError


def _fake_upscale_directory(input_dir, output_dir, *, binary_path, model, scale, tile, threads, tta):
    for name in os.listdir(input_dir):
        image = Image.open(os.path.join(input_dir, name))
        resized = image.resize((image.width * scale, image.height * scale))
        resized.save(os.path.join(output_dir, name))


def test_process_rasterize_upscale_produces_pdf_with_original_page_size(
    monkeypatch, synthetic_pdf_path, tmp_path
):
    monkeypatch.setattr(pipeline_module, "find_realesrgan", lambda explicit_path=None: "/fake/realesrgan")
    monkeypatch.setattr(pipeline_module, "upscale_directory", _fake_upscale_directory)

    output_path = str(tmp_path / "output.pdf")
    result = process_rasterize_upscale(synthetic_pdf_path, output_path, dpi=72)

    assert result.pages_processed == 1
    assert os.path.exists(output_path)

    output_pdf = pikepdf.open(output_path)
    mediabox = output_pdf.pages[0].mediabox
    width = float(mediabox[2]) - float(mediabox[0])
    height = float(mediabox[3]) - float(mediabox[1])
    assert abs(width - 612.0) < 1.0
    assert abs(height - 792.0) < 1.0


def test_process_rasterize_upscale_applies_crop_before_upscaling(
    monkeypatch, synthetic_pdf_path, tmp_path
):
    seen_sizes = []

    def spying_upscale_directory(input_dir, output_dir, *, binary_path, model, scale, tile, threads, tta):
        for name in os.listdir(input_dir):
            image = Image.open(os.path.join(input_dir, name))
            seen_sizes.append(image.size)
            image.save(os.path.join(output_dir, name))

    monkeypatch.setattr(pipeline_module, "find_realesrgan", lambda explicit_path=None: "/fake/realesrgan")
    monkeypatch.setattr(pipeline_module, "upscale_directory", spying_upscale_directory)

    output_path = str(tmp_path / "output.pdf")
    result_no_crop_dir = tmp_path / "nocrop"
    result_no_crop_dir.mkdir()

    # Baseline: no crop, dpi=72 (612x792pt page -> 612x792px at 72 dpi)
    process_rasterize_upscale(synthetic_pdf_path, str(result_no_crop_dir / "out.pdf"), dpi=72)
    baseline_size = seen_sizes[-1]

    process_rasterize_upscale(
        synthetic_pdf_path, output_path, dpi=72, crop_x=10, crop_y=10
    )
    cropped_size = seen_sizes[-1]

    assert cropped_size[0] < baseline_size[0]
    assert cropped_size[1] < baseline_size[1]


def test_process_rasterize_upscale_fails_before_rasterizing_when_binary_missing(
    monkeypatch, synthetic_pdf_path, tmp_path
):
    def fake_find(explicit_path=None):
        raise RealesrganNotFoundError("not found")

    rasterize_called = []

    def fake_rasterize(input_path, output_dir, dpi=300):
        rasterize_called.append(True)
        return []

    monkeypatch.setattr(pipeline_module, "find_realesrgan", fake_find)
    monkeypatch.setattr(pipeline_module, "rasterize_pdf", fake_rasterize)

    output_path = str(tmp_path / "output.pdf")
    with pytest.raises(RealesrganNotFoundError):
        process_rasterize_upscale(synthetic_pdf_path, output_path)

    assert rasterize_called == []
    assert not os.path.exists(output_path)
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_rasterize_upscale_pipeline.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'pdfbetter.rasterize_upscale_pipeline'`

- [ ] **Step 3: Write the implementation**

Create `src/pdfbetter/rasterize_upscale_pipeline.py`:

```python
import io
import os
import tempfile
from dataclasses import dataclass

import pikepdf
from PIL import Image

from pdfbetter.crop import crop_margins, points_to_pixels
from pdfbetter.rasterize import rasterize_pdf
from pdfbetter.upscale import find_realesrgan, upscale_directory


@dataclass(frozen=True)
class RasterizeUpscaleResult:
    output_path: str
    pages_processed: int


def _reassemble_pdf(image_paths: list[str], output_path: str, dpi: float) -> None:
    pdf = pikepdf.new()
    for image_path in image_paths:
        image = Image.open(image_path)
        if image.mode != "RGB":
            image = image.convert("RGB")

        jpeg_buf = io.BytesIO()
        image.save(jpeg_buf, format="JPEG", quality=90)
        jpeg_bytes = jpeg_buf.getvalue()

        page_width_pt = image.width / dpi * 72
        page_height_pt = image.height / dpi * 72
        page = pdf.add_blank_page(page_size=(page_width_pt, page_height_pt))

        image_obj = pikepdf.Stream(pdf, jpeg_bytes)
        image_obj.Type = pikepdf.Name("/XObject")
        image_obj.Subtype = pikepdf.Name("/Image")
        image_obj.Width = image.width
        image_obj.Height = image.height
        image_obj.BitsPerComponent = 8
        image_obj.ColorSpace = pikepdf.Name("/DeviceRGB")
        image_obj.Filter = pikepdf.Name("/DCTDecode")

        page.Resources = pikepdf.Dictionary(XObject=pikepdf.Dictionary(Im0=image_obj))
        content = f"q {page_width_pt} 0 0 {page_height_pt} 0 0 cm /Im0 Do Q".encode()
        page.Contents = pdf.make_stream(content)

    pdf.save(output_path)


def process_rasterize_upscale(
    input_path: str,
    output_path: str,
    *,
    dpi: int = 300,
    realesrgan_path: str | None = None,
    model: str = "realesrgan-x4plus",
    scale: int = 2,
    crop_x: float = 0.0,
    crop_y: float = 0.0,
    tile: int = 0,
    threads: str = "1:2:2",
    tta: bool = False,
) -> RasterizeUpscaleResult:
    binary_path = find_realesrgan(realesrgan_path)

    with tempfile.TemporaryDirectory() as rendered_dir, tempfile.TemporaryDirectory() as upscaled_dir:
        rendered_paths = rasterize_pdf(input_path, rendered_dir, dpi=dpi)

        if crop_x > 0 or crop_y > 0:
            crop_x_px = points_to_pixels(crop_x, dpi)
            crop_y_px = points_to_pixels(crop_y, dpi)
            for path in rendered_paths:
                image = Image.open(path)
                cropped = crop_margins(image, crop_x_px, crop_y_px)
                cropped.save(path)

        upscale_directory(
            rendered_dir,
            upscaled_dir,
            binary_path=binary_path,
            model=model,
            scale=scale,
            tile=tile,
            threads=threads,
            tta=tta,
        )

        upscaled_paths = sorted(
            os.path.join(upscaled_dir, name)
            for name in os.listdir(upscaled_dir)
            if name.lower().endswith(".png")
        )
        _reassemble_pdf(upscaled_paths, output_path, dpi=dpi * scale)

    return RasterizeUpscaleResult(output_path=output_path, pages_processed=len(rendered_paths))
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_rasterize_upscale_pipeline.py -v`
Expected: PASS (3 passed)

- [ ] **Step 5: Commit**

```bash
git add src/pdfbetter/rasterize_upscale_pipeline.py tests/test_rasterize_upscale_pipeline.py
git commit -m "Add rasterize/crop/upscale/reassemble pipeline orchestration"
```

---

### Task 18: CLI integration — `--mode rasterize`

**Files:**
- Modify: `src/pdfbetter/cli.py`
- Modify: `tests/test_cli.py`

**Interfaces:**
- Consumes: `pdfbetter.rasterize_upscale_pipeline.{process_rasterize_upscale, RasterizeUpscaleResult}` (imported lazily, inside a function, not at module level — see Step 3).
- Produces: no new public interfaces; `main()`'s behavior is extended with a `--mode` flag and eight new mode-specific flags.

- [ ] **Step 1: Write the failing tests**

Add to `tests/test_cli.py` (add `import pdfbetter.cli as cli_module` near the top alongside the existing imports):

```python
def test_cli_rejects_surgery_flags_with_rasterize_mode(synthetic_pdf_path, tmp_path, capsys):
    output_path = str(tmp_path / "output.pdf")
    exit_code = main([synthetic_pdf_path, "-o", output_path, "--mode", "rasterize", "--audit"])

    assert exit_code == 1
    captured = capsys.readouterr()
    assert "surgery-mode-only" in captured.err


def test_cli_rasterize_mode_reports_missing_extra_cleanly(monkeypatch, synthetic_pdf_path, tmp_path, capsys):
    def fake_import():
        raise ImportError("No module named 'pypdfium2'")

    monkeypatch.setattr(cli_module, "_import_process_rasterize_upscale", fake_import)

    output_path = str(tmp_path / "output.pdf")
    exit_code = main([synthetic_pdf_path, "-o", output_path, "--mode", "rasterize"])

    assert exit_code == 1
    captured = capsys.readouterr()
    assert "pip install pdfbetter[rasterize]" in captured.err


def test_cli_rasterize_mode_success_path_passes_all_flags_through(monkeypatch, synthetic_pdf_path, tmp_path, capsys):
    from pdfbetter.rasterize_upscale_pipeline import RasterizeUpscaleResult

    captured_kwargs = {}

    def fake_process(input_path, output_path, **kwargs):
        captured_kwargs.update(kwargs)
        with open(output_path, "wb") as f:
            f.write(b"%PDF-fake")
        return RasterizeUpscaleResult(output_path=output_path, pages_processed=3)

    monkeypatch.setattr(cli_module, "_import_process_rasterize_upscale", lambda: fake_process)

    output_path = str(tmp_path / "output.pdf")
    exit_code = main(
        [
            synthetic_pdf_path,
            "-o",
            output_path,
            "--mode",
            "rasterize",
            "--render-dpi",
            "150",
            "--crop-x",
            "10",
            "--crop-y",
            "20",
            "--realesrgan-model",
            "realesrgan-x4plus-anime",
            "--realesrgan-tile",
            "128",
            "--realesrgan-threads",
            "2:4:4",
            "--realesrgan-tta",
        ]
    )

    assert exit_code == 0
    captured = capsys.readouterr()
    assert "wrote" in captured.out
    assert os.path.exists(output_path)
    assert captured_kwargs["dpi"] == 150
    assert captured_kwargs["crop_x"] == 10.0
    assert captured_kwargs["crop_y"] == 20.0
    assert captured_kwargs["model"] == "realesrgan-x4plus-anime"
    assert captured_kwargs["tile"] == 128
    assert captured_kwargs["threads"] == "2:4:4"
    assert captured_kwargs["tta"] is True
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_cli.py -v`
Expected: FAIL — `--mode` isn't a recognized argument yet (argparse error), and `_import_process_rasterize_upscale` doesn't exist on `cli_module`.

- [ ] **Step 3: Replace the contents of `src/pdfbetter/cli.py`**

```python
import argparse
import sys
from pathlib import Path

from pdfbetter.classify import Thresholds
from pdfbetter.pipeline import process


def _default_output_path(input_path: str) -> str:
    input_stem = Path(input_path).stem
    output_dir = Path("output")
    if not output_dir.is_dir():
        output_dir = Path.home() / "Documents" / "PDFBETTER OUTPUT"
        output_dir.mkdir(parents=True, exist_ok=True)
    return str(output_dir / f"{input_stem}_printerfriendly.pdf")


def _import_process_rasterize_upscale():
    from pdfbetter.rasterize_upscale_pipeline import process_rasterize_upscale

    return process_rasterize_upscale


def _run_surgery_mode(args, output_path: str) -> int:
    thresholds = Thresholds(
        background_coverage=args.bg_threshold if args.bg_threshold is not None else 0.8,
        contrast_luminance=args.contrast_luminance if args.contrast_luminance is not None else 0.6,
    )
    try:
        result = process(args.input, output_path, thresholds=thresholds, audit=args.audit)
    except Exception as exc:
        print(f"pdfbetter: failed to process {args.input}: {exc}", file=sys.stderr)
        return 1

    print(f"pdfbetter: wrote {result.output_path} ({result.pages_processed} pages)")
    if args.audit:
        print(f"pdfbetter: audit report at {result.audit_report_path}")
        print(f"pdfbetter: debug overlay at {result.audit_overlay_path}")
    for page_number in result.unimproved_pages:
        print(
            f"pdfbetter: warning: page {page_number} left unchanged (background removal would have left it blank)",
            file=sys.stderr,
        )
    if result.failed_pages:
        for page_number, message in result.failed_pages:
            print(f"pdfbetter: page {page_number} failed to process: {message}", file=sys.stderr)
        print(f"pdfbetter: {len(result.failed_pages)} page(s) failed, see above", file=sys.stderr)
        return 1
    return 0


def _run_rasterize_mode(args, output_path: str) -> int:
    try:
        process_rasterize_upscale = _import_process_rasterize_upscale()
    except ImportError:
        print(
            "pdfbetter: --mode rasterize requires the 'rasterize' extra: pip install pdfbetter[rasterize]",
            file=sys.stderr,
        )
        return 1

    try:
        result = process_rasterize_upscale(
            args.input,
            output_path,
            dpi=args.render_dpi,
            realesrgan_path=args.realesrgan_path,
            model=args.realesrgan_model,
            crop_x=args.crop_x,
            crop_y=args.crop_y,
            tile=args.realesrgan_tile,
            threads=args.realesrgan_threads,
            tta=args.realesrgan_tta,
        )
    except Exception as exc:
        print(f"pdfbetter: failed to process {args.input}: {exc}", file=sys.stderr)
        return 1

    print(f"pdfbetter: wrote {result.output_path} ({result.pages_processed} pages)")
    return 0


def main(argv: list | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="pdfbetter",
        description="Strip ink-heavy backgrounds from a PDF, keeping content faithful.",
    )
    parser.add_argument("input", help="path to the source PDF")
    parser.add_argument(
        "-o",
        "--output",
        default=None,
        help="path to write the output PDF (default: ./output/<name>_printerfriendly.pdf if "
        "./output exists, else ~/Documents/PDFBETTER OUTPUT/<name>_printerfriendly.pdf)",
    )
    parser.add_argument(
        "--mode",
        choices=["surgery", "rasterize"],
        default="surgery",
        help="processing mode: 'surgery' edits the content stream directly (default); "
        "'rasterize' renders each page to an image, upscales it with realesrgan-ncnn-vulkan, "
        "and reassembles the result as a new PDF (for PDFs with no text/vector layer to preserve)",
    )
    parser.add_argument(
        "--bg-threshold",
        type=float,
        default=None,
        help="[surgery mode] min page-coverage fraction (0-1) for a fill/image to be treated as background (default: 0.8)",
    )
    parser.add_argument(
        "--contrast-luminance",
        type=float,
        default=None,
        help="[surgery mode] min luminance (0-1) for a kept color to be recolored to black (default: 0.6)",
    )
    parser.add_argument(
        "--audit",
        action="store_true",
        help="[surgery mode] also write a JSON classification report and a debug overlay PDF",
    )
    parser.add_argument(
        "--render-dpi",
        type=int,
        default=300,
        help="[rasterize mode] pre-upscale render resolution in DPI (default: 300; effective final "
        "resolution is 2x this with the default scale, e.g. 300 -> ~600 DPI-equivalent)",
    )
    parser.add_argument(
        "--crop-x",
        type=float,
        default=0.0,
        help="[rasterize mode] margin in points trimmed from both left and right of each rendered page (default: 0, no cropping)",
    )
    parser.add_argument(
        "--crop-y",
        type=float,
        default=0.0,
        help="[rasterize mode] margin in points trimmed from both top and bottom of each rendered page (default: 0, no cropping)",
    )
    parser.add_argument(
        "--realesrgan-path",
        default=None,
        help="[rasterize mode] path to the realesrgan-ncnn-vulkan executable (default: "
        "PDFBETTER_REALESRGAN_PATH env var, then PATH lookup)",
    )
    parser.add_argument(
        "--realesrgan-model",
        default="realesrgan-x4plus",
        help="[rasterize mode] realesrgan-ncnn-vulkan model name (default: realesrgan-x4plus)",
    )
    parser.add_argument(
        "--realesrgan-tile",
        type=int,
        default=0,
        help="[rasterize mode] realesrgan-ncnn-vulkan tile size, 0=auto (default: 0)",
    )
    parser.add_argument(
        "--realesrgan-threads",
        default="1:2:2",
        help="[rasterize mode] realesrgan-ncnn-vulkan load:proc:save thread counts (default: 1:2:2)",
    )
    parser.add_argument(
        "--realesrgan-tta",
        action="store_true",
        help="[rasterize mode] enable realesrgan-ncnn-vulkan TTA mode: ~8x slower, marginally cleaner output",
    )
    args = parser.parse_args(argv)

    if args.mode == "rasterize" and (
        args.bg_threshold is not None or args.contrast_luminance is not None or args.audit
    ):
        print(
            "pdfbetter: --bg-threshold/--contrast-luminance/--audit are surgery-mode-only "
            "and cannot be combined with --mode rasterize",
            file=sys.stderr,
        )
        return 1

    output_path = args.output or _default_output_path(args.input)

    if args.mode == "rasterize":
        return _run_rasterize_mode(args, output_path)
    return _run_surgery_mode(args, output_path)


if __name__ == "__main__":
    sys.exit(main())
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_cli.py -v`
Expected: PASS (all tests in the file, including the 3 new ones)

- [ ] **Step 5: Run the full test suite**

Run: `uv run pytest -v`
Expected: all tests pass

- [ ] **Step 6: Commit**

```bash
git add src/pdfbetter/cli.py tests/test_cli.py
git commit -m "Add --mode rasterize to the CLI, with crop/tile/threads/tta tuning flags"
```

---

### Task 19: Packaging, README, and manual smoke test

**Files:**
- Modify: `pyproject.toml`
- Modify: `requirements.dev.txt`
- Modify: `README.md`

**Interfaces:**
- Consumes: nothing new.
- Produces: no new interfaces — packaging metadata and documentation only.

- [ ] **Step 1: Add the `rasterize` optional-dependency group to `pyproject.toml`**

In the `[project.optional-dependencies]` table, add a new `rasterize` key alongside the existing `dev` key:

```toml
[project.optional-dependencies]
dev = [
    "pytest>=8.0",
    "reportlab>=4.0",
    "pillow>=10.0",
    "pdfplumber>=0.11",
    "pypdfium2>=4.0",
]
rasterize = [
    "pypdfium2>=4.0",
    "pillow>=10.0",
]
```

(This adds `pypdfium2>=4.0` to `dev` too, since `tests/test_rasterize.py` and `tests/test_rasterize_upscale_pipeline.py` need it to run at all.)

- [ ] **Step 2: Add `pypdfium2` to `requirements.dev.txt`**

```text
-r requirements.txt
pytest>=8.0
reportlab>=4.0
pillow>=10.0
pdfplumber>=0.11
pypdfium2>=4.0
```

- [ ] **Step 3: Sync the dev environment and run the full suite**

Run: `uv pip install -e ".[dev]"`
Run: `uv run pytest -v`
Expected: all tests pass (existing suite plus this plan's new tests)

- [ ] **Step 4: Manually smoke-test `--mode rasterize` against the real sample file**

Run: `uv run pdfbetter input/DND5.5e.pdf -o /tmp/dnd-rasterized.pdf --mode rasterize --render-dpi 96`
(Use `--render-dpi 96` for the manual check rather than the 300 default — this is a 387-page file and a full 300 DPI run would take real time even at the now-corrected scale=2; the default itself is not being changed by this smoke test.)

Expected: completes without crashing (will take real time — rendering + one batch GPU upscale call over 387 pages), writes the output file. Open a couple of pages of the output and confirm they're visibly sharper than the input and still the same physical page size. This is a manual, one-time check — not a repeatable automated test (same reasoning as the existing surgery-mode smoke test).

- [ ] **Step 5: Update `README.md`**

Add a new section after the existing "## Use" section (before "## How it works"):

````markdown
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
````

- [ ] **Step 6: Update the "Status / next up" checklist**

Add these lines to the checklist:

```markdown
- [x] Rasterize/upscale mode (`--mode rasterize`) — `src/pdfbetter/rasterize.py`, `src/pdfbetter/crop.py`, `src/pdfbetter/upscale.py`, `src/pdfbetter/rasterize_upscale_pipeline.py`
- [ ] Manual smoke test of `--mode rasterize` against `input/DND5.5e.pdf` at the full 300 DPI default (only tested at 96 DPI so far, for turnaround time) — confirm the default is actually practical on a 387-page file, or reconsider it
```

- [ ] **Step 7: Commit**

```bash
git add pyproject.toml requirements.dev.txt README.md
git commit -m "Add rasterize extra, README docs, and smoke-test notes for --mode rasterize"
```
