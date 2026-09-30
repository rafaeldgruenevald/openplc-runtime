#!/usr/bin/env python3

"""Create an asyncua server-ready NodeSet copy."""

from __future__ import annotations

import argparse
from pathlib import Path
import xml.etree.ElementTree as ET


UA_NAMESPACE = (
    "http://opcfoundation.org/UA/"
    "2011/03/UANodeSet.xsd"
)


def parse_args():
    parser = argparse.ArgumentParser()

    parser.add_argument(
        "source",
        type=Path,
    )

    parser.add_argument(
        "output",
        type=Path,
    )

    return parser.parse_args()


def main():
    args = parse_args()

    ET.register_namespace("", UA_NAMESPACE)

    tree = ET.parse(args.source)
    root = tree.getroot()

    design_ids = {
        element.attrib["NodeId"]
        for element in root
        if element.attrib.get("NodeId")
        and element.attrib.get(
            "DesignToolOnly",
            "",
        ).lower() == "true"
    }

    parent_dependencies = []
    external_references = []

    for element in root:
        source_id = element.attrib.get("NodeId")
        source_is_design = source_id in design_ids

        parent_id = element.attrib.get("ParentNodeId")

        if (
            parent_id in design_ids
            and not source_is_design
        ):
            parent_dependencies.append(
                (source_id, parent_id)
            )

        references = element.find(
            f"{{{UA_NAMESPACE}}}References"
        )

        if references is None:
            continue

        for reference in references:
            target = (reference.text or "").strip()

            if (
                target in design_ids
                and not source_is_design
            ):
                external_references.append(
                    (
                        source_id,
                        reference.attrib.get(
                            "ReferenceType"
                        ),
                        target,
                    )
                )

    if parent_dependencies:
        raise RuntimeError(
            "Normal nodes use DesignToolOnly nodes "
            f"as parents: {parent_dependencies}"
        )

    if external_references:
        raise RuntimeError(
            "Normal nodes reference DesignToolOnly "
            f"nodes: {external_references}"
        )

    removed = 0

    for element in list(root):
        node_id = element.attrib.get("NodeId")

        if node_id in design_ids:
            root.remove(element)
            removed += 1

    args.output.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    tree.write(
        args.output,
        encoding="utf-8",
        xml_declaration=True,
    )

    print("Source:", args.source)
    print("Output:", args.output)
    print("Removed DesignToolOnly nodes:", removed)


if __name__ == "__main__":
    main()