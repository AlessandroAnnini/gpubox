from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import pytest

from gpubox import AuthError, ProviderError, SshNotReady, wait_until_login
from gpubox._models import LaunchSpec
from gpubox._ssh import run_scp, run_ssh
from gpubox.testing import FakeCloud


def test_run_ssh_publickey_is_auth_error(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    key = tmp_path / "id_ed25519"
    key.write_text("dummy")

    def fake_run(*_a, **_k):
        return SimpleNamespace(
            returncode=255,
            stderr="Permission denied (publickey,password).",
            stdout="",
        )

    monkeypatch.setattr("gpubox._ssh.subprocess.run", fake_run)
    with pytest.raises(AuthError, match="already running"):
        run_ssh(key, "host.example", 22, "root", "true", provider="runpod")


def test_run_scp_other_failure_is_provider_error(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    key = tmp_path / "id_ed25519"
    key.write_text("dummy")

    def fake_run(*_a, **_k):
        return SimpleNamespace(returncode=1, stderr="connection timed out", stdout="")

    monkeypatch.setattr("gpubox._ssh.subprocess.run", fake_run)
    with pytest.raises(ProviderError, match="timed out"):
        run_scp(key, "host.example", 22, str(tmp_path / "a"), "root@host.example:/a", provider="runpod")


def test_wait_until_login_returns_instance() -> None:
    cloud = FakeCloud()
    box = cloud.create("101", LaunchSpec(image="ubuntu:22.04", label="gpubox"))
    inst = wait_until_login(cloud, box, timeout=2, interval=0.01)
    assert inst.id == box
    assert inst.ssh_open
    assert "true" in cloud.commands


def test_wait_until_login_auth_error_is_immediate() -> None:
    cloud = FakeCloud()
    box = cloud.create("101", LaunchSpec(image="ubuntu:22.04", label="gpubox"))

    def denied(_id: str, _cmd: str) -> str:
        raise AuthError("publickey")

    cloud.run = denied  # type: ignore[method-assign]
    with pytest.raises(AuthError, match="publickey"):
        wait_until_login(cloud, box, timeout=2, interval=0.01)


def test_wait_until_login_timeout(monkeypatch: pytest.MonkeyPatch) -> None:
    cloud = FakeCloud()
    box = cloud.create("101", LaunchSpec(image="ubuntu:22.04", label="gpubox"))

    def never(_id: str, _cmd: str) -> str:
        raise ProviderError("not ready", provider="fake")

    cloud.run = never  # type: ignore[method-assign]
    monkeypatch.setattr("gpubox._ssh.time.sleep", lambda _s: None)
    ticks = iter([0.0, 0.0, 10.0])
    monkeypatch.setattr("gpubox._ssh.time.monotonic", lambda: next(ticks, 10.0))
    with pytest.raises(SshNotReady, match="login"):
        wait_until_login(cloud, box, timeout=5, interval=0.01)
