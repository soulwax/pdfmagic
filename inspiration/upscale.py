#!/usr/bin/env python3
"""Batch-upscale cut/<project>/*_Seite_NNN.png files with realesrgan-ncnn-vulkan."""

import argparse
import re
import subprocess
import sys
from pathlib import Path

EXE = "realesrgan-ncnn-vulkan.exe"
PATTERN = re.compile(r"^(?P<project>.+)_Seite_(?P<num>\d+)\.png$", re.IGNORECASE)
SCALE = "2"
# realesrgan-x4plus is the general-purpose model; it renders sharp,
# non-stylized edges which suits text/document pages far better than
# the anime-tuned models (or the tool's default, realesr-animevideov3).
MODEL = "realesrgan-x4plus"
# Tile size (0 = auto) and load:proc:save thread counts. An RTX 3070 Ti
# has 8GB VRAM, comfortably enough to raise the tile size above the
# auto-picked default and cut per-tile overhead; tune TILE if needed.
TILE = "0"
THREADS = "1:2:2"


def parse_args():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--no-overwrite",
        action="store_true",
        help="skip files that already exist in upscaled/<project>/ instead of overwriting them",
    )
    parser.add_argument(
        "--tta",
        action="store_true",
        help="enable TTA mode (-x): ~8x slower, marginally cleaner output; usually not worth it for text",
    )
    return parser.parse_args()


def main():
    args = parse_args()

    folder = Path(__file__).resolve().parent
    cut_root = folder / "cut"
    upscaled_root = folder / "upscaled"

    files = sorted(
        (f for f in cut_root.rglob("*.png") if PATTERN.match(f.name)),
        key=lambda f: (PATTERN.match(f.name).group("project"), int(PATTERN.match(f.name).group("num"))),
    )

    if not files:
        print("No matching files found in cut/.")
        return

    for src in files:
        match = PATTERN.match(src.name)
        project = match.group("project")
        n = match.group("num")

        out_dir = upscaled_root / project
        out_dir.mkdir(parents=True, exist_ok=True)
        dst = out_dir / f"{project}_Seite_{n}_x2.png"

        if args.no_overwrite and dst.exists():
            print(f"Skipping {src.name} (already exists: {dst.relative_to(folder)})")
            continue

        print(f"Upscaling {src.relative_to(folder)} -> {dst.relative_to(folder)}")
        cmd = [
            EXE, "-i", str(src), "-o", str(dst),
            "-s", SCALE, "-n", MODEL, "-t", TILE, "-j", THREADS,
        ]
        if args.tta:
            cmd.append("-x")
        result = subprocess.run(cmd, cwd=folder)
        if result.returncode != 0:
            print(f"Failed on {src.name} (exit code {result.returncode})", file=sys.stderr)
            sys.exit(result.returncode)

    print(f"Done. Processed {len(files)} file(s).")


if __name__ == "__main__":
    main()
