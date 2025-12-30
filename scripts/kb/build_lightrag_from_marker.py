#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import re
import sys
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Iterable


REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT))

from src.tools.lightrag_kb import build_lightrag_instance  # noqa: E402


_DOI_RE = re.compile(r"\b10\.\d{4,9}/[-._;()/:A-Z0-9]+\b", re.IGNORECASE)


def _iter_pdfs(pdf_dir: Path) -> list[Path]:
    return sorted([p for p in pdf_dir.iterdir() if p.is_file() and p.suffix.lower() == ".pdf"])


def _extract_doi(text: str) -> str | None:
    match = _DOI_RE.search(text)
    if not match:
        return None
    return match.group(0).rstrip(").,;")


def _marker_md_for_pdf(marker_out_dir: Path, pdf_path: Path) -> Path:
    # marker writes into `<output_dir>/<basename>/<basename>.md`
    return marker_out_dir / pdf_path.stem / f"{pdf_path.stem}.md"


@dataclass(frozen=True)
class DocManifestItem:
    kb_namespace: str
    doc_id: str
    source: str  # DOI or filename/path (no page number)
    pdf_path: str
    marker_md_path: str


def _write_jsonl(path: Path, rows: Iterable[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        for row in rows:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Build a LightRAG (HKU) knowledge base from existing Marker markdown outputs."
    )
    parser.add_argument("--kb-namespace", required=True, help="e.g. kb_principles / kb_modulation")
    parser.add_argument("--pdf-dir", required=True, help="Folder containing PDFs (used for stable doc ids + fallback source)")
    parser.add_argument("--marker-out-dir", required=True, help="Folder containing Marker outputs for that pdf-dir")
    parser.add_argument("--lightrag-workdir", required=True, help="LightRAG working_dir for storage")
    parser.add_argument("--chunk-size", type=int, default=512, help="Token chunk size (spec default: 512)")
    parser.add_argument("--manifest-path", default="", help="Optional: write a JSONL manifest mapping sources->files")
    args = parser.parse_args()

    kb_namespace = args.kb_namespace.strip()
    pdf_dir = Path(args.pdf_dir).expanduser().resolve()
    marker_out_dir = Path(args.marker_out_dir).expanduser().resolve()
    lightrag_workdir = Path(args.lightrag_workdir).expanduser().resolve()

    if not pdf_dir.exists():
        raise SystemExit(f"--pdf-dir does not exist: {pdf_dir}")
    if not marker_out_dir.exists():
        raise SystemExit(
            f"--marker-out-dir does not exist: {marker_out_dir}\n"
            f"Run marker first (scripts/kb/run_marker_dir.py) to generate markdown outputs."
        )

    pdfs = _iter_pdfs(pdf_dir)
    if not pdfs:
        raise SystemExit(f"No PDFs found in: {pdf_dir}")

    inputs: list[str] = []
    ids: list[str] = []
    file_paths: list[str] = []
    manifest: list[DocManifestItem] = []

    missing_md = 0
    for pdf_path in pdfs:
        md_path = _marker_md_for_pdf(marker_out_dir, pdf_path)
        if not md_path.exists():
            missing_md += 1
            continue

        md_text = md_path.read_text(encoding="utf-8", errors="replace")
        doi = _extract_doi(md_text)

        # Citation source: DOI if present, otherwise filename/path.
        source = doi or pdf_path.name

        # Stable doc id: namespace + relative pdf path (string)
        rel = os.path.relpath(str(pdf_path), start=str(pdf_dir))
        doc_id = f"{kb_namespace}__{rel}"

        inputs.append(md_text)
        ids.append(doc_id)
        file_paths.append(source)
        manifest.append(
            DocManifestItem(
                kb_namespace=kb_namespace,
                doc_id=doc_id,
                source=source,
                pdf_path=str(pdf_path),
                marker_md_path=str(md_path),
            )
        )

    if missing_md:
        print(f"[warn] Missing Marker outputs for {missing_md}/{len(pdfs)} PDFs under: {marker_out_dir}")

    if not inputs:
        raise SystemExit("No documents to ingest (no Marker markdown found).")

    rag = build_lightrag_instance(
        working_dir=str(lightrag_workdir),
        workspace=kb_namespace,
        chunk_size=int(args.chunk_size),
    )

    print(f"[lightrag] Ingesting {len(inputs)} docs into working_dir={lightrag_workdir} workspace={kb_namespace}")
    from lightrag.utils import always_get_an_event_loop

    always_get_an_event_loop().run_until_complete(rag.initialize_storages())
    track_id = rag.insert(inputs, ids=ids, file_paths=file_paths)
    print(f"[lightrag] Insert done. track_id={track_id}")

    if args.manifest_path:
        manifest_path = Path(args.manifest_path).expanduser().resolve()
        _write_jsonl(manifest_path, [asdict(m) for m in manifest])
        print(f"[manifest] Wrote: {manifest_path}")


if __name__ == "__main__":
    main()
