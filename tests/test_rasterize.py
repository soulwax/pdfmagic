import pytest
from PIL import Image
from reportlab.pdfgen import canvas

from pdfbetter.rasterize import rasterize_pdf


@pytest.fixture
def two_page_pdf_path(tmp_path):
    path = tmp_path / "two_pages.pdf"
    c = canvas.Canvas(str(path), pagesize=(200, 200))
    c.drawString(50, 100, "Page One")
    c.showPage()
    c.drawString(50, 100, "Page Two")
    c.showPage()
    c.save()
    return str(path)


def test_rasterize_pdf_produces_one_png_per_page(synthetic_pdf_path, tmp_path):
    output_dir = tmp_path / "rendered"
    output_dir.mkdir()

    output_paths = rasterize_pdf(synthetic_pdf_path, str(output_dir), dpi=72)

    assert len(output_paths) == 1
    assert output_paths[0].endswith(".png")
    Image.open(output_paths[0]).verify()


def test_rasterize_pdf_scales_with_dpi(synthetic_pdf_path, tmp_path):
    output_dir_72 = tmp_path / "rendered_72"
    output_dir_72.mkdir()
    paths_72 = rasterize_pdf(synthetic_pdf_path, str(output_dir_72), dpi=72)
    image_72 = Image.open(paths_72[0])

    output_dir_144 = tmp_path / "rendered_144"
    output_dir_144.mkdir()
    paths_144 = rasterize_pdf(synthetic_pdf_path, str(output_dir_144), dpi=144)
    image_144 = Image.open(paths_144[0])

    assert image_144.width == image_72.width * 2
    assert image_144.height == image_72.height * 2


def test_rasterize_pdf_produces_correctly_ordered_pages(two_page_pdf_path, tmp_path):
    output_dir = tmp_path / "rendered"
    output_dir.mkdir()

    output_paths = rasterize_pdf(two_page_pdf_path, str(output_dir), dpi=72)

    assert len(output_paths) == 2
    assert output_paths == sorted(output_paths)
    assert "page_0000" in output_paths[0]
    assert "page_0001" in output_paths[1]
