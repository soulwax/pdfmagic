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
