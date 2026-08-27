#!/usr/bin/env python3
"""Verify external dependencies for grobid-docling-pdf.

This script checks only user/environment prerequisites: Python packages,
Docker availability, the unique local GROBID runtime policy, and optional CUDA availability.
Repository files, sample PDFs, generated artifacts, and parser self-tests are
internal health checks and are intentionally outside this dependency check.
"""

from __future__ import annotations

import platform
import shutil
import subprocess
import sys
from pathlib import Path


SCRIPT_DIR = Path(__file__).resolve().parent / "scripts"
sys.path.insert(0, str(SCRIPT_DIR))

from manage_grobid_runtime import RuntimePolicyError, inspect_runtime  # noqa: E402


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


def docker_guidance(system: str | None = None) -> tuple[str, str]:
    system = system or platform.system()
    if system == "Windows":
        return (
            "Install WSL2 and Docker Desktop, then start Docker Desktop.",
            "Start Docker Desktop and ensure its WSL2 backend is working.",
        )
    return (
        "Install Docker Desktop for Mac, then start Docker Desktop.",
        "Start Docker Desktop for Mac and wait for the Docker engine to become ready.",
    )


def check_docker() -> str | None:
    install_guidance, start_guidance = docker_guidance()
    docker = shutil.which("docker")
    if not docker:
        fail_check(
            "Docker",
            f"docker command not found. {install_guidance}",
        )
        return None

    try:
        result = subprocess.run(
            [docker, "version", "--format", "{{.Server.Version}}"],
            check=True,
            capture_output=True,
            text=True,
            timeout=15,
        )
    except (subprocess.SubprocessError, OSError) as exc:
        detail = getattr(exc, "stderr", "") or str(exc)
        fail_check(
            "Docker",
            f"Docker is installed but unavailable: {detail.strip()}. "
            f"{start_guidance}",
        )
        return None

    pass_check("Docker", f"server {result.stdout.strip() or 'available'}")
    return docker


def check_grobid_runtime() -> bool:
    try:
        state = inspect_runtime()
    except RuntimePolicyError as exc:
        fail_check("GROBID runtime", str(exc))
        return False
    pass_check("GROBID image", "grobid/grobid:0.8.2 (unique)")
    if state.container is None:
        pass_check("GROBID container", "absent; the pipeline will create the shared container")
    else:
        status = "running" if state.container.get("State", {}).get("Running", False) else "stopped"
        pass_check("GROBID container", f"grobid-docling-pdf ({status}, unique)")
    return True


def main() -> int:
    ok = True
    ok = import_module("docling", "docling") and ok
    ok = import_module("lxml", "lxml") and ok
    ok = import_module("torch", "torch") and ok
    check_torch_cuda()

    docker = check_docker()
    ok = bool(docker) and ok
    if docker:
        ok = check_grobid_runtime() and ok
    else:
        warn_check("GROBID runtime", "skipped because Docker is unavailable")

    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
