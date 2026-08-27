#!/usr/bin/env python3
"""Inspect and ensure the single shared local GROBID Docker runtime."""

from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
import time
import urllib.error
import urllib.request
from dataclasses import dataclass
from typing import Any, Callable


CANONICAL_IMAGE = "grobid/grobid:0.8.2"
CANONICAL_CONTAINER = "grobid-docling-pdf"
CANONICAL_IMAGE_LABEL = "org.label-schema.name=GROBID"
CONTAINER_LABEL = "io.codex.skill=grobid-docling-pdf"
HOST_IP = "127.0.0.1"
HOST_PORT = "8070"
CONTAINER_PORT = "8070/tcp"
HEALTH_URL = f"http://{HOST_IP}:{HOST_PORT}/api/isalive"


class RuntimePolicyError(RuntimeError):
    """Raised when Docker state violates the single-runtime policy."""


@dataclass(frozen=True)
class RuntimeState:
    image: dict[str, Any]
    container: dict[str, Any] | None


DockerRunner = Callable[[list[str], bool], subprocess.CompletedProcess[str]]


def run_docker(args: list[str], check: bool = True) -> subprocess.CompletedProcess[str]:
    docker = shutil.which("docker")
    if not docker:
        raise RuntimePolicyError("docker command not found")
    try:
        return subprocess.run(
            [docker, *args],
            check=check,
            capture_output=True,
            text=True,
            timeout=60,
        )
    except subprocess.CalledProcessError as exc:
        detail = (exc.stderr or exc.stdout or str(exc)).strip()
        raise RuntimePolicyError(f"docker {' '.join(args)} failed: {detail}") from exc
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise RuntimePolicyError(f"docker {' '.join(args)} failed: {exc}") from exc


def parse_json_lines(text: str) -> list[dict[str, Any]]:
    return [json.loads(line) for line in text.splitlines() if line.strip()]


def inspect_one(kind: str, identifier: str, runner: DockerRunner) -> dict[str, Any]:
    result = runner([kind, "inspect", identifier], True)
    payload = json.loads(result.stdout)
    if not payload:
        raise RuntimePolicyError(f"docker {kind} inspect returned no data for {identifier}")
    return payload[0]


def discover_grobid_images(runner: DockerRunner = run_docker) -> list[dict[str, Any]]:
    candidate_ids: set[str] = set()
    all_rows = parse_json_lines(
        runner(["image", "ls", "--all", "--no-trunc", "--format", "{{json .}}"], True).stdout
    )
    candidate_ids.update(
        row["ID"]
        for row in all_rows
        if "grobid" in str(row.get("Repository", "")).lower()
    )
    labeled_rows = parse_json_lines(
        runner(
            [
                "image",
                "ls",
                "--all",
                "--no-trunc",
                "--filter",
                f"label={CANONICAL_IMAGE_LABEL}",
                "--format",
                "{{json .}}",
            ],
            True,
        ).stdout
    )
    candidate_ids.update(row["ID"] for row in labeled_rows)
    return [inspect_one("image", image_id, runner) for image_id in sorted(candidate_ids)]


def validate_unique_image(images: list[dict[str, Any]]) -> dict[str, Any]:
    if not images:
        raise RuntimePolicyError(
            f"no GROBID image found; install exactly {CANONICAL_IMAGE}"
        )
    if len(images) != 1:
        ids = ", ".join(str(image.get("Id", "unknown")) for image in images)
        raise RuntimePolicyError(f"expected one GROBID image ID, found {len(images)}: {ids}")
    image = images[0]
    tags = image.get("RepoTags") or []
    if tags != [CANONICAL_IMAGE]:
        raise RuntimePolicyError(
            f"the sole GROBID image must have only tag {CANONICAL_IMAGE}; found {tags}"
        )
    return image


def discover_grobid_containers(
    image_id: str,
    runner: DockerRunner = run_docker,
) -> list[dict[str, Any]]:
    rows = parse_json_lines(
        runner(
            ["container", "ls", "--all", "--no-trunc", "--format", "{{json .}}"],
            True,
        ).stdout
    )
    containers: list[dict[str, Any]] = []
    for row in rows:
        container = inspect_one("container", row["ID"], runner)
        configured_image = str(container.get("Config", {}).get("Image", ""))
        name = str(container.get("Name", ""))
        if (
            container.get("Image") == image_id
            or "grobid" in configured_image.lower()
            or "grobid" in name.lower()
        ):
            containers.append(container)
    return containers


def validate_container(
    containers: list[dict[str, Any]],
    image_id: str,
) -> dict[str, Any] | None:
    if len(containers) > 1:
        names = ", ".join(str(item.get("Name", "unknown")).lstrip("/") for item in containers)
        raise RuntimePolicyError(
            f"expected at most one GROBID container, found {len(containers)}: {names}"
        )
    if not containers:
        return None

    container = containers[0]
    errors: list[str] = []
    if str(container.get("Name", "")).lstrip("/") != CANONICAL_CONTAINER:
        errors.append(f"name must be {CANONICAL_CONTAINER}")
    if container.get("Image") != image_id:
        errors.append("image ID does not match the canonical image")
    if container.get("Config", {}).get("Image") != CANONICAL_IMAGE:
        errors.append(f"configured image must be {CANONICAL_IMAGE}")

    host_config = container.get("HostConfig", {})
    expected_binding = [{"HostIp": HOST_IP, "HostPort": HOST_PORT}]
    actual_binding = (host_config.get("PortBindings") or {}).get(CONTAINER_PORT)
    if actual_binding != expected_binding:
        errors.append(f"port must be {HOST_IP}:{HOST_PORT}->{CONTAINER_PORT}")
    if (host_config.get("RestartPolicy") or {}).get("Name") != "unless-stopped":
        errors.append("restart policy must be unless-stopped")
    if errors:
        raise RuntimePolicyError("GROBID container configuration drift: " + "; ".join(errors))
    return container


def inspect_runtime(runner: DockerRunner = run_docker) -> RuntimeState:
    image = validate_unique_image(discover_grobid_images(runner))
    containers = discover_grobid_containers(image["Id"], runner)
    container = validate_container(containers, image["Id"])
    return RuntimeState(image=image, container=container)


def create_container(runner: DockerRunner = run_docker) -> None:
    result = runner(
        [
            "container",
            "run",
            "--detach",
            "--name",
            CANONICAL_CONTAINER,
            "--restart",
            "unless-stopped",
            "--publish",
            f"{HOST_IP}:{HOST_PORT}:8070",
            "--label",
            CONTAINER_LABEL,
            CANONICAL_IMAGE,
        ],
        False,
    )
    if result.returncode == 0:
        return

    # A concurrent caller may have created the fixed-name container first.
    state = inspect_runtime(runner)
    if state.container is None:
        detail = (result.stderr or result.stdout or "unknown docker error").strip()
        raise RuntimePolicyError(f"could not create {CANONICAL_CONTAINER}: {detail}")


def wait_for_health(timeout: float = 120.0, interval: float = 2.0) -> None:
    deadline = time.monotonic() + timeout
    last_error = "service did not respond"
    while True:
        try:
            with urllib.request.urlopen(HEALTH_URL, timeout=5) as response:
                body = response.read().decode("utf-8", errors="replace").strip().lower()
                if response.status == 200 and body == "true":
                    return
                last_error = f"HTTP {response.status}: {body}"
        except (OSError, urllib.error.URLError) as exc:
            last_error = str(exc)
        if time.monotonic() >= deadline:
            raise RuntimePolicyError(
                f"GROBID did not become healthy at {HEALTH_URL} within {timeout:g}s: {last_error}"
            )
        time.sleep(interval)


def ensure_runtime(runner: DockerRunner = run_docker) -> RuntimeState:
    state = inspect_runtime(runner)
    if state.container is None:
        create_container(runner)
        state = inspect_runtime(runner)
    elif not state.container.get("State", {}).get("Running", False):
        runner(["container", "start", CANONICAL_CONTAINER], True)
        state = inspect_runtime(runner)

    if state.container is None or not state.container.get("State", {}).get("Running", False):
        raise RuntimePolicyError(f"{CANONICAL_CONTAINER} is not running")
    wait_for_health()
    return state


def print_status(state: RuntimeState) -> None:
    print(f"PASS GROBID image: {CANONICAL_IMAGE} ({state.image['Id']})")
    if state.container is None:
        print(f"PASS GROBID container: absent; ensure will create {CANONICAL_CONTAINER}")
        return
    running = state.container.get("State", {}).get("Running", False)
    print(
        f"PASS GROBID container: {CANONICAL_CONTAINER} "
        f"({'running' if running else 'stopped'}) at http://{HOST_IP}:{HOST_PORT}"
    )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=["status", "ensure"])
    args = parser.parse_args()
    try:
        state = inspect_runtime() if args.action == "status" else ensure_runtime()
    except RuntimePolicyError as exc:
        print(f"FAIL GROBID runtime: {exc}", file=sys.stderr)
        return 1
    print_status(state)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
