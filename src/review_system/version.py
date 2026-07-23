from __future__ import annotations

from importlib.metadata import PackageNotFoundError, version as package_version

from .paths import asset


def get_version() -> str:
    try:
        return asset("VERSION").read_text(encoding="utf-8").strip()
    except FileNotFoundError:
        try:
            return package_version("project-intelligence-engine")
        except PackageNotFoundError:
            return "0+unknown"
