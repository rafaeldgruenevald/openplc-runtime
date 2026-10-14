"""
Safe resolution of the files an uploaded program ships for the OPC UA
semantic model (NodeSet XML and binding JSON).

A path from a configuration file is input data: it must stay inside one
of a few trusted roots, whatever symlinks or '..' it carries.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Iterable, List, Tuple

GENERATED_DIR_ENV = "OPENPLC_GENERATED_DIR"

# Largest model file accepted, so a hostile upload cannot exhaust memory.
MAX_MODEL_FILE_BYTES = 32 * 1024 * 1024


def generated_root() -> Path:
    """Directory the uploaded program is extracted to (core/generated)."""
    configured = os.getenv(GENERATED_DIR_ENV, "").strip()

    if configured:
        return Path(configured).resolve()

    # <runtime>/core/src/drivers/plugins/python/opcua/model_paths.py
    return Path(__file__).resolve().parents[5] / "generated"


def resolve_model_file(
    raw_path: str,
    roots: Iterable[Path],
    suffixes: Tuple[str, ...],
) -> Path:
    """
    Resolve one model file path against the trusted roots.

    A relative path is taken relative to the generated directory. The
    resolved file must be below one of the roots, exist, be a regular
    file with an allowed suffix and not exceed MAX_MODEL_FILE_BYTES.
    """
    if not raw_path or not raw_path.strip():
        raise ValueError("Model file path cannot be empty")

    candidate = Path(raw_path).expanduser()

    if not candidate.is_absolute():
        candidate = generated_root() / candidate

    resolved = candidate.resolve()

    trusted: List[Path] = [Path(root).resolve() for root in roots]

    if not any(_is_inside(resolved, root) for root in trusted):
        raise ValueError(
            f"Model file path is outside the allowed directories: {resolved}"
        )

    if not resolved.exists():
        raise FileNotFoundError(f"Model file does not exist: {resolved}")

    if not resolved.is_file():
        raise ValueError(f"Model file path is not a regular file: {resolved}")

    if resolved.suffix.lower() not in suffixes:
        raise ValueError(
            f"Model file must have one of the extensions {suffixes}: {resolved}"
        )

    if resolved.stat().st_size > MAX_MODEL_FILE_BYTES:
        raise ValueError(
            f"Model file is larger than {MAX_MODEL_FILE_BYTES} bytes: {resolved}"
        )

    return resolved


def _is_inside(path: Path, root: Path) -> bool:
    try:
        path.relative_to(root)
    except ValueError:
        return False

    return True
