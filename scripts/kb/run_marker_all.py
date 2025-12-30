#!/usr/bin/env python3
from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]
RUN_ONE = REPO_ROOT / "scripts" / "kb" / "run_marker_dir.py"


def _run(cmd: list[str]) -> None:
    print(f"[cmd] {' '.join(cmd)}")
    subprocess.run(cmd, check=True)


def main() -> None:
    parser = argparse.ArgumentParser(description="Run Marker for both KB folders (principles + modulation).")
    parser.add_argument("--skip-existing", action="store_true")
    parser.add_argument("--max-files", type=int, default=0)
    parser.add_argument("--workers", type=int, default=1)
    parser.add_argument("--disable-ocr", action="store_true")
    parser.add_argument("--disable-tqdm", action="store_true")
    parser.add_argument("--debug", action="store_true")
    parser.add_argument("--debug-print", action="store_true")
    parser.add_argument(
        "--torch-device",
        default="",
        help="Forwarded to run_marker_dir.py; sets marker env TORCH_DEVICE (e.g. 'cpu').",
    )
    args = parser.parse_args()

    marker_base = (REPO_ROOT / "data" / "marker").resolve()

    tasks = [
        (
            REPO_ROOT / "original_assets" / "光催化二氧化碳还原文献" / "原理",
            marker_base / "kb_principles",
        ),
        (
            REPO_ROOT / "original_assets" / "光催化二氧化碳还原文献" / "调控性文献",
            marker_base / "kb_modulation",
        ),
    ]

    for pdf_dir, out_dir in tasks:
        cmd = [
            sys.executable,
            str(RUN_ONE),
            "--pdf-dir",
            str(pdf_dir),
            "--output-dir",
            str(out_dir),
            "--workers",
            str(args.workers),
        ]
        if args.skip_existing:
            cmd.append("--skip-existing")
        if args.max_files and args.max_files > 0:
            cmd.extend(["--max-files", str(args.max_files)])
        if args.disable_ocr:
            cmd.append("--disable-ocr")
        if args.disable_tqdm:
            cmd.append("--disable-tqdm")
        if args.debug:
            cmd.append("--debug")
        if args.debug_print:
            cmd.append("--debug-print")
        if args.torch_device.strip():
            cmd.extend(["--torch-device", args.torch_device.strip()])
        _run(cmd)


if __name__ == "__main__":
    main()
