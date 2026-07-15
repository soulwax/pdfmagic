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
