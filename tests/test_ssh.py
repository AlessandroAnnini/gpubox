from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import pytest

from gpubox import AuthError, ProviderError
from gpubox._ssh import run_scp, run_ssh


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
