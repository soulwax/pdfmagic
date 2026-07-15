import os

import pikepdf
import pytest
import reportlab
from PIL import Image
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.pdfgen import canvas


@pytest.fixture
def synthetic_pdf_path(tmp_path):
    vera = os.path.join(os.path.dirname(reportlab.__file__), "fonts", "Vera.ttf")
    pdfmetrics.registerFont(TTFont("VeraEmbed", vera))

    img_path = tmp_path / "small.png"
    Image.new("RGB", (40, 40), (200, 30, 30)).save(img_path)

    pdf_path = tmp_path / "source.pdf"
    c = canvas.Canvas(str(pdf_path), pagesize=(612, 792))
    c.setFillColorRGB(0.05, 0.05, 0.05)
    c.rect(0, 0, 612, 792, fill=1, stroke=0)
    c.setFont("VeraEmbed", 24)
    c.setFillColorRGB(1, 1, 1)
    c.drawString(72, 692, "Hello")
    c.setFont("Helvetica", 12)
    c.setFillColorRGB(0, 0, 0)
    c.drawString(72, 642, "Normal body text, standard font, already dark.")
    c.setStrokeColorRGB(0, 0, 0)
    c.setLineWidth(1)
    c.line(72, 622, 540, 622)
    c.drawImage(str(img_path), 72, 532, width=40, height=40)
    c.showPage()
    c.save()
    return str(pdf_path)


@pytest.fixture
def embedded_font_resource_name(synthetic_pdf_path):
    pdf = pikepdf.open(synthetic_pdf_path)
    for name, fdict in pdf.pages[0].Resources.Font.items():
        if fdict.get("/Subtype") == pikepdf.Name("/TrueType"):
            return str(name)
    raise AssertionError("no embedded TrueType font found in synthetic fixture")


@pytest.fixture
def background_only_pdf_path(tmp_path):
    """A page whose only content is a full-bleed background fill -- nothing
    else -- so background-stripping should leave the page blank."""
    pdf_path = tmp_path / "background_only.pdf"
    c = canvas.Canvas(str(pdf_path), pagesize=(612, 792))
    c.setFillColorRGB(0.05, 0.05, 0.05)
    c.rect(0, 0, 612, 792, fill=1, stroke=0)
    c.showPage()
    c.save()
    return str(pdf_path)
