from __future__ import annotations

from pathlib import Path
from typing import Any

from ..profile import repository_root_for
from ..validation import validate_profile_file


def load_profile_and_root(
    profile_path: str | Path,
    repository_root: str | Path | None = None,
) -> tuple[dict[str, Any], Path]:
    profile, errors = validate_profile_file(profile_path)
    if errors:
        raise ValueError("invalid project profile: " + "; ".join(errors))

    root = (
        Path(repository_root).resolve()
        if repository_root
        else repository_root_for(str(profile_path), profile)
    )
    return profile, root
