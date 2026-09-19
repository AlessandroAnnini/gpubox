from __future__ import annotations

from gpubox._cli import main


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
