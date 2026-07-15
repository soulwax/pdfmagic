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
