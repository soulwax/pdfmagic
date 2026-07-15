import json

import pikepdf

from pdfbetter.audit import build_report, write_debug_overlay, write_report
from pdfbetter.classify import Classified, Decision
from pdfbetter.color import Color
from pdfbetter.geometry import BBox
from pdfbetter.walk import FillOp, ImageOp


def test_build_report_lists_drop_and_keep_entries_with_reasons():
    fill = FillOp(2, 3, BBox(0, 0, 612, 792), Color("rgb", (0.05, 0.05, 0.05)))
    classified = Classified(fills=[(fill, Decision("drop", "fill covers 100%x100% of page"))], strokes=[], images=[], text_shows=[])
    report = build_report({0: classified})
    assert report["pages"][0]["page_number"] == 0
    entry = report["pages"][0]["entries"][0]
    assert entry["kind"] == "fill"
    assert entry["action"] == "drop"
    assert entry["reason"] == "fill covers 100%x100% of page"
    assert entry["bbox"] == [0, 0, 612, 792]


def test_write_report_produces_valid_json_file(tmp_path):
    image = ImageOp(0, "/Bg", BBox(0, 0, 612, 792))
    classified = Classified(fills=[], strokes=[], images=[(image, Decision("drop", "image covers 100%x100% of page"))], text_shows=[])
    path = tmp_path / "report.json"
    write_report({0: classified}, str(path))
    with open(path, encoding="utf-8") as f:
        report = json.load(f)
    assert report["pages"][0]["entries"][0]["kind"] == "image"
    assert report["pages"][0]["entries"][0]["xobject_name"] == "/Bg"


def test_write_debug_overlay_adds_annotation_rects(tmp_path):
    pdf = pikepdf.new()
    page = pdf.add_blank_page(page_size=(612, 792))
    page.Contents = pdf.make_stream(b"")
    fill = FillOp(2, 3, BBox(10, 10, 100, 100), Color("rgb", (0.05, 0.05, 0.05)))
    classified = Classified(fills=[(fill, Decision("drop", "test"))], strokes=[], images=[], text_shows=[])
    path = tmp_path / "debug.pdf"
    write_debug_overlay(pdf, {0: classified}, str(path))

    reopened = pikepdf.open(str(path))
    instructions = pikepdf.parse_content_stream(reopened.pages[0])
    ops = [str(ins.operator) for ins in instructions]
    assert "re" in ops
    assert "S" in ops
