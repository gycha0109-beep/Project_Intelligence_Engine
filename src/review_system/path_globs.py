from __future__ import annotations


def expand_trailing_recursive_glob(pattern: str) -> tuple[str, ...]:
    """Return version-stable pathlib glob patterns for a trailing ``/**``.

    Python 3.11 treats a pattern ending in ``/**`` as matching directories,
    while newer versions also yield descendant files. Appending ``/*`` keeps
    the recursive segment and makes descendant-file collection explicit on
    every supported Python version.
    """
    if pattern.endswith("/**"):
        return pattern, f"{pattern}/*"
    return (pattern,)
