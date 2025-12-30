#!/usr/bin/env python3
from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]
BUILD_ONE = REPO_ROOT / "scripts" / "kb" / "build_lightrag_from_marker.py"


def _run(cmd: list[str]) -> None:
    print(f"[cmd] {' '.join(cmd)}")
    subprocess.run(cmd, check=True)


def main() -> None:
    parser = argparse.ArgumentParser(description="Build both LightRAG KB instances from existing Marker outputs.")
    parser.add_argument("--chunk-size", type=int, default=512)
    parser.add_argument("--manifest-dir", default="data/kb_manifests", help="Where JSONL manifests will be written")
    args = parser.parse_args()

    manifest_dir = (REPO_ROOT / args.manifest_dir).resolve()
    marker_dir = (REPO_ROOT / "data" / "marker").resolve()
    lightrag_dir = (REPO_ROOT / "data" / "lightrag").resolve()

    tasks = [
        {
            "kb_namespace": "kb_principles",
            "pdf_dir": REPO_ROOT / "original_assets" / "光催化二氧化碳还原文献" / "原理",
            "marker_out_dir": marker_dir / "kb_principles",
            "lightrag_workdir": lightrag_dir / "kb_principles",
        },
        {
            "kb_namespace": "kb_modulation",
            "pdf_dir": REPO_ROOT / "original_assets" / "光催化二氧化碳还原文献" / "调控性文献",
            "marker_out_dir": marker_dir / "kb_modulation",
            "lightrag_workdir": lightrag_dir / "kb_modulation",
        },
    ]

    for t in tasks:
        cmd = [
            sys.executable,
            str(BUILD_ONE),
            "--kb-namespace",
            t["kb_namespace"],
            "--pdf-dir",
            str(t["pdf_dir"]),
            "--marker-out-dir",
            str(t["marker_out_dir"]),
            "--lightrag-workdir",
            str(t["lightrag_workdir"]),
            "--chunk-size",
            str(args.chunk_size),
            "--manifest-path",
            str(manifest_dir / f"{t['kb_namespace']}.jsonl"),
        ]
        _run(cmd)


if __name__ == "__main__":
    main()

