from dataclasses import dataclass, field

import pikepdf

from pdfbetter.audit import write_debug_overlay, write_report
from pdfbetter.classify import Classified, Thresholds, classify
from pdfbetter.edit import apply_edits
from pdfbetter.walk import walk_page


@dataclass(frozen=True)
class ProcessResult:
    output_path: str
    pages_processed: int
    failed_pages: list = field(default_factory=list)
    blank_pages: list = field(default_factory=list)
    audit_report_path: str | None = None
    audit_overlay_path: str | None = None


def _image_xobject_names(page) -> set:
    xobjects = page.Resources.get("/XObject", {})
    return {
        str(name)
        for name, obj in xobjects.items()
        if obj.get("/Subtype") == pikepdf.Name("/Image")
    }


def _page_became_blank(classified: Classified, walk_result) -> bool:
    had_fill_or_image = bool(walk_result.fills or walk_result.images)
    kept_fills = [d for _, d in classified.fills if d.action != "drop"]
    kept_images = [d for _, d in classified.images if d.action != "drop"]
    now_empty = not kept_fills and not kept_images and not classified.strokes and not classified.text_shows
    return had_fill_or_image and now_empty


def process(
    input_path: str,
    output_path: str,
    *,
    thresholds: Thresholds = Thresholds(),
    audit: bool = False,
    audit_report_path: str | None = None,
    audit_overlay_path: str | None = None,
) -> ProcessResult:
    pdf = pikepdf.open(input_path)
    classified_by_page: dict[int, Classified] = {}
    failed_pages = []
    blank_pages = []

    for page_number, page in enumerate(pdf.pages):
        try:
            mediabox = page.mediabox
            page_width = float(mediabox[2]) - float(mediabox[0])
            page_height = float(mediabox[3]) - float(mediabox[1])
            image_names = _image_xobject_names(page)

            instructions = pikepdf.parse_content_stream(page)
            walk_result = walk_page(instructions, page_width, page_height, image_names)
            classified = classify(walk_result, page_width, page_height, thresholds)
            classified_by_page[page_number] = classified

            if _page_became_blank(classified, walk_result):
                blank_pages.append(page_number)

            new_instructions, xobject_names_to_remove = apply_edits(instructions, classified)
            page.Contents = pdf.make_stream(pikepdf.unparse_content_stream(new_instructions))
            xobjects = page.Resources.get("/XObject", {})
            for name in xobject_names_to_remove:
                if name in xobjects:
                    del page.Resources.XObject[name]
        except Exception as exc:
            failed_pages.append((page_number, str(exc)))

    pdf.save(output_path)

    report_path = None
    overlay_path = None
    if audit:
        report_path = audit_report_path or f"{output_path}.audit.json"
        write_report(classified_by_page, report_path)
        overlay_path = audit_overlay_path or f"{output_path}.debug.pdf"
        write_debug_overlay(pdf, classified_by_page, overlay_path)

    return ProcessResult(
        output_path=output_path,
        pages_processed=len(pdf.pages),
        failed_pages=failed_pages,
        blank_pages=blank_pages,
        audit_report_path=report_path,
        audit_overlay_path=overlay_path,
    )
