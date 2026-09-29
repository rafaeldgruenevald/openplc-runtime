import asyncio
import os

from asyncua import Server, ua
from asyncua.common.instantiate_util import instantiate


DI_MODEL = os.environ["DI_MODEL_PATH"]
IRDI_MODEL = os.environ["IRDI_MODEL_PATH"]
PADIM_MODEL = os.environ["PADIM_MODEL_PATH"]

DI_URI = "http://opcfoundation.org/UA/DI/"
PADIM_URI = "http://opcfoundation.org/UA/PADIM/"
INSTANCE_URI = "urn:openplc:test:padim-device"

PRESSURE_VALUE = 12.5
PRESSURE_RANGE_LOW = 0.0
PRESSURE_RANGE_HIGH = 16.0

UN_CEFACT_NAMESPACE_URI = (
    "http://www.opcfoundation.org/"
    "UA/units/un/cefact"
)

BAR_UNIT_CODE = "BAR"
BAR_UNIT_ID = 4342098

DEVICE_HEALTH_NORMAL = 0


async def import_model(server, name, path):
    print(f"Importing {name}: {path}")

    imported_nodes = await server.import_xml(
        path=path,
        strict_mode=True,
        auto_load_definitions=True,
    )

    print(
        f"Imported {name}: "
        f"{len(imported_nodes or [])} nodes"
    )


async def find_child(parent, browse_name_text):
    children = await parent.get_children()

    for child in children:
        browse_name = await child.read_browse_name()

        if browse_name.Name == browse_name_text:
            return child

    return None


async def require_child(parent, browse_name_text):
    child = await find_child(
        parent,
        browse_name_text,
    )

    if child is None:
        raise RuntimeError(
            f"Required child was not found: "
            f"{browse_name_text}"
        )

    return child


async def validate_node_exists(node):
    try:
        await node.read_node_class()
        return True
    except ua.UaStatusCodeError:
        return False


async def print_node_details(node, label):
    print()
    print(label)
    print("  NodeId:", node.nodeid)
    print(
        "  BrowseName:",
        await node.read_browse_name(),
    )
    print(
        "  DisplayName:",
        await node.read_display_name(),
    )
    print(
        "  NodeClass:",
        await node.read_node_class(),
    )
    print(
        "  TypeDefinition:",
        await node.read_type_definition(),
    )

    node_class = await node.read_node_class()

    if node_class in (
        ua.NodeClass.Variable,
        ua.NodeClass.VariableType,
    ):
        print(
            "  DataType:",
            await node.read_data_type(),
        )
        print(
            "  Value:",
            repr(await node.read_value()),
        )


async def print_children(parent, title):
    print()
    print(title)

    children = await parent.get_children()

    if not children:
        print("  No children")
        return

    for child in children:
        browse_name = await child.read_browse_name()
        node_class = await child.read_node_class()
        type_definition = await child.read_type_definition()

        data_type = None
        value = None

        if node_class in (
            ua.NodeClass.Variable,
            ua.NodeClass.VariableType,
        ):
            data_type = await child.read_data_type()
            value = await child.read_value()

        print()
        print("  BrowseName:", browse_name)
        print("  NodeId:", child.nodeid)
        print("  NodeClass:", node_class)
        print("  TypeDefinition:", type_definition)
        print("  DataType:", data_type)
        print("  Value:", repr(value))


async def write_variant_value(
    parent,
    child_name,
    value,
    variant_type,
):
    child = await require_child(
        parent,
        child_name,
    )

    await child.write_value(
        ua.Variant(
            value,
            variant_type,
        )
    )

    actual_value = await child.read_value()
    actual_data_type = await child.read_data_type()

    print()
    print("Wrote metadata:")
    print("  Name:", child_name)
    print("  NodeId:", child.nodeid)
    print("  DataType:", actual_data_type)
    print("  Value:", repr(actual_value))

    return child, actual_value


def localized_text_matches(
    value,
    expected_text,
):
    return (
        isinstance(
            value,
            ua.LocalizedText,
        )
        and value.Text == expected_text
    )


def eu_information_matches(
    value,
    namespace_uri,
    unit_id,
    display_name,
):
    return (
        isinstance(
            value,
            ua.EUInformation,
        )
        and value.NamespaceUri == namespace_uri
        and value.UnitId == unit_id
        and value.DisplayName.Text == display_name
    )


def range_matches(
    value,
    low,
    high,
):
    return (
        isinstance(
            value,
            ua.Range,
        )
        and value.Low == low
        and value.High == high
    )


async def main():
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

    di_index = await server.get_namespace_index(
        DI_URI
    )

    padim_index = await server.get_namespace_index(
        PADIM_URI
    )

    instance_index = await server.register_namespace(
        INSTANCE_URI
    )

    print()
    print("Namespace indexes:")
    print("  DI:", di_index)
    print("  PADIM:", padim_index)
    print("  Instance:", instance_index)

    expected_bar_unit_id = int.from_bytes(
        BAR_UNIT_CODE.encode("ascii"),
        byteorder="big",
    )

    bar_unit_id_valid = (
        expected_bar_unit_id
        == BAR_UNIT_ID
    )

    print()
    print("UN/CEFACT bar unit:")
    print("  Common code:", BAR_UNIT_CODE)
    print(
        "  Computed UnitId:",
        expected_bar_unit_id,
    )
    print(
        "  Configured UnitId:",
        BAR_UNIT_ID,
    )
    print(
        "  PASS" if bar_unit_id_valid else "  FAIL",
        "bar UnitId is 4342098",
    )

    if not bar_unit_id_valid:
        raise SystemExit(
            "FAIL: invalid UnitId configured for bar"
        )

    devices_folder = await server.nodes.objects.add_folder(
        ua.NodeId(
            "PADIMDevices",
            instance_index,
        ),
        ua.QualifiedName(
            "PADIMDevices",
            instance_index,
        ),
    )

    padim_type = server.get_node(
        ua.NodeId(
            1009,
            padim_index,
        )
    )

    signal_set_type = server.get_node(
        ua.NodeId(
            1021,
            padim_index,
        )
    )

    analog_signal_type = server.get_node(
        ua.NodeId(
            1022,
            padim_index,
        )
    )

    pressure_variable_type = server.get_node(
        ua.NodeId(
            1121,
            padim_index,
        )
    )

    print()
    print("Creating mandatory PADIM PT101")

    pt101_created = await instantiate(
        parent=devices_folder,
        node_type=padim_type,
        nodeid=ua.NodeId(
            "PT101",
            instance_index,
        ),
        bname=ua.QualifiedName(
            "PT101",
            instance_index,
        ),
        dname=ua.LocalizedText(
            "PT101 Pressure Transmitter"
        ),
        idx=instance_index,
        instantiate_optional=False,
    )

    print(
        "PT101 created nodes:",
        len(pt101_created),
    )

    for node in pt101_created:
        print(" ", node.nodeid)

    pt101 = server.get_node(
        ua.NodeId(
            "PT101",
            instance_index,
        )
    )

    print()
    print("Creating explicit SignalSet")

    signal_set_created = await instantiate(
        parent=pt101,
        node_type=signal_set_type,
        nodeid=ua.NodeId(
            "PT101.SignalSet",
            instance_index,
        ),
        bname=ua.QualifiedName(
            "SignalSet",
            padim_index,
        ),
        dname=ua.LocalizedText(
            "Signal Set"
        ),
        idx=instance_index,
        instantiate_optional=False,
    )

    print(
        "SignalSet created nodes:",
        len(signal_set_created),
    )

    for node in signal_set_created:
        print(" ", node.nodeid)

    signal_set = server.get_node(
        ua.NodeId(
            "PT101.SignalSet",
            instance_index,
        )
    )

    print()
    print("Creating explicit Pressure signal")

    pressure_created = await instantiate(
        parent=signal_set,
        node_type=analog_signal_type,
        nodeid=ua.NodeId(
            "PT101.SignalSet.Pressure",
            instance_index,
        ),
        bname=ua.QualifiedName(
            "Pressure",
            instance_index,
        ),
        dname=ua.LocalizedText(
            "Pressure Signal"
        ),
        idx=instance_index,
        instantiate_optional=False,
    )

    print(
        "Pressure signal created nodes:",
        len(pressure_created),
    )

    for node in pressure_created:
        print(" ", node.nodeid)

    pressure = server.get_node(
        ua.NodeId(
            "PT101.SignalSet.Pressure",
            instance_index,
        )
    )

    generic_analog_signal = await require_child(
        pressure,
        "AnalogSignal",
    )

    generic_node_id = (
        generic_analog_signal.nodeid
    )

    generic_type_definition = (
        await generic_analog_signal.read_type_definition()
    )

    expected_generic_type = ua.NodeId(
        1111,
        padim_index,
    )

    print()
    print("Generic AnalogSignal:")
    print("  NodeId:", generic_node_id)
    print(
        "  TypeDefinition:",
        generic_type_definition,
    )

    if generic_type_definition != expected_generic_type:
        raise SystemExit(
            "FAIL: generated AnalogSignal does not use "
            "AnalogSignalVariableType"
        )

    generic_children = (
        await generic_analog_signal.get_children()
    )

    generic_child_ids = [
        child.nodeid
        for child in generic_children
    ]

    print()
    print("Deleting generic AnalogSignal recursively")

    deleted_nodes = await generic_analog_signal.delete(
        delete_references=True,
        recursive=True,
    )

    print(
        "Deleted node count:",
        len(deleted_nodes),
    )

    for node in deleted_nodes:
        print(" ", node.nodeid)

    generic_removed = not await validate_node_exists(
        server.get_node(
            generic_node_id
        )
    )

    deleted_children_removed = True

    for child_id in generic_child_ids:
        child_exists = await validate_node_exists(
            server.get_node(
                child_id
            )
        )

        print(
            "  FAIL" if child_exists else "  PASS",
            "deleted descendant unavailable:",
            child_id,
        )

        if child_exists:
            deleted_children_removed = False

    if not generic_removed:
        raise SystemExit(
            "FAIL: generic AnalogSignal still exists"
        )

    if not deleted_children_removed:
        raise SystemExit(
            "FAIL: generic AnalogSignal descendants "
            "still exist"
        )

    print()
    print(
        "Creating pressure-specific AnalogSignal"
    )

    specialized_created = await instantiate(
        parent=pressure,
        node_type=pressure_variable_type,
        nodeid=generic_node_id,
        bname=ua.QualifiedName(
            "AnalogSignal",
            padim_index,
        ),
        dname=ua.LocalizedText(
            "Pressure Measurement"
        ),
        idx=instance_index,
        instantiate_optional=False,
    )

    print(
        "Specialized pressure variable created nodes:",
        len(specialized_created),
    )

    for node in specialized_created:
        print(" ", node.nodeid)

    analog_signal = server.get_node(
        generic_node_id
    )

    analog_signal_exists = await validate_node_exists(
        analog_signal
    )

    if not analog_signal_exists:
        raise SystemExit(
            "FAIL: specialized AnalogSignal "
            "was not created"
        )

    engineering_units = await require_child(
        analog_signal,
        "EngineeringUnits",
    )

    eu_range = await require_child(
        analog_signal,
        "EURange",
    )

    pressure_unit = ua.EUInformation(
        NamespaceUri=UN_CEFACT_NAMESPACE_URI,
        UnitId=BAR_UNIT_ID,
        DisplayName=ua.LocalizedText(
            "bar"
        ),
        Description=ua.LocalizedText(
            "bar"
        ),
    )

    pressure_range = ua.Range(
        Low=PRESSURE_RANGE_LOW,
        High=PRESSURE_RANGE_HIGH,
    )

    print()
    print("Writing pressure values")

    await analog_signal.write_value(
        ua.Variant(
            PRESSURE_VALUE,
            ua.VariantType.Float,
        )
    )

    await engineering_units.write_value(
        ua.Variant(
            pressure_unit,
            ua.VariantType.ExtensionObject,
        )
    )

    await eu_range.write_value(
        ua.Variant(
            pressure_range,
            ua.VariantType.ExtensionObject,
        )
    )

    metadata_results = {}

    metadata_results["Manufacturer"] = (
        await write_variant_value(
            pt101,
            "Manufacturer",
            ua.LocalizedText(
                "OpenPLC Project"
            ),
            ua.VariantType.LocalizedText,
        )
    )

    metadata_results["ManufacturerUri"] = (
        await write_variant_value(
            pt101,
            "ManufacturerUri",
            "urn:openplc",
            ua.VariantType.String,
        )
    )

    metadata_results["Model"] = (
        await write_variant_value(
            pt101,
            "Model",
            ua.LocalizedText(
                "PADIM Pressure Transmitter PoC"
            ),
            ua.VariantType.LocalizedText,
        )
    )

    metadata_results["SerialNumber"] = (
        await write_variant_value(
            pt101,
            "SerialNumber",
            "PT101-001",
            ua.VariantType.String,
        )
    )

    metadata_results["SoftwareRevision"] = (
        await write_variant_value(
            pt101,
            "SoftwareRevision",
            "4.2.2-poc",
            ua.VariantType.String,
        )
    )

    metadata_results["HardwareRevision"] = (
        await write_variant_value(
            pt101,
            "HardwareRevision",
            "virtual",
            ua.VariantType.String,
        )
    )

    metadata_results["ProductCode"] = (
        await write_variant_value(
            pt101,
            "ProductCode",
            "OPENPLC-PT",
            ua.VariantType.String,
        )
    )

    metadata_results["DeviceHealth"] = (
        await write_variant_value(
            pt101,
            "DeviceHealth",
            DEVICE_HEALTH_NORMAL,
            ua.VariantType.Int32,
        )
    )

    metadata_results["ProductInstanceUri"] = (
        await write_variant_value(
            pt101,
            "ProductInstanceUri",
            "urn:openplc:device:pt101",
            ua.VariantType.String,
        )
    )

    metadata_results["AssetId"] = (
        await write_variant_value(
            pt101,
            "AssetId",
            "PT101",
            ua.VariantType.String,
        )
    )

    metadata_results["RevisionCounter"] = (
        await write_variant_value(
            pt101,
            "RevisionCounter",
            1,
            ua.VariantType.Int32,
        )
    )

    actual_pressure_value = (
        await analog_signal.read_value()
    )

    actual_pressure_type = (
        await analog_signal.read_data_type()
    )

    actual_pressure_type_definition = (
        await analog_signal.read_type_definition()
    )

    actual_engineering_units = (
        await engineering_units.read_value()
    )

    actual_engineering_units_type = (
        await engineering_units.read_data_type()
    )

    actual_eu_range = (
        await eu_range.read_value()
    )

    actual_eu_range_type = (
        await eu_range.read_data_type()
    )

    manufacturer_value = (
        metadata_results["Manufacturer"][1]
    )

    manufacturer_uri_value = (
        metadata_results["ManufacturerUri"][1]
    )

    model_value = (
        metadata_results["Model"][1]
    )

    serial_number_value = (
        metadata_results["SerialNumber"][1]
    )

    software_revision_value = (
        metadata_results["SoftwareRevision"][1]
    )

    hardware_revision_value = (
        metadata_results["HardwareRevision"][1]
    )

    product_code_value = (
        metadata_results["ProductCode"][1]
    )

    device_health_value = (
        metadata_results["DeviceHealth"][1]
    )

    product_instance_uri_value = (
        metadata_results["ProductInstanceUri"][1]
    )

    asset_id_value = (
        metadata_results["AssetId"][1]
    )

    revision_counter_value = (
        metadata_results["RevisionCounter"][1]
    )

    print()
    print("Final pressure values:")
    print(
        "  Pressure:",
        repr(actual_pressure_value),
    )
    print(
        "  EngineeringUnits:",
        repr(actual_engineering_units),
    )
    print(
        "  EURange:",
        repr(actual_eu_range),
    )

    checks = [
        (
            "bar UnitId is 4342098",
            bar_unit_id_valid,
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
            "SignalSet uses SignalSetType",
            await signal_set.read_type_definition()
            == ua.NodeId(
                1021,
                padim_index,
            ),
        ),
        (
            "Pressure uses AnalogSignalType",
            await pressure.read_type_definition()
            == ua.NodeId(
                1022,
                padim_index,
            ),
        ),
        (
            "generic AnalogSignal was removed",
            generic_removed,
        ),
        (
            "generic descendants were removed",
            deleted_children_removed,
        ),
        (
            "specialized AnalogSignal exists",
            analog_signal_exists,
        ),
        (
            "AnalogSignal uses "
            "PressureMeasurementVariableType",
            actual_pressure_type_definition
            == ua.NodeId(
                1121,
                padim_index,
            ),
        ),
        (
            "Pressure DataType is Float",
            actual_pressure_type
            == ua.NodeId(
                10,
                0,
            ),
        ),
        (
            "Pressure value equals 12.5",
            actual_pressure_value
            == PRESSURE_VALUE,
        ),
        (
            "EngineeringUnits DataType "
            "is EUInformation",
            actual_engineering_units_type
            == ua.NodeId(
                887,
                0,
            ),
        ),
        (
            "EngineeringUnits is bar",
            eu_information_matches(
                actual_engineering_units,
                UN_CEFACT_NAMESPACE_URI,
                BAR_UNIT_ID,
                "bar",
            ),
        ),
        (
            "EURange DataType is Range",
            actual_eu_range_type
            == ua.NodeId(
                884,
                0,
            ),
        ),
        (
            "EURange is 0.0 to 16.0",
            range_matches(
                actual_eu_range,
                PRESSURE_RANGE_LOW,
                PRESSURE_RANGE_HIGH,
            ),
        ),
        (
            "Manufacturer is OpenPLC Project",
            localized_text_matches(
                manufacturer_value,
                "OpenPLC Project",
            ),
        ),
        (
            "ManufacturerUri is urn:openplc",
            manufacturer_uri_value
            == "urn:openplc",
        ),
        (
            "Model identifies PADIM PoC",
            localized_text_matches(
                model_value,
                "PADIM Pressure Transmitter PoC",
            ),
        ),
        (
            "SerialNumber is PT101-001",
            serial_number_value
            == "PT101-001",
        ),
        (
            "SoftwareRevision is 4.2.2-poc",
            software_revision_value
            == "4.2.2-poc",
        ),
        (
            "HardwareRevision is virtual",
            hardware_revision_value
            == "virtual",
        ),
        (
            "ProductCode is OPENPLC-PT",
            product_code_value
            == "OPENPLC-PT",
        ),
        (
            "DeviceHealth is NORMAL",
            device_health_value
            == DEVICE_HEALTH_NORMAL,
        ),
        (
            "ProductInstanceUri identifies PT101",
            product_instance_uri_value
            == "urn:openplc:device:pt101",
        ),
        (
            "AssetId is PT101",
            asset_id_value
            == "PT101",
        ),
        (
            "RevisionCounter is 1",
            revision_counter_value
            == 1,
        ),
    ]

    expected_metadata_types = {
        "Manufacturer": ua.NodeId(21, 0),
        "ManufacturerUri": ua.NodeId(12, 0),
        "Model": ua.NodeId(21, 0),
        "SerialNumber": ua.NodeId(12, 0),
        "SoftwareRevision": ua.NodeId(12, 0),
        "HardwareRevision": ua.NodeId(12, 0),
        "ProductCode": ua.NodeId(12, 0),
        "DeviceHealth": ua.NodeId(
            6244,
            di_index,
        ),
        "ProductInstanceUri": ua.NodeId(12, 0),
        "AssetId": ua.NodeId(12, 0),
        "RevisionCounter": ua.NodeId(6, 0),
    }

    for name, expected_data_type in (
        expected_metadata_types.items()
    ):
        node = metadata_results[name][0]

        actual_data_type = (
            await node.read_data_type()
        )

        checks.append(
            (
                f"{name} DataType is correct",
                actual_data_type
                == expected_data_type,
            )
        )

    print()
    print("Complete PADIM PT101 validation:")

    failed = False

    for name, passed in checks:
        print(
            "  PASS" if passed else "  FAIL",
            name,
        )

        if not passed:
            failed = True

    await print_node_details(
        pt101,
        "PT101 details:",
    )

    await print_children(
        pt101,
        "PT101 metadata:",
    )

    await print_node_details(
        signal_set,
        "SignalSet details:",
    )

    await print_node_details(
        pressure,
        "Pressure signal details:",
    )

    await print_node_details(
        analog_signal,
        "AnalogSignal details:",
    )

    await print_children(
        analog_signal,
        "AnalogSignal properties:",
    )

    if failed:
        raise SystemExit(
            "Complete PADIM PT101 validation failed"
        )

    print()
    print(
        "Complete PADIM PT101 instance passed"
    )


if __name__ == "__main__":
    asyncio.run(main())
