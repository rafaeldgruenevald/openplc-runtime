"""
Optional OPC UA NodeSet loading.

This module imports UANodeSet XML files after asyncua.Server.init()
and before OpenPLC creates its normal PLC-backed address space.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Tuple
from xml.etree import ElementTree

try:
    from .model_paths import generated_root, resolve_model_file
    from .opcua_logging import log_debug, log_info
except ImportError:
    from model_paths import generated_root, resolve_model_file
    from opcua_logging import log_debug, log_info


ALLOWED_MODEL_ROOT = Path("/opt/openplc/models").resolve()

NODESET_NS = "{http://opcfoundation.org/UA/2011/03/UANodeSet.xsd}"

# asyncua cannot import an object that has no ParentNodeId and is a
# FunctionalGroupType instance nobody references (the DI "Configuration",
# "Identification"... groups): the whole import fails with
# BadParentNodeIdInvalid. They are skipped here, with a log line, and the
# NodeSet file itself stays untouched.
FUNCTIONAL_GROUP_TYPE_NAME = "FunctionalGroupType"


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


def find_unimportable_objects(root: ElementTree.Element) -> List[str]:
    """
    NodeIds of the standalone FunctionalGroupType instances asyncua cannot
    import (see FUNCTIONAL_GROUP_TYPE_NAME).
    """
    nodes = [element for element in root if element.get("NodeId")]

    group_types = {
        element.get("NodeId")
        for element in nodes
        if element.tag == f"{NODESET_NS}UAObjectType"
        and (element.get("BrowseName") or "").split(":")[-1]
        == FUNCTIONAL_GROUP_TYPE_NAME
    }

    if not group_types:
        return []

    referenced = {
        reference.text
        for element in nodes
        for reference in element.iter(f"{NODESET_NS}Reference")
    }

    skipped: List[str] = []

    for element in nodes:
        if element.tag != f"{NODESET_NS}UAObject" or element.get("ParentNodeId"):
            continue

        node_id = element.get("NodeId", "")

        has_group_type = any(
            reference.get("ReferenceType") == "HasTypeDefinition"
            and reference.text in group_types
            for reference in element.iter(f"{NODESET_NS}Reference")
        )

        if has_group_type and node_id not in referenced:
            skipped.append(node_id)

    return skipped


def prepare_nodeset(path: Path) -> Tuple[Optional[str], List[str]]:
    """
    Returns (xml_text, skipped_node_ids). xml_text is None when nothing
    has to be skipped and the file can be imported as it is.
    """
    root = ElementTree.parse(path).getroot()

    skipped = find_unimportable_objects(root)

    if not skipped:
        return None, []

    for element in list(root):
        if element.get("NodeId") in skipped:
            root.remove(element)

    ElementTree.register_namespace("", NODESET_NS[1:-1])

    return ElementTree.tostring(root, encoding="unicode"), skipped


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

        xml_text, skipped = prepare_nodeset(path)

        if skipped:
            log_info(
                f"Skipping {len(skipped)} standalone group object(s) of "
                f"{path.name} that asyncua cannot import: {', '.join(skipped)}"
            )
            imported_nodes = await server.import_xml(
                xmlstring=xml_text,
                strict_mode=True,
                auto_load_definitions=True,
            )
        else:
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
