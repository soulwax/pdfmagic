import io
import os
import tempfile
from dataclasses import dataclass

import pikepdf
from PIL import Image

from pdfbetter.crop import crop_margins, points_to_pixels
from pdfbetter.rasterize import rasterize_pdf
from pdfbetter.upscale import find_realesrgan, upscale_directory


@dataclass(frozen=True)
class RasterizeUpscaleResult:
    output_path: str
    pages_processed: int


def _reassemble_pdf(image_paths: list[str], output_path: str, dpi: float) -> None:
    pdf = pikepdf.new()
    for image_path in image_paths:
        image = Image.open(image_path)
        if image.mode != "RGB":
            image = image.convert("RGB")

        jpeg_buf = io.BytesIO()
        image.save(jpeg_buf, format="JPEG", quality=90)
        jpeg_bytes = jpeg_buf.getvalue()

        page_width_pt = image.width / dpi * 72
        page_height_pt = image.height / dpi * 72
        page = pdf.add_blank_page(page_size=(page_width_pt, page_height_pt))

        image_obj = pikepdf.Stream(pdf, jpeg_bytes)
        image_obj.Type = pikepdf.Name("/XObject")
        image_obj.Subtype = pikepdf.Name("/Image")
        image_obj.Width = image.width
        image_obj.Height = image.height
        image_obj.BitsPerComponent = 8
        image_obj.ColorSpace = pikepdf.Name("/DeviceRGB")
        image_obj.Filter = pikepdf.Name("/DCTDecode")

        page.Resources = pikepdf.Dictionary(XObject=pikepdf.Dictionary(Im0=image_obj))
        content = f"q {page_width_pt} 0 0 {page_height_pt} 0 0 cm /Im0 Do Q".encode()
        page.Contents = pdf.make_stream(content)

    pdf.save(output_path)


def process_rasterize_upscale(
    input_path: str,
    output_path: str,
    *,
    dpi: int = 300,
    realesrgan_path: str | None = None,
    model: str = "realesrgan-x4plus",
    scale: int = 2,
    crop_x: float = 0.0,
    crop_y: float = 0.0,
    tile: int = 0,
    threads: str = "1:2:2",
    tta: bool = False,
) -> RasterizeUpscaleResult:
    binary_path = find_realesrgan(realesrgan_path)

    with tempfile.TemporaryDirectory() as rendered_dir, tempfile.TemporaryDirectory() as upscaled_dir:
        rendered_paths = rasterize_pdf(input_path, rendered_dir, dpi=dpi)

        if crop_x > 0 or crop_y > 0:
            crop_x_px = points_to_pixels(crop_x, dpi)
            crop_y_px = points_to_pixels(crop_y, dpi)
            for path in rendered_paths:
                image = Image.open(path)
                cropped = crop_margins(image, crop_x_px, crop_y_px)
                cropped.save(path)

        upscale_directory(
            rendered_dir,
            upscaled_dir,
            binary_path=binary_path,
            model=model,
            scale=scale,
            tile=tile,
            threads=threads,
            tta=tta,
        )

        upscaled_paths = sorted(
            os.path.join(upscaled_dir, name)
            for name in os.listdir(upscaled_dir)
            if name.lower().endswith(".png")
        )
        _reassemble_pdf(upscaled_paths, output_path, dpi=dpi * scale)

    return RasterizeUpscaleResult(output_path=output_path, pages_processed=len(rendered_paths))
