#!/usr/bin/env python3
"""Trim the white border from original page images into cut/<project>/."""

import re
import sys
from pathlib import Path

from PIL import Image

LEFT_RIGHT = 114
TOP_BOTTOM = 291
PATTERN = re.compile(r"^(?P<project>.+)_Seite_(?P<num>\d+)\.png$", re.IGNORECASE)


def main():
    folder = Path(__file__).resolve().parent
    cut_root = folder / "cut"

    files = sorted(
        (f for f in folder.iterdir() if f.is_file() and PATTERN.match(f.name)),
        key=lambda f: (PATTERN.match(f.name).group("project"), int(PATTERN.match(f.name).group("num"))),
    )

    if not files:
        print("No matching page files found.")
        return

    for src in files:
        project = PATTERN.match(src.name).group("project")
        cut_dir = cut_root / project
        cut_dir.mkdir(parents=True, exist_ok=True)
        dst = cut_dir / src.name

        if dst.exists():
            print(f"Skipping {src.name} (already exists: {dst.relative_to(folder)})")
            continue

        with Image.open(src) as img:
            w, h = img.size
            box = (LEFT_RIGHT, TOP_BOTTOM, w - LEFT_RIGHT, h - TOP_BOTTOM)

            if box[2] <= box[0] or box[3] <= box[1]:
                print(f"Skipping {src.name}: image ({w}x{h}) too small to trim", file=sys.stderr)
                continue

            cropped = img.crop(box)
            cropped.save(dst)

        print(f"Cut {src.name} -> {dst.relative_to(folder)}")

    print("Done.")


if __name__ == "__main__":
    main()
