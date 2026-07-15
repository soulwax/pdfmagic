import pikepdf

from pdfbetter.classify import Classified
from pdfbetter.color import black_operator


def apply_edits(instructions: list, classified: Classified) -> tuple[list, set]:
    drop_ranges = []
    wrap_ranges = []
    drop_single = set()
    wrap_single = {}
    xobject_names_to_remove = set()

    for fill, decision in classified.fills:
        if decision.action == "drop":
            drop_ranges.append((fill.start, fill.end))
        elif decision.action == "recolor":
            wrap_ranges.append((fill.start, fill.end, fill.color.colorspace, "fill"))

    for stroke, decision in classified.strokes:
        if decision.action == "recolor":
            wrap_ranges.append((stroke.start, stroke.end, stroke.color.colorspace, "stroke"))

    for image, decision in classified.images:
        if decision.action == "drop":
            drop_single.add(image.index)
            xobject_names_to_remove.add(image.xobject_name)

    for text, decision in classified.text_shows:
        if decision.action == "recolor":
            wrap_single[text.index] = (text.color.colorspace, "fill")

    def in_drop_range(idx: int) -> bool:
        return any(start <= idx <= end for start, end in drop_ranges)

    wrap_starts = {start: (colorspace, target) for start, end, colorspace, target in wrap_ranges}
    wrap_ends = {end for _, end, _, _ in wrap_ranges}

    output = []
    for i, ins in enumerate(instructions):
        if in_drop_range(i) or i in drop_single:
            continue
        if i in wrap_single:
            colorspace, target = wrap_single[i]
            output.append(pikepdf.ContentStreamInstruction([], pikepdf.Operator("q")))
            output.append(black_operator(colorspace, target))
            output.append(ins)
            output.append(pikepdf.ContentStreamInstruction([], pikepdf.Operator("Q")))
            continue
        if i in wrap_starts:
            colorspace, target = wrap_starts[i]
            output.append(pikepdf.ContentStreamInstruction([], pikepdf.Operator("q")))
            output.append(black_operator(colorspace, target))
        output.append(ins)
        if i in wrap_ends:
            output.append(pikepdf.ContentStreamInstruction([], pikepdf.Operator("Q")))

    return output, xobject_names_to_remove
