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
