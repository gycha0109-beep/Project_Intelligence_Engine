from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path
from typing import Any

import yaml


def load_data(path: str | Path) -> Any:
    source = Path(path)
    text = source.read_text(encoding="utf-8")
    suffix = source.suffix.lower()
    if suffix == ".json":
        return json.loads(text)
    if suffix in {".yml", ".yaml"}:
        return yaml.safe_load(text)
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        return yaml.safe_load(text)


def dump_json(path: str | Path, data: Any) -> None:
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def dump_yaml(path: str | Path, data: Any) -> None:
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(yaml.safe_dump(data, sort_keys=False, allow_unicode=True), encoding="utf-8")


def dump_yaml_pair_atomic(
    first_path: str | Path,
    first_data: Any,
    second_path: str | Path,
    second_data: Any,
) -> None:
    targets = [Path(first_path), Path(second_path)]
    payloads = [
        yaml.safe_dump(first_data, sort_keys=False, allow_unicode=True),
        yaml.safe_dump(second_data, sort_keys=False, allow_unicode=True),
    ]
    for target in targets:
        target.parent.mkdir(parents=True, exist_ok=True)
    lock_path = targets[0].with_name(targets[0].name + ".approval.lock")
    try:
        lock_fd = os.open(lock_path, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
    except FileExistsError as exc:
        raise RuntimeError(f"approval files are locked by another process: {lock_path}") from exc
    os.close(lock_fd)
    originals = [target.read_bytes() if target.exists() else None for target in targets]
    temp_paths: list[Path] = []
    replaced: list[int] = []
    try:
        for target, payload in zip(targets, payloads):
            with tempfile.NamedTemporaryFile(
                mode="w",
                encoding="utf-8",
                dir=target.parent,
                prefix=target.name + ".",
                suffix=".tmp",
                delete=False,
            ) as handle:
                handle.write(payload)
                handle.flush()
                os.fsync(handle.fileno())
                temp_paths.append(Path(handle.name))
        for index, (temporary, target) in enumerate(zip(temp_paths, targets)):
            temporary.replace(target)
            replaced.append(index)
    except Exception:
        for index in replaced:
            target = targets[index]
            original = originals[index]
            if original is None:
                target.unlink(missing_ok=True)
            else:
                target.write_bytes(original)
        raise
    finally:
        for temporary in temp_paths:
            temporary.unlink(missing_ok=True)
        lock_path.unlink(missing_ok=True)
