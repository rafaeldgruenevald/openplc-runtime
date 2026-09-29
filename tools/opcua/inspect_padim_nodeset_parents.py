from __future__ import annotations

import xml.etree.ElementTree as ET
from pathlib import Path


NODESET_PATH = Path(
    "models/generated/"
    "Test.PADIMDevice.NodeSet2.xml"
)


def local_name(element) -> str:
    return element.tag.split("}")[-1]


def main() -> None:
    if not NODESET_PATH.is_file():
        raise FileNotFoundError(
            f"Missing NodeSet: {NODESET_PATH}"
        )

    root = ET.parse(
        NODESET_PATH
    ).getroot()

    declared_node_ids = {
        element.attrib["NodeId"]
        for element in root
        if "NodeId" in element.attrib
    }

    broken_parents = []

    for element in root:
        node_id = element.attrib.get(
            "NodeId"
        )

        if node_id is None:
            continue

        parent_node_id = element.attrib.get(
            "ParentNodeId"
        )

        if parent_node_id is None:
            continue

        parent_is_standard = (
            parent_node_id.startswith(
                "i="
            )
            or parent_node_id.startswith(
                "ns=0;"
            )
        )

        parent_is_declared = (
            parent_node_id
            in declared_node_ids
        )

        status = (
            "VALID"
            if (
                parent_is_standard
                or parent_is_declared
            )
            else "MISSING"
        )

        print()
        print(
            "Node:",
            node_id,
        )
        print(
            "  Element:",
            local_name(element),
        )
        print(
            "  ParentNodeId:",
            parent_node_id,
        )
        print(
            "  Parent status:",
            status,
        )

        if status == "MISSING":
            broken_parents.append(
                (
                    node_id,
                    parent_node_id,
                )
            )

    print()
    print(
        "Declared nodes:",
        len(declared_node_ids),
    )
    print(
        "Broken parent references:",
        len(broken_parents),
    )

    for node_id, parent_node_id in (
        broken_parents
    ):
        print(
            "  ",
            node_id,
            "->",
            parent_node_id,
        )

    if not broken_parents:
        print()
        print(
            "PASS: all ParentNodeId "
            "references are resolvable"
        )
        return

    raise SystemExit(
        "FAIL: unresolved ParentNodeId "
        "references exist"
    )


if __name__ == "__main__":
    main()
