#!/usr/bin/env python3
"""Run the GROBID + Docling pipeline and leave one XML package."""

from __future__ import annotations

import argparse
import shutil
import subprocess
import sys
import zipfile
from pathlib import Path


SCRIPT_DIR = Path(__file__).resolve().parent


def run(stage: str, command: list[str]) -> None:
    print(f"+ [{stage}] {' '.join(command)}")
    try:
        subprocess.run(command, check=True)
    except subprocess.CalledProcessError as exc:
        raise SystemExit(f"{stage} failed with exit code {exc.returncode}") from exc


def archive_intermediate_outputs(output_paths: list[Path], archive_path: Path) -> int:
    archive_path.parent.mkdir(parents=True, exist_ok=True)
    if archive_path.exists():
        archive_path.unlink()

    archived = 0
    with zipfile.ZipFile(archive_path, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for output_path in output_paths:
            if not output_path.exists():
                continue
            if output_path.is_file():
                archive.write(output_path, output_path.name)
                archived += 1
                continue
            for path in sorted(output_path.rglob("*")):
                if path.is_file():
                    archive.write(path, path.relative_to(output_path.parent))
                    archived += 1
    return archived


def remove_intermediate_outputs(output_paths: list[Path]) -> None:
    for output_path in output_paths:
        if not output_path.exists():
            continue
        if output_path.is_dir():
            shutil.rmtree(output_path)
        else:
            output_path.unlink()


def main() -> int:
    parser = argparse.ArgumentParser(description="Run scholarly PDF extraction and package one XML file.")
    parser.add_argument("--pdf", required=True, type=Path)
    parser.add_argument("--out", required=True, type=Path)
    parser.add_argument("--grobid-url", default="http://localhost:8070")
    parser.add_argument("--docling-device", choices=["auto", "cuda", "cpu"], default="auto")
    parser.add_argument("--ocr", action="store_true")
    parser.add_argument(
        "--final-out",
        type=Path,
        help="Directory for final XML and images. Defaults to <out>/final.",
    )
    parser.add_argument(
        "--intermediate-archive",
        type=Path,
        help="Zip archive for intermediate parser results. Defaults to <out>/<pdf-name>.intermediate_parse_results.zip.",
    )
    parser.add_argument(
        "--keep-intermediate",
        action="store_true",
        help="Keep loose intermediate parser directories after archiving.",
    )
    args = parser.parse_args()

    basename = args.pdf.stem
    grobid_dir = args.out / "grobid"
    docling_dir = args.out / "docling"
    work_dir = args.out / "work"
    stale_dirs = [args.out / "comparison", args.out / "merged"]
    final_dir = args.final_out or args.out / "final"
    image_dir = final_dir / "images"
    final_xml = final_dir / f"{basename}.xml"
    merge_manifest = work_dir / f"{basename}.merge_manifest.json"
    validation_report = work_dir / f"{basename}.validation_report.json"
    intermediate_archive = args.intermediate_archive or args.out / f"{basename}.intermediate_parse_results.zip"

    for stale_path in [final_dir, grobid_dir, docling_dir, work_dir, *stale_dirs]:
        if stale_path.exists():
            shutil.rmtree(stale_path)
    final_dir.mkdir(parents=True, exist_ok=True)
    work_dir.mkdir(parents=True, exist_ok=True)

    python = sys.executable
    run(
        "grobid",
        [
            python,
            str(SCRIPT_DIR / "grobid_parse_pdf.py"),
            "--pdf",
            str(args.pdf),
            "--out",
            str(grobid_dir),
            "--grobid-url",
            args.grobid_url,
            "--basename",
            basename,
        ],
    )
    run(
        "docling",
        [
            python,
            str(SCRIPT_DIR / "docling_export.py"),
            "--pdf",
            str(args.pdf),
            "--out",
            str(docling_dir),
            "--device",
            args.docling_device,
            *(["--ocr"] if args.ocr else []),
        ],
    )
    run(
        "merge",
        [
            python,
            str(SCRIPT_DIR / "merge_docling_into_grobid_tei.py"),
            "--grobid-tei",
            str(grobid_dir / f"{basename}.fulltext.tei.xml"),
            "--docling-json",
            str(docling_dir / f"{basename}.json"),
            "--docling-image-dir",
            str(docling_dir),
            "--out-xml",
            str(final_xml),
            "--image-out-dir",
            str(image_dir),
            "--manifest",
            str(merge_manifest),
        ],
    )
    run(
        "validate",
        [
            python,
            str(SCRIPT_DIR / "validate_hybrid_outputs.py"),
            "--xml",
            str(final_xml),
            "--image-dir",
            str(image_dir),
            "--out-json",
            str(validation_report),
        ],
    )

    intermediate_paths = [grobid_dir, docling_dir, work_dir]
    archived = archive_intermediate_outputs(intermediate_paths, intermediate_archive)
    if not args.keep_intermediate:
        remove_intermediate_outputs(intermediate_paths)

    print(f"Done. Final XML: {final_xml}")
    print(f"Final images: {image_dir}")
    print(f"Intermediate parse results archived to: {intermediate_archive} ({archived} files)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
