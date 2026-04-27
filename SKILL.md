---
name: grobid-docling-pdf
description: Produce one clean scholarly PDF XML package with GROBID text structure and Docling-truth figure/table images. Use when Codex needs to parse a research paper or technical PDF into a single TEI/XML file that correctly indexes exported images, with intermediate parser files archived and removed after packaging.
---

# GROBID + Docling PDF XML Package

Use the bundled scripts. Do not rewrite parsing, image export, merge, cleanup, or validation code inline.

## Default Workflow

For one PDF:

```bash
python scripts/run_hybrid_pipeline.py \
  --pdf path/to/paper.pdf \
  --out .tmp/pdf_xml/<paper-name> \
  --grobid-url http://localhost:8070 \
  --docling-device auto
```

Use `--docling-device cuda` only after verifying CUDA PyTorch works. Use `--ocr` only for scanned PDFs; leave OCR off for born-digital papers.

The pipeline:

1. Runs GROBID for scholarly text structure and references.
2. Runs Docling for visual truth and exports figure/table PNGs.
3. Writes one final TEI/XML file that indexes every exported Docling image.
4. Deletes original GROBID figure/table records so Docling remains the only visual index.
5. Validates that XML image references resolve to files and every final image is indexed.
6. Reports how many indexed images are also linked from real body `<ref>` elements.
7. Archives intermediate parser outputs into `<out>/<paper-name>.intermediate_parse_results.zip`.
8. Deletes the loose intermediate parser directories/files after the archive is created.

## Final Output Contract

Only these deliverables should remain outside the archive:

```text
<out>/
+-- final/
|   +-- <name>.xml
|   +-- images/
|       +-- picture_*.png
|       +-- table_*.png
+-- <name>.intermediate_parse_results.zip
```

Use `<out>/final/<name>.xml` as the downstream XML. Its Docling image references point to `images/...` paths beside the XML.

## Interpretation Rules

- Use GROBID TEI for title, abstract, body text, sentence nodes, coordinates, citations, and bibliography.
- Use Docling as the only figure/table image truth.
- Remove original GROBID figure/table records from the final XML after body references are rewired to Docling targets.
- Strip unresolved GROBID visual-reference targets when no Docling image can support them; keep the visible text but do not leave dangling `target` attributes.
- Do not build or consume a GROBID-to-Docling crosswalk.
- Include every Docling-exported `picture_*.png` and `table_*.png` in the final XML.
- Treat inline image references inserted by the merge script as inferred links when no original GROBID reference exists.
- Treat validation failure as a packaging failure: fix missing, broken, or unindexed image references before reporting success.
- Do not claim every image has a correct body-position reference unless validation reports no `indexed_without_body_ref` items.

## Reporting

When summarizing results, include:

- Final XML path.
- Final image directory path and image count.
- Intermediate archive path.
- Validation status: referenced images, missing references, unindexed images, body-linked images, and images indexed only in the image index.
- GROBID text counts and Docling visual counts if useful; read them from the archived intermediate reports only when needed.
