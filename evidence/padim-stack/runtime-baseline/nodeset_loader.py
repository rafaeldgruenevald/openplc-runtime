"""
Optional OPC UA NodeSet loading.

This module imports UANodeSet XML files after asyncua.Server.init()
and before OpenPLC creates its normal PLC-backed address space.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, Iterable, List

try:
    from .opcua_logging import log_debug, log_info
except ImportError:
    from opcua_logging import log_debug, log_info


ALLOWED_MODEL_ROOT = Path("/opt/openplc/models").resolve()


def validate_nodeset_path(raw_path: str) -> Path:
    """
    Resolve and validate one NodeSet XML path.

    The resolved file must:
    - Be located below /opt/openplc/models
    - Exist
    - Be a regular file
    - Have an .xml extension
    """

    if not raw_path or not raw_path.strip():
        raise ValueError("NodeSet path cannot be empty")

    path = Path(raw_path).expanduser().resolve()

    try:
        path.relative_to(ALLOWED_MODEL_ROOT)
    except ValueError as exc:
        raise ValueError(
            "NodeSet path is outside the allowed model directory: "
            f"{path}"
        ) from exc

    if not path.exists():
        raise FileNotFoundError(
            f"NodeSet file does not exist: {path}"
        )

    if not path.is_file():
        raise ValueError(
            f"NodeSet path is not a regular file: {path}"
        )

    if path.suffix.lower() != ".xml":
        raise ValueError(
            f"NodeSet file must have an .xml extension: {path}"
        )

    return path


async def import_nodesets(
    server,
    raw_paths: Iterable[str],
) -> List[Dict[str, Any]]:
    """
    Import NodeSet XML files in the supplied order.

    Dependency NodeSets must be listed before models that reference
    them.
    """

    results: List[Dict[str, Any]] = []

    for raw_path in raw_paths:
        path = validate_nodeset_path(raw_path)

        log_info(f"Importing OPC UA NodeSet: {path}")

        imported_nodes = await server.import_xml(
            path=str(path),
            strict_mode=True,
            auto_load_definitions=True,
        )

        imported_count = len(imported_nodes or [])

        result = {
            "path": str(path),
            "status": "success",
            "nodes_imported": imported_count,
        }

        results.append(result)

        log_info(
            "Imported OPC UA NodeSet "
            f"{path.name}: {imported_count} nodes"
        )

    log_debug(
        f"Imported {len(results)} OPC UA NodeSet file(s)"
    )

    return results
