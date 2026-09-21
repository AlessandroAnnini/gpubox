from __future__ import annotations

from pathlib import Path

import pytest

from gpubox._cli import main
from gpubox._errors import SshNotReady
from gpubox.testing import FakeCloud


def test_version_flag(capsys) -> None:
    pin = (Path(__file__).resolve().parents[1] / "VERSION").read_text(encoding="utf-8").strip().splitlines()[0].strip()
    with pytest.raises(SystemExit) as exc:
        main(["--version"])
    assert exc.value.code == 0
    assert pin in capsys.readouterr().out


def test_list_fake(capsys) -> None:
    assert main(["list", "-p", "fake", "--gpu", "RTX_4090"]) == 0
    out = capsys.readouterr().out
    assert "101" in out
    assert "0.32" in out


def test_list_rank_fake(capsys) -> None:
    assert main(["list", "-p", "fake", "--rank"]) == 0
    assert "101" in capsys.readouterr().out


def test_rent_fake_always_destroys(capsys) -> None:
    assert main(["rent", "-p", "fake", "--cmd", "echo hi", "--timeout", "5"]) == 0
    assert "ok" in capsys.readouterr().out


def test_status_and_destroy_fake(capsys) -> None:
    assert main(["status", "-p", "fake", "77"]) == 0
    assert "ssh_open=False" in capsys.readouterr().out
    assert main(["destroy", "-p", "fake", "77"]) == 0


def test_rent_returns_1_and_destroys_on_ssh_fail(monkeypatch, capsys) -> None:
    cloud = FakeCloud()

    def boom(*_a, **_k):
        raise SshNotReady("no ssh")

    monkeypatch.setattr("gpubox._cli.connect", lambda *_a, **_k: cloud)
    monkeypatch.setattr("gpubox._cli.wait_until_login", boom)
    assert main(["rent", "-p", "fake", "--timeout", "1"]) == 1
    assert "no ssh" in capsys.readouterr().err
    assert cloud.destroyed is True


def test_list_passes_raw_query(monkeypatch, capsys) -> None:
    seen: dict = {}

    class Cloud(FakeCloud):
        def list_offers(self, query=None):
            seen["raw"] = query.raw if query else None
            return super().list_offers(query)

    monkeypatch.setattr("gpubox._cli.connect", lambda *_a, **_k: Cloud())
    assert main(["list", "-p", "fake", "--raw", "COMMUNITY"]) == 0
    capsys.readouterr()
    assert seen["raw"] == "COMMUNITY"


def test_list_passes_ssh_key_flag(monkeypatch, capsys) -> None:
    seen: dict = {}

    def fake_connect(provider, api_key="", **kwargs):
        seen.update(kwargs)
        return FakeCloud()

    monkeypatch.setattr("gpubox._cli.connect", fake_connect)
    assert main(["list", "-p", "fake", "--ssh-key", "/tmp/k"]) == 0
    capsys.readouterr()
    assert seen["ssh_key"] == "/tmp/k"
