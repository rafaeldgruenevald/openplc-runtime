from __future__ import annotations

import asyncio
import hashlib
import os
from pathlib import Path
from typing import Any

from asyncua import Server, ua


DI_MODEL = Path(
    os.environ["DI_MODEL_PATH"]
).resolve()

IRDI_MODEL = Path(
    os.environ["IRDI_MODEL_PATH"]
).resolve()

PADIM_MODEL = Path(
    os.environ["PADIM_MODEL_PATH"]
).resolve()

PROJECT_MODEL = Path(
    os.environ["PROJECT_MODEL_PATH"]
).resolve()

DI_URI = (
    "http:"
    + "//opcfoundation.org"
    + "/UA/DI/"
)

PADIM_URI = (
    "http:"
    + "//opcfoundation.org"
    + "/UA/PADIM/"
)

PROJECT_URI = (
    "urn:openplc:test:padim-device"
)

UN_CEFACT_URI = (
    "http:"
    + "//www.opcfoundation.org"
    + "/UA/units/un/cefact"
)

BAR_UNIT_ID = 4342098

DEVICES_FOLDER_ID = "PADIMDevices"
PT101_ID = "PT101"
SIGNAL_SET_ID = "PT101.SignalSet"

PRESSURE_ID = (
    "PT101.SignalSet.Pressure"
)

SIGNAL_TAG_ID = (
    "PT101.SignalSet.Pressure.SignalTag"
)

ANALOG_SIGNAL_ID = (
    "PT101.SignalSet.Pressure."
    "AnalogSignal"
)

ENGINEERING_UNITS_ID = (
    "PT101.SignalSet.Pressure."
    "AnalogSignal.EngineeringUnits"
)

EU_RANGE_ID = (
    "PT101.SignalSet.Pressure."
    "AnalogSignal.EURange"
)

EXPECTED_NODE_IDENTIFIERS = {
    "PADIMDevices",
    "PT101",
    "PT101.Manufacturer",
    "PT101.ManufacturerUri",
    "PT101.Model",
    "PT101.SerialNumber",
    "PT101.SoftwareRevision",
    "PT101.HardwareRevision",
    "PT101.ProductCode",
    "PT101.DeviceHealth",
    "PT101.ProductInstanceUri",
    "PT101.AssetId",
    "PT101.RevisionCounter",
    "PT101.SignalSet",
    "PT101.SignalSet.Pressure",
    "PT101.SignalSet.Pressure.SignalTag",
    ANALOG_SIGNAL_ID,
    ENGINEERING_UNITS_ID,
    EU_RANGE_ID,
}

EXPECTED_METADATA = {
    "Manufacturer": {
        "value": "OpenPLC Project",
        "datatype": ua.NodeId(
            ua.ObjectIds.LocalizedText
        ),
    },
    "ManufacturerUri": {
        "value": "urn:openplc",
        "datatype": ua.NodeId(
            ua.ObjectIds.String
        ),
    },
    "Model": {
        "value": (
            "PADIM Pressure Transmitter PoC"
        ),
        "datatype": ua.NodeId(
            ua.ObjectIds.LocalizedText
        ),
    },
    "SerialNumber": {
        "value": "PT101-001",
        "datatype": ua.NodeId(
            ua.ObjectIds.String
        ),
    },
    "SoftwareRevision": {
        "value": "4.2.2-poc",
        "datatype": ua.NodeId(
            ua.ObjectIds.String
        ),
    },
    "HardwareRevision": {
        "value": "virtual",
        "datatype": ua.NodeId(
            ua.ObjectIds.String
        ),
    },
    "ProductCode": {
        "value": "OPENPLC-PT",
        "datatype": ua.NodeId(
            ua.ObjectIds.String
        ),
    },
    "ProductInstanceUri": {
        "value": (
            "urn:openplc:device:pt101"
        ),
        "datatype": ua.NodeId(
            ua.ObjectIds.String
        ),
    },
    "AssetId": {
        "value": "PT101",
        "datatype": ua.NodeId(
            ua.ObjectIds.String
        ),
    },
    "RevisionCounter": {
        "value": 1,
        "datatype": ua.NodeId(
            ua.ObjectIds.Int32
        ),
    },
}


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


def validate_input_file(
    label: str,
    path: Path,
) -> None:
    if not path.is_file():
        raise FileNotFoundError(
            f"{label} does not exist: {path}"
        )

    if path.stat().st_size == 0:
        raise ValueError(
            f"{label} is empty: {path}"
        )


async def import_model(
    server: Server,
    label: str,
    path: Path,
) -> list:
    print(
        f"Importing {label}: {path}"
    )

    nodes = await server.import_xml(
        path=str(path),
        strict_mode=True,
        auto_load_definitions=True,
    )

    result = list(
        nodes or []
    )

    print(
        f"Imported {label}: "
        f"{len(result)} nodes"
    )

    return result


async def require_node(
    server: Server,
    namespace_index: int,
    identifier: str,
):
    node = server.get_node(
        ua.NodeId(
            identifier,
            namespace_index,
        )
    )

    try:
        await node.read_node_class()
    except Exception as exception:
        raise RuntimeError(
            "Required project node does not "
            f"exist: {identifier}"
        ) from exception

    return node


async def collect_project_nodes(
    root_node,
    project_index: int,
) -> list:
    result = []
    visited = set()

    async def visit(node) -> None:
        key = node.nodeid.to_string()

        if key in visited:
            return

        visited.add(key)

        if (
            node.nodeid.NamespaceIndex
            == project_index
        ):
            result.append(node)

        children = await node.get_children(
            refs=(
                ua.ObjectIds
                .HierarchicalReferences
            ),
        )

        for child in children:
            await visit(child)

    await visit(root_node)

    result.sort(
        key=lambda node: (
            str(node.nodeid.Identifier)
        )
    )

    return result


async def read_parent_ids(
    node,
) -> set[ua.NodeId]:
    parents = await node.get_referenced_nodes(
        refs=(
            ua.ObjectIds
            .HierarchicalReferences
        ),
        direction=ua.BrowseDirection.Inverse,
    )

    return {
        parent.nodeid
        for parent in parents
    }


def normalize_value(
    value: Any,
) -> Any:
    if isinstance(
        value,
        ua.LocalizedText,
    ):
        return value.Text

    return value


def eu_information_matches(
    value: Any,
) -> bool:
    return (
        isinstance(
            value,
            ua.EUInformation,
        )
        and value.NamespaceUri
        == UN_CEFACT_URI
        and value.UnitId
        == BAR_UNIT_ID
        and value.DisplayName.Text
        == "bar"
        and value.Description.Text
        == "bar"
    )


def range_matches(
    value: Any,
) -> bool:
    return (
        isinstance(
            value,
            ua.Range,
        )
        and value.Low == 0.0
        and value.High == 16.0
    )


def print_checks(
    title: str,
    checks: list[
        tuple[str, bool]
    ],
) -> bool:
    print()
    print(title)

    all_passed = True

    for name, passed in checks:
        print(
            "  PASS" if passed else "  FAIL",
            name,
        )

        if not passed:
            all_passed = False

    return all_passed


async def validate_metadata(
    server: Server,
    project_index: int,
    di_index: int,
) -> list[
    tuple[str, bool]
]:
    checks = []

    for name, expected in (
        EXPECTED_METADATA.items()
    ):
        node = await require_node(
            server,
            project_index,
            "PT101." + name,
        )

        value = await node.read_value()
        datatype = (
            await node.read_data_type()
        )

        checks.append(
            (
                f"{name} value",
                normalize_value(value)
                == expected["value"],
            )
        )

        checks.append(
            (
                f"{name} DataType",
                datatype
                == expected["datatype"],
            )
        )

        print()
        print(
            "Metadata:",
            name,
        )
        print(
            "  Value:",
            repr(value),
        )
        print(
            "  DataType:",
            datatype,
        )

    health = await require_node(
        server,
        project_index,
        "PT101.DeviceHealth",
    )

    health_value = (
        await health.read_value()
    )

    health_datatype = (
        await health.read_data_type()
    )

    checks.append(
        (
            "DeviceHealth value",
            health_value == 0,
        )
    )

    checks.append(
        (
            "DeviceHealth DataType",
            health_datatype
            == ua.NodeId(
                6244,
                di_index,
            ),
        )
    )

    print()
    print(
        "Metadata: DeviceHealth"
    )
    print(
        "  Value:",
        repr(health_value),
    )
    print(
        "  DataType:",
        health_datatype,
    )

    return checks


async def main() -> None:
    print(
        "Complete PADIM PT101 NodeSet "
        "import validation"
    )

    inputs = [
        (
            "DI NodeSet",
            DI_MODEL,
        ),
        (
            "IRDI NodeSet",
            IRDI_MODEL,
        ),
        (
            "PADIM NodeSet",
            PADIM_MODEL,
        ),
        (
            "Project NodeSet",
            PROJECT_MODEL,
        ),
    ]

    for label, path in inputs:
        validate_input_file(
            label,
            path,
        )

        print(
            f"{label} SHA-256:",
            calculate_sha256(path),
        )

    server = Server()
    await server.init()

    await import_model(
        server,
        "DI",
        DI_MODEL,
    )

    await import_model(
        server,
        "IRDI",
        IRDI_MODEL,
    )

    await import_model(
        server,
        "PADIM",
        PADIM_MODEL,
    )

    imported_project_nodes = (
        await import_model(
            server,
            "project",
            PROJECT_MODEL,
        )
    )

    di_index = (
        await server.get_namespace_index(
            DI_URI
        )
    )

    padim_index = (
        await server.get_namespace_index(
            PADIM_URI
        )
    )

    project_index = (
        await server.get_namespace_index(
            PROJECT_URI
        )
    )

    print()
    print("Namespace indexes:")
    print(
        "  DI:",
        di_index,
    )
    print(
        "  PADIM:",
        padim_index,
    )
    print(
        "  Project:",
        project_index,
    )

    devices_folder = await require_node(
        server,
        project_index,
        DEVICES_FOLDER_ID,
    )

    pt101 = await require_node(
        server,
        project_index,
        PT101_ID,
    )

    signal_set = await require_node(
        server,
        project_index,
        SIGNAL_SET_ID,
    )

    pressure = await require_node(
        server,
        project_index,
        PRESSURE_ID,
    )

    signal_tag = await require_node(
        server,
        project_index,
        SIGNAL_TAG_ID,
    )

    analog_signal = await require_node(
        server,
        project_index,
        ANALOG_SIGNAL_ID,
    )

    engineering_units = (
        await require_node(
            server,
            project_index,
            ENGINEERING_UNITS_ID,
        )
    )

    eu_range = await require_node(
        server,
        project_index,
        EU_RANGE_ID,
    )

    collected_nodes = (
        await collect_project_nodes(
            devices_folder,
            project_index,
        )
    )

    collected_identifiers = {
        str(node.nodeid.Identifier)
        for node in collected_nodes
    }

    devices_parent_ids = (
        await read_parent_ids(
            devices_folder
        )
    )

    pt101_parent_ids = (
        await read_parent_ids(
            pt101
        )
    )

    signal_set_parent_ids = (
        await read_parent_ids(
            signal_set
        )
    )

    pressure_parent_ids = (
        await read_parent_ids(
            pressure
        )
    )

    analog_parent_ids = (
        await read_parent_ids(
            analog_signal
        )
    )

    signal_tag_parent_ids = (
        await read_parent_ids(
            signal_tag
        )
    )

    analog_value = (
        await analog_signal.read_value()
    )

    analog_datatype = (
        await analog_signal.read_data_type()
    )

    analog_type_definition = (
        await analog_signal
        .read_type_definition()
    )

    units_value = (
        await engineering_units.read_value()
    )

    range_value = (
        await eu_range.read_value()
    )

    signal_tag_browse_name = (
        await signal_tag.read_browse_name()
    )

    print()
    print(
        "Imported project nodes:",
        len(imported_project_nodes),
    )
    print(
        "Collected project nodes:",
        len(collected_nodes),
    )

    for node in collected_nodes:
        print(
            " ",
            node.nodeid,
            await node.read_browse_name(),
        )

    hierarchy_checks = [
        (
            "PADIMDevices is Object",
            await devices_folder
            .read_node_class()
            == ua.NodeClass.Object,
        ),
        (
            "PADIMDevices parent is Objects",
            ua.NodeId(
                ua.ObjectIds.ObjectsFolder
            )
            in devices_parent_ids,
        ),
        (
            "PT101 is Object",
            await pt101.read_node_class()
            == ua.NodeClass.Object,
        ),
        (
            "PT101 parent is PADIMDevices",
            devices_folder.nodeid
            in pt101_parent_ids,
        ),
        (
            "PT101 uses PADIMType",
            await pt101.read_type_definition()
            == ua.NodeId(
                1009,
                padim_index,
            ),
        ),
        (
            "SignalSet parent is PT101",
            pt101.nodeid
            in signal_set_parent_ids,
        ),
        (
            "SignalSet uses SignalSetType",
            await signal_set
            .read_type_definition()
            == ua.NodeId(
                1021,
                padim_index,
            ),
        ),
        (
            "Pressure parent is SignalSet",
            signal_set.nodeid
            in pressure_parent_ids,
        ),
        (
            "Pressure uses AnalogSignalType",
            await pressure
            .read_type_definition()
            == ua.NodeId(
                1022,
                padim_index,
            ),
        ),
        (
            "AnalogSignal parent is Pressure",
            pressure.nodeid
            in analog_parent_ids,
        ),
        (
            (
                "AnalogSignal uses "
                "PressureMeasurementVariableType"
            ),
            analog_type_definition
            == ua.NodeId(
                1121,
                padim_index,
            ),
        ),
        (
            "AnalogSignal DataType is Float",
            analog_datatype
            == ua.NodeId(
                ua.ObjectIds.Float
            ),
        ),
        (
            "AnalogSignal value is 12.5",
            analog_value == 12.5,
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
            "EngineeringUnits is bar",
            eu_information_matches(
                units_value
            ),
        ),
        (
            "EURange DataType",
            await eu_range.read_data_type()
            == ua.NodeId(
                ua.ObjectIds.Range
            ),
        ),
        (
            "EURange is 0.0 to 16.0",
            range_matches(
                range_value
            ),
        ),
        (
            "SignalTag parent is Pressure",
            pressure.nodeid
            in signal_tag_parent_ids,
        ),
        (
            "SignalTag BrowseName is correct",
            signal_tag_browse_name.Name
            == "SignalTag",
        ),
        (
            "SignalTag BrowseName uses PADIM",
            signal_tag_browse_name
            .NamespaceIndex
            == padim_index,
        ),
        (
            "19 project nodes imported",
            len(imported_project_nodes)
            == 19,
        ),
        (
            "19 project nodes collected",
            len(collected_nodes) == 19,
        ),
        (
            "all expected NodeIds exist",
            collected_identifiers
            == EXPECTED_NODE_IDENTIFIERS,
        ),
    ]

    metadata_checks = (
        await validate_metadata(
            server,
            project_index,
            di_index,
        )
    )

    hierarchy_passed = print_checks(
        "Hierarchy and semantic validation:",
        hierarchy_checks,
    )

    metadata_passed = print_checks(
        "Metadata validation:",
        metadata_checks,
    )

    print()
    print(
        "Resolved semantic references:"
    )
    print(
        "  PADIMDevices parents:",
        sorted(
            str(node_id)
            for node_id
            in devices_parent_ids
        ),
    )
    print(
        "  PT101 TypeDefinition:",
        await pt101.read_type_definition(),
    )
    print(
        "  SignalSet TypeDefinition:",
        await signal_set
        .read_type_definition(),
    )
    print(
        "  Pressure TypeDefinition:",
        await pressure
        .read_type_definition(),
    )
    print(
        "  AnalogSignal TypeDefinition:",
        analog_type_definition,
    )
    print(
        "  AnalogSignal DataType:",
        analog_datatype,
    )
    print(
        "  AnalogSignal value:",
        repr(analog_value),
    )
    print(
        "  EngineeringUnits:",
        repr(units_value),
    )
    print(
        "  EURange:",
        repr(range_value),
    )
    print(
        "  SignalTag BrowseName:",
        signal_tag_browse_name,
    )

    if (
        not hierarchy_passed
        or not metadata_passed
    ):
        raise SystemExit(
            "Complete PADIM PT101 NodeSet "
            "import validation failed"
        )

    print()
    print(
        "Complete PADIM PT101 NodeSet "
        "import validation passed"
    )


if __name__ == "__main__":
    asyncio.run(main())
