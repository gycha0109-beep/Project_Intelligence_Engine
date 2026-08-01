from __future__ import annotations

from pathlib import Path


def package_root() -> Path:
    return Path(__file__).resolve().parent


def asset(path: str, *parts: str) -> Path:
    relative = Path(path).joinpath(*parts)
    target = package_root() / "assets" / relative
    if not target.exists():
        raise FileNotFoundError(f"review-system asset not found: {relative.as_posix()}")
    return target
