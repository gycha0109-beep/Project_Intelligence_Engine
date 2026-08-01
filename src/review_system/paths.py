from __future__ import annotations

from pathlib import Path


def package_root() -> Path:
    return Path(__file__).resolve().parent


def asset(path: str) -> Path:
    target = package_root() / "assets" / path
    if not target.exists():
        raise FileNotFoundError(f"review-system asset not found: {path}")
    return target
