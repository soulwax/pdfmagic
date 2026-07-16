import os

import pikepdf
import pytest
from PIL import Image

import pdfbetter.rasterize_upscale_pipeline as pipeline_module
from pdfbetter.rasterize_upscale_pipeline import process_rasterize_upscale
from pdfbetter.upscale import RealesrganNotFoundError


def _fake_upscale_directory(input_dir, output_dir, *, binary_path, model, scale, tile, threads, tta):
    for name in os.listdir(input_dir):
        image = Image.open(os.path.join(input_dir, name))
        resized = image.resize((image.width * scale, image.height * scale))
        resized.save(os.path.join(output_dir, name))


def test_process_rasterize_upscale_produces_pdf_with_original_page_size(
    monkeypatch, synthetic_pdf_path, tmp_path
):
    monkeypatch.setattr(pipeline_module, "find_realesrgan", lambda explicit_path=None: "/fake/realesrgan")
    monkeypatch.setattr(pipeline_module, "upscale_directory", _fake_upscale_directory)

    output_path = str(tmp_path / "output.pdf")
    result = process_rasterize_upscale(synthetic_pdf_path, output_path, dpi=72)

    assert result.pages_processed == 1
    assert os.path.exists(output_path)

    output_pdf = pikepdf.open(output_path)
    mediabox = output_pdf.pages[0].mediabox
    width = float(mediabox[2]) - float(mediabox[0])
    height = float(mediabox[3]) - float(mediabox[1])
    assert abs(width - 612.0) < 1.0
    assert abs(height - 792.0) < 1.0


def test_process_rasterize_upscale_applies_crop_before_upscaling(
    monkeypatch, synthetic_pdf_path, tmp_path
):
    seen_sizes = []

    def spying_upscale_directory(input_dir, output_dir, *, binary_path, model, scale, tile, threads, tta):
        for name in os.listdir(input_dir):
            image = Image.open(os.path.join(input_dir, name))
            seen_sizes.append(image.size)
            image.save(os.path.join(output_dir, name))

    monkeypatch.setattr(pipeline_module, "find_realesrgan", lambda explicit_path=None: "/fake/realesrgan")
    monkeypatch.setattr(pipeline_module, "upscale_directory", spying_upscale_directory)

    output_path = str(tmp_path / "output.pdf")
    result_no_crop_dir = tmp_path / "nocrop"
    result_no_crop_dir.mkdir()

    # Baseline: no crop, dpi=72 (612x792pt page -> 612x792px at 72 dpi)
    process_rasterize_upscale(synthetic_pdf_path, str(result_no_crop_dir / "out.pdf"), dpi=72)
    baseline_size = seen_sizes[-1]

    process_rasterize_upscale(
        synthetic_pdf_path, output_path, dpi=72, crop_x=10, crop_y=10
    )
    cropped_size = seen_sizes[-1]

    assert cropped_size[0] < baseline_size[0]
    assert cropped_size[1] < baseline_size[1]


def test_process_rasterize_upscale_fails_before_rasterizing_when_binary_missing(
    monkeypatch, synthetic_pdf_path, tmp_path
):
    def fake_find(explicit_path=None):
        raise RealesrganNotFoundError("not found")

    rasterize_called = []

    def fake_rasterize(input_path, output_dir, dpi=300):
        rasterize_called.append(True)
        return []

    monkeypatch.setattr(pipeline_module, "find_realesrgan", fake_find)
    monkeypatch.setattr(pipeline_module, "rasterize_pdf", fake_rasterize)

    output_path = str(tmp_path / "output.pdf")
    with pytest.raises(RealesrganNotFoundError):
        process_rasterize_upscale(synthetic_pdf_path, output_path)

    assert rasterize_called == []
    assert not os.path.exists(output_path)
