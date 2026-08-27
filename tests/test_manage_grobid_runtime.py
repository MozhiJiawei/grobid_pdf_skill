from __future__ import annotations

import importlib.util
import subprocess
import sys
import unittest
from pathlib import Path
from unittest.mock import Mock, patch


MODULE_PATH = Path(__file__).resolve().parents[1] / "scripts" / "manage_grobid_runtime.py"
SPEC = importlib.util.spec_from_file_location("manage_grobid_runtime", MODULE_PATH)
assert SPEC and SPEC.loader
runtime = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = runtime
SPEC.loader.exec_module(runtime)


IMAGE_ID = "sha256:canonical"


def canonical_image() -> dict:
    return {"Id": IMAGE_ID, "RepoTags": [runtime.CANONICAL_IMAGE]}


def canonical_container(*, running: bool = True) -> dict:
    return {
        "Id": "container-id",
        "Name": f"/{runtime.CANONICAL_CONTAINER}",
        "Image": IMAGE_ID,
        "Config": {"Image": runtime.CANONICAL_IMAGE},
        "HostConfig": {
            "PortBindings": {
                runtime.CONTAINER_PORT: [
                    {"HostIp": runtime.HOST_IP, "HostPort": runtime.HOST_PORT}
                ]
            },
            "RestartPolicy": {"Name": "unless-stopped"},
        },
        "State": {"Running": running},
    }


class ImagePolicyTests(unittest.TestCase):
    def test_zero_images_fails(self) -> None:
        with self.assertRaisesRegex(runtime.RuntimePolicyError, "no GROBID image"):
            runtime.validate_unique_image([])

    def test_one_canonical_image_passes(self) -> None:
        self.assertEqual(runtime.validate_unique_image([canonical_image()])["Id"], IMAGE_ID)

    def test_multiple_images_fail(self) -> None:
        with self.assertRaisesRegex(runtime.RuntimePolicyError, "found 2"):
            runtime.validate_unique_image(
                [canonical_image(), {"Id": "sha256:extra", "RepoTags": ["grobid/grobid:latest"]}]
            )


class ContainerPolicyTests(unittest.TestCase):
    def test_zero_containers_is_allowed(self) -> None:
        self.assertIsNone(runtime.validate_container([], IMAGE_ID))

    def test_one_canonical_container_passes(self) -> None:
        container = canonical_container()
        self.assertIs(runtime.validate_container([container], IMAGE_ID), container)

    def test_multiple_containers_fail(self) -> None:
        extra = canonical_container()
        extra["Name"] = "/extra-grobid"
        with self.assertRaisesRegex(runtime.RuntimePolicyError, "found 2"):
            runtime.validate_container([canonical_container(), extra], IMAGE_ID)

    def test_configuration_drift_fails(self) -> None:
        container = canonical_container()
        container["HostConfig"]["PortBindings"][runtime.CONTAINER_PORT][0]["HostPort"] = "18075"
        with self.assertRaisesRegex(runtime.RuntimePolicyError, "configuration drift"):
            runtime.validate_container([container], IMAGE_ID)


class EnsureRuntimeTests(unittest.TestCase):
    @patch.object(runtime, "wait_for_health")
    @patch.object(runtime, "inspect_runtime")
    def test_stopped_container_is_started(self, inspect_runtime: Mock, wait_for_health: Mock) -> None:
        stopped = runtime.RuntimeState(canonical_image(), canonical_container(running=False))
        running = runtime.RuntimeState(canonical_image(), canonical_container(running=True))
        inspect_runtime.side_effect = [stopped, running]
        runner = Mock(return_value=subprocess.CompletedProcess([], 0, "", ""))

        result = runtime.ensure_runtime(runner)

        runner.assert_called_once_with(["container", "start", runtime.CANONICAL_CONTAINER], True)
        wait_for_health.assert_called_once_with()
        self.assertTrue(result.container["State"]["Running"])

    @patch.object(runtime, "inspect_runtime")
    def test_concurrent_create_conflict_reuses_winner(self, inspect_runtime: Mock) -> None:
        inspect_runtime.return_value = runtime.RuntimeState(canonical_image(), canonical_container())
        runner = Mock(
            return_value=subprocess.CompletedProcess([], 125, "", "name is already in use")
        )

        runtime.create_container(runner)

        inspect_runtime.assert_called_once_with(runner)

    @patch.object(runtime.time, "sleep")
    @patch.object(runtime.time, "monotonic", side_effect=[0.0, 0.0])
    @patch.object(runtime.urllib.request, "urlopen", side_effect=OSError("connection refused"))
    def test_health_timeout_fails(self, _urlopen: Mock, _monotonic: Mock, sleep: Mock) -> None:
        with self.assertRaisesRegex(runtime.RuntimePolicyError, "did not become healthy"):
            runtime.wait_for_health(timeout=0, interval=0)
        sleep.assert_not_called()


if __name__ == "__main__":
    unittest.main()
