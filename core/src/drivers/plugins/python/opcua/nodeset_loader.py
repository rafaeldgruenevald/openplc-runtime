"""
Optional OPC UA NodeSet loading.

This module imports UANodeSet XML files after asyncua.Server.init()
and before OpenPLC creates its normal PLC-backed address space.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, Iterable, List

try:
    from .model_paths import generated_root, resolve_model_file
    from .opcua_logging import log_debug, log_info
except ImportError:
    from model_paths import generated_root, resolve_model_file
    from opcua_logging import log_debug, log_info


ALLOWED_MODEL_ROOT = Path("/opt/openplc/models").resolve()


def validate_nodeset_path(raw_path: str) -> Path:
    """
    Resolve and validate one NodeSet XML path.

    A relative path is taken relative to the extracted program
    (core/generated). The resolved file must be below that directory or
    below /opt/openplc/models, exist, be a regular .xml file and be of
    a bounded size.
    """

    return resolve_model_file(
        raw_path,
        roots=(generated_root(), ALLOWED_MODEL_ROOT),
        suffixes=(".xml",),
    )


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
