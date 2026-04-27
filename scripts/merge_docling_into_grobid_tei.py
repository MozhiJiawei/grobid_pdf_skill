#!/usr/bin/env python3
"""Create one TEI XML file that indexes all Docling-exported images."""

from __future__ import annotations

import argparse
import json
import math
import re
import shutil
from pathlib import Path
from typing import Any

from lxml import etree


TEI_NS = "http://www.tei-c.org/ns/1.0"
NS = {"tei": TEI_NS}
XML_ID = "{http://www.w3.org/XML/1998/namespace}id"


def clean_text(value: str) -> str:
    return re.sub(r"\s+", " ", value or "").strip()


def dereference_text(docling_json: dict[str, Any], ref: str) -> str:
    if not isinstance(ref, str) or not ref.startswith("#/texts/"):
        return ""
    try:
        index = int(ref.rsplit("/", 1)[1])
    except ValueError:
        return ""
    texts = docling_json.get("texts", [])
    if 0 <= index < len(texts):
        item = texts[index]
        return clean_text(item.get("text") or item.get("orig") or "")
    return ""


def docling_caption(docling_json: dict[str, Any], item: dict[str, Any]) -> str:
    parts: list[str] = []
    for caption_ref in item.get("captions") or []:
        if isinstance(caption_ref, dict):
            ref = caption_ref.get("$ref") or caption_ref.get("cref") or caption_ref.get("ref") or ""
        else:
            ref = str(caption_ref)
        parts.append(dereference_text(docling_json, ref) or clean_text(str(caption_ref)))
    return clean_text(" ".join(parts))


def infer_label(caption: str) -> str:
    match = re.search(
        r"\b(?:fig(?:ure)?|figure|table)\s*\.?\s*([0-9]+[a-z]?)",
        caption,
        flags=re.IGNORECASE,
    )
    return match.group(1) if match else ""


def infer_kind(default_kind: str, caption: str) -> str:
    if re.search(r"\btable\s*\.?\s*[0-9]+[a-z]?", caption, flags=re.IGNORECASE):
        return "table"
    if re.search(r"\b(?:fig(?:ure)?|figure)\s*\.?\s*[0-9]+[a-z]?", caption, flags=re.IGNORECASE):
        return "figure"
    return default_kind


def normalize_label(value: str) -> str:
    match = re.search(r"([0-9]+[a-z]?)", value or "", flags=re.IGNORECASE)
    return match.group(1).lower() if match else ""


def bbox_string(bbox: dict[str, Any]) -> str:
    return ",".join(str(bbox.get(key, "")) for key in ("l", "b", "r", "t"))


def docling_center(prov: dict[str, Any]) -> tuple[int, float, float] | None:
    bbox = prov.get("bbox") or {}
    page = prov.get("page_no")
    if page is None:
        return None
    try:
        return (
            int(page),
            (float(bbox["l"]) + float(bbox["r"])) / 2,
            (float(bbox["t"]) + float(bbox["b"])) / 2,
        )
    except (KeyError, TypeError, ValueError):
        return None


def grobid_center(coords: str) -> tuple[int, float, float] | None:
    parsed = []
    for chunk in (coords or "").split(";"):
        values = chunk.split(",")
        if len(values) < 5:
            continue
        try:
            page, x, y, width, height = int(float(values[0])), *map(float, values[1:5])
        except ValueError:
            continue
        parsed.append((page, x, y, width, height))
    if not parsed:
        return None
    page = parsed[0][0]
    same_page = [item for item in parsed if item[0] == page]
    min_x = min(x for _, x, _y, _w, _h in same_page)
    max_x = max(x + width for _, x, _y, width, _h in same_page)
    min_y = min(y for _, _x, y, _w, _h in same_page)
    max_y = max(y + height for _, _x, y, _w, height in same_page)
    return page, (min_x + max_x) / 2, (min_y + max_y) / 2


def collect_sentences(tree: etree._ElementTree) -> list[tuple[etree._Element, tuple[int, float, float]]]:
    sentences = []
    for sentence in tree.xpath("//tei:text//tei:s[@coords]", namespaces=NS):
        center = grobid_center(sentence.get("coords", ""))
        if center:
            sentences.append((sentence, center))
    return sentences


def find_nearest_sentence(
    sentences: list[tuple[etree._Element, tuple[int, float, float]]],
    metadata: dict[str, Any],
) -> tuple[etree._Element, tuple[int, float, float], float] | None:
    center = metadata.get("center")
    if not center:
        return None
    page, cx, cy = center
    same_page = [(sentence, item_center) for sentence, item_center in sentences if item_center[0] == page]
    if not same_page:
        return None

    def distance(item: tuple[etree._Element, tuple[int, float, float]]) -> float:
        _sentence, (_page, sx, sy) = item
        return math.hypot((sx - cx) / 2.0, sy - cy)

    sentence, sentence_center = min(same_page, key=distance)
    return sentence, sentence_center, distance((sentence, sentence_center))


def build_docling_image_metadata(docling_json: dict[str, Any], image_dir: Path) -> list[dict[str, Any]]:
    metadata = []
    for collection, kind, prefix in [
        ("pictures", "figure", "picture"),
        ("tables", "table", "table"),
    ]:
        for index, item in enumerate(docling_json.get(collection, []), start=1):
            image_file = f"{prefix}_{index:03d}.png"
            image_path = image_dir / image_file
            if not image_path.exists():
                continue
            caption = docling_caption(docling_json, item)
            prov = (item.get("prov") or [{}])[0]
            bbox = prov.get("bbox") or {}
            inferred_kind = infer_kind(kind, caption)
            metadata.append(
                {
                    "collection": collection,
                    "index": index,
                    "image_file": image_file,
                    "kind": inferred_kind,
                    "label": infer_label(caption),
                    "caption": caption,
                    "self_ref": item.get("self_ref", ""),
                    "page": prov.get("page_no", ""),
                    "bbox": bbox,
                    "center": docling_center(prov),
                }
            )
    return metadata


def grobid_items(tree: etree._ElementTree) -> list[dict[str, Any]]:
    items = []
    for figure in tree.xpath("//tei:figure[not(@source='docling')]", namespaces=NS):
        kind = "table" if figure.get("type") == "table" else "figure"
        label = clean_text(" ".join(figure.xpath("./tei:label/text()", namespaces=NS)))
        head = clean_text(" ".join(figure.xpath("./tei:head//text()", namespaces=NS)))
        if not label:
            label = infer_label(head)
        center = grobid_center(figure.get("coords", ""))
        items.append(
            {
                "xml_id": figure.get(XML_ID, ""),
                "kind": kind,
                "label": normalize_label(label),
                "page": center[0] if center else None,
                "center": center,
                "head": head,
            }
        )
    return items


def fill_missing_docling_labels(images: list[dict[str, Any]], grobid: list[dict[str, Any]]) -> None:
    used_labels = {(image["kind"], normalize_label(image.get("label", ""))) for image in images if image.get("label")}
    for image in images:
        if image.get("label") or not image.get("center"):
            continue
        page, cx, cy = image["center"]
        candidates = [
            item
            for item in grobid
            if item["kind"] == image["kind"]
            and item.get("label")
            and item.get("page") == page
            and (item["kind"], item["label"]) not in used_labels
            and item.get("center")
        ]
        if not candidates:
            continue
        nearest = min(
            candidates,
            key=lambda item: math.hypot((item["center"][1] - cx) / 2.0, item["center"][2] - cy),
        )
        image["label"] = nearest["label"]
        image["label_source"] = "grobid-nearest-same-page"
        used_labels.add((image["kind"], image["label"]))


def ensure_body(tree: etree._ElementTree) -> etree._Element:
    body = tree.find(".//tei:text/tei:body", NS)
    if body is not None:
        return body
    text = tree.find(".//tei:text", NS)
    if text is None:
        text = etree.SubElement(tree.getroot(), f"{{{TEI_NS}}}text")
    return etree.SubElement(text, f"{{{TEI_NS}}}body")


def remove_prior_docling_outputs(tree: etree._ElementTree) -> None:
    for div in tree.xpath("//tei:div[@type='docling-images']", namespaces=NS):
        parent = div.getparent()
        if parent is not None:
            parent.remove(div)
    for ref in tree.xpath("//tei:ref[@source='docling']", namespaces=NS):
        parent = ref.getparent()
        if parent is not None:
            parent.remove(ref)
    for note in tree.xpath("//tei:note[@type='docling-inline-ref']", namespaces=NS):
        parent = note.getparent()
        if parent is not None:
            parent.remove(note)


def append_docling_figures(tree: etree._ElementTree, images: list[dict[str, Any]]) -> list[dict[str, Any]]:
    body = ensure_body(tree)
    div = etree.SubElement(body, f"{{{TEI_NS}}}div")
    div.set("type", "docling-images")
    head = etree.SubElement(div, f"{{{TEI_NS}}}head")
    head.text = "Docling image index"

    appended = []
    for image in images:
        xml_id = "docling_" + Path(image["image_file"]).stem
        figure = etree.SubElement(div, f"{{{TEI_NS}}}figure")
        figure.set(XML_ID, xml_id)
        figure.set("source", "docling")
        figure.set("type", image["kind"])
        if image.get("self_ref"):
            figure.set("corresp", str(image["self_ref"]))

        title = "Table" if image["kind"] == "table" else "Figure"
        head = etree.SubElement(figure, f"{{{TEI_NS}}}head")
        head.text = clean_text(f"Docling {title} {image.get('label', '')}") or f"Docling {title}"
        if image.get("label"):
            label = etree.SubElement(figure, f"{{{TEI_NS}}}label")
            label.text = str(image["label"])

        graphic = etree.SubElement(figure, f"{{{TEI_NS}}}graphic")
        graphic.set("url", f"images/{image['image_file']}")
        graphic.set("mimeType", "image/png")
        graphic.set("source", "docling")
        graphic.set("n", str(image["index"]))
        graphic.set("docling-page", str(image.get("page", "")))
        if image.get("bbox"):
            graphic.set("docling-bbox", bbox_string(image["bbox"]))
            graphic.set("docling-coord-origin", str(image["bbox"].get("coord_origin", "")))
        if image.get("self_ref"):
            graphic.set("docling-ref", str(image["self_ref"]))

        if image.get("caption"):
            fig_desc = etree.SubElement(figure, f"{{{TEI_NS}}}figDesc")
            paragraph = etree.SubElement(fig_desc, f"{{{TEI_NS}}}p")
            paragraph.text = str(image["caption"])
        appended.append({"xml_id": xml_id, **image})
    return appended


def ref_page(ref: etree._Element) -> int | None:
    node = ref
    while node is not None:
        center = grobid_center(node.get("coords", ""))
        if center:
            return center[0]
        node = node.getparent()
    return None


def choose_image_for_ref(
    images: list[dict[str, Any]],
    *,
    kind: str,
    label: str,
    page: int | None,
) -> dict[str, Any] | None:
    label = normalize_label(label)
    candidates = [image for image in images if image["kind"] == kind and normalize_label(image.get("label", "")) == label]
    if not candidates:
        return None
    if page is not None:
        same_page = [image for image in candidates if image.get("page") == page]
        if same_page:
            return same_page[0]
    return candidates[0] if len(candidates) == 1 else None


def link_existing_body_refs(
    tree: etree._ElementTree,
    appended: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    image_index = {image["xml_id"]: image for image in appended}
    linked = []
    for ref in tree.xpath(
        "//tei:text//tei:ref[(@type='figure' or @type='table') and not(ancestor::tei:div[@type='docling-images'])]",
        namespaces=NS,
    ):
        kind = str(ref.get("type"))
        label = normalize_label(clean_text("".join(ref.itertext())))
        if not label:
            continue
        image = choose_image_for_ref(appended, kind=kind, label=label, page=ref_page(ref))
        if image is None:
            continue
        old_target = ref.get("target", "")
        ref.set("target", f"#{image['xml_id']}")
        ref.set("source", "docling")
        ref.set("subtype", "body-reference")
        ref.set("docling-image", image["image_file"])
        ref.set("docling-page", str(image.get("page", "")))
        linked.append(
            {
                "target": ref.get("target"),
                "old_target": old_target,
                "image": image["image_file"],
                "kind": kind,
                "label": label,
                "ref_page": ref_page(ref),
                "docling_page": image.get("page", ""),
            }
        )
        image_index.pop(image["xml_id"], None)
    return linked


def remove_original_grobid_figures(tree: etree._ElementTree) -> list[dict[str, Any]]:
    removed = []
    for figure in tree.xpath("//tei:figure[not(@source='docling')]", namespaces=NS):
        parent = figure.getparent()
        if parent is None:
            continue
        xml_id = figure.get(XML_ID, "")
        kind = "table" if figure.get("type") == "table" else "figure"
        label = clean_text(" ".join(figure.xpath("./tei:label/text()", namespaces=NS)))
        head = clean_text(" ".join(figure.xpath("./tei:head//text()", namespaces=NS)))
        parent.remove(figure)
        removed.append({"xml_id": xml_id, "kind": kind, "label": label, "head": head})
    return removed


def strip_unlinked_grobid_ref_targets(tree: etree._ElementTree) -> list[dict[str, Any]]:
    stripped = []
    for ref in tree.xpath(
        "//tei:text//tei:ref[(@type='figure' or @type='table') and not(@source='docling') and @target]",
        namespaces=NS,
    ):
        if ref.xpath("ancestor::tei:div[@type='docling-images']", namespaces=NS):
            continue
        old_target = ref.get("target", "")
        ref.attrib.pop("target", None)
        ref.set("subtype", "unresolved-visual-ref")
        stripped.append(
            {
                "text": clean_text("".join(ref.itertext())),
                "type": ref.get("type", ""),
                "old_target": old_target,
            }
        )
    return stripped


def copy_images(source_dir: Path, output_dir: Path) -> int:
    if output_dir.exists():
        shutil.rmtree(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    copied = 0
    for pattern in ("picture_*.png", "table_*.png"):
        for image_path in sorted(source_dir.glob(pattern)):
            shutil.copy2(image_path, output_dir / image_path.name)
            copied += 1
    return copied


def merge(
    grobid_tei: Path,
    docling_json: Path,
    docling_image_dir: Path,
    out_xml: Path,
    image_out_dir: Path,
    manifest_path: Path,
) -> dict[str, Any]:
    parser = etree.XMLParser(remove_blank_text=False, recover=True)
    tree = etree.parse(str(grobid_tei), parser)
    docling_data = json.loads(docling_json.read_text(encoding="utf-8"))

    copied_images = copy_images(docling_image_dir, image_out_dir)
    images = build_docling_image_metadata(docling_data, image_out_dir)
    remove_prior_docling_outputs(tree)
    fill_missing_docling_labels(images, grobid_items(tree))
    appended = append_docling_figures(tree, images)
    linked_refs = link_existing_body_refs(tree, appended)
    removed_grobid_figures = remove_original_grobid_figures(tree)
    stripped_ref_targets = strip_unlinked_grobid_ref_targets(tree)

    out_xml.parent.mkdir(parents=True, exist_ok=True)
    tree.write(str(out_xml), encoding="utf-8", xml_declaration=True, pretty_print=True)

    manifest = {
        "xml": str(out_xml),
        "image_dir": str(image_out_dir),
        "source_grobid_tei": str(grobid_tei),
        "source_docling_json": str(docling_json),
        "policy": "GROBID is the text/structure truth. Docling is the figure/table image truth.",
        "counts": {
            "docling_images_copied": copied_images,
            "docling_images_indexed": len(appended),
            "body_refs_linked": len(linked_refs),
            "removed_grobid_figures": len(removed_grobid_figures),
            "stripped_unlinked_grobid_ref_targets": len(stripped_ref_targets),
        },
        "indexed_images": appended,
        "body_refs_linked": linked_refs,
        "removed_grobid_figures": removed_grobid_figures,
        "stripped_unlinked_grobid_ref_targets": stripped_ref_targets,
    }
    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({"xml": str(out_xml), "counts": manifest["counts"]}, ensure_ascii=False, indent=2))
    return manifest


def main() -> int:
    parser = argparse.ArgumentParser(description="Merge Docling image truth into one GROBID TEI XML file.")
    parser.add_argument("--grobid-tei", required=True, type=Path)
    parser.add_argument("--docling-json", required=True, type=Path)
    parser.add_argument("--docling-image-dir", required=True, type=Path)
    parser.add_argument("--out-xml", required=True, type=Path)
    parser.add_argument("--image-out-dir", required=True, type=Path)
    parser.add_argument("--manifest", required=True, type=Path)
    args = parser.parse_args()

    merge(
        args.grobid_tei,
        args.docling_json,
        args.docling_image_dir,
        args.out_xml,
        args.image_out_dir,
        args.manifest,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
