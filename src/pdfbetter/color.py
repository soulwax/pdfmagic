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
