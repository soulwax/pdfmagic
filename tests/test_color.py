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
