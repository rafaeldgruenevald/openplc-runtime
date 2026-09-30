from __future__ import annotations

import asyncio
import hashlib
import os
import tempfile
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Iterable

from asyncua import Server, ua
from asyncua.common.xmlexporter import XmlExporter


PROJECT_NAMESPACE_URI = (
    "urn:openplc:test:"
    "xmlexporter-structured-roundtrip"
)

PRESSURE_NODE_ID = "Test.Pressure"
ENGINEERING_UNITS_NODE_ID = (
    "Test.Pressure.EngineeringUnits"
)
EU_RANGE_NODE_ID = (
    "Test.Pressure.EURange"
)

PRESSURE_VALUE = 12.5
PRESSURE_RANGE_LOW = 0.0
PRESSURE_RANGE_HIGH = 16.0

UN_CEFACT_NAMESPACE_URI = (
    "http:"
    + "//www.opcfoundation.org"
    + "/UA/units/un/cefact"
)

BAR_UNIT_ID = 4342098

NODESET_XML_NAMESPACE = (
    "http:"
    + "//opcfoundation.org"
    + "/UA/2011/03/UANodeSet.xsd"
)

OUTPUT_PATH = Path(
    os.environ.get(
        "XML_EXPORTER_TEST_OUTPUT",
        (
            "/tmp/"
            "Test.StructuredValues.NodeSet2.xml"
        ),
    )
)


def calculate_sha256(
    path: Path,
) -> str:
    digest = hashlib.sha256()

    with path.open("rb") as file_handle:
        while True:
            block = file_handle.read(
                1024 * 1024
            )

            if not block:
                break

            digest.update(block)

    return digest.hexdigest()


async def collect_project_nodes(
    root,
    project_namespace_index: int,
) -> list:
    collected = []
    visited = set()

    async def visit(node) -> None:
        node_id_text = (
            node.nodeid.to_string()
        )

        if node_id_text in visited:
            return

        visited.add(
            node_id_text
        )

        if (
            node.nodeid.NamespaceIndex
            == project_namespace_index
        ):
            collected.append(node)

        children = await node.get_children(
            refs=(
                ua.ObjectIds
                .HierarchicalReferences
            ),
        )

        for child in children:
            await visit(child)

    await visit(root)

    collected.sort(
        key=lambda node: (
            node.nodeid.to_string()
        )
    )

    return collected


def validate_exported_xml(
    path: Path,
) -> None:
    if not path.is_file():
        raise RuntimeError(
            "Exported NodeSet does not exist: "
            f"{path}"
        )

    if path.stat().st_size == 0:
        raise RuntimeError(
            "Exported NodeSet is empty"
        )

    root = ET.parse(
        path
    ).getroot()

    expected_root_tag = (
        "{"
        + NODESET_XML_NAMESPACE
        + "}UANodeSet"
    )

    if root.tag != expected_root_tag:
        raise RuntimeError(
            "Unexpected NodeSet root element: "
            f"{root.tag!r}"
        )

    namespace_element = root.find(
        (
            "{"
            + NODESET_XML_NAMESPACE
            + "}NamespaceUris"
        )
    )

    if namespace_element is None:
        raise RuntimeError(
            "Exported NodeSet has no "
            "NamespaceUris element"
        )

    uri_elements = namespace_element.findall(
        (
            "{"
            + NODESET_XML_NAMESPACE
            + "}Uri"
        )
    )

    namespace_uris = [
        element.text
        for element in uri_elements
    ]

    if (
        PROJECT_NAMESPACE_URI
        not in namespace_uris
    ):
        raise RuntimeError(
            "Project namespace URI is missing "
            "from exported NodeSet"
        )

    node_elements = [
        child
        for child in root
        if child.tag.split("}")[-1]
        in {
            "UAObject",
            "UAVariable",
        }
    ]

    if len(node_elements) != 4:
        raise RuntimeError(
            "Expected 4 exported nodes, "
            f"found {len(node_elements)}"
        )

    print()
    print("Exported XML validation:")
    print(
        "  Namespace URIs:",
        len(namespace_uris),
    )
    print(
        "  Exported nodes:",
        len(node_elements),
    )


def eu_information_matches(
    value,
) -> bool:
    return (
        isinstance(
            value,
            ua.EUInformation,
        )
        and value.NamespaceUri
        == UN_CEFACT_NAMESPACE_URI
        and value.UnitId
        == BAR_UNIT_ID
        and value.DisplayName.Text
        == "bar"
        and value.Description.Text
        == "bar"
    )


def range_matches(
    value,
) -> bool:
    return (
        isinstance(
            value,
            ua.Range,
        )
        and value.Low
        == PRESSURE_RANGE_LOW
        and value.High
        == PRESSURE_RANGE_HIGH
    )


def print_checks(
    title: str,
    checks: Iterable[
        tuple[str, bool]
    ],
) -> bool:
    print()
    print(title)

    failed = False

    for name, passed in checks:
        print(
            "  PASS"
            if passed
            else "  FAIL",
            name,
        )

        if not passed:
            failed = True

    return not failed


async def build_source_server(
    output_path: Path,
) -> None:
    server = Server()
    await server.init()

    project_index = (
        await server.register_namespace(
            PROJECT_NAMESPACE_URI
        )
    )

    root_object = (
        await server.nodes.objects
        .add_object(
            ua.NodeId(
                "Test",
                project_index,
            ),
            ua.QualifiedName(
                "Test",
                project_index,
            ),
        )
    )

    pressure = await root_object.add_variable(
        ua.NodeId(
            PRESSURE_NODE_ID,
            project_index,
        ),
        ua.QualifiedName(
            "Pressure",
            project_index,
        ),
        ua.Variant(
            PRESSURE_VALUE,
            ua.VariantType.Float,
        ),
        datatype=ua.VariantType.Float,
    )

    engineering_units = (
        await pressure.add_property(
            ua.NodeId(
                ENGINEERING_UNITS_NODE_ID,
                project_index,
            ),
            ua.QualifiedName(
                "EngineeringUnits",
                0,
            ),
            ua.Variant(
                ua.EUInformation(
                    NamespaceUri=(
                        UN_CEFACT_NAMESPACE_URI
                    ),
                    UnitId=BAR_UNIT_ID,
                    DisplayName=(
                        ua.LocalizedText(
                            "bar"
                        )
                    ),
                    Description=(
                        ua.LocalizedText(
                            "bar"
                        )
                    ),
                ),
                ua.VariantType.ExtensionObject,
            ),
            datatype=ua.NodeId(
                ua.ObjectIds.EUInformation
            ),
        )
    )

    eu_range = await pressure.add_property(
        ua.NodeId(
            EU_RANGE_NODE_ID,
            project_index,
        ),
        ua.QualifiedName(
            "EURange",
            0,
        ),
        ua.Variant(
            ua.Range(
                Low=PRESSURE_RANGE_LOW,
                High=PRESSURE_RANGE_HIGH,
            ),
            ua.VariantType.ExtensionObject,
        ),
        datatype=ua.NodeId(
            ua.ObjectIds.Range
        ),
    )

    nodes = await collect_project_nodes(
        root_object,
        project_index,
    )

    print()
    print("Source server:")
    print(
        "  Project namespace index:",
        project_index,
    )
    print(
        "  Collected nodes:",
        len(nodes),
    )

    for node in nodes:
        print(
            " ",
            node.nodeid,
            await node.read_browse_name(),
        )

    source_checks = [
        (
            "four nodes collected",
            len(nodes) == 4,
        ),
        (
            "pressure value is 12.5",
            await pressure.read_value()
            == PRESSURE_VALUE,
        ),
        (
            "pressure DataType is Float",
            await pressure.read_data_type()
            == ua.NodeId(
                ua.ObjectIds.Float
            ),
        ),
        (
            "EngineeringUnits is bar",
            eu_information_matches(
                await engineering_units
                .read_value()
            ),
        ),
        (
            "EngineeringUnits DataType",
            await engineering_units
            .read_data_type()
            == ua.NodeId(
                ua.ObjectIds.EUInformation
            ),
        ),
        (
            "EURange is correct",
            range_matches(
                await eu_range.read_value()
            ),
        ),
        (
            "EURange DataType",
            await eu_range.read_data_type()
            == ua.NodeId(
                ua.ObjectIds.Range
            ),
        ),
    ]

    if not print_checks(
        "Source server validation:",
        source_checks,
    ):
        raise RuntimeError(
            "Source server validation failed"
        )

    exporter = XmlExporter(
        server,
        export_values=True,
    )

    await exporter.build_etree(
        nodes,
        add_all_namespaces=False,
    )

    output_path.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    await exporter.write_xml(
        str(output_path),
        pretty=True,
    )

    validate_exported_xml(
        output_path
    )

    print()
    print("NodeSet exported:")
    print(" ", output_path)
    print(
        "  Size:",
        output_path.stat().st_size,
        "bytes",
    )
    print(
        "  SHA-256:",
        calculate_sha256(
            output_path
        ),
    )


async def validate_imported_server(
    nodeset_path: Path,
) -> None:
    server = Server()
    await server.init()

    imported_nodes = await server.import_xml(
        path=str(nodeset_path),
        strict_mode=True,
        auto_load_definitions=True,
    )

    project_index = (
        await server.get_namespace_index(
            PROJECT_NAMESPACE_URI
        )
    )

    pressure = server.get_node(
        ua.NodeId(
            PRESSURE_NODE_ID,
            project_index,
        )
    )

    engineering_units = server.get_node(
        ua.NodeId(
            ENGINEERING_UNITS_NODE_ID,
            project_index,
        )
    )

    eu_range = server.get_node(
        ua.NodeId(
            EU_RANGE_NODE_ID,
            project_index,
        )
    )

    actual_pressure = (
        await pressure.read_value()
    )

    actual_pressure_type = (
        await pressure.read_data_type()
    )

    actual_units = (
        await engineering_units
        .read_value()
    )

    actual_units_type = (
        await engineering_units
        .read_data_type()
    )

    actual_range = (
        await eu_range.read_value()
    )

    actual_range_type = (
        await eu_range.read_data_type()
    )

    print()
    print("Imported server:")
    print(
        "  Imported nodes:",
        len(imported_nodes or []),
    )
    print(
        "  Project namespace index:",
        project_index,
    )
    print(
        "  Pressure:",
        repr(actual_pressure),
    )
    print(
        "  EngineeringUnits:",
        repr(actual_units),
    )
    print(
        "  EURange:",
        repr(actual_range),
    )

    imported_checks = [
        (
            "pressure node exists",
            await pressure.read_node_class()
            == ua.NodeClass.Variable,
        ),
        (
            "pressure value round trip",
            actual_pressure
            == PRESSURE_VALUE,
        ),
        (
            "pressure DataType round trip",
            actual_pressure_type
            == ua.NodeId(
                ua.ObjectIds.Float
            ),
        ),
        (
            "EngineeringUnits round trip",
            eu_information_matches(
                actual_units
            ),
        ),
        (
            "EngineeringUnits DataType",
            actual_units_type
            == ua.NodeId(
                ua.ObjectIds.EUInformation
            ),
        ),
        (
            "EURange round trip",
            range_matches(
                actual_range
            ),
        ),
        (
            "EURange DataType",
            actual_range_type
            == ua.NodeId(
                ua.ObjectIds.Range
            ),
        ),
    ]

    if not print_checks(
        "Imported server validation:",
        imported_checks,
    ):
        raise RuntimeError(
            "Imported server validation failed"
        )


async def main() -> None:
    print(
        "XmlExporter structured-value "
        "round-trip test"
    )

    print(
        "Output path:",
        OUTPUT_PATH,
    )

    if OUTPUT_PATH.exists():
        OUTPUT_PATH.unlink()

    await build_source_server(
        OUTPUT_PATH
    )

    await validate_imported_server(
        OUTPUT_PATH
    )

    print()
    print(
        "XmlExporter structured-value "
        "round trip passed"
    )


if __name__ == "__main__":
    asyncio.run(main())
