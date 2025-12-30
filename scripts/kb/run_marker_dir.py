#!/usr/bin/env python3
from __future__ import annotations

import argparse
import os
import subprocess
from pathlib import Path


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Run Marker (marker-pdf) to convert a directory of PDFs into per-PDF markdown outputs."
    )
    parser.add_argument("--pdf-dir", required=True, help="Folder containing PDFs (non-recursive).")
    parser.add_argument("--output-dir", required=True, help="Marker output directory (will be created).")
    parser.add_argument(
        "--skip-existing",
        action="store_true",
        help="Marker: skip PDFs whose outputs already exist under output-dir.",
    )
    parser.add_argument(
        "--max-files",
        type=int,
        default=0,
        help="Marker: limit number of PDFs (0 = no limit). Useful for a quick sanity run.",
    )
    parser.add_argument(
        "--workers",
        type=int,
        default=1,
        help="Marker worker processes. Default 1 for safety on dev machines.",
    )
    parser.add_argument(
        "--disable-ocr",
        action="store_true",
        help="Marker: disable OCR (faster, but may reduce quality for scanned PDFs).",
    )
    parser.add_argument(
        "--disable-tqdm",
        action="store_true",
        help="Marker: disable tqdm progress bars (less noisy, but may look 'stuck' on long PDFs).",
    )
    parser.add_argument(
        "--debug",
        action="store_true",
        help="Marker: enable debug mode (-d).",
    )
    parser.add_argument(
        "--debug-print",
        action="store_true",
        help="Marker: print debug information (--debug_print).",
    )
    parser.add_argument(
        "--torch-device",
        default="",
        help="Set marker env TORCH_DEVICE (e.g. 'cpu' to avoid CUDA/MPS warnings). Default: unset (auto).",
    )
    args = parser.parse_args()

    pdf_dir = Path(args.pdf_dir).expanduser().resolve()
    output_dir = Path(args.output_dir).expanduser().resolve()
    output_dir.mkdir(parents=True, exist_ok=True)

    if not pdf_dir.exists():
        raise SystemExit(f"--pdf-dir does not exist: {pdf_dir}")

    cmd = [
        "marker",
        str(pdf_dir),
        "--output_dir",
        str(output_dir),
        "--output_format",
        "markdown",
        "--disable_image_extraction",
        "--workers",
        str(args.workers),
    ]
    if args.disable_ocr:
        cmd.append("--disable_ocr")
    if args.disable_tqdm:
        cmd.append("--disable_tqdm")
    if args.debug:
        cmd.append("-d")
    if args.debug_print:
        cmd.append("--debug_print")
    if args.skip_existing:
        cmd.append("--skip_existing")
    if args.max_files and args.max_files > 0:
        cmd.extend(["--max_files", str(args.max_files)])

    print(f"[marker] {' '.join(cmd)}")
    env = None
    if args.torch_device.strip():
        env = dict(**os.environ)
        env["TORCH_DEVICE"] = args.torch_device.strip()
    subprocess.run(cmd, check=True, env=env)


if __name__ == "__main__":
    main()
