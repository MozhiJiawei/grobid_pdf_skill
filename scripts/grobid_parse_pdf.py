#!/usr/bin/env python3
"""Run GROBID PDF parsing with stable defaults for scholarly papers."""

from __future__ import annotations

import argparse
import http.client
import json
import socket
import mimetypes
import time
import uuid
from pathlib import Path
from urllib.parse import urlparse


DEFAULT_COORDS = ["persName", "figure", "ref", "biblStruct", "formula", "s"]


def api_url(base_url: str, path: str) -> str:
    return base_url.rstrip("/") + "/api/" + path.lstrip("/")


def http_get(url: str, timeout: int = 30) -> tuple[int, bytes]:
    parsed = urlparse(url)
    conn_cls = http.client.HTTPSConnection if parsed.scheme == "https" else http.client.HTTPConnection
    conn = conn_cls(parsed.netloc, timeout=timeout)
    target = parsed.path or "/"
    if parsed.query:
        target += "?" + parsed.query
    conn.request("GET", target)
    response = conn.getresponse()
    data = response.read()
    conn.close()
    return response.status, data


def multipart_body(pdf_path: Path, fields: list[tuple[str, str]]) -> tuple[str, bytes]:
    boundary = "----grobid-skill-" + uuid.uuid4().hex
    chunks: list[bytes] = []

    for name, value in fields:
        chunks.extend(
            [
                f"--{boundary}\r\n".encode(),
                f'Content-Disposition: form-data; name="{name}"\r\n\r\n'.encode(),
                str(value).encode("utf-8"),
                b"\r\n",
            ]
        )

    mime = mimetypes.guess_type(pdf_path.name)[0] or "application/pdf"
    chunks.extend(
        [
            f"--{boundary}\r\n".encode(),
            f'Content-Disposition: form-data; name="input"; filename="{pdf_path.name}"\r\n'.encode(),
            f"Content-Type: {mime}\r\n\r\n".encode(),
            pdf_path.read_bytes(),
            b"\r\n",
            f"--{boundary}--\r\n".encode(),
        ]
    )
    return boundary, b"".join(chunks)


def http_post_multipart(
    url: str,
    pdf_path: Path,
    fields: list[tuple[str, str]],
    *,
    accept: str = "application/xml",
    timeout: int = 300,
) -> tuple[int, bytes, float]:
    parsed = urlparse(url)
    boundary, body = multipart_body(pdf_path, fields)
    headers = {
        "Accept": accept,
        "Content-Type": f"multipart/form-data; boundary={boundary}",
        "Content-Length": str(len(body)),
    }
    conn_cls = http.client.HTTPSConnection if parsed.scheme == "https" else http.client.HTTPConnection
    conn = conn_cls(parsed.netloc, timeout=timeout)
    target = parsed.path or "/"
    if parsed.query:
        target += "?" + parsed.query
    started = time.perf_counter()
    conn.request("POST", target, body=body, headers=headers)
    response = conn.getresponse()
    data = response.read()
    elapsed = time.perf_counter() - started
    conn.close()
    return response.status, data, elapsed


def write_response(path: Path, data: bytes) -> int:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data)
    return path.stat().st_size


def parse_pdf(pdf_path: Path, out_dir: Path, grobid_url: str, basename: str) -> dict:
    out_dir.mkdir(parents=True, exist_ok=True)

    try:
        status, body = http_get(api_url(grobid_url, "isalive"))
    except (ConnectionError, OSError, socket.error) as exc:
        raise SystemExit(
            f"GROBID is not reachable at {grobid_url}. Start the service first. "
            f"Original error: {exc}"
        ) from exc
    if status != 200 or body.strip() != b"true":
        raise SystemExit(f"GROBID is not alive at {grobid_url}: status={status} body={body[:100]!r}")

    jobs = [
        {
            "name": "fulltext",
            "endpoint": "processFulltextDocument",
            "output": out_dir / f"{basename}.fulltext.tei.xml",
            "fields": [
                ("consolidateHeader", "1"),
                ("consolidateCitations", "1"),
                ("includeRawCitations", "1"),
                ("includeRawAffiliations", "1"),
                ("includeRawCopyrights", "1"),
                ("segmentSentences", "1"),
                *[("teiCoordinates", coord) for coord in DEFAULT_COORDS],
            ],
        },
    ]

    manifest = {
        "pdf": str(pdf_path),
        "grobid_url": grobid_url,
        "basename": basename,
        "jobs": [],
    }
    for job in jobs:
        status, data, elapsed = http_post_multipart(
            api_url(grobid_url, job["endpoint"]),
            pdf_path,
            job["fields"],
        )
        size = write_response(job["output"], data)
        manifest["jobs"].append(
            {
                "name": job["name"],
                "endpoint": job["endpoint"],
                "status": status,
                "seconds": round(elapsed, 3),
                "bytes": size,
                "output": str(job["output"]),
            }
        )
        if status != 200:
            raise SystemExit(f"GROBID {job['name']} failed: status={status}, output={job['output']}")

    return manifest


def main() -> int:
    parser = argparse.ArgumentParser(description="Parse a PDF with GROBID using skill defaults.")
    parser.add_argument("--pdf", required=True, type=Path)
    parser.add_argument("--out", required=True, type=Path)
    parser.add_argument("--grobid-url", default="http://localhost:8070")
    parser.add_argument("--basename")
    args = parser.parse_args()

    basename = args.basename or args.pdf.stem
    manifest = parse_pdf(args.pdf, args.out, args.grobid_url, basename)
    print(json.dumps(manifest, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
