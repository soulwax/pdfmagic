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
