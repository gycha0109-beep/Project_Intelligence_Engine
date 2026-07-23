from __future__ import annotations

import shutil
from pathlib import Path
from typing import Any

from .paths import asset


_PRESETS = {"bejewely", "buildmap", "journey-connect", "generic-webapp"}


def available_presets() -> list[str]:
    return sorted(_PRESETS)



def initialize_project(repository_root: str | Path, *, preset: str, force: bool = False) -> dict[str, Any]:
    if preset not in _PRESETS:
        raise ValueError(f"unknown preset {preset!r}; choose one of: {', '.join(available_presets())}")
    root = Path(repository_root).resolve()
    if not root.is_dir():
        raise ValueError(f"repository root does not exist: {root}")

    profile_source = asset(f"profiles/examples/{preset}.yml")
    config_source = asset(f"intelligence/examples/{preset}-config.yml")
    mappings = [
        (profile_source, root / ".review" / "project.yml"),
        (config_source, root / ".review" / "intelligence" / "config.yml"),
        (asset("bootstrap/intelligence/approved-rules.yml"), root / ".review" / "intelligence" / "approved-rules.yml"),
        (asset("bootstrap/intelligence/candidate-rules.yml"), root / ".review" / "intelligence" / "candidate-rules.yml"),
        (asset("bootstrap/intelligence/README.md"), root / ".review" / "intelligence" / "README.md"),
    ]
    files: list[dict[str, str]] = []
    for source, target in mappings:
        existed = target.exists()
        if existed and not force:
            action = "skipped"
        else:
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source, target)
            action = "overwritten" if existed else "created"
        files.append({"path": target.relative_to(root).as_posix(), "action": action})
    gitignore = root / ".gitignore"
    existing = gitignore.read_text(encoding="utf-8") if gitignore.exists() else ""
    ignored = {line.strip() for line in existing.splitlines()}
    if ".pie/" not in ignored and ".pie" not in ignored:
        separator = "" if not existing or existing.endswith(("\n", "\r")) else "\n"
        gitignore.write_text(f"{existing}{separator}.pie/\n", encoding="utf-8")
        action = "updated" if existing else "created"
    else:
        action = "unchanged"
    files.append({"path": ".gitignore", "action": action})
    return {"repository_root": str(root), "preset": preset, "files": files}
