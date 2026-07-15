import argparse
import sys

from pdfbetter.classify import Thresholds
from pdfbetter.pipeline import process


def main(argv: list | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="pdfbetter",
        description="Strip ink-heavy backgrounds from a PDF, keeping content faithful.",
    )
    parser.add_argument("input", help="path to the source PDF")
    parser.add_argument("-o", "--output", required=True, help="path to write the output PDF")
    parser.add_argument(
        "--bg-threshold",
        type=float,
        default=0.8,
        help="min page-coverage fraction (0-1) for a fill/image to be treated as background (default: 0.8)",
    )
    parser.add_argument(
        "--contrast-luminance",
        type=float,
        default=0.6,
        help="min luminance (0-1) for a kept color to be recolored to black (default: 0.6)",
    )
    parser.add_argument(
        "--audit",
        action="store_true",
        help="also write a JSON classification report and a debug overlay PDF",
    )
    args = parser.parse_args(argv)

    thresholds = Thresholds(background_coverage=args.bg_threshold, contrast_luminance=args.contrast_luminance)
    try:
        result = process(args.input, args.output, thresholds=thresholds, audit=args.audit)
    except Exception as exc:
        print(f"pdfbetter: failed to process {args.input}: {exc}", file=sys.stderr)
        return 1

    print(f"pdfbetter: wrote {result.output_path} ({result.pages_processed} pages)")
    if args.audit:
        print(f"pdfbetter: audit report at {result.audit_report_path}")
        print(f"pdfbetter: debug overlay at {result.audit_overlay_path}")
    for page_number in result.blank_pages:
        print(f"pdfbetter: warning: page {page_number} has no content left after background removal", file=sys.stderr)
    if result.failed_pages:
        for page_number, message in result.failed_pages:
            print(f"pdfbetter: page {page_number} failed to process: {message}", file=sys.stderr)
        print(f"pdfbetter: {len(result.failed_pages)} page(s) failed, see above", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
