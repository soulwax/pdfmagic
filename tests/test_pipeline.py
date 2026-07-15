import json

import pdfplumber
import pikepdf

from pdfbetter.classify import Thresholds
from pdfbetter.pipeline import process


def test_pipeline_strips_background_keeps_content(synthetic_pdf_path, tmp_path):
    output_path = str(tmp_path / "output.pdf")
    result = process(synthetic_pdf_path, output_path, thresholds=Thresholds())

    assert result.pages_processed == 1

    with pdfplumber.open(output_path) as pdf:
        page = pdf.pages[0]
        assert page.rects == []
        assert len(page.lines) == 1
        assert len(page.images) == 1
        hello_chars = [ch for ch in page.chars if ch["text"] == "H"]
        assert hello_chars
        assert hello_chars[0]["non_stroking_color"] == (0.0, 0.0, 0.0)
        dark_chars = [ch for ch in page.chars if ch["text"] == "N"]
        assert dark_chars
        assert dark_chars[0]["non_stroking_color"] == (0, 0, 0)


def test_pipeline_preserves_embedded_font_bytes_exactly(synthetic_pdf_path, embedded_font_resource_name, tmp_path):
    output_path = str(tmp_path / "output.pdf")
    process(synthetic_pdf_path, output_path)

    source_pdf = pikepdf.open(synthetic_pdf_path)
    output_pdf = pikepdf.open(output_path)
    source_font = source_pdf.pages[0].Resources.Font[embedded_font_resource_name]
    output_font = output_pdf.pages[0].Resources.Font[embedded_font_resource_name]
    source_bytes = bytes(source_font.FontDescriptor.FontFile2.read_bytes())
    output_bytes = bytes(output_font.FontDescriptor.FontFile2.read_bytes())
    assert source_bytes == output_bytes


def test_pipeline_audit_report_lists_dropped_background(synthetic_pdf_path, tmp_path):
    output_path = str(tmp_path / "output.pdf")
    report_path = str(tmp_path / "report.json")
    overlay_path = str(tmp_path / "overlay.pdf")
    result = process(
        synthetic_pdf_path,
        output_path,
        audit=True,
        audit_report_path=report_path,
        audit_overlay_path=overlay_path,
    )

    assert result.audit_report_path == report_path
    assert result.audit_overlay_path == overlay_path

    with open(report_path, encoding="utf-8") as f:
        report = json.load(f)
    dropped = [e for e in report["pages"][0]["entries"] if e["action"] == "drop"]
    assert len(dropped) == 1
    assert dropped[0]["kind"] == "fill"


def test_pipeline_respects_custom_thresholds(synthetic_pdf_path, tmp_path):
    output_path = str(tmp_path / "output.pdf")
    process(synthetic_pdf_path, output_path, thresholds=Thresholds(background_coverage=1.5))

    with pdfplumber.open(output_path) as pdf:
        page = pdf.pages[0]
        assert len(page.rects) == 1


def test_pipeline_flags_page_that_becomes_blank(background_only_pdf_path, tmp_path):
    output_path = str(tmp_path / "output.pdf")
    result = process(background_only_pdf_path, output_path)

    assert result.blank_pages == [0]
    assert result.failed_pages == []


def test_pipeline_does_not_flag_normal_page_as_blank(synthetic_pdf_path, tmp_path):
    output_path = str(tmp_path / "output.pdf")
    result = process(synthetic_pdf_path, output_path)

    assert result.blank_pages == []
    assert result.failed_pages == []
