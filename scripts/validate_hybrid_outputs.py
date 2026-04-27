#!/usr/bin/env python3
"""Validate the final XML package image index."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from lxml import etree


NS = {"tei": "http://www.tei-c.org/ns/1.0"}


def validate_package(xml_path: Path, image_dir: Path) -> dict:
    parser = etree.XMLParser(recover=True)
    tree = etree.parse(str(xml_path), parser)

    graphic_urls = [
        str(graphic.get("url"))
        for graphic in tree.xpath("//tei:graphic[@url]", namespaces=NS)
        if graphic.get("url")
    ]
    docling_urls = [url for url in graphic_urls if url.startswith("images/")]
    referenced_images = sorted({Path(url).name for url in docling_urls})
    available_images = sorted(path.name for path in image_dir.glob("*.png"))

    missing_references = [
        {"url": url, "expected_path": str(xml_path.parent / url)}
        for url in docling_urls
        if not (xml_path.parent / url).exists()
    ]
    unindexed_images = sorted(set(available_images) - set(referenced_images))
    duplicate_references = sorted(
        image for image in set(referenced_images) if referenced_images.count(image) > 1
    )
    body_refs = [
        ref
        for ref in tree.xpath(
            "//tei:text//tei:ref[@source='docling'][@subtype='body-reference'][@docling-image]",
            namespaces=NS,
        )
        if not ref.xpath("ancestor::tei:div[@type='docling-images']", namespaces=NS)
    ]
    body_ref_images = sorted({str(ref.get("docling-image")) for ref in body_refs if ref.get("docling-image")})
    indexed_without_body_ref = sorted(set(referenced_images) - set(body_ref_images))
    body_refs_missing_targets = [
        {
            "text": " ".join("".join(ref.itertext()).split()),
            "target": ref.get("target", ""),
            "docling_image": ref.get("docling-image", ""),
        }
        for ref in body_refs
        if ref.get("docling-image") not in available_images
    ]
    remaining_grobid_figures = [
        {
            "xml_id": figure.get("{http://www.w3.org/XML/1998/namespace}id", ""),
            "type": figure.get("type", "figure"),
            "label": " ".join("".join(figure.xpath("./tei:label//text()", namespaces=NS)).split()),
            "head": " ".join("".join(figure.xpath("./tei:head//text()", namespaces=NS)).split()),
        }
        for figure in tree.xpath("//tei:figure[not(@source='docling')]", namespaces=NS)
    ]
    unlinked_body_refs = [
        {
            "text": " ".join("".join(ref.itertext()).split()),
            "type": ref.get("type", ""),
            "target": ref.get("target", ""),
        }
        for ref in tree.xpath(
            "//tei:text//tei:ref[(@type='figure' or @type='table') and not(@source='docling')]",
            namespaces=NS,
        )
        if not ref.xpath("ancestor::tei:div[@type='docling-images']", namespaces=NS)
    ]
    dangling_visual_ref_targets = [
        {
            "text": " ".join("".join(ref.itertext()).split()),
            "type": ref.get("type", ""),
            "target": ref.get("target", ""),
        }
        for ref in tree.xpath(
            "//tei:text//tei:ref[(@type='figure' or @type='table') and @target and not(@source='docling')]",
            namespaces=NS,
        )
        if not ref.xpath("ancestor::tei:div[@type='docling-images']", namespaces=NS)
    ]

    report = {
        "valid": (
            not missing_references
            and not unindexed_images
            and not body_refs_missing_targets
            and not remaining_grobid_figures
            and not dangling_visual_ref_targets
        ),
        "xml": str(xml_path),
        "image_dir": str(image_dir),
        "counts": {
            "graphic_urls": len(graphic_urls),
            "docling_graphic_urls": len(docling_urls),
            "referenced_images": len(referenced_images),
            "available_images": len(available_images),
            "missing_references": len(missing_references),
            "unindexed_images": len(unindexed_images),
            "duplicate_references": len(duplicate_references),
            "body_refs": len(body_refs),
            "body_ref_images": len(body_ref_images),
            "indexed_without_body_ref": len(indexed_without_body_ref),
            "body_refs_missing_targets": len(body_refs_missing_targets),
            "remaining_grobid_figures": len(remaining_grobid_figures),
            "unlinked_body_refs": len(unlinked_body_refs),
            "dangling_visual_ref_targets": len(dangling_visual_ref_targets),
        },
        "missing_references": missing_references,
        "unindexed_images": unindexed_images,
        "duplicate_references": duplicate_references,
        "indexed_without_body_ref": indexed_without_body_ref,
        "body_refs_missing_targets": body_refs_missing_targets,
        "remaining_grobid_figures": remaining_grobid_figures,
        "unlinked_body_refs": unlinked_body_refs,
        "dangling_visual_ref_targets": dangling_visual_ref_targets,
    }
    return report


def main() -> int:
    parser = argparse.ArgumentParser(description="Validate that final XML indexes all final images.")
    parser.add_argument("--xml", required=True, type=Path)
    parser.add_argument("--image-dir", required=True, type=Path)
    parser.add_argument("--out-json", required=True, type=Path)
    args = parser.parse_args()

    report = validate_package(args.xml, args.image_dir)
    args.out_json.parent.mkdir(parents=True, exist_ok=True)
    args.out_json.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({"valid": report["valid"], "counts": report["counts"]}, ensure_ascii=False, indent=2))
    return 0 if report["valid"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
