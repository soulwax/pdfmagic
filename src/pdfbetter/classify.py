from dataclasses import dataclass

from pdfbetter.color import luminance
from pdfbetter.geometry import coverage_fraction
from pdfbetter.walk import FillOp, ImageOp, StrokeOp, TextShowOp, WalkResult


@dataclass(frozen=True)
class Thresholds:
    background_coverage: float = 0.8
    contrast_luminance: float = 0.6


@dataclass(frozen=True)
class Decision:
    action: str
    reason: str


@dataclass(frozen=True)
class Classified:
    fills: list
    strokes: list
    images: list
    text_shows: list


def classify(
    walk_result: WalkResult,
    page_width: float,
    page_height: float,
    thresholds: Thresholds = Thresholds(),
) -> Classified:
    fills = []
    for fill in walk_result.fills:
        wf, hf = coverage_fraction(fill.bbox, page_width, page_height)
        if wf >= thresholds.background_coverage and hf >= thresholds.background_coverage:
            fills.append((fill, Decision("drop", f"fill covers {wf:.0%}x{hf:.0%} of page")))
        else:
            fills.append((fill, Decision("keep", "below background-coverage threshold")))

    images = []
    for image in walk_result.images:
        wf, hf = coverage_fraction(image.bbox, page_width, page_height)
        if wf >= thresholds.background_coverage and hf >= thresholds.background_coverage:
            images.append((image, Decision("drop", f"image covers {wf:.0%}x{hf:.0%} of page")))
        else:
            images.append((image, Decision("keep", "below background threshold")))

    strokes = []
    for stroke in walk_result.strokes:
        lum = luminance(stroke.color)
        if lum >= thresholds.contrast_luminance:
            strokes.append((stroke, Decision("recolor", f"stroke luminance {lum:.2f} low-contrast on white")))
        else:
            strokes.append((stroke, Decision("keep", "normal-contrast stroke")))

    text_shows = []
    for text in walk_result.text_shows:
        lum = luminance(text.color)
        if lum >= thresholds.contrast_luminance:
            text_shows.append((text, Decision("recolor", f"text luminance {lum:.2f} low-contrast on white")))
        else:
            text_shows.append((text, Decision("keep", "normal-contrast text")))

    return Classified(fills=fills, strokes=strokes, images=images, text_shows=text_shows)
