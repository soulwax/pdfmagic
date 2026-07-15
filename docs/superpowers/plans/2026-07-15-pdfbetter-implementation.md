# pdfbetter Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build `pdfbetter`, a pip-installable CLI + Python library that takes any PDF and produces a faithful, printer-friendly copy: ink-heavy backgrounds (large fills/full-bleed images) removed, everything else (text, real images, separator/rule lines, fonts, positions, non-background colors) preserved byte-for-byte.

**Architecture:** For each page, parse the content stream into operators (`pikepdf.parse_content_stream`), walk it once tracking graphics state (CTM stack, active fill/stroke color) to find every fill/stroke/image/text-show operation with its device-space bbox and color, classify each as drop/recolor/keep against configurable thresholds, then rebuild the instruction list — omitting dropped paint operators, wrapping low-contrast kept paints in a local black-color override, copying everything else through unchanged — and reassemble with `pikepdf.unparse_content_stream`. No page is ever redrawn from scratch, so font programs, exact positions, and non-background colors are never reinterpreted or approximated.

**Tech Stack:** Python ≥3.10, `pikepdf` (runtime), `pytest` + `reportlab` + `pillow` + `pdfplumber` (dev/test only), `uv` for environment/dependency management, `hatchling` build backend.

## Global Constraints

- Python ≥3.10 (uses `X | None` union syntax and `list[X]`/`dict[X, Y]` generics).
- Runtime dependency: `pikepdf` only. Never import `reportlab`, `pdfplumber`, or `pillow` from any module under `src/pdfbetter/` — those are dev/test-only, used solely in `tests/`.
- `pikepdf` version floor: `>=9.0` (verified working: `10.10.0`).
- No font extraction, re-embedding, or re-typesetting anywhere — fonts and non-dropped content are carried through as the same PDF objects, untouched.
- Every drop/recolor decision must be traceable to a reason string (consumed by the audit module).
- TDD: write the failing test, run it, then write the minimal implementation, then run again. Commit after each step group as marked.
- Distribution name and import package: `pdfbetter`.

---

### Task 1: Project scaffolding

**Files:**
- Create: `pyproject.toml`
- Create: `requirements.txt`
- Create: `requirements.dev.txt`
- Create: `src/pdfbetter/__init__.py`
- Create: `tests/test_package.py`

**Interfaces:**
- Produces: an installed, importable `pdfbetter` package (`pdfbetter.__version__`), a registered-but-not-yet-implemented `pdfbetter` console script, and a working `pytest` command for all later tasks.

- [ ] **Step 1: Create `pyproject.toml`**

```toml
[project]
name = "pdfbetter"
version = "0.1.0"
description = "Strip ink-heavy backgrounds from a PDF while keeping text, images, and lines exactly as they were."
readme = "README.md"
requires-python = ">=3.10"
license = { text = "MIT" }
dependencies = [
    "pikepdf>=9.0",
]

[project.scripts]
pdfbetter = "pdfbetter.cli:main"

[project.optional-dependencies]
dev = [
    "pytest>=8.0",
    "reportlab>=4.0",
    "pillow>=10.0",
    "pdfplumber>=0.11",
]

[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"

[tool.hatch.build.targets.wheel]
packages = ["src/pdfbetter"]
```

- [ ] **Step 2: Create `requirements.txt`**

```text
pikepdf>=9.0
```

- [ ] **Step 3: Create `requirements.dev.txt`**

```text
-r requirements.txt
pytest>=8.0
reportlab>=4.0
pillow>=10.0
pdfplumber>=0.11
```

- [ ] **Step 4: Create `src/pdfbetter/__init__.py`**

```python
__version__ = "0.1.0"
```

- [ ] **Step 5: Write the failing test**

Create `tests/test_package.py`:

```python
import pdfbetter


def test_package_version():
    assert pdfbetter.__version__ == "0.1.0"
```

- [ ] **Step 6: Create the environment and install the package in editable mode**

Run: `uv venv`
Run: `uv pip install -e ".[dev]"`

- [ ] **Step 7: Run the test to verify it passes**

Run: `uv run pytest tests/test_package.py -v`
Expected: PASS (1 passed)

- [ ] **Step 8: Verify the console script is registered**

Run: `uv run pdfbetter --help`
Expected: a `ModuleNotFoundError` or `ImportError` for `pdfbetter.cli` (it doesn't exist yet) — this confirms the entry point is wired up and will work once Task 9 creates `cli.py`. This is expected at this stage, not a failure of this task.

- [ ] **Step 9: Commit**

```bash
git add pyproject.toml requirements.txt requirements.dev.txt src/pdfbetter/__init__.py tests/test_package.py
git commit -m "Scaffold pdfbetter package with uv/hatchling and pinned dev requirements"
```

---

### Task 2: Geometry — matrix math and bbox coverage

**Files:**
- Create: `src/pdfbetter/geometry.py`
- Test: `tests/test_geometry.py`

**Interfaces:**
- Produces: `Matrix` (type alias `tuple[float, float, float, float, float, float]`), `Point` (type alias `tuple[float, float]`), `IDENTITY: Matrix`, `BBox` (frozen dataclass with `x0, y0, x1, y1` and `.width`/`.height` properties), `multiply(m1: Matrix, m2: Matrix) -> Matrix`, `apply(point: Point, matrix: Matrix) -> Point`, `bbox_of_points(points: list[Point]) -> BBox`, `coverage_fraction(bbox: BBox, page_width: float, page_height: float) -> tuple[float, float]`.

- [ ] **Step 1: Write the failing tests**

Create `tests/test_geometry.py`:

```python
from pdfbetter.geometry import IDENTITY, BBox, apply, bbox_of_points, coverage_fraction, multiply


def test_apply_identity_leaves_point_unchanged():
    assert apply((3.0, 4.0), IDENTITY) == (3.0, 4.0)


def test_apply_translation():
    m = (1.0, 0.0, 0.0, 1.0, 10.0, 20.0)
    assert apply((1.0, 1.0), m) == (11.0, 21.0)


def test_apply_scale():
    m = (2.0, 0.0, 0.0, 3.0, 0.0, 0.0)
    assert apply((5.0, 5.0), m) == (10.0, 15.0)


def test_multiply_composes_new_transform_before_existing_ctm():
    translate = (1.0, 0.0, 0.0, 1.0, 10.0, 0.0)
    scale = (2.0, 0.0, 0.0, 2.0, 0.0, 0.0)
    combined = multiply(scale, translate)
    assert apply((1.0, 1.0), combined) == (12.0, 2.0)


def test_bbox_of_points():
    bbox = bbox_of_points([(0.0, 0.0), (10.0, 5.0), (3.0, 20.0)])
    assert bbox == BBox(0.0, 0.0, 10.0, 20.0)


def test_bbox_width_and_height():
    bbox = BBox(2.0, 3.0, 12.0, 23.0)
    assert bbox.width == 10.0
    assert bbox.height == 20.0


def test_coverage_fraction_full_page():
    bbox = BBox(0.0, 0.0, 612.0, 792.0)
    assert coverage_fraction(bbox, 612.0, 792.0) == (1.0, 1.0)


def test_coverage_fraction_quarter_page():
    bbox = BBox(0.0, 0.0, 306.0, 396.0)
    assert coverage_fraction(bbox, 612.0, 792.0) == (0.5, 0.5)
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_geometry.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'pdfbetter.geometry'`

- [ ] **Step 3: Write the implementation**

Create `src/pdfbetter/geometry.py`:

```python
from dataclasses import dataclass

Matrix = tuple[float, float, float, float, float, float]
Point = tuple[float, float]

IDENTITY: Matrix = (1.0, 0.0, 0.0, 1.0, 0.0, 0.0)


@dataclass(frozen=True)
class BBox:
    x0: float
    y0: float
    x1: float
    y1: float

    @property
    def width(self) -> float:
        return self.x1 - self.x0

    @property
    def height(self) -> float:
        return self.y1 - self.y0


def multiply(m1: Matrix, m2: Matrix) -> Matrix:
    a1, b1, c1, d1, e1, f1 = m1
    a2, b2, c2, d2, e2, f2 = m2
    return (
        a1 * a2 + b1 * c2,
        a1 * b2 + b1 * d2,
        c1 * a2 + d1 * c2,
        c1 * b2 + d1 * d2,
        e1 * a2 + f1 * c2 + e2,
        e1 * b2 + f1 * d2 + f2,
    )


def apply(point: Point, matrix: Matrix) -> Point:
    x, y = point
    a, b, c, d, e, f = matrix
    return (a * x + c * y + e, b * x + d * y + f)


def bbox_of_points(points: list[Point]) -> BBox:
    xs = [p[0] for p in points]
    ys = [p[1] for p in points]
    return BBox(min(xs), min(ys), max(xs), max(ys))


def coverage_fraction(bbox: BBox, page_width: float, page_height: float) -> tuple[float, float]:
    return (bbox.width / page_width, bbox.height / page_height)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_geometry.py -v`
Expected: PASS (8 passed)

- [ ] **Step 5: Commit**

```bash
git add src/pdfbetter/geometry.py tests/test_geometry.py
git commit -m "Add PDF matrix math and bbox coverage helpers"
```

---

### Task 3: Color model, luminance, and black-color operator construction

**Files:**
- Create: `src/pdfbetter/color.py`
- Test: `tests/test_color.py`

**Interfaces:**
- Consumes: nothing from earlier tasks.
- Produces: `Color` (frozen dataclass: `colorspace: str` one of `"gray"/"rgb"/"cmyk"`, `values: tuple[float, ...]`), `DEFAULT_COLOR: Color`, `FILL_COLOR_OPS: set[str]`, `STROKE_COLOR_OPS: set[str]`, `color_from_operands(operator: str, operands: list) -> Color | None`, `luminance(color: Color) -> float`, `black_operator(colorspace: str, target: str) -> pikepdf.ContentStreamInstruction` (`target` is `"fill"` or `"stroke"`).

- [ ] **Step 1: Write the failing tests**

Create `tests/test_color.py`:

```python
import pikepdf
import pytest

from pdfbetter.color import Color, black_operator, color_from_operands, luminance


def test_color_from_operands_gray():
    assert color_from_operands("g", [0.5]) == Color("gray", (0.5,))


def test_color_from_operands_rgb():
    assert color_from_operands("rg", [1.0, 1.0, 1.0]) == Color("rgb", (1.0, 1.0, 1.0))


def test_color_from_operands_cmyk():
    assert color_from_operands("k", [0.0, 0.0, 0.0, 1.0]) == Color("cmyk", (0.0, 0.0, 0.0, 1.0))


def test_color_from_operands_stroke_variant_maps_to_same_colorspace():
    assert color_from_operands("RG", [0.2, 0.3, 0.4]) == Color("rgb", (0.2, 0.3, 0.4))


def test_color_from_operands_scn_infers_colorspace_by_operand_count():
    assert color_from_operands("scn", [0.1, 0.2, 0.3, 0.4]) == Color("cmyk", (0.1, 0.2, 0.3, 0.4))


def test_color_from_operands_pattern_fill_returns_none():
    assert color_from_operands("scn", [pikepdf.Name("/P1")]) is None


def test_luminance_white_rgb_is_one():
    assert luminance(Color("rgb", (1.0, 1.0, 1.0))) == pytest.approx(1.0)


def test_luminance_black_gray_is_zero():
    assert luminance(Color("gray", (0.0,))) == 0.0


def test_luminance_pure_black_cmyk_is_zero():
    assert luminance(Color("cmyk", (0.0, 0.0, 0.0, 1.0))) == 0.0


def test_black_operator_rgb_fill():
    ins = black_operator("rgb", "fill")
    assert str(ins.operator) == "rg"
    assert list(ins.operands) == [0, 0, 0]


def test_black_operator_cmyk_stroke():
    ins = black_operator("cmyk", "stroke")
    assert str(ins.operator) == "K"
    assert list(ins.operands) == [0, 0, 0, 1]


def test_black_operator_gray_fill():
    ins = black_operator("gray", "fill")
    assert str(ins.operator) == "g"
    assert list(ins.operands) == [0]
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_color.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'pdfbetter.color'`

- [ ] **Step 3: Write the implementation**

Create `src/pdfbetter/color.py`:

```python
from dataclasses import dataclass

import pikepdf

FILL_COLOR_OPS = {"g", "rg", "k", "sc", "scn"}
STROKE_COLOR_OPS = {"G", "RG", "K", "SC", "SCN"}

_STROKE_TO_FILL_OP = {"G": "g", "RG": "rg", "K": "k", "SC": "sc", "SCN": "scn"}


@dataclass(frozen=True)
class Color:
    colorspace: str
    values: tuple[float, ...]


DEFAULT_COLOR = Color("gray", (0.0,))


def color_from_operands(operator: str, operands: list) -> Color | None:
    base_op = _STROKE_TO_FILL_OP.get(operator, operator)
    numeric = [float(o) for o in operands if not isinstance(o, pikepdf.Name)]
    if base_op == "g" and len(numeric) == 1:
        return Color("gray", tuple(numeric))
    if base_op == "rg" and len(numeric) == 3:
        return Color("rgb", tuple(numeric))
    if base_op == "k" and len(numeric) == 4:
        return Color("cmyk", tuple(numeric))
    if base_op in ("sc", "scn"):
        if len(numeric) == 1:
            return Color("gray", tuple(numeric))
        if len(numeric) == 3:
            return Color("rgb", tuple(numeric))
        if len(numeric) == 4:
            return Color("cmyk", tuple(numeric))
    return None


def luminance(color: Color) -> float:
    if color.colorspace == "gray":
        return color.values[0]
    if color.colorspace == "rgb":
        r, g, b = color.values
        return 0.299 * r + 0.587 * g + 0.114 * b
    c, m, y, k = color.values
    r = (1 - c) * (1 - k)
    g = (1 - m) * (1 - k)
    b = (1 - y) * (1 - k)
    return 0.299 * r + 0.587 * g + 0.114 * b


def black_operator(colorspace: str, target: str) -> pikepdf.ContentStreamInstruction:
    if colorspace == "gray":
        op, operands = ("g", [0]) if target == "fill" else ("G", [0])
    elif colorspace == "rgb":
        op, operands = ("rg", [0, 0, 0]) if target == "fill" else ("RG", [0, 0, 0])
    elif colorspace == "cmyk":
        op, operands = ("k", [0, 0, 0, 1]) if target == "fill" else ("K", [0, 0, 0, 1])
    else:
        raise ValueError(f"unsupported colorspace: {colorspace}")
    return pikepdf.ContentStreamInstruction(operands, pikepdf.Operator(op))
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_color.py -v`
Expected: PASS (12 passed)

- [ ] **Step 5: Commit**

```bash
git add src/pdfbetter/color.py tests/test_color.py
git commit -m "Add PDF color model, luminance heuristic, and black-color operator builder"
```

---

### Task 4: Content-stream walker

**Files:**
- Create: `src/pdfbetter/walk.py`
- Test: `tests/test_walk.py`

**Interfaces:**
- Consumes: `pdfbetter.color.{Color, DEFAULT_COLOR, FILL_COLOR_OPS, STROKE_COLOR_OPS, color_from_operands}`, `pdfbetter.geometry.{IDENTITY, Matrix, Point, BBox, apply, multiply, bbox_of_points}`.
- Produces: `FillOp(start: int, end: int, bbox: BBox, color: Color)`, `StrokeOp(start: int, end: int, color: Color)`, `ImageOp(index: int, xobject_name: str, bbox: BBox)`, `TextShowOp(index: int, color: Color)`, `WalkResult(fills: list[FillOp], strokes: list[StrokeOp], images: list[ImageOp], text_shows: list[TextShowOp])`, `walk_page(instructions: list, page_width: float, page_height: float, image_xobject_names: set[str]) -> WalkResult`.

Note: combined fill+stroke paint operators (`B`, `B*`, `b`, `b*`) are classified only as fills, never also as strokes — a background rect that happens to also have a stroke is dropped in full, including its stroke. This keeps every instruction index owned by at most one op, so drop/recolor edits from different categories can never overlap or conflict.

- [ ] **Step 1: Write the failing tests**

Create `tests/test_walk.py`:

```python
import pikepdf

from pdfbetter.color import Color
from pdfbetter.walk import walk_page


def _ins(operands, op):
    return pikepdf.ContentStreamInstruction(operands, pikepdf.Operator(op))


def test_walk_detects_full_page_background_fill():
    instructions = [
        _ins([0.05, 0.05, 0.05], "rg"),
        _ins([], "n"),
        _ins([0, 0, 612, 792], "re"),
        _ins([], "f*"),
    ]
    result = walk_page(instructions, page_width=612, page_height=792, image_xobject_names=set())
    assert len(result.fills) == 1
    fill = result.fills[0]
    assert fill.color == Color("rgb", (0.05, 0.05, 0.05))
    assert fill.bbox.width == 612
    assert fill.bbox.height == 792
    assert fill.start == 2 and fill.end == 3
    assert result.strokes == []


def test_walk_ignores_clip_only_path():
    instructions = [
        _ins([0, 0, 100, 100], "re"),
        _ins([], "W"),
        _ins([], "n"),
    ]
    result = walk_page(instructions, page_width=612, page_height=792, image_xobject_names=set())
    assert result.fills == []
    assert result.strokes == []


def test_walk_detects_separator_line_as_stroke_not_fill():
    instructions = [
        _ins([0, 0, 0], "RG"),
        _ins([1], "w"),
        _ins([72, 622], "m"),
        _ins([540, 622], "l"),
        _ins([], "S"),
    ]
    result = walk_page(instructions, page_width=612, page_height=792, image_xobject_names=set())
    assert result.fills == []
    assert len(result.strokes) == 1
    stroke = result.strokes[0]
    assert stroke.color == Color("rgb", (0, 0, 0))
    assert stroke.start == 2 and stroke.end == 4


def test_walk_detects_placed_image_bbox_via_ctm():
    instructions = [
        _ins([], "q"),
        _ins([40, 0, 0, 40, 72, 220], "cm"),
        _ins([pikepdf.Name("/Im0")], "Do"),
        _ins([], "Q"),
    ]
    result = walk_page(instructions, page_width=612, page_height=792, image_xobject_names={"/Im0"})
    assert len(result.images) == 1
    image = result.images[0]
    assert image.xobject_name == "/Im0"
    assert image.bbox.x0 == 72 and image.bbox.y0 == 220
    assert image.bbox.width == 40 and image.bbox.height == 40


def test_walk_ignores_form_xobject_not_in_image_names():
    instructions = [
        _ins([], "q"),
        _ins([1, 0, 0, 1, 0, 0], "cm"),
        _ins([pikepdf.Name("/Fm0")], "Do"),
        _ins([], "Q"),
    ]
    result = walk_page(instructions, page_width=612, page_height=792, image_xobject_names=set())
    assert result.images == []


def test_walk_tracks_active_fill_color_for_text_show():
    instructions = [
        _ins([1, 1, 1], "rg"),
        _ins(["Hello"], "Tj"),
    ]
    result = walk_page(instructions, page_width=612, page_height=792, image_xobject_names=set())
    assert len(result.text_shows) == 1
    assert result.text_shows[0].color == Color("rgb", (1, 1, 1))
    assert result.text_shows[0].index == 1


def test_walk_default_color_is_black_before_any_color_operator():
    instructions = [_ins(["A"], "Tj")]
    result = walk_page(instructions, page_width=612, page_height=792, image_xobject_names=set())
    assert result.text_shows[0].color.colorspace == "gray"
    assert result.text_shows[0].color.values == (0.0,)
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_walk.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'pdfbetter.walk'`

- [ ] **Step 3: Write the implementation**

Create `src/pdfbetter/walk.py`:

```python
from dataclasses import dataclass, field

from pdfbetter.color import (
    DEFAULT_COLOR,
    FILL_COLOR_OPS,
    STROKE_COLOR_OPS,
    Color,
    color_from_operands,
)
from pdfbetter.geometry import IDENTITY, BBox, Matrix, Point, apply, bbox_of_points, multiply

PATH_CONSTRUCTION_OPS = {"m", "l", "c", "v", "y", "re", "h"}
FILL_PAINT_OPS = {"f", "F", "f*", "B", "B*", "b", "b*"}
STROKE_PAINT_OPS = {"S", "s"}
PAINT_TERMINATORS = FILL_PAINT_OPS | STROKE_PAINT_OPS | {"n"}
TEXT_SHOW_OPS = {"Tj", "TJ", "'", '"'}


@dataclass(frozen=True)
class FillOp:
    start: int
    end: int
    bbox: BBox
    color: Color


@dataclass(frozen=True)
class StrokeOp:
    start: int
    end: int
    color: Color


@dataclass(frozen=True)
class ImageOp:
    index: int
    xobject_name: str
    bbox: BBox


@dataclass(frozen=True)
class TextShowOp:
    index: int
    color: Color


@dataclass
class WalkResult:
    fills: list = field(default_factory=list)
    strokes: list = field(default_factory=list)
    images: list = field(default_factory=list)
    text_shows: list = field(default_factory=list)


def _path_points(instructions: list, start: int, end: int) -> list[Point]:
    points: list[Point] = []
    for ins in instructions[start:end]:
        op = str(ins.operator)
        if op not in PATH_CONSTRUCTION_OPS:
            continue
        operands = [float(o) for o in ins.operands]
        if op == "re":
            x, y, w, h = operands
            points.extend([(x, y), (x + w, y), (x + w, y + h), (x, y + h)])
        elif op in ("m", "l"):
            points.append((operands[0], operands[1]))
        elif op == "c":
            points.append((operands[0], operands[1]))
            points.append((operands[2], operands[3]))
            points.append((operands[4], operands[5]))
        elif op in ("v", "y"):
            points.append((operands[0], operands[1]))
            points.append((operands[2], operands[3]))
    return points


def walk_page(
    instructions: list,
    page_width: float,
    page_height: float,
    image_xobject_names: set,
) -> WalkResult:
    result = WalkResult()
    ctm_stack: list[Matrix] = [IDENTITY]
    fill_color = DEFAULT_COLOR
    stroke_color = DEFAULT_COLOR
    path_start: int | None = None

    for i, ins in enumerate(instructions):
        op = str(ins.operator)

        if op == "q":
            ctm_stack.append(ctm_stack[-1])
        elif op == "Q":
            if len(ctm_stack) > 1:
                ctm_stack.pop()
        elif op == "cm":
            m = tuple(float(o) for o in ins.operands)
            ctm_stack[-1] = multiply(m, ctm_stack[-1])
        elif op in FILL_COLOR_OPS:
            color = color_from_operands(op, list(ins.operands))
            if color is not None:
                fill_color = color
        elif op in STROKE_COLOR_OPS:
            color = color_from_operands(op, list(ins.operands))
            if color is not None:
                stroke_color = color
        elif op in PATH_CONSTRUCTION_OPS:
            if path_start is None:
                path_start = i
        elif op in PAINT_TERMINATORS:
            if path_start is not None:
                points = _path_points(instructions, path_start, i)
                if points:
                    device_points = [apply(p, ctm_stack[-1]) for p in points]
                    bbox = bbox_of_points(device_points)
                    if op in FILL_PAINT_OPS:
                        result.fills.append(FillOp(path_start, i, bbox, fill_color))
                    elif op in STROKE_PAINT_OPS:
                        result.strokes.append(StrokeOp(path_start, i, stroke_color))
                path_start = None
        elif op == "Do":
            name = str(ins.operands[0])
            if name in image_xobject_names:
                corners = [apply(p, ctm_stack[-1]) for p in [(0, 0), (1, 0), (1, 1), (0, 1)]]
                result.images.append(ImageOp(i, name, bbox_of_points(corners)))
        elif op in TEXT_SHOW_OPS:
            result.text_shows.append(TextShowOp(i, fill_color))

    return result
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_walk.py -v`
Expected: PASS (7 passed)

- [ ] **Step 5: Commit**

```bash
git add src/pdfbetter/walk.py tests/test_walk.py
git commit -m "Add content-stream walker: CTM tracking and paint-op detection"
```

---

### Task 5: Classification

**Files:**
- Create: `src/pdfbetter/classify.py`
- Test: `tests/test_classify.py`

**Interfaces:**
- Consumes: `pdfbetter.color.luminance`, `pdfbetter.geometry.coverage_fraction`, `pdfbetter.walk.{WalkResult, FillOp, StrokeOp, ImageOp, TextShowOp}`.
- Produces: `Thresholds(background_coverage: float = 0.8, contrast_luminance: float = 0.6)`, `Decision(action: str, reason: str)` (`action` is `"drop"`, `"recolor"`, or `"keep"`), `Classified(fills: list[tuple[FillOp, Decision]], strokes: list[tuple[StrokeOp, Decision]], images: list[tuple[ImageOp, Decision]], text_shows: list[tuple[TextShowOp, Decision]])`, `classify(walk_result: WalkResult, page_width: float, page_height: float, thresholds: Thresholds = Thresholds()) -> Classified`.

- [ ] **Step 1: Write the failing tests**

Create `tests/test_classify.py`:

```python
from pdfbetter.classify import Thresholds, classify
from pdfbetter.color import Color
from pdfbetter.geometry import BBox
from pdfbetter.walk import FillOp, ImageOp, StrokeOp, TextShowOp, WalkResult


def test_classify_drops_full_page_fill():
    fill = FillOp(2, 3, BBox(0, 0, 612, 792), Color("rgb", (0.05, 0.05, 0.05)))
    result = classify(WalkResult(fills=[fill]), page_width=612, page_height=792)
    assert len(result.fills) == 1
    _, decision = result.fills[0]
    assert decision.action == "drop"


def test_classify_keeps_small_dark_fill():
    fill = FillOp(2, 3, BBox(0, 0, 40, 40), Color("rgb", (0.0, 0.0, 0.0)))
    result = classify(WalkResult(fills=[fill]), page_width=612, page_height=792)
    _, decision = result.fills[0]
    assert decision.action == "keep"


def test_classify_recolors_small_low_contrast_fill():
    fill = FillOp(2, 3, BBox(0, 0, 40, 40), Color("rgb", (0.95, 0.95, 0.95)))
    result = classify(WalkResult(fills=[fill]), page_width=612, page_height=792)
    _, decision = result.fills[0]
    assert decision.action == "recolor"


def test_classify_respects_custom_background_threshold():
    fill = FillOp(2, 3, BBox(0, 0, 400, 700), Color("rgb", (0.0, 0.0, 0.0)))
    loose = classify(WalkResult(fills=[fill]), page_width=612, page_height=792, thresholds=Thresholds(background_coverage=0.5))
    _, decision = loose.fills[0]
    assert decision.action == "drop"


def test_classify_drops_full_page_image():
    image = ImageOp(0, "/Bg", BBox(0, 0, 612, 792))
    result = classify(WalkResult(images=[image]), page_width=612, page_height=792)
    _, decision = result.images[0]
    assert decision.action == "drop"


def test_classify_keeps_small_image():
    image = ImageOp(0, "/Im0", BBox(72, 220, 112, 260))
    result = classify(WalkResult(images=[image]), page_width=612, page_height=792)
    _, decision = result.images[0]
    assert decision.action == "keep"


def test_classify_recolors_low_contrast_stroke():
    stroke = StrokeOp(1, 3, Color("rgb", (0.9, 0.9, 0.9)))
    result = classify(WalkResult(strokes=[stroke]), page_width=612, page_height=792)
    _, decision = result.strokes[0]
    assert decision.action == "recolor"


def test_classify_keeps_normal_contrast_stroke():
    stroke = StrokeOp(1, 3, Color("gray", (0.0,)))
    result = classify(WalkResult(strokes=[stroke]), page_width=612, page_height=792)
    _, decision = result.strokes[0]
    assert decision.action == "keep"


def test_classify_recolors_low_contrast_text():
    text = TextShowOp(1, Color("rgb", (1.0, 1.0, 1.0)))
    result = classify(WalkResult(text_shows=[text]), page_width=612, page_height=792)
    _, decision = result.text_shows[0]
    assert decision.action == "recolor"


def test_classify_keeps_normal_contrast_text():
    text = TextShowOp(1, Color("gray", (0.0,)))
    result = classify(WalkResult(text_shows=[text]), page_width=612, page_height=792)
    _, decision = result.text_shows[0]
    assert decision.action == "keep"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_classify.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'pdfbetter.classify'`

- [ ] **Step 3: Write the implementation**

Create `src/pdfbetter/classify.py`:

```python
from dataclasses import dataclass

from pdfbetter.color import luminance
from pdfbetter.geometry import coverage_fraction
from pdfbetter.walk import FillOp, ImageOp, StrokeOp, TextShowOp, WalkResult


@dataclass(frozen=True)
class Thresholds:
    background_coverage: float = 0.8
    contrast_luminance: float = 0.6


@dataclass(frozen=True)
class Decision:
    action: str
    reason: str


@dataclass(frozen=True)
class Classified:
    fills: list
    strokes: list
    images: list
    text_shows: list


def classify(
    walk_result: WalkResult,
    page_width: float,
    page_height: float,
    thresholds: Thresholds = Thresholds(),
) -> Classified:
    fills = []
    for fill in walk_result.fills:
        wf, hf = coverage_fraction(fill.bbox, page_width, page_height)
        lum = luminance(fill.color)
        if wf >= thresholds.background_coverage and hf >= thresholds.background_coverage:
            fills.append((fill, Decision("drop", f"fill covers {wf:.0%}x{hf:.0%} of page")))
        elif lum >= thresholds.contrast_luminance:
            fills.append((fill, Decision("recolor", f"fill luminance {lum:.2f} low-contrast on white")))
        else:
            fills.append((fill, Decision("keep", "normal-contrast fill below background threshold")))

    images = []
    for image in walk_result.images:
        wf, hf = coverage_fraction(image.bbox, page_width, page_height)
        if wf >= thresholds.background_coverage and hf >= thresholds.background_coverage:
            images.append((image, Decision("drop", f"image covers {wf:.0%}x{hf:.0%} of page")))
        else:
            images.append((image, Decision("keep", "below background threshold")))

    strokes = []
    for stroke in walk_result.strokes:
        lum = luminance(stroke.color)
        if lum >= thresholds.contrast_luminance:
            strokes.append((stroke, Decision("recolor", f"stroke luminance {lum:.2f} low-contrast on white")))
        else:
            strokes.append((stroke, Decision("keep", "normal-contrast stroke")))

    text_shows = []
    for text in walk_result.text_shows:
        lum = luminance(text.color)
        if lum >= thresholds.contrast_luminance:
            text_shows.append((text, Decision("recolor", f"text luminance {lum:.2f} low-contrast on white")))
        else:
            text_shows.append((text, Decision("keep", "normal-contrast text")))

    return Classified(fills=fills, strokes=strokes, images=images, text_shows=text_shows)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_classify.py -v`
Expected: PASS (10 passed)

- [ ] **Step 5: Commit**

```bash
git add src/pdfbetter/classify.py tests/test_classify.py
git commit -m "Add background/contrast classification against configurable thresholds"
```

---

### Task 6: Instruction-list editing

**Files:**
- Create: `src/pdfbetter/edit.py`
- Test: `tests/test_edit.py`

**Interfaces:**
- Consumes: `pdfbetter.color.black_operator`, `pdfbetter.classify.Classified`.
- Produces: `apply_edits(instructions: list, classified: Classified) -> tuple[list, set[str]]` (returns the edited instruction list and the set of XObject resource names to remove).

- [ ] **Step 1: Write the failing tests**

Create `tests/test_edit.py`:

```python
import pikepdf

from pdfbetter.classify import Classified, Decision
from pdfbetter.color import Color
from pdfbetter.edit import apply_edits
from pdfbetter.geometry import BBox
from pdfbetter.walk import FillOp, ImageOp, StrokeOp, TextShowOp


def _ins(operands, op):
    return pikepdf.ContentStreamInstruction(operands, pikepdf.Operator(op))


def _empty_classified(**kwargs):
    return Classified(
        fills=kwargs.get("fills", []),
        strokes=kwargs.get("strokes", []),
        images=kwargs.get("images", []),
        text_shows=kwargs.get("text_shows", []),
    )


def test_apply_edits_drops_background_fill_keeps_color_op():
    instructions = [
        _ins([0.05, 0.05, 0.05], "rg"),
        _ins([], "n"),
        _ins([0, 0, 612, 792], "re"),
        _ins([], "f*"),
    ]
    fill = FillOp(2, 3, BBox(0, 0, 612, 792), Color("rgb", (0.05, 0.05, 0.05)))
    classified = _empty_classified(fills=[(fill, Decision("drop", "covers 100%"))])
    output, removed = apply_edits(instructions, classified)
    assert [str(ins.operator) for ins in output] == ["rg", "n"]
    assert removed == set()


def test_apply_edits_wraps_low_contrast_text():
    instructions = [_ins([1, 1, 1], "rg"), _ins(["A"], "Tj")]
    text = TextShowOp(1, Color("rgb", (1, 1, 1)))
    classified = _empty_classified(text_shows=[(text, Decision("recolor", "low contrast"))])
    output, removed = apply_edits(instructions, classified)
    assert [str(ins.operator) for ins in output] == ["rg", "q", "rg", "Tj", "Q"]
    assert list(output[2].operands) == [0, 0, 0]
    assert list(output[3].operands) == ["A"]


def test_apply_edits_drops_background_image_and_collects_resource_name():
    instructions = [_ins([], "q"), _ins([612, 0, 0, 792, 0, 0], "cm"), _ins([pikepdf.Name("/Bg")], "Do"), _ins([], "Q")]
    image = ImageOp(2, "/Bg", BBox(0, 0, 612, 792))
    classified = _empty_classified(images=[(image, Decision("drop", "covers 100%"))])
    output, removed = apply_edits(instructions, classified)
    assert [str(ins.operator) for ins in output] == ["q", "cm", "Q"]
    assert removed == {"/Bg"}


def test_apply_edits_wraps_low_contrast_stroke():
    instructions = [_ins([0.9, 0.9, 0.9], "RG"), _ins([72, 622], "m"), _ins([540, 622], "l"), _ins([], "S")]
    stroke = StrokeOp(1, 3, Color("rgb", (0.9, 0.9, 0.9)))
    classified = _empty_classified(strokes=[(stroke, Decision("recolor", "low contrast"))])
    output, removed = apply_edits(instructions, classified)
    assert [str(ins.operator) for ins in output] == ["RG", "q", "RG", "m", "l", "S", "Q"]


def test_apply_edits_leaves_kept_untouched_content_unchanged():
    instructions = [_ins([0, 0, 0], "rg"), _ins(["Normal text"], "Tj")]
    text = TextShowOp(1, Color("gray", (0.0,)))
    classified = _empty_classified(text_shows=[(text, Decision("keep", "normal-contrast text"))])
    output, removed = apply_edits(instructions, classified)
    assert [str(ins.operator) for ins in output] == ["rg", "Tj"]
    assert removed == set()
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_edit.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'pdfbetter.edit'`

- [ ] **Step 3: Write the implementation**

Create `src/pdfbetter/edit.py`:

```python
import pikepdf

from pdfbetter.classify import Classified
from pdfbetter.color import black_operator


def apply_edits(instructions: list, classified: Classified) -> tuple[list, set]:
    drop_ranges = []
    wrap_ranges = []
    drop_single = set()
    wrap_single = {}
    xobject_names_to_remove = set()

    for fill, decision in classified.fills:
        if decision.action == "drop":
            drop_ranges.append((fill.start, fill.end))
        elif decision.action == "recolor":
            wrap_ranges.append((fill.start, fill.end, fill.color.colorspace, "fill"))

    for stroke, decision in classified.strokes:
        if decision.action == "recolor":
            wrap_ranges.append((stroke.start, stroke.end, stroke.color.colorspace, "stroke"))

    for image, decision in classified.images:
        if decision.action == "drop":
            drop_single.add(image.index)
            xobject_names_to_remove.add(image.xobject_name)

    for text, decision in classified.text_shows:
        if decision.action == "recolor":
            wrap_single[text.index] = (text.color.colorspace, "fill")

    def in_drop_range(idx: int) -> bool:
        return any(start <= idx <= end for start, end in drop_ranges)

    wrap_starts = {start: (colorspace, target) for start, end, colorspace, target in wrap_ranges}
    wrap_ends = {end for _, end, _, _ in wrap_ranges}

    output = []
    for i, ins in enumerate(instructions):
        if in_drop_range(i) or i in drop_single:
            continue
        if i in wrap_single:
            colorspace, target = wrap_single[i]
            output.append(pikepdf.ContentStreamInstruction([], pikepdf.Operator("q")))
            output.append(black_operator(colorspace, target))
            output.append(ins)
            output.append(pikepdf.ContentStreamInstruction([], pikepdf.Operator("Q")))
            continue
        if i in wrap_starts:
            colorspace, target = wrap_starts[i]
            output.append(pikepdf.ContentStreamInstruction([], pikepdf.Operator("q")))
            output.append(black_operator(colorspace, target))
        output.append(ins)
        if i in wrap_ends:
            output.append(pikepdf.ContentStreamInstruction([], pikepdf.Operator("Q")))

    return output, xobject_names_to_remove
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_edit.py -v`
Expected: PASS (5 passed)

- [ ] **Step 5: Commit**

```bash
git add src/pdfbetter/edit.py tests/test_edit.py
git commit -m "Add instruction-list editor: drop background paints, wrap low-contrast recolors"
```

---

### Task 7: Audit report and debug overlay

**Files:**
- Create: `src/pdfbetter/audit.py`
- Test: `tests/test_audit.py`

**Interfaces:**
- Consumes: `pdfbetter.classify.Classified`.
- Produces: `build_report(classified_by_page: dict[int, Classified]) -> dict`, `write_report(classified_by_page: dict[int, Classified], path: str) -> None`, `write_debug_overlay(pdf, classified_by_page: dict[int, Classified], path: str) -> None` (`pdf` is a `pikepdf.Pdf`).

- [ ] **Step 1: Write the failing tests**

Create `tests/test_audit.py`:

```python
import json

import pikepdf

from pdfbetter.audit import build_report, write_debug_overlay, write_report
from pdfbetter.classify import Classified, Decision
from pdfbetter.color import Color
from pdfbetter.geometry import BBox
from pdfbetter.walk import FillOp, ImageOp


def test_build_report_lists_drop_and_keep_entries_with_reasons():
    fill = FillOp(2, 3, BBox(0, 0, 612, 792), Color("rgb", (0.05, 0.05, 0.05)))
    classified = Classified(fills=[(fill, Decision("drop", "fill covers 100%x100% of page"))], strokes=[], images=[], text_shows=[])
    report = build_report({0: classified})
    assert report["pages"][0]["page_number"] == 0
    entry = report["pages"][0]["entries"][0]
    assert entry["kind"] == "fill"
    assert entry["action"] == "drop"
    assert entry["reason"] == "fill covers 100%x100% of page"
    assert entry["bbox"] == [0, 0, 612, 792]


def test_write_report_produces_valid_json_file(tmp_path):
    image = ImageOp(0, "/Bg", BBox(0, 0, 612, 792))
    classified = Classified(fills=[], strokes=[], images=[(image, Decision("drop", "image covers 100%x100% of page"))], text_shows=[])
    path = tmp_path / "report.json"
    write_report({0: classified}, str(path))
    with open(path, encoding="utf-8") as f:
        report = json.load(f)
    assert report["pages"][0]["entries"][0]["kind"] == "image"
    assert report["pages"][0]["entries"][0]["xobject_name"] == "/Bg"


def test_write_debug_overlay_adds_annotation_rects(tmp_path):
    pdf = pikepdf.new()
    page = pdf.add_blank_page(page_size=(612, 792))
    page.Contents = pdf.make_stream(b"")
    fill = FillOp(2, 3, BBox(10, 10, 100, 100), Color("rgb", (0.05, 0.05, 0.05)))
    classified = Classified(fills=[(fill, Decision("drop", "test"))], strokes=[], images=[], text_shows=[])
    path = tmp_path / "debug.pdf"
    write_debug_overlay(pdf, {0: classified}, str(path))

    reopened = pikepdf.open(str(path))
    instructions = pikepdf.parse_content_stream(reopened.pages[0])
    ops = [str(ins.operator) for ins in instructions]
    assert "re" in ops
    assert "S" in ops
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_audit.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'pdfbetter.audit'`

- [ ] **Step 3: Write the implementation**

Create `src/pdfbetter/audit.py`:

```python
import json

import pikepdf


def build_report(classified_by_page: dict) -> dict:
    pages = []
    for page_number in sorted(classified_by_page):
        classified = classified_by_page[page_number]
        entries = []
        for fill, decision in classified.fills:
            entries.append({
                "kind": "fill",
                "action": decision.action,
                "reason": decision.reason,
                "bbox": [fill.bbox.x0, fill.bbox.y0, fill.bbox.x1, fill.bbox.y1],
            })
        for image, decision in classified.images:
            entries.append({
                "kind": "image",
                "action": decision.action,
                "reason": decision.reason,
                "xobject_name": image.xobject_name,
                "bbox": [image.bbox.x0, image.bbox.y0, image.bbox.x1, image.bbox.y1],
            })
        for stroke, decision in classified.strokes:
            entries.append({"kind": "stroke", "action": decision.action, "reason": decision.reason})
        for text, decision in classified.text_shows:
            entries.append({"kind": "text", "action": decision.action, "reason": decision.reason})
        pages.append({"page_number": page_number, "entries": entries})
    return {"pages": pages}


def write_report(classified_by_page: dict, path: str) -> None:
    report = build_report(classified_by_page)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(report, f, indent=2)


def write_debug_overlay(pdf, classified_by_page: dict, path: str) -> None:
    for page_number, classified in classified_by_page.items():
        page = pdf.pages[page_number]
        dropped_bboxes = [fill.bbox for fill, decision in classified.fills if decision.action == "drop"]
        dropped_bboxes += [image.bbox for image, decision in classified.images if decision.action == "drop"]
        if not dropped_bboxes:
            continue

        overlay = [
            pikepdf.ContentStreamInstruction([], pikepdf.Operator("q")),
            pikepdf.ContentStreamInstruction([1, 0, 1], pikepdf.Operator("RG")),
            pikepdf.ContentStreamInstruction([2], pikepdf.Operator("w")),
        ]
        for bbox in dropped_bboxes:
            overlay.append(pikepdf.ContentStreamInstruction([bbox.x0, bbox.y0, bbox.width, bbox.height], pikepdf.Operator("re")))
            overlay.append(pikepdf.ContentStreamInstruction([], pikepdf.Operator("S")))
        overlay.append(pikepdf.ContentStreamInstruction([], pikepdf.Operator("Q")))

        existing = pikepdf.parse_content_stream(page)
        combined = list(existing) + overlay
        page.Contents = pdf.make_stream(pikepdf.unparse_content_stream(combined))

    pdf.save(path)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_audit.py -v`
Expected: PASS (3 passed)

- [ ] **Step 5: Commit**

```bash
git add src/pdfbetter/audit.py tests/test_audit.py
git commit -m "Add JSON audit report and debug overlay PDF for classification decisions"
```

---

### Task 8: Pipeline orchestration and end-to-end test fixture

**Files:**
- Create: `src/pdfbetter/pipeline.py`
- Create: `tests/conftest.py`
- Test: `tests/test_pipeline.py`

**Interfaces:**
- Consumes: `pdfbetter.walk.walk_page`, `pdfbetter.classify.{Thresholds, classify, Classified}`, `pdfbetter.edit.apply_edits`, `pdfbetter.audit.{write_report, write_debug_overlay}`.
- Produces: `ProcessResult(output_path: str, pages_processed: int, failed_pages: list[tuple[int, str]], blank_pages: list[int], audit_report_path: str | None, audit_overlay_path: str | None)`, `process(input_path: str, output_path: str, *, thresholds: Thresholds = Thresholds(), audit: bool = False, audit_report_path: str | None = None, audit_overlay_path: str | None = None) -> ProcessResult`. This is the package's public API, used directly by `cli.py` in Task 9.

Per the design spec's error-handling section: a single page's processing failure must not abort the rest of the document (collected in `failed_pages`, page continues to next), and a page whose only fills/images all get dropped as background (leaving no other content) must be flagged (`blank_pages`), not silently produced as an empty page without comment.

- [ ] **Step 1: Create the synthetic PDF fixture**

Create `tests/conftest.py`:

```python
import os

import pikepdf
import pytest
import reportlab
from PIL import Image
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.pdfgen import canvas


@pytest.fixture
def synthetic_pdf_path(tmp_path):
    vera = os.path.join(os.path.dirname(reportlab.__file__), "fonts", "Vera.ttf")
    pdfmetrics.registerFont(TTFont("VeraEmbed", vera))

    img_path = tmp_path / "small.png"
    Image.new("RGB", (40, 40), (200, 30, 30)).save(img_path)

    pdf_path = tmp_path / "source.pdf"
    c = canvas.Canvas(str(pdf_path), pagesize=(612, 792))
    c.setFillColorRGB(0.05, 0.05, 0.05)
    c.rect(0, 0, 612, 792, fill=1, stroke=0)
    c.setFont("VeraEmbed", 24)
    c.setFillColorRGB(1, 1, 1)
    c.drawString(72, 692, "Hello")
    c.setFont("Helvetica", 12)
    c.setFillColorRGB(0, 0, 0)
    c.drawString(72, 642, "Normal body text, standard font, already dark.")
    c.setStrokeColorRGB(0, 0, 0)
    c.setLineWidth(1)
    c.line(72, 622, 540, 622)
    c.drawImage(str(img_path), 72, 532, width=40, height=40)
    c.showPage()
    c.save()
    return str(pdf_path)


@pytest.fixture
def embedded_font_resource_name(synthetic_pdf_path):
    pdf = pikepdf.open(synthetic_pdf_path)
    for name, fdict in pdf.pages[0].Resources.Font.items():
        if fdict.get("/Subtype") == pikepdf.Name("/TrueType"):
            return str(name)
    raise AssertionError("no embedded TrueType font found in synthetic fixture")


@pytest.fixture
def background_only_pdf_path(tmp_path):
    """A page whose only content is a full-bleed background fill -- nothing
    else -- so background-stripping should leave the page blank."""
    pdf_path = tmp_path / "background_only.pdf"
    c = canvas.Canvas(str(pdf_path), pagesize=(612, 792))
    c.setFillColorRGB(0.05, 0.05, 0.05)
    c.rect(0, 0, 612, 792, fill=1, stroke=0)
    c.showPage()
    c.save()
    return str(pdf_path)
```

- [ ] **Step 2: Write the failing tests**

Create `tests/test_pipeline.py`:

```python
import json

import pdfplumber
import pikepdf

from pdfbetter.classify import Thresholds
from pdfbetter.pipeline import process


def test_pipeline_strips_background_keeps_content(synthetic_pdf_path, tmp_path):
    output_path = str(tmp_path / "output.pdf")
    result = process(synthetic_pdf_path, output_path, thresholds=Thresholds())

    assert result.pages_processed == 1

    with pdfplumber.open(output_path) as pdf:
        page = pdf.pages[0]
        assert page.rects == []
        assert len(page.lines) == 1
        assert len(page.images) == 1
        hello_chars = [ch for ch in page.chars if ch["text"] == "H"]
        assert hello_chars
        assert hello_chars[0]["non_stroking_color"] == (0.0, 0.0, 0.0)
        dark_chars = [ch for ch in page.chars if ch["text"] == "N"]
        assert dark_chars
        assert dark_chars[0]["non_stroking_color"] == (0, 0, 0)


def test_pipeline_preserves_embedded_font_bytes_exactly(synthetic_pdf_path, embedded_font_resource_name, tmp_path):
    output_path = str(tmp_path / "output.pdf")
    process(synthetic_pdf_path, output_path)

    source_pdf = pikepdf.open(synthetic_pdf_path)
    output_pdf = pikepdf.open(output_path)
    source_font = source_pdf.pages[0].Resources.Font[embedded_font_resource_name]
    output_font = output_pdf.pages[0].Resources.Font[embedded_font_resource_name]
    source_bytes = bytes(source_font.FontDescriptor.FontFile2.read_bytes())
    output_bytes = bytes(output_font.FontDescriptor.FontFile2.read_bytes())
    assert source_bytes == output_bytes


def test_pipeline_audit_report_lists_dropped_background(synthetic_pdf_path, tmp_path):
    output_path = str(tmp_path / "output.pdf")
    report_path = str(tmp_path / "report.json")
    overlay_path = str(tmp_path / "overlay.pdf")
    result = process(
        synthetic_pdf_path,
        output_path,
        audit=True,
        audit_report_path=report_path,
        audit_overlay_path=overlay_path,
    )

    assert result.audit_report_path == report_path
    assert result.audit_overlay_path == overlay_path

    with open(report_path, encoding="utf-8") as f:
        report = json.load(f)
    dropped = [e for e in report["pages"][0]["entries"] if e["action"] == "drop"]
    assert len(dropped) == 1
    assert dropped[0]["kind"] == "fill"


def test_pipeline_respects_custom_thresholds(synthetic_pdf_path, tmp_path):
    output_path = str(tmp_path / "output.pdf")
    process(synthetic_pdf_path, output_path, thresholds=Thresholds(background_coverage=1.5))

    with pdfplumber.open(output_path) as pdf:
        page = pdf.pages[0]
        assert len(page.rects) == 1


def test_pipeline_flags_page_that_becomes_blank(background_only_pdf_path, tmp_path):
    output_path = str(tmp_path / "output.pdf")
    result = process(background_only_pdf_path, output_path)

    assert result.blank_pages == [0]
    assert result.failed_pages == []


def test_pipeline_does_not_flag_normal_page_as_blank(synthetic_pdf_path, tmp_path):
    output_path = str(tmp_path / "output.pdf")
    result = process(synthetic_pdf_path, output_path)

    assert result.blank_pages == []
    assert result.failed_pages == []
```

- [ ] **Step 3: Run tests to verify they fail**

Run: `uv run pytest tests/test_pipeline.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'pdfbetter.pipeline'`

- [ ] **Step 4: Write the implementation**

Create `src/pdfbetter/pipeline.py`:

```python
from dataclasses import dataclass, field

import pikepdf

from pdfbetter.audit import write_debug_overlay, write_report
from pdfbetter.classify import Classified, Thresholds, classify
from pdfbetter.edit import apply_edits
from pdfbetter.walk import walk_page


@dataclass(frozen=True)
class ProcessResult:
    output_path: str
    pages_processed: int
    failed_pages: list = field(default_factory=list)
    blank_pages: list = field(default_factory=list)
    audit_report_path: str | None = None
    audit_overlay_path: str | None = None


def _image_xobject_names(page) -> set:
    xobjects = page.Resources.get("/XObject", {})
    return {
        str(name)
        for name, obj in xobjects.items()
        if obj.get("/Subtype") == pikepdf.Name("/Image")
    }


def _page_became_blank(classified: Classified, walk_result) -> bool:
    had_fill_or_image = bool(walk_result.fills or walk_result.images)
    kept_fills = [d for _, d in classified.fills if d.action != "drop"]
    kept_images = [d for _, d in classified.images if d.action != "drop"]
    now_empty = not kept_fills and not kept_images and not classified.strokes and not classified.text_shows
    return had_fill_or_image and now_empty


def process(
    input_path: str,
    output_path: str,
    *,
    thresholds: Thresholds = Thresholds(),
    audit: bool = False,
    audit_report_path: str | None = None,
    audit_overlay_path: str | None = None,
) -> ProcessResult:
    pdf = pikepdf.open(input_path)
    classified_by_page: dict[int, Classified] = {}
    failed_pages = []
    blank_pages = []

    for page_number, page in enumerate(pdf.pages):
        try:
            mediabox = page.mediabox
            page_width = float(mediabox[2]) - float(mediabox[0])
            page_height = float(mediabox[3]) - float(mediabox[1])
            image_names = _image_xobject_names(page)

            instructions = pikepdf.parse_content_stream(page)
            walk_result = walk_page(instructions, page_width, page_height, image_names)
            classified = classify(walk_result, page_width, page_height, thresholds)
            classified_by_page[page_number] = classified

            if _page_became_blank(classified, walk_result):
                blank_pages.append(page_number)

            new_instructions, xobject_names_to_remove = apply_edits(instructions, classified)
            page.Contents = pdf.make_stream(pikepdf.unparse_content_stream(new_instructions))
            xobjects = page.Resources.get("/XObject", {})
            for name in xobject_names_to_remove:
                if name in xobjects:
                    del page.Resources.XObject[name]
        except Exception as exc:
            failed_pages.append((page_number, str(exc)))

    pdf.save(output_path)

    report_path = None
    overlay_path = None
    if audit:
        report_path = audit_report_path or f"{output_path}.audit.json"
        write_report(classified_by_page, report_path)
        overlay_path = audit_overlay_path or f"{output_path}.debug.pdf"
        write_debug_overlay(pdf, classified_by_page, overlay_path)

    return ProcessResult(
        output_path=output_path,
        pages_processed=len(pdf.pages),
        failed_pages=failed_pages,
        blank_pages=blank_pages,
        audit_report_path=report_path,
        audit_overlay_path=overlay_path,
    )
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `uv run pytest tests/test_pipeline.py -v`
Expected: PASS (6 passed)

- [ ] **Step 6: Run the full test suite so far**

Run: `uv run pytest -v`
Expected: all tests across all modules PASS

- [ ] **Step 7: Commit**

```bash
git add src/pdfbetter/pipeline.py tests/conftest.py tests/test_pipeline.py
git commit -m "Add pipeline orchestration with end-to-end synthetic-PDF test coverage"
```

---

### Task 9: CLI

**Files:**
- Create: `src/pdfbetter/cli.py`
- Test: `tests/test_cli.py`

**Interfaces:**
- Consumes: `pdfbetter.classify.Thresholds`, `pdfbetter.pipeline.process`.
- Produces: `main(argv: list | None = None) -> int`, registered as the `pdfbetter` console script (already wired in `pyproject.toml` from Task 1).

- [ ] **Step 1: Write the failing tests**

Create `tests/test_cli.py`:

```python
import os

from pdfbetter.cli import main


def test_cli_writes_output_pdf(synthetic_pdf_path, tmp_path, capsys):
    output_path = str(tmp_path / "output.pdf")
    exit_code = main([synthetic_pdf_path, "-o", output_path])

    assert exit_code == 0
    assert os.path.exists(output_path)
    captured = capsys.readouterr()
    assert "wrote" in captured.out


def test_cli_reports_failure_for_missing_input(tmp_path, capsys):
    exit_code = main([str(tmp_path / "does-not-exist.pdf"), "-o", str(tmp_path / "out.pdf")])

    assert exit_code == 1
    captured = capsys.readouterr()
    assert "failed to process" in captured.err


def test_cli_audit_flag_writes_report(synthetic_pdf_path, tmp_path, capsys):
    output_path = str(tmp_path / "output.pdf")
    exit_code = main([synthetic_pdf_path, "-o", output_path, "--audit"])

    assert exit_code == 0
    assert os.path.exists(f"{output_path}.audit.json")
    captured = capsys.readouterr()
    assert "audit report" in captured.out


def test_cli_custom_threshold_flag_is_applied(synthetic_pdf_path, tmp_path):
    import pdfplumber

    output_path = str(tmp_path / "output.pdf")
    main([synthetic_pdf_path, "-o", output_path, "--bg-threshold", "1.5"])

    with pdfplumber.open(output_path) as pdf:
        assert len(pdf.pages[0].rects) == 1


def test_cli_warns_but_succeeds_on_blank_page(background_only_pdf_path, tmp_path, capsys):
    output_path = str(tmp_path / "output.pdf")
    exit_code = main([background_only_pdf_path, "-o", output_path])

    assert exit_code == 0
    captured = capsys.readouterr()
    assert "no content left after background removal" in captured.err
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_cli.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'pdfbetter.cli'`

- [ ] **Step 3: Write the implementation**

Create `src/pdfbetter/cli.py`:

```python
import argparse
import sys

from pdfbetter.classify import Thresholds
from pdfbetter.pipeline import process


def main(argv: list | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="pdfbetter",
        description="Strip ink-heavy backgrounds from a PDF, keeping content faithful.",
    )
    parser.add_argument("input", help="path to the source PDF")
    parser.add_argument("-o", "--output", required=True, help="path to write the output PDF")
    parser.add_argument(
        "--bg-threshold",
        type=float,
        default=0.8,
        help="min page-coverage fraction (0-1) for a fill/image to be treated as background (default: 0.8)",
    )
    parser.add_argument(
        "--contrast-luminance",
        type=float,
        default=0.6,
        help="min luminance (0-1) for a kept color to be recolored to black (default: 0.6)",
    )
    parser.add_argument(
        "--audit",
        action="store_true",
        help="also write a JSON classification report and a debug overlay PDF",
    )
    args = parser.parse_args(argv)

    thresholds = Thresholds(background_coverage=args.bg_threshold, contrast_luminance=args.contrast_luminance)
    try:
        result = process(args.input, args.output, thresholds=thresholds, audit=args.audit)
    except Exception as exc:
        print(f"pdfbetter: failed to process {args.input}: {exc}", file=sys.stderr)
        return 1

    print(f"pdfbetter: wrote {result.output_path} ({result.pages_processed} pages)")
    if args.audit:
        print(f"pdfbetter: audit report at {result.audit_report_path}")
        print(f"pdfbetter: debug overlay at {result.audit_overlay_path}")
    for page_number in result.blank_pages:
        print(f"pdfbetter: warning: page {page_number} has no content left after background removal", file=sys.stderr)
    if result.failed_pages:
        for page_number, message in result.failed_pages:
            print(f"pdfbetter: page {page_number} failed to process: {message}", file=sys.stderr)
        print(f"pdfbetter: {len(result.failed_pages)} page(s) failed, see above", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_cli.py -v`
Expected: PASS (5 passed)

- [ ] **Step 5: Verify the installed console script works end-to-end**

Run: `uv run pdfbetter --help`
Expected: prints usage text, exit code 0

- [ ] **Step 6: Run the entire test suite**

Run: `uv run pytest -v`
Expected: all tests across the whole package PASS

- [ ] **Step 7: Commit**

```bash
git add src/pdfbetter/cli.py tests/test_cli.py
git commit -m "Add pdfbetter CLI entry point"
```

---

### Task 10: Manual smoke test against the real sample PDF, and README

**Files:**
- Modify: `README.md`

**Interfaces:**
- Consumes: nothing (this task doesn't add library code).
- Produces: a filled-in `README.md`; no new public interfaces.

- [ ] **Step 1: Manually smoke-test against the real sample file**

Run: `uv run pdfbetter input/DND5.5e.pdf -o /tmp/dnd-output.pdf --audit`

Expected: completes without a crash (may take a while given the file's size), prints a page count, and writes `/tmp/dnd-output.pdf` plus `/tmp/dnd-output.pdf.audit.json`. Open a few pages of both the audit JSON and the output PDF and confirm backgrounds look stripped and text/art are intact. This file is too large for automated CI (per the design spec) — this is a manual, one-time verification step, not a repeatable test.

- [ ] **Step 2: Write `README.md`**

Replace the contents of `README.md` (currently a placeholder comment) with:

`````markdown
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
recolor low-contrast kept ones in place, reassemble). The implementation
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
- [ ] Manual smoke test against `input/DND5.5e.pdf` and note any misclassifications found (adjust `--bg-threshold` default if the 80% heuristic proves wrong in practice on a real, large, multi-section rulebook)
- [ ] Decide whether combined fill+stroke operators (`B`/`B*`/`b`/`b*`) need independent stroke-recolor handling — currently they're only ever treated as fills (see `walk.py` note); revisit if real-world testing finds a case where this drops a border that should have stayed
- [ ] Consider a `--dry-run` mode that only writes the audit report/overlay, no output PDF, for faster iteration on threshold tuning against a large file
- [ ] Consider whether `/Resources` inherited from a parent `/Pages` node (rather than set directly on the page) needs explicit resolution — current code assumes `page.Resources`/`page.mediabox` are directly accessible, which pikepdf's `.mediabox` property already handles, but `.Resources` XObject-deletion code does not go through an inherited-attribute helper

Whoever picks this up next: read the design spec first, then the plan above
— the plan has exact function signatures for every module, so cross-module
changes should update both this file's checklist and the relevant module's
docstring-level intent, not just the code.
`````

- [ ] **Step 3: Commit**

```bash
git add README.md
git commit -m "Write README with usage, design pointers, and status/next-up checklist"
```

---

### Task 11: Never drop content that would leave a page blank

**Why:** the manual smoke test against `input/DND5.5e.pdf` (a fully rasterized PDF — every page is one full-page image, zero text/vector operators) found that the classifier drops that one image on every page (it exceeds the 80% background-coverage threshold), leaving every page blank. The design spec's "scanned image-only pages" section anticipated and accepted this as a known limitation, but the user asked for a small safety rule instead: never drop a fill/image if doing so would leave the page with zero remaining content. Keep the content untouched on that page instead, and report it as "left unchanged" rather than producing a blank page.

**Files:**
- Modify: `src/pdfbetter/pipeline.py`
- Modify: `src/pdfbetter/cli.py`
- Modify: `tests/test_pipeline.py`
- Modify: `tests/test_cli.py`
- Modify: `tests/conftest.py` (docstring only)

**Interfaces:**
- Consumes: `pdfbetter.classify.{Classified, Decision}`.
- Produces: `ProcessResult.unimproved_pages: list[int]` — replaces `ProcessResult.blank_pages` (renamed; the old field never actually reaches the caller with a truly-blank page anymore, since this task prevents that outcome). `pipeline._would_become_blank` and `pipeline._keep_everything` are new private helpers.

This task **replaces** `blank_pages` with `unimproved_pages` everywhere it appears (`pipeline.py`, `cli.py`, and the tests) — it is a rename plus a behavior change, not an addition alongside the old field.

- [ ] **Step 1: Update the failing/changing tests in `tests/test_pipeline.py`**

Replace the two blank-page tests (currently `test_pipeline_flags_page_that_becomes_blank` and `test_pipeline_does_not_flag_normal_page_as_blank`) with:

```python
def test_pipeline_leaves_page_unchanged_when_stripping_would_blank_it(background_only_pdf_path, tmp_path):
    output_path = str(tmp_path / "output.pdf")
    result = process(background_only_pdf_path, output_path)

    assert result.unimproved_pages == [0]
    assert result.failed_pages == []

    with pdfplumber.open(output_path) as pdf:
        assert len(pdf.pages[0].rects) == 1


def test_pipeline_does_not_flag_normal_page_as_unimproved(synthetic_pdf_path, tmp_path):
    output_path = str(tmp_path / "output.pdf")
    result = process(synthetic_pdf_path, output_path)

    assert result.unimproved_pages == []
    assert result.failed_pages == []
```

- [ ] **Step 2: Run the pipeline tests to verify the new ones fail**

Run: `uv run pytest tests/test_pipeline.py -v`
Expected: FAIL — `test_pipeline_leaves_page_unchanged_when_stripping_would_blank_it` fails because `ProcessResult` has no `unimproved_pages` attribute yet (`AttributeError`), and the background rect is currently dropped (0 rects, not 1) under the old behavior.

- [ ] **Step 3: Update `src/pdfbetter/pipeline.py`**

Replace the whole file with:

```python
from dataclasses import dataclass, field

import pikepdf

from pdfbetter.audit import write_debug_overlay, write_report
from pdfbetter.classify import Classified, Decision, Thresholds, classify
from pdfbetter.edit import apply_edits
from pdfbetter.walk import walk_page


@dataclass(frozen=True)
class ProcessResult:
    output_path: str
    pages_processed: int
    failed_pages: list = field(default_factory=list)
    unimproved_pages: list = field(default_factory=list)
    audit_report_path: str | None = None
    audit_overlay_path: str | None = None


def _image_xobject_names(page) -> set:
    xobjects = page.Resources.get("/XObject", {})
    return {
        str(name)
        for name, obj in xobjects.items()
        if obj.get("/Subtype") == pikepdf.Name("/Image")
    }


def _would_become_blank(classified: Classified, walk_result) -> bool:
    had_fill_or_image = bool(walk_result.fills or walk_result.images)
    kept_fills = [d for _, d in classified.fills if d.action != "drop"]
    kept_images = [d for _, d in classified.images if d.action != "drop"]
    now_empty = not kept_fills and not kept_images and not classified.strokes and not classified.text_shows
    return had_fill_or_image and now_empty


def _keep_everything(classified: Classified) -> Classified:
    reason = "kept: dropping would have left the page with no content"
    fills = [
        (op, Decision("keep", reason)) if d.action == "drop" else (op, d)
        for op, d in classified.fills
    ]
    images = [
        (op, Decision("keep", reason)) if d.action == "drop" else (op, d)
        for op, d in classified.images
    ]
    return Classified(fills=fills, strokes=classified.strokes, images=images, text_shows=classified.text_shows)


def process(
    input_path: str,
    output_path: str,
    *,
    thresholds: Thresholds = Thresholds(),
    audit: bool = False,
    audit_report_path: str | None = None,
    audit_overlay_path: str | None = None,
) -> ProcessResult:
    pdf = pikepdf.open(input_path)
    classified_by_page: dict[int, Classified] = {}
    failed_pages = []
    unimproved_pages = []

    for page_number, page in enumerate(pdf.pages):
        try:
            mediabox = page.mediabox
            page_width = float(mediabox[2]) - float(mediabox[0])
            page_height = float(mediabox[3]) - float(mediabox[1])
            image_names = _image_xobject_names(page)

            instructions = pikepdf.parse_content_stream(page)
            walk_result = walk_page(instructions, page_width, page_height, image_names)
            classified = classify(walk_result, page_width, page_height, thresholds)

            if _would_become_blank(classified, walk_result):
                classified = _keep_everything(classified)
                unimproved_pages.append(page_number)

            classified_by_page[page_number] = classified

            new_instructions, xobject_names_to_remove = apply_edits(instructions, classified)
            page.Contents = pdf.make_stream(pikepdf.unparse_content_stream(new_instructions))
            xobjects = page.Resources.get("/XObject", {})
            for name in xobject_names_to_remove:
                if name in xobjects:
                    del page.Resources.XObject[name]
        except Exception as exc:
            failed_pages.append((page_number, str(exc)))

    pdf.save(output_path)

    report_path = None
    overlay_path = None
    if audit:
        report_path = audit_report_path or f"{output_path}.audit.json"
        write_report(classified_by_page, report_path)
        overlay_path = audit_overlay_path or f"{output_path}.debug.pdf"
        write_debug_overlay(pdf, classified_by_page, overlay_path)

    return ProcessResult(
        output_path=output_path,
        pages_processed=len(pdf.pages),
        failed_pages=failed_pages,
        unimproved_pages=unimproved_pages,
        audit_report_path=report_path,
        audit_overlay_path=overlay_path,
    )
```

- [ ] **Step 4: Run the pipeline tests to verify they pass**

Run: `uv run pytest tests/test_pipeline.py -v`
Expected: PASS (all pipeline tests, including the 2 updated ones)

- [ ] **Step 5: Update `tests/test_cli.py`**

Replace `test_cli_warns_but_succeeds_on_blank_page` with:

```python
def test_cli_warns_but_succeeds_on_unimproved_page(background_only_pdf_path, tmp_path, capsys):
    output_path = str(tmp_path / "output.pdf")
    exit_code = main([background_only_pdf_path, "-o", output_path])

    assert exit_code == 0
    captured = capsys.readouterr()
    assert "left unchanged" in captured.err
```

- [ ] **Step 6: Update `src/pdfbetter/cli.py`**

Replace this block:

```python
    for page_number in result.blank_pages:
        print(f"pdfbetter: warning: page {page_number} has no content left after background removal", file=sys.stderr)
```

with:

```python
    for page_number in result.unimproved_pages:
        print(f"pdfbetter: warning: page {page_number} left unchanged (background removal would have left it blank)", file=sys.stderr)
```

- [ ] **Step 7: Update the docstring in `tests/conftest.py`**

Change the `background_only_pdf_path` fixture's docstring from:

```python
    """A page whose only content is a full-bleed background fill -- nothing
    else -- so background-stripping should leave the page blank."""
```

to:

```python
    """A page whose only content is a full-bleed background fill -- nothing
    else -- so the safety rule should leave it unchanged rather than
    stripping it down to a blank page."""
```

- [ ] **Step 8: Run the full test suite**

Run: `uv run pytest -v`
Expected: all tests pass (same total count as before, since this renamed 2 tests and updated 1, not added new ones)

- [ ] **Step 9: Commit**

```bash
git add src/pdfbetter/pipeline.py src/pdfbetter/cli.py tests/test_pipeline.py tests/test_cli.py tests/conftest.py
git commit -m "Never drop content that would leave a page blank; report as unimproved instead"
```

---

### Task 12: Default output location when `-o` is omitted

**Why:** the user asked for `-o`/`--output` to become optional: default to `./output` (relative to the current working directory) if that directory already exists; otherwise fall back to a `PDFBETTER OUTPUT` folder under the platform's Documents directory, creating it if needed. The output filename is derived from the input file's name.

**Files:**
- Modify: `src/pdfbetter/cli.py`
- Modify: `tests/test_cli.py`

**Interfaces:**
- Consumes: nothing new.
- Produces: `cli._default_output_path(input_path: str) -> str` (new private helper). `main`'s `-o`/`--output` argument becomes optional; behavior when provided is unchanged.

- [ ] **Step 1: Write the failing tests**

Add to `tests/test_cli.py` (add `from pathlib import Path` to the top of the file alongside the existing `import os`):

```python
def test_cli_defaults_output_to_existing_output_dir(synthetic_pdf_path, tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    (tmp_path / "output").mkdir()

    exit_code = main([synthetic_pdf_path])

    assert exit_code == 0
    expected = tmp_path / "output" / f"{Path(synthetic_pdf_path).stem}_printerfriendly.pdf"
    assert expected.exists()


def test_cli_defaults_output_to_documents_folder_when_no_output_dir(synthetic_pdf_path, tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    fake_home = tmp_path / "home"
    fake_home.mkdir()
    monkeypatch.setattr(Path, "home", lambda: fake_home)

    exit_code = main([synthetic_pdf_path])

    assert exit_code == 0
    expected = fake_home / "Documents" / "PDFBETTER OUTPUT" / f"{Path(synthetic_pdf_path).stem}_printerfriendly.pdf"
    assert expected.exists()


def test_cli_explicit_output_still_overrides_default(synthetic_pdf_path, tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    explicit_path = str(tmp_path / "explicit.pdf")

    exit_code = main([synthetic_pdf_path, "-o", explicit_path])

    assert exit_code == 0
    assert os.path.exists(explicit_path)
    assert not (tmp_path / "output").exists()
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_cli.py -v`
Expected: FAIL — the first two new tests fail because `-o` is currently required (`argparse` exits with an error/`SystemExit` when it's omitted); the third passes already (explicit `-o` already works) but run the file together to confirm the first two fail for the expected reason.

- [ ] **Step 3: Update `src/pdfbetter/cli.py`**

Add `from pathlib import Path` to the imports, add this new function before `main`:

```python
def _default_output_path(input_path: str) -> str:
    input_stem = Path(input_path).stem
    output_dir = Path("output")
    if not output_dir.is_dir():
        output_dir = Path.home() / "Documents" / "PDFBETTER OUTPUT"
        output_dir.mkdir(parents=True, exist_ok=True)
    return str(output_dir / f"{input_stem}_printerfriendly.pdf")
```

Change the `-o`/`--output` argument definition from:

```python
    parser.add_argument("-o", "--output", required=True, help="path to write the output PDF")
```

to:

```python
    parser.add_argument(
        "-o",
        "--output",
        default=None,
        help="path to write the output PDF (default: ./output/<name>_printerfriendly.pdf if "
        "./output exists, else ~/Documents/PDFBETTER OUTPUT/<name>_printerfriendly.pdf)",
    )
```

And change this line (right after `args = parser.parse_args(argv)`):

```python
    thresholds = Thresholds(background_coverage=args.bg_threshold, contrast_luminance=args.contrast_luminance)
    try:
        result = process(args.input, args.output, thresholds=thresholds, audit=args.audit)
```

to:

```python
    output_path = args.output or _default_output_path(args.input)
    thresholds = Thresholds(background_coverage=args.bg_threshold, contrast_luminance=args.contrast_luminance)
    try:
        result = process(args.input, output_path, thresholds=thresholds, audit=args.audit)
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
git commit -m "Make -o optional: default to ./output, falling back to ~/Documents/PDFBETTER OUTPUT"
```
