from __future__ import annotations

from importlib.metadata import version
from pathlib import Path


def test_package_version_matches_version_file() -> None:
    pin = (Path(__file__).resolve().parents[1] / "VERSION").read_text(encoding="utf-8")
    assert version("gpubox") == pin.strip().splitlines()[0].strip()
