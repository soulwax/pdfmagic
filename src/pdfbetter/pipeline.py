from dataclasses import dataclass, field

import pikepdf

from pdfbetter.audit import write_debug_overlay, write_report
from pdfbetter.classify import Classified, Decision, Thresholds, classify
from pdfbetter.edit import apply_edits
from pdfbetter.walk import walk_page


@dataclass(frozen=True)
class ProcessResult:
    output_path: str
    pages_processed: int
    failed_pages: list = field(default_factory=list)
    unimproved_pages: list = field(default_factory=list)
    audit_report_path: str | None = None
    audit_overlay_path: str | None = None


def _image_xobject_names(page) -> set:
    xobjects = page.Resources.get("/XObject", {})
    return {
        str(name)
        for name, obj in xobjects.items()
        if obj.get("/Subtype") == pikepdf.Name("/Image")
    }


def _would_become_blank(classified: Classified, walk_result) -> bool:
    had_fill_or_image = bool(walk_result.fills or walk_result.images)
    kept_fills = [d for _, d in classified.fills if d.action != "drop"]
    kept_images = [d for _, d in classified.images if d.action != "drop"]
    now_empty = not kept_fills and not kept_images and not classified.strokes and not classified.text_shows
    return had_fill_or_image and now_empty


def _keep_everything(classified: Classified) -> Classified:
    reason = "kept: dropping would have left the page with no content"
    fills = [
        (op, Decision("keep", reason)) if d.action == "drop" else (op, d)
        for op, d in classified.fills
    ]
    images = [
        (op, Decision("keep", reason)) if d.action == "drop" else (op, d)
        for op, d in classified.images
    ]
    return Classified(fills=fills, strokes=classified.strokes, images=images, text_shows=classified.text_shows)


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
    unimproved_pages = []

    for page_number, page in enumerate(pdf.pages):
        try:
            mediabox = page.mediabox
            page_width = float(mediabox[2]) - float(mediabox[0])
            page_height = float(mediabox[3]) - float(mediabox[1])
            image_names = _image_xobject_names(page)

            instructions = pikepdf.parse_content_stream(page)
            walk_result = walk_page(instructions, page_width, page_height, image_names)
            classified = classify(walk_result, page_width, page_height, thresholds)

            if _would_become_blank(classified, walk_result):
                classified = _keep_everything(classified)
                unimproved_pages.append(page_number)

            classified_by_page[page_number] = classified

            new_instructions, xobject_names_to_remove = apply_edits(instructions, classified)
            page.Contents = pdf.make_stream(pikepdf.unparse_content_stream(new_instructions))
            if xobject_names_to_remove:
                xobjects = page.Resources.get("/XObject", {})
                remaining = pikepdf.Dictionary()
                for key, value in xobjects.items():
                    if key not in xobject_names_to_remove and str(key) not in xobject_names_to_remove:
                        remaining[key] = value
                new_resources = pikepdf.Dictionary(page.Resources)
                new_resources["/XObject"] = remaining
                page.Resources = new_resources
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
        unimproved_pages=unimproved_pages,
        audit_report_path=report_path,
        audit_overlay_path=overlay_path,
    )
