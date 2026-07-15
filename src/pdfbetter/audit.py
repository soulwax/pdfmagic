import json

import pikepdf


def build_report(classified_by_page: dict) -> dict:
    pages = []
    for page_number in sorted(classified_by_page):
        classified = classified_by_page[page_number]
        entries = []
        for fill, decision in classified.fills:
            entries.append({
                "kind": "fill",
                "action": decision.action,
                "reason": decision.reason,
                "bbox": [fill.bbox.x0, fill.bbox.y0, fill.bbox.x1, fill.bbox.y1],
            })
        for image, decision in classified.images:
            entries.append({
                "kind": "image",
                "action": decision.action,
                "reason": decision.reason,
                "xobject_name": image.xobject_name,
                "bbox": [image.bbox.x0, image.bbox.y0, image.bbox.x1, image.bbox.y1],
            })
        for stroke, decision in classified.strokes:
            entries.append({"kind": "stroke", "action": decision.action, "reason": decision.reason})
        for text, decision in classified.text_shows:
            entries.append({"kind": "text", "action": decision.action, "reason": decision.reason})
        pages.append({"page_number": page_number, "entries": entries})
    return {"pages": pages}


def write_report(classified_by_page: dict, path: str) -> None:
    report = build_report(classified_by_page)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(report, f, indent=2)


def write_debug_overlay(pdf, classified_by_page: dict, path: str) -> None:
    for page_number, classified in classified_by_page.items():
        page = pdf.pages[page_number]
        dropped_bboxes = [fill.bbox for fill, decision in classified.fills if decision.action == "drop"]
        dropped_bboxes += [image.bbox for image, decision in classified.images if decision.action == "drop"]
        if not dropped_bboxes:
            continue

        overlay = [
            pikepdf.ContentStreamInstruction([], pikepdf.Operator("q")),
            pikepdf.ContentStreamInstruction([1, 0, 1], pikepdf.Operator("RG")),
            pikepdf.ContentStreamInstruction([2], pikepdf.Operator("w")),
        ]
        for bbox in dropped_bboxes:
            overlay.append(pikepdf.ContentStreamInstruction([bbox.x0, bbox.y0, bbox.width, bbox.height], pikepdf.Operator("re")))
            overlay.append(pikepdf.ContentStreamInstruction([], pikepdf.Operator("S")))
        overlay.append(pikepdf.ContentStreamInstruction([], pikepdf.Operator("Q")))

        existing = pikepdf.parse_content_stream(page)
        combined = list(existing) + overlay
        page.Contents = pdf.make_stream(pikepdf.unparse_content_stream(combined))

    pdf.save(path)
