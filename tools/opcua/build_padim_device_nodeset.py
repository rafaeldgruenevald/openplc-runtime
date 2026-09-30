from __future__ import annotations

import hashlib
import os
import sys
import tempfile
import xml.etree.ElementTree as ET
from pathlib import Path


REPOSITORY_ROOT = Path(
    os.environ.get(
        "OPENPLC_REPOSITORY_ROOT",
        Path.cwd(),
    )
).resolve()

BASELINE_PATH = (
    REPOSITORY_ROOT
    / "tools"
    / "opcua"
    / "instantiate_padim_pressure_values.py"
)

OUTPUT_PATH = Path(
    os.environ.get(
        "PADIM_DEVICE_NODESET_OUTPUT",
        (
            "/tmp/"
            "Test.PADIMDevice.NodeSet2.xml"
        ),
    )
).resolve()

EXPECTED_BASELINE_SHA256 = (
    "3f73d68c7661ba3f6fb0a40710d4c3d9"
    "dbe65f4956e3c2821528d50232ad8531"
)

PROJECT_MODEL_URI = (
    "urn:openplc:test:padim-device"
)

PROJECT_MODEL_VERSION = "1.0.0"

NODESET_XML_NAMESPACE = (
    "http:"
    + "//opcfoundation.org"
    + "/UA/2011/03/UANodeSet.xsd"
)

EXPECTED_PROJECT_NODE_COUNT = 19

PROJECT_NODE_IDENTIFIERS = {
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
    (
        "PT101.SignalSet.Pressure."
        "SignalTag"
    ),
    (
        "PT101.SignalSet.Pressure."
        "AnalogSignal"
    ),
    (
        "PT101.SignalSet.Pressure."
        "AnalogSignal.EngineeringUnits"
    ),
    (
        "PT101.SignalSet.Pressure."
        "AnalogSignal.EURange"
    ),
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


def validate_baseline() -> str:
    if not BASELINE_PATH.is_file():
        raise FileNotFoundError(
            "Approved procedural baseline "
            f"does not exist: {BASELINE_PATH}"
        )

    actual_sha256 = calculate_sha256(
        BASELINE_PATH
    )

    if actual_sha256 != EXPECTED_BASELINE_SHA256:
        raise RuntimeError(
            "Approved procedural baseline hash "
            "does not match the expected value. "
            f"Expected {EXPECTED_BASELINE_SHA256}, "
            f"found {actual_sha256}"
        )

    source = BASELINE_PATH.read_text(
        encoding="utf-8",
    )

    required_fragments = [
        "async def main():",
        "Complete PADIM PT101 instance passed",
        "if __name__ == \"__main__\":",
        "asyncio.run(main())",
    ]

    for fragment in required_fragments:
        if fragment not in source:
            raise RuntimeError(
                "Approved baseline does not contain "
                f"the required fragment: {fragment!r}"
            )

    print("PASS: approved baseline hash")
    print(
        "Baseline:",
        BASELINE_PATH,
    )
    print(
        "SHA-256:",
        actual_sha256,
    )

    return source


def build_injected_helpers() -> str:
    return r'''
async def collect_nodeset_project_nodes(
    root,
    project_namespace_index,
):
    collected = []
    visited = set()

    async def visit(node):
        node_id_text = node.nodeid.to_string()

        if node_id_text in visited:
            return

        visited.add(node_id_text)

        if (
            node.nodeid.NamespaceIndex
            == project_namespace_index
        ):
            collected.append(node)

        children = await node.get_children(
            refs=ua.ObjectIds.HierarchicalReferences,
        )

        for child in children:
            await visit(child)

    await visit(root)

    collected.sort(
        key=lambda node: node.nodeid.to_string()
    )

    return collected


def nodeset_local_name(element):
    return element.tag.split("}")[-1]


def read_nodeset_model_identity(path):
    tree = ET.parse(path)
    root = tree.getroot()

    models = None

    for child in root:
        if nodeset_local_name(child) == "Models":
            models = child
            break

    if models is None:
        raise RuntimeError(
            f"NodeSet has no Models element: {path}"
        )

    model = None

    for child in models:
        if nodeset_local_name(child) == "Model":
            model = child
            break

    if model is None:
        raise RuntimeError(
            f"NodeSet has no Model declaration: {path}"
        )

    model_uri = model.attrib.get(
        "ModelUri"
    )

    if not model_uri:
        raise RuntimeError(
            f"NodeSet Model has no ModelUri: {path}"
        )

    identity = {
        "ModelUri": model_uri,
    }

    version = model.attrib.get(
        "Version"
    )

    if version:
        identity["Version"] = version

    publication_date = model.attrib.get(
        "PublicationDate"
    )

    if publication_date:
        identity[
            "PublicationDate"
        ] = publication_date

    return identity


def add_nodeset_models(
    output_path,
):
    ET.register_namespace(
        "",
        NODESET_XML_NAMESPACE,
    )

    ET.register_namespace(
        "xsi",
        (
            "http:"
            + "//www.w3.org/2001/"
            + "XMLSchema-instance"
        ),
    )

    ET.register_namespace(
        "uax",
        (
            "http:"
            + "//opcfoundation.org/"
            + "UA/2008/02/Types.xsd"
        ),
    )

    tree = ET.parse(output_path)
    root = tree.getroot()

    existing_models = [
        child
        for child in root
        if nodeset_local_name(child)
        == "Models"
    ]

    for element in existing_models:
        root.remove(element)

    models_tag = (
        "{"
        + NODESET_XML_NAMESPACE
        + "}Models"
    )

    model_tag = (
        "{"
        + NODESET_XML_NAMESPACE
        + "}Model"
    )

    required_model_tag = (
        "{"
        + NODESET_XML_NAMESPACE
        + "}RequiredModel"
    )

    models = ET.Element(
        models_tag
    )

    project_model = ET.SubElement(
        models,
        model_tag,
        {
            "ModelUri": PROJECT_MODEL_URI,
            "Version": PROJECT_MODEL_VERSION,
        },
    )

    dependency_paths = [
        DI_MODEL,
        IRDI_MODEL,
        PADIM_MODEL,
    ]

    required_identities = []

    for dependency_path in dependency_paths:
        identity = read_nodeset_model_identity(
            dependency_path
        )

        required_identities.append(
            identity
        )

        ET.SubElement(
            project_model,
            required_model_tag,
            identity,
        )

    insertion_index = 0

    for index, child in enumerate(
        list(root)
    ):
        if (
            nodeset_local_name(child)
            == "NamespaceUris"
        ):
            insertion_index = index + 1
            break

    root.insert(
        insertion_index,
        models,
    )

    ET.indent(
        tree,
        space="  ",
    )

    tree.write(
        output_path,
        encoding="utf-8",
        xml_declaration=True,
    )

    return required_identities


def validate_generated_nodeset(
    output_path,
):
    tree = ET.parse(output_path)
    root = tree.getroot()

    expected_root_tag = (
        "{"
        + NODESET_XML_NAMESPACE
        + "}UANodeSet"
    )

    if root.tag != expected_root_tag:
        raise RuntimeError(
            "Unexpected UANodeSet root: "
            f"{root.tag!r}"
        )

    namespace_uris = []

    for child in root:
        if (
            nodeset_local_name(child)
            != "NamespaceUris"
        ):
            continue

        for uri_element in child:
            if (
                nodeset_local_name(uri_element)
                == "Uri"
                and uri_element.text
            ):
                namespace_uris.append(
                    uri_element.text
                )

    if (
        PROJECT_MODEL_URI
        not in namespace_uris
    ):
        raise RuntimeError(
            "Project namespace URI is missing "
            "from NamespaceUris"
        )

    models = [
        child
        for child in root
        if nodeset_local_name(child)
        == "Models"
    ]

    if len(models) != 1:
        raise RuntimeError(
            "Expected exactly one Models element, "
            f"found {len(models)}"
        )

    project_models = [
        child
        for child in models[0]
        if (
            nodeset_local_name(child)
            == "Model"
            and child.attrib.get(
                "ModelUri"
            )
            == PROJECT_MODEL_URI
        )
    ]

    if len(project_models) != 1:
        raise RuntimeError(
            "Expected one project Model declaration"
        )

    required_models = [
        child
        for child in project_models[0]
        if nodeset_local_name(child)
        == "RequiredModel"
    ]

    if len(required_models) != 3:
        raise RuntimeError(
            "Expected three RequiredModel "
            "declarations, found "
            f"{len(required_models)}"
        )

    project_node_ids = set()
    project_node_count = 0

    for element in root:
        local_name = nodeset_local_name(
            element
        )

        if local_name not in {
            "UAObject",
            "UAVariable",
        }:
            continue

        node_id = element.attrib.get(
            "NodeId",
            "",
        )

        if ";s=" not in node_id:
            continue

        identifier = node_id.split(
            ";s=",
            1,
        )[1]

        if identifier not in (
            PROJECT_NODE_IDENTIFIERS
        ):
            continue

        project_node_ids.add(
            identifier
        )

        project_node_count += 1

    missing_node_ids = (
        PROJECT_NODE_IDENTIFIERS
        - project_node_ids
    )

    unexpected_count = (
        project_node_count
        != EXPECTED_PROJECT_NODE_COUNT
    )

    if missing_node_ids:
        raise RuntimeError(
            "Generated NodeSet is missing project "
            "NodeIds: "
            f"{sorted(missing_node_ids)}"
        )

    if unexpected_count:
        raise RuntimeError(
            "Unexpected project node count: "
            f"{project_node_count}; expected "
            f"{EXPECTED_PROJECT_NODE_COUNT}"
        )

    content = output_path.read_text(
        encoding="utf-8",
    )

    required_terms = [
        "EngineeringUnits",
        "EURange",
        "EUInformation",
        "4342098",
        "12.5",
        "OpenPLC Project",
        "PT101-001",
    ]

    missing_terms = [
        term
        for term in required_terms
        if term not in content
    ]

    if missing_terms:
        raise RuntimeError(
            "Generated NodeSet is missing expected "
            f"content: {missing_terms}"
        )

    print()
    print("Generated NodeSet XML validation:")
    print(
        "  Namespace URIs:",
        len(namespace_uris),
    )
    print(
        "  Required models:",
        len(required_models),
    )
    print(
        "  Project nodes:",
        project_node_count,
    )


async def export_complete_padim_nodeset(
    server,
    pt101,
    instance_index,
    output_path,
):
    from asyncua.common.xmlexporter import (
        XmlExporter,
    )

    project_nodes = (
        await collect_nodeset_project_nodes(
            pt101,
            instance_index,
        )
    )

    node_identifiers = {
        node.nodeid.Identifier
        for node in project_nodes
    }

    missing_identifiers = (
        PROJECT_NODE_IDENTIFIERS
        - node_identifiers
    )

    unexpected_identifiers = (
        node_identifiers
        - PROJECT_NODE_IDENTIFIERS
    )

    print()
    print("Project-node collection:")
    print(
        "  Collected nodes:",
        len(project_nodes),
    )

    for node in project_nodes:
        print(
            " ",
            node.nodeid,
            await node.read_browse_name(),
        )

    if missing_identifiers:
        raise RuntimeError(
            "Project-node collection is missing: "
            f"{sorted(missing_identifiers)}"
        )

    if unexpected_identifiers:
        raise RuntimeError(
            "Project-node collection has unexpected "
            "nodes: "
            f"{sorted(unexpected_identifiers)}"
        )

    if (
        len(project_nodes)
        != EXPECTED_PROJECT_NODE_COUNT
    ):
        raise RuntimeError(
            "Expected "
            f"{EXPECTED_PROJECT_NODE_COUNT} "
            "project nodes, collected "
            f"{len(project_nodes)}"
        )

    exporter = XmlExporter(
        server,
        export_values=True,
    )

    await exporter.build_etree(
        project_nodes,
        add_all_namespaces=False,
    )

    output_path.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    if output_path.exists():
        output_path.unlink()

    await exporter.write_xml(
        str(output_path),
        pretty=True,
    )

    required_identities = (
        add_nodeset_models(
            output_path
        )
    )

    validate_generated_nodeset(
        output_path
    )

    print()
    print("Required models:")

    for identity in required_identities:
        print(
            " ",
            identity,
        )

    print()
    print("PADIM device NodeSet generated:")
    print(
        " ",
        output_path,
    )
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
'''


def instrument_baseline(
    baseline_source: str,
) -> str:
    main_marker = "async def main():"

    helper_source = (
        build_injected_helpers()
    )

    if main_marker not in baseline_source:
        raise RuntimeError(
            "Could not locate main function "
            "in approved baseline"
        )

    instrumented_source = (
        baseline_source.replace(
            main_marker,
            (
                helper_source
                + "\n\n"
                + main_marker
            ),
            1,
        )
    )

    success_marker = (
        '    print(\n'
        '        "Complete PADIM PT101 instance passed"\n'
        '    )'
    )

    export_and_success = (
        "    await export_complete_padim_nodeset(\n"
        "        server=server,\n"
        "        pt101=devices_folder,\n"
        "        instance_index=instance_index,\n"
        "        output_path=OUTPUT_PATH,\n"
        "    )\n"
        "\n"
        + success_marker
    )

    if success_marker not in instrumented_source:
        raise RuntimeError(
            "Could not locate final success marker "
            "in approved baseline"
        )

    instrumented_source = (
        instrumented_source.replace(
            success_marker,
            export_and_success,
            1,
        )
    )

    imports_marker = (
        "from pathlib import Path"
    )

    required_imports = (
        "import xml.etree.ElementTree as ET\n"
        "from pathlib import Path"
    )

    if imports_marker in instrumented_source:
        instrumented_source = (
            instrumented_source.replace(
                imports_marker,
                required_imports,
                1,
            )
        )
    else:
        instrumented_source = (
            "import xml.etree.ElementTree as ET\n"
            "from pathlib import Path\n"
            + instrumented_source
        )

    output_definition = (
        "\n\n"
        "OUTPUT_PATH = Path(\n"
        "    os.environ.get(\n"
        "        \"PADIM_DEVICE_NODESET_OUTPUT\",\n"
        "        \"/tmp/Test.PADIMDevice.NodeSet2.xml\",\n"
        "    )\n"
        ").resolve()\n"
        "\n"
        "PROJECT_MODEL_URI = INSTANCE_URI\n"
        "PROJECT_MODEL_VERSION = \"1.0.0\"\n"
        "NODESET_XML_NAMESPACE = (\n"
        "    \"http:\"\n"
        "    + \"//opcfoundation.org\"\n"
        "    + \"/UA/2011/03/UANodeSet.xsd\"\n"
        ")\n"
        "EXPECTED_PROJECT_NODE_COUNT = 19\n"
        "PROJECT_NODE_IDENTIFIERS = "
        + repr(PROJECT_NODE_IDENTIFIERS)
        + "\n"
    )

    constant_marker = (
        "DEVICE_HEALTH_NORMAL = 0"
    )

    if constant_marker not in instrumented_source:
        raise RuntimeError(
            "Could not locate baseline constants"
        )

    instrumented_source = (
        instrumented_source.replace(
            constant_marker,
            (
                constant_marker
                + output_definition
            ),
            1,
        )
    )

    return instrumented_source


def execute_instrumented_baseline(
    source: str,
) -> None:
    compile(
        source,
        str(BASELINE_PATH),
        "exec",
    )

    execution_globals = {
        "__name__": "__main__",
        "__file__": str(BASELINE_PATH),
        "__package__": None,
        "calculate_sha256": calculate_sha256,
    }

    exec(
        compile(
            source,
            str(BASELINE_PATH),
            "exec",
        ),
        execution_globals,
        execution_globals,
    )


def main() -> None:
    print(
        "PADIM PT101 NodeSet generator"
    )
    print(
        "Repository root:",
        REPOSITORY_ROOT,
    )
    print(
        "Output path:",
        OUTPUT_PATH,
    )

    baseline_source = (
        validate_baseline()
    )

    instrumented_source = (
        instrument_baseline(
            baseline_source
        )
    )

    with tempfile.NamedTemporaryFile(
        mode="w",
        encoding="utf-8",
        prefix=(
            "build_padim_device_nodeset_"
        ),
        suffix=".py",
        delete=False,
    ) as temporary_file:
        temporary_file.write(
            instrumented_source
        )

        temporary_path = Path(
            temporary_file.name
        )

    print(
        "Instrumented execution file:",
        temporary_path,
    )

    try:
        execute_instrumented_baseline(
            instrumented_source
        )
    finally:
        try:
            temporary_path.unlink()
        except FileNotFoundError:
            pass

    if not OUTPUT_PATH.is_file():
        raise SystemExit(
            "FAIL: PADIM device NodeSet "
            "was not generated"
        )


    print()
    print(
        "PADIM PT101 NodeSet build passed"
    )


if __name__ == "__main__":
    main()
