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
