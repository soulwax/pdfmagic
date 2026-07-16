import argparse
import sys
from pathlib import Path

from pdfbetter.classify import Thresholds
from pdfbetter.pipeline import process


def _default_output_path(input_path: str) -> str:
    input_stem = Path(input_path).stem
    output_dir = Path("output")
    if not output_dir.is_dir():
        output_dir = Path.home() / "Documents" / "PDFBETTER OUTPUT"
        output_dir.mkdir(parents=True, exist_ok=True)
    return str(output_dir / f"{input_stem}_printerfriendly.pdf")


def _import_process_rasterize_upscale():
    from pdfbetter.rasterize_upscale_pipeline import process_rasterize_upscale

    return process_rasterize_upscale


def _run_surgery_mode(args, output_path: str) -> int:
    thresholds = Thresholds(
        background_coverage=args.bg_threshold if args.bg_threshold is not None else 0.8,
        contrast_luminance=args.contrast_luminance if args.contrast_luminance is not None else 0.6,
    )
    try:
        result = process(args.input, output_path, thresholds=thresholds, audit=args.audit)
    except Exception as exc:
        print(f"pdfbetter: failed to process {args.input}: {exc}", file=sys.stderr)
        return 1

    print(f"pdfbetter: wrote {result.output_path} ({result.pages_processed} pages)")
    if args.audit:
        print(f"pdfbetter: audit report at {result.audit_report_path}")
        print(f"pdfbetter: debug overlay at {result.audit_overlay_path}")
    for page_number in result.unimproved_pages:
        print(
            f"pdfbetter: warning: page {page_number} left unchanged (background removal would have left it blank)",
            file=sys.stderr,
        )
    if result.failed_pages:
        for page_number, message in result.failed_pages:
            print(f"pdfbetter: page {page_number} failed to process: {message}", file=sys.stderr)
        print(f"pdfbetter: {len(result.failed_pages)} page(s) failed, see above", file=sys.stderr)
        return 1
    return 0


def _run_rasterize_mode(args, output_path: str) -> int:
    try:
        process_rasterize_upscale = _import_process_rasterize_upscale()
    except ImportError:
        print(
            "pdfbetter: --mode rasterize requires the 'rasterize' extra: pip install pdfbetter[rasterize]",
            file=sys.stderr,
        )
        return 1

    try:
        result = process_rasterize_upscale(
            args.input,
            output_path,
            dpi=args.render_dpi,
            realesrgan_path=args.realesrgan_path,
            model=args.realesrgan_model,
            crop_x=args.crop_x,
            crop_y=args.crop_y,
            tile=args.realesrgan_tile,
            threads=args.realesrgan_threads,
            tta=args.realesrgan_tta,
        )
    except Exception as exc:
        print(f"pdfbetter: failed to process {args.input}: {exc}", file=sys.stderr)
        return 1

    print(f"pdfbetter: wrote {result.output_path} ({result.pages_processed} pages)")
    return 0


def main(argv: list | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="pdfbetter",
        description="Strip ink-heavy backgrounds from a PDF, keeping content faithful.",
    )
    parser.add_argument("input", help="path to the source PDF")
    parser.add_argument(
        "-o",
        "--output",
        default=None,
        help="path to write the output PDF (default: ./output/<name>_printerfriendly.pdf if "
        "./output exists, else ~/Documents/PDFBETTER OUTPUT/<name>_printerfriendly.pdf)",
    )
    parser.add_argument(
        "--mode",
        choices=["surgery", "rasterize"],
        default="surgery",
        help="processing mode: 'surgery' edits the content stream directly (default); "
        "'rasterize' renders each page to an image, upscales it with realesrgan-ncnn-vulkan, "
        "and reassembles the result as a new PDF (for PDFs with no text/vector layer to preserve)",
    )
    parser.add_argument(
        "--bg-threshold",
        type=float,
        default=None,
        help="[surgery mode] min page-coverage fraction (0-1) for a fill/image to be treated as background (default: 0.8)",
    )
    parser.add_argument(
        "--contrast-luminance",
        type=float,
        default=None,
        help="[surgery mode] min luminance (0-1) for a kept color to be recolored to black (default: 0.6)",
    )
    parser.add_argument(
        "--audit",
        action="store_true",
        help="[surgery mode] also write a JSON classification report and a debug overlay PDF",
    )
    parser.add_argument(
        "--render-dpi",
        type=int,
        default=300,
        help="[rasterize mode] pre-upscale render resolution in DPI (default: 300; effective final "
        "resolution is 2x this with the default scale, e.g. 300 -> ~600 DPI-equivalent)",
    )
    parser.add_argument(
        "--crop-x",
        type=float,
        default=0.0,
        help="[rasterize mode] margin in points trimmed from both left and right of each rendered page (default: 0, no cropping)",
    )
    parser.add_argument(
        "--crop-y",
        type=float,
        default=0.0,
        help="[rasterize mode] margin in points trimmed from both top and bottom of each rendered page (default: 0, no cropping)",
    )
    parser.add_argument(
        "--realesrgan-path",
        default=None,
        help="[rasterize mode] path to the realesrgan-ncnn-vulkan executable (default: "
        "PDFBETTER_REALESRGAN_PATH env var, then PATH lookup)",
    )
    parser.add_argument(
        "--realesrgan-model",
        default="realesrgan-x4plus",
        help="[rasterize mode] realesrgan-ncnn-vulkan model name (default: realesrgan-x4plus)",
    )
    parser.add_argument(
        "--realesrgan-tile",
        type=int,
        default=0,
        help="[rasterize mode] realesrgan-ncnn-vulkan tile size, 0=auto (default: 0)",
    )
    parser.add_argument(
        "--realesrgan-threads",
        default="1:2:2",
        help="[rasterize mode] realesrgan-ncnn-vulkan load:proc:save thread counts (default: 1:2:2)",
    )
    parser.add_argument(
        "--realesrgan-tta",
        action="store_true",
        help="[rasterize mode] enable realesrgan-ncnn-vulkan TTA mode: ~8x slower, marginally cleaner output",
    )
    args = parser.parse_args(argv)

    if args.mode == "rasterize" and (
        args.bg_threshold is not None or args.contrast_luminance is not None or args.audit
    ):
        print(
            "pdfbetter: --bg-threshold/--contrast-luminance/--audit are surgery-mode-only "
            "and cannot be combined with --mode rasterize",
            file=sys.stderr,
        )
        return 1

    output_path = args.output or _default_output_path(args.input)

    if args.mode == "rasterize":
        return _run_rasterize_mode(args, output_path)
    return _run_surgery_mode(args, output_path)


if __name__ == "__main__":
    sys.exit(main())
