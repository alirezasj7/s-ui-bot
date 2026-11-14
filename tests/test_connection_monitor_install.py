"""Offline automatic-core setup: integrity, configuration preservation and repair."""

from __future__ import annotations

import contextlib
import hashlib
import io
import os
import subprocess
import tempfile
import unittest
import zipfile
from pathlib import Path
from typing import Iterator
from unittest.mock import Mock, patch

import httpx

from app.cli.connection_monitor_install import main
from app.config import Settings
from app.services import connection_monitor_distribution as distribution
from app.services import connection_monitor_install as installer
from app.services.connection_monitor_distribution import CoreInstallError, XrayDistribution
from app.services.connection_monitor_install_update import setup_updated_monitor_core


HTTP_CLIENT = httpx.Client
ROOT = Path(__file__).resolve().parents[1]
BINARY = b"synthetic test executable; never executed"


def release_archive(*, symlink: bool = False, extra: bool = False) -> bytes:
    output = io.BytesIO()
    with zipfile.ZipFile(output, "w") as archive:
        entry = zipfile.ZipInfo("xray")
        entry.external_attr = (0o120777 if symlink else 0o100755) << 16
        archive.writestr(entry, BINARY)
        archive.writestr("LICENSE", "Synthetic license notice")
        archive.writestr("README.md", "Synthetic source attribution")
        if extra:
            archive.writestr("../../outside", "must not be extracted")
    return output.getvalue()


class AutomaticCoreTests(unittest.TestCase):
    def setUp(self) -> None:
        temporary = tempfile.TemporaryDirectory(prefix="pgclock-core-install-")
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name).resolve()
        self.env = self.root / ".env"
        self.original = '# keep this comment\nWEB_SECRET="synthetic-original"\nPG_API_KEY="synthetic-key"\nCUSTOM_SETTING="keep me"\n'
        self.env.write_text(self.original)
        self.env.chmod(0o600)
        self.archive = release_archive()
        self.requests: list[str] = []
        self.asset = XrayDistribution("amd64", "Xray-linux-64.zip", hashlib.sha256(self.archive).hexdigest(), hashlib.sha256(BINARY).hexdigest())
        for patcher in (
            patch.dict(os.environ, {key: value for key, value in os.environ.items() if key not in installer.CORE_KEYS}, clear=True),
            patch.object(installer, "select_distribution", return_value=self.asset),
            patch.object(distribution.httpx, "Client", side_effect=lambda **kwargs: HTTP_CLIENT(transport=httpx.MockTransport(self.respond), **kwargs)),
        ):
            patcher.start()
            self.addCleanup(patcher.stop)

    def respond(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(str(request.url))
        return httpx.Response(200, content=self.archive)

    def binary(self) -> Path:
        return self.root.joinpath(*installer.MANAGED_DIRECTORY, self.asset.directory_name, "xray")

    def test_installs_verified_core_and_notices_and_preserves_all_other_settings(self) -> None:
        self.assertEqual(installer.ensure_monitor_core(self.root), "managed")
        self.assertEqual(self.binary().read_bytes(), BINARY)
        self.assertEqual(self.binary().stat().st_mode & 0o777, 0o755)
        text = self.env.read_text()
        self.assertTrue(text.startswith(self.original))
        self.assertEqual(self.env.stat().st_mode & 0o777, 0o600)
        self.assertEqual(installer._configured_core(text), {installer.PATH_KEY: str(self.binary()), installer.HASH_KEY: self.asset.binary_sha256})
        self.assertEqual((self.binary().parent / "LICENSE").read_text(), "Synthetic license notice")
        self.assertEqual((self.binary().parent / "README.md").read_text(), "Synthetic source attribution")
        self.assertEqual(self.requests, [f"{distribution.RELEASE_URL}/{self.asset.archive_name}"])
        self.assertFalse(list(self.binary().parent.parent.glob(".download-*")))

    def test_repeated_setup_reuses_verified_binary_without_download_or_env_rewrite(self) -> None:
        installer.ensure_monitor_core(self.root)
        before = self.env.stat().st_mtime_ns
        installer.ensure_monitor_core(self.root)
        self.assertEqual(len(self.requests), 1)
        self.assertEqual(self.env.stat().st_mtime_ns, before)

    def test_path_with_spaces_and_quotes_loads_through_the_application_settings(self) -> None:
        root = self.root / "owner's bot"
        root.mkdir()
        env = root / ".env"
        env.write_text(self.original)
        installer.ensure_monitor_core(root)
        settings = Settings(_env_file=env)
        self.assertEqual(settings.connection_monitor_xray_path, str(root.joinpath(*installer.MANAGED_DIRECTORY, self.asset.directory_name, "xray")))
        self.assertEqual(settings.connection_monitor_xray_sha256, self.asset.binary_sha256)

    def test_modified_managed_binary_is_restored_from_the_pinned_archive(self) -> None:
        installer.ensure_monitor_core(self.root)
        self.binary().write_bytes(b"tampered")
        installer.ensure_monitor_core(self.root)
        self.assertEqual(self.binary().read_bytes(), BINARY)
        self.assertEqual(len(self.requests), 2)

    def test_bad_archive_checksum_keeps_configuration_and_existing_core(self) -> None:
        installer.ensure_monitor_core(self.root)
        text = self.env.read_text()
        self.binary().write_bytes(b"old core")
        self.archive = b"invalid downloaded payload"
        with self.assertRaisesRegex(CoreInstallError, "archive_checksum"):
            installer.ensure_monitor_core(self.root)
        self.assertEqual(self.binary().read_bytes(), b"old core")
        self.assertEqual(self.env.read_text(), text)
        self.assertFalse(list(self.binary().parent.parent.glob(".download-*")))

    def test_executable_checksum_is_checked_independently_of_the_archive(self) -> None:
        bad = XrayDistribution("amd64", self.asset.archive_name, self.asset.archive_sha256, "a" * 64)
        with patch.object(installer, "select_distribution", return_value=bad):
            with self.assertRaisesRegex(ValueError, "core_checksum"):
                installer.ensure_monitor_core(self.root)
        self.assertEqual(self.env.read_text(), self.original)
        self.assertFalse(self.binary().exists())

    def test_manual_verified_core_is_kept_even_on_an_unsupported_platform(self) -> None:
        custom = self.root / "custom-xray"
        custom.write_bytes(BINARY)
        custom.chmod(0o755)
        text = self.original + f'{installer.PATH_KEY}="{custom}"\n{installer.HASH_KEY}="{self.asset.binary_sha256}"\n'
        self.env.write_text(text)
        with patch.object(installer, "select_distribution", side_effect=CoreInstallError("unsupported_platform")):
            self.assertEqual(installer.ensure_monitor_core(self.root), "custom")
        self.assertEqual(self.env.read_text(), text)
        self.assertFalse(self.requests)

    def test_invalid_or_partial_manual_configuration_is_not_overwritten(self) -> None:
        for value in ('/missing/xray', ''):
            with self.subTest(value=value):
                text = self.original + f'{installer.PATH_KEY}="{value}"\n{installer.HASH_KEY}="bad"\n'
                self.env.write_text(text)
                with self.assertRaisesRegex(CoreInstallError, "custom_configuration"):
                    installer.ensure_monitor_core(self.root)
                self.assertEqual(self.env.read_text(), text)
        self.assertFalse(self.requests)

    def test_failed_download_does_not_expose_provider_text_or_secrets(self) -> None:
        with patch.object(distribution, "download_archive", side_effect=httpx.ReadTimeout("sensitive-provider-body")):
            output = io.StringIO()
            with contextlib.redirect_stderr(output):
                self.assertEqual(main(["--root", str(self.root)]), 1)
        self.assertNotIn("sensitive-provider-body", output.getvalue())
        self.assertNotIn("synthetic-key", output.getvalue())
        self.assertEqual(self.env.read_text(), self.original)

    def test_unrelated_settings_changed_during_download_are_preserved(self) -> None:
        def downloading(client: httpx.Client, asset: XrayDistribution, path: Path) -> None:
            self.env.write_text(self.original.replace("synthetic-original", "synthetic-updated"))
            path.write_bytes(self.archive)
        with patch.object(distribution, "download_archive", side_effect=downloading):
            installer.ensure_monitor_core(self.root)
        self.assertIn('WEB_SECRET="synthetic-updated"', self.env.read_text())

    def test_changed_core_settings_during_download_are_not_overwritten(self) -> None:
        changed = self.original + f'{installer.PATH_KEY}="/custom/new"\n'
        def downloading(client: httpx.Client, asset: XrayDistribution, path: Path) -> None:
            self.env.write_text(changed)
            path.write_bytes(self.archive)
        with patch.object(distribution, "download_archive", side_effect=downloading):
            with self.assertRaisesRegex(CoreInstallError, "configuration_changed"):
                installer.ensure_monitor_core(self.root)
        self.assertEqual(self.env.read_text(), changed)

    def test_symlinked_install_directory_and_env_are_refused(self) -> None:
        outside = self.root / "outside"
        outside.mkdir()
        (self.root / "data").symlink_to(outside, target_is_directory=True)
        with self.assertRaisesRegex(CoreInstallError, "directory_permissions"):
            installer.ensure_monitor_core(self.root)
        self.assertFalse(list(outside.iterdir()))
        (self.root / "data").unlink()
        self.env.rename(self.root / "config")
        self.env.symlink_to(self.root / "config")
        with self.assertRaises(OSError):
            installer.ensure_monitor_core(self.root)

    def test_symlinked_executable_in_archive_is_rejected(self) -> None:
        self.archive = release_archive(symlink=True)
        self.asset = XrayDistribution("amd64", self.asset.archive_name, hashlib.sha256(self.archive).hexdigest(), self.asset.binary_sha256)
        with patch.object(installer, "select_distribution", return_value=self.asset):
            with self.assertRaisesRegex(CoreInstallError, "archive_contents"):
                installer.ensure_monitor_core(self.root)
        self.assertEqual(self.env.read_text(), self.original)

    def test_unlisted_archive_members_are_never_extracted(self) -> None:
        self.archive = release_archive(extra=True)
        self.asset = XrayDistribution("amd64", self.asset.archive_name, hashlib.sha256(self.archive).hexdigest(), self.asset.binary_sha256)
        with patch.object(installer, "select_distribution", return_value=self.asset):
            installer.ensure_monitor_core(self.root)
        self.assertFalse(self.root.joinpath(*installer.MANAGED_DIRECTORY, "outside").exists())
        self.assertEqual({item.name for item in self.binary().parent.iterdir()}, {"xray", "LICENSE", "README.md"})

    def test_download_size_limit_keeps_env_unchanged(self) -> None:
        with patch.object(distribution, "MAX_ARCHIVE_BYTES", 5):
            with self.assertRaisesRegex(CoreInstallError, "download_limit"):
                installer.ensure_monitor_core(self.root)
        self.assertEqual(self.env.read_text(), self.original)

    def test_slow_stream_is_stopped_before_waiting_for_another_buffered_chunk(self) -> None:
        clock = [0.0]
        class SlowStream(httpx.SyncByteStream):
            def __iter__(self) -> Iterator[bytes]:
                clock[0] = distribution.DOWNLOAD_SECONDS + 1
                yield b"x"
                raise AssertionError("must stop before reading another slow chunk")
        with HTTP_CLIENT(transport=httpx.MockTransport(lambda request: httpx.Response(200, stream=SlowStream()))) as client:
            with patch.object(distribution.time, "monotonic", side_effect=lambda: clock[0]):
                with self.assertRaisesRegex(CoreInstallError, "download_limit"):
                    distribution.download_archive(client, self.asset, self.root / "slow.zip")

    def test_environment_override_is_validated_without_editing_dotenv(self) -> None:
        with patch.dict(os.environ, {installer.PATH_KEY: "", installer.HASH_KEY: ""}):
            with self.assertRaisesRegex(CoreInstallError, "custom_configuration"):
                installer.ensure_monitor_core(self.root)
        self.assertEqual(self.env.read_text(), self.original)

    def test_another_installer_holds_the_lock_without_partial_configuration(self) -> None:
        directory = installer._install_directory(self.root)
        with installer._install_lock(directory):
            with self.assertRaisesRegex(CoreInstallError, "install_busy"):
                installer.ensure_monitor_core(self.root)
        self.assertEqual(self.env.read_text(), self.original)
        self.assertFalse(self.requests)

    def test_env_replace_failure_preserves_the_old_file_and_removes_the_temporary_file(self) -> None:
        replace = os.replace
        def fail_env(source: Path, destination: Path) -> None:
            if destination == self.env:
                raise OSError("synthetic write failure")
            replace(source, destination)
        with patch.object(installer.os, "replace", side_effect=fail_env):
            with self.assertRaises(OSError):
                installer.ensure_monitor_core(self.root)
        self.assertEqual(self.env.read_text(), self.original)
        self.assertFalse(list(self.root.glob(".env.xray-*")))

    def test_world_writable_install_directory_is_refused(self) -> None:
        data = self.root / "data"
        data.mkdir()
        data.chmod(0o777)
        with self.assertRaisesRegex(CoreInstallError, "directory_permissions"):
            installer.ensure_monitor_core(self.root)
        self.assertFalse(self.requests)


class DistributionPlatformTests(unittest.TestCase):
    def test_supported_architectures_select_the_matching_pinned_asset(self) -> None:
        for machine, arch in (("x86_64", "amd64"), ("amd64", "amd64"), ("aarch64", "arm64"), ("arm64", "arm64")):
            with self.subTest(machine=machine), patch.object(distribution.platform, "system", return_value="Linux"), \
                 patch.object(distribution.platform, "machine", return_value=machine):
                self.assertEqual(distribution.select_distribution(), distribution.DISTRIBUTIONS[arch])
        with patch.object(distribution.platform, "system", return_value="Darwin"):
            with self.assertRaisesRegex(CoreInstallError, "unsupported_platform"):
                distribution.select_distribution()

    def test_update_hook_uses_a_fresh_cli_and_does_not_log_command_output(self) -> None:
        for status in (0, 1):
            runner = Mock(return_value=(status, "secret command output"))
            log = Mock()
            setup_updated_monitor_core(Path("/install"), runner=runner, log=log)
            self.assertIn("app.cli.connection_monitor_install", runner.call_args.args[0])
            self.assertEqual(runner.call_args.kwargs, {"cwd": Path("/install"), "timeout": 120})
            self.assertNotIn("secret command output", str(log.call_args_list))

    def test_script_xray_action_invokes_setup_for_its_own_install(self) -> None:
        with tempfile.TemporaryDirectory(prefix="pgclock-xray-cli-") as folder:
            root = Path(folder).resolve()
            (root / "pgclock.sh").write_bytes((ROOT / "pgclock.sh").read_bytes())
            (root / ".env").write_text("WEB_SECRET=synthetic\n")
            binary = root / ".venv/bin/python"
            binary.parent.mkdir(parents=True)
            binary.write_text('#!/bin/sh\nprintf "%s\\n" "$@" > "$0.args"\n')
            binary.chmod(0o755)
            systemctl = root / "systemctl"
            systemctl.write_text("#!/bin/sh\nexit 1\n")
            systemctl.chmod(0o755)
            result = subprocess.run(["bash", "pgclock.sh", "xray"], cwd=root, env={**os.environ, "PATH": f"{root}:{os.environ['PATH']}"}, capture_output=True, timeout=10)
            self.assertEqual(result.returncode, 0, result.stderr.decode())
            self.assertEqual(binary.with_suffix(".args").read_text().splitlines(), ["-m", "app.cli.connection_monitor_install", "--root", str(root)])
