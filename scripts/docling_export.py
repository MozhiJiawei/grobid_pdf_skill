#!/usr/bin/env python3
"""Export Docling structure and figure/table images."""

from __future__ import annotations

import argparse
import json
from pathlib import Path


def import_docling():
    from docling.datamodel.accelerator_options import AcceleratorDevice, AcceleratorOptions
    from docling.datamodel.base_models import InputFormat
    from docling.datamodel.pipeline_options import PdfPipelineOptions
    from docling.document_converter import DocumentConverter, PdfFormatOption

    return AcceleratorDevice, AcceleratorOptions, InputFormat, PdfPipelineOptions, DocumentConverter, PdfFormatOption


def torch_status() -> dict:
    try:
        import torch
    except Exception as exc:
        return {"available": False, "error": str(exc)}
    status = {
        "available": True,
        "version": getattr(torch, "__version__", ""),
        "cuda_available": bool(torch.cuda.is_available()),
        "cuda": getattr(torch.version, "cuda", None),
    }
    if status["cuda_available"]:
        status["device"] = torch.cuda.get_device_name(0)
    return status


def dereference_text(doc_dict: dict, ref: str) -> str:
    if not isinstance(ref, str) or not ref.startswith("#/texts/"):
        return ""
    try:
        index = int(ref.rsplit("/", 1)[1])
    except ValueError:
        return ""
    texts = doc_dict.get("texts", [])
    if 0 <= index < len(texts):
        item = texts[index]
        return " ".join((item.get("text") or item.get("orig") or "").split())
    return ""


def caption_for_item(doc_dict: dict, item) -> str:
    captions = []
    for caption_ref in getattr(item, "captions", []) or []:
        ref = getattr(caption_ref, "cref", "") or str(caption_ref)
        captions.append(dereference_text(doc_dict, ref) or str(caption_ref))
    return " ".join(" ".join(caption.split()) for caption in captions).strip()


def export_docling(pdf_path: Path, out_dir: Path, device: str, images_scale: float, do_ocr: bool) -> dict:
    AcceleratorDevice, AcceleratorOptions, InputFormat, PdfPipelineOptions, DocumentConverter, PdfFormatOption = import_docling()

    out_dir.mkdir(parents=True, exist_ok=True)
    pipeline_options = PdfPipelineOptions()
    if device == "cuda":
        accelerator_device = AcceleratorDevice.CUDA
    elif device == "cpu":
        accelerator_device = AcceleratorDevice.CPU
    else:
        accelerator_device = AcceleratorDevice.AUTO
    pipeline_options.accelerator_options = AcceleratorOptions(num_threads=8, device=accelerator_device)
    pipeline_options.do_ocr = do_ocr
    pipeline_options.do_table_structure = True
    pipeline_options.generate_page_images = True
    pipeline_options.generate_picture_images = True
    pipeline_options.generate_table_images = True
    pipeline_options.images_scale = images_scale

    converter = DocumentConverter(
        format_options={InputFormat.PDF: PdfFormatOption(pipeline_options=pipeline_options)}
    )
    result = converter.convert(pdf_path)
    doc = result.document
    doc_dict = doc.export_to_dict()

    json_path = out_dir / f"{pdf_path.stem}.json"
    json_path.write_text(json.dumps(doc_dict, ensure_ascii=False, indent=2), encoding="utf-8")

    exported = 0
    for _kind, collection, prefix in [
        ("picture", getattr(doc, "pictures", []) or [], "picture"),
        ("table", getattr(doc, "tables", []) or [], "table"),
    ]:
        for index, item in enumerate(collection, start=1):
            image = item.get_image(doc)
            if image is None:
                continue
            image_path = out_dir / f"{prefix}_{index:03d}.png"
            image.save(image_path)
            exported += 1

    manifest = {
        "pdf": str(pdf_path),
        "out_dir": str(out_dir),
        "device_requested": device,
        "torch": torch_status(),
        "json": str(json_path),
        "pictures": len(getattr(doc, "pictures", []) or []),
        "tables": len(getattr(doc, "tables", []) or []),
        "exported_images": exported,
    }
    return manifest


def main() -> int:
    parser = argparse.ArgumentParser(description="Export Docling outputs for one PDF.")
    parser.add_argument("--pdf", required=True, type=Path)
    parser.add_argument("--out", required=True, type=Path)
    parser.add_argument("--device", choices=["auto", "cuda", "cpu"], default="auto")
    parser.add_argument("--images-scale", type=float, default=2.0)
    parser.add_argument("--ocr", action="store_true", help="Enable OCR. Leave off for born-digital papers.")
    args = parser.parse_args()

    manifest = export_docling(args.pdf, args.out, args.device, args.images_scale, args.ocr)
    print(json.dumps(manifest, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
