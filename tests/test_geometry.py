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
