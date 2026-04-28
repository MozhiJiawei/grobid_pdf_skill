#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from urllib.parse import urljoin
from urllib.request import urlopen


def pass_check(name: str, detail: str = "") -> None:
    print(f"PASS {name}{': ' + detail if detail else ''}")


def warn_check(name: str, detail: str) -> None:
    print(f"WARN {name}: {detail}")


def fail_check(name: str, detail: str) -> None:
    print(f"FAIL {name}: {detail}")


def import_module(module_name: str, package_name: str) -> bool:
    try:
        module = __import__(module_name)
    except Exception as exc:
        fail_check(package_name, str(exc))
        return False

    version = getattr(module, "__version__", "")
    pass_check(package_name, version or "import ok")
    return True


def check_torch_cuda() -> None:
    try:
        import torch
    except Exception as exc:
        warn_check("torch cuda", f"torch unavailable, CUDA check skipped: {exc}")
        return

    if torch.cuda.is_available():
        pass_check("torch cuda", torch.cuda.get_device_name(0))
    else:
        warn_check("torch cuda", "CUDA is not available; use --docling-device cpu or auto.")


def check_grobid_service(grobid_url: str) -> bool:
    alive_url = urljoin(grobid_url.rstrip("/") + "/", "api/isalive")
    try:
        with urlopen(alive_url, timeout=10) as response:
            body = response.read().decode("utf-8", errors="replace").strip()
    except Exception as exc:
        fail_check("GROBID service", f"{alive_url} is not reachable: {exc}")
        return False

    try:
        parsed = json.loads(body)
    except json.JSONDecodeError:
        parsed = body

    pass_check("GROBID service", f"{alive_url} -> {parsed}")
    return True


def main() -> int:
    parser = argparse.ArgumentParser(description="Verify dependencies for grobid-docling-pdf.")
    parser.add_argument("--grobid-url", default="http://localhost:8070")
    parser.add_argument(
        "--skip-services",
        action="store_true",
        help="Only verify local Python dependencies; skip the GROBID HTTP service check.",
    )
    args = parser.parse_args()

    ok = True
    ok = import_module("docling", "docling") and ok
    ok = import_module("lxml", "lxml") and ok
    ok = import_module("torch", "torch") and ok
    check_torch_cuda()

    if args.skip_services:
        warn_check("GROBID service", "skipped")
    else:
        ok = check_grobid_service(args.grobid_url) and ok

    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
