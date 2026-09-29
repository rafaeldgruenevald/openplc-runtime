from __future__ import annotations

import asyncio
import os
import sys
from pathlib import Path

from asyncua import Server, ua


REPOSITORY_ROOT = Path(
    os.environ.get(
        "OPENPLC_REPOSITORY_ROOT",
        "/workdir",
    )
).resolve()

PLUGIN_ROOT = (
    REPOSITORY_ROOT
    / "core"
    / "src"
    / "drivers"
    / "plugins"
    / "python"
)

if str(PLUGIN_ROOT) not in sys.path:
    sys.path.insert(
        0,
        str(PLUGIN_ROOT),
    )

from opcua.imported_node_bindings import (
    COLLISION_POLICY_REPLACE,
    load_and_resolve_imported_node_bindings,
)
from opcua.opcua_types import VariableNode


DI_MODEL_PATH = Path(
    os.environ["DI_MODEL_PATH"]
).resolve()

IRDI_MODEL_PATH = Path(
    os.environ["IRDI_MODEL_PATH"]
).resolve()

PADIM_MODEL_PATH = Path(
    os.environ["PADIM_MODEL_PATH"]
).resolve()

PROJECT_MODEL_PATH = Path(
    os.environ["PROJECT_MODEL_PATH"]
).resolve()

BINDING_PATH = Path(
    os.environ["BINDING_PATH"]
).resolve()

PROJECT_NAMESPACE_URI = (
    "urn:openplc:test:padim-device"
)

TARGET_IDENTIFIER = (
    "PT101.SignalSet.Pressure."
    "AnalogSignal"
)

LEGACY_IDENTIFIER = (
    "Legacy.Pressure"
)

OPENPLC_ADDRESS = (
    0,
    14,
)


async def import_nodeset(
    server: Server,
    label: str,
    path: Path,
) -> None:
    if not path.is_file():
        raise FileNotFoundError(
            f"{label} does not exist: {path}"
        )

    imported_nodes = await server.import_xml(
        path=str(path),
        strict_mode=True,
        auto_load_definitions=True,
    )

    print(
        f"Imported {label}: "
        f"{len(imported_nodes or [])} nodes"
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


async def main() -> None:
    print(
        "Real PADIM binding resolution test"
    )

    print(
        "Binding:",
        BINDING_PATH,
    )

    server = Server()
    await server.init()

    await import_nodeset(
        server,
        "DI",
        DI_MODEL_PATH,
    )

    await import_nodeset(
        server,
        "IRDI",
        IRDI_MODEL_PATH,
    )

    await import_nodeset(
        server,
        "PADIM",
        PADIM_MODEL_PATH,
    )

    await import_nodeset(
        server,
        "PADIM project",
        PROJECT_MODEL_PATH,
    )

    namespace_index = (
        await server.get_namespace_index(
            PROJECT_NAMESPACE_URI
        )
    )

    target_node = server.get_node(
        ua.NodeId(
            TARGET_IDENTIFIER,
            namespace_index,
        )
    )

    target_node_class = (
        await target_node.read_node_class()
    )

    target_data_type = (
        await target_node.read_data_type()
    )

    target_value_rank = (
        await target_node.read_value_rank()
    )

    target_value = (
        await target_node.read_value()
    )

    legacy_node = (
        await server.nodes.objects
        .add_variable(
            ua.NodeId(
                LEGACY_IDENTIFIER,
                namespace_index,
            ),
            ua.QualifiedName(
                "LegacyPressure",
                namespace_index,
            ),
            ua.Variant(
                0.0,
                ua.VariantType.Float,
            ),
            datatype=(
                ua.VariantType.Float
            ),
        )
    )

    legacy_variable = VariableNode(
        node=legacy_node,
        arr=OPENPLC_ADDRESS[0],
        elem=OPENPLC_ADDRESS[1],
        datatype="REAL",
        access_mode="readwrite",
        is_array_element=False,
        array_index=None,
        array_length=None,
    )

    existing_variable_nodes = {
        OPENPLC_ADDRESS: legacy_variable,
    }

    result = (
        await load_and_resolve_imported_node_bindings(
            server=server,
            binding_path=BINDING_PATH,
            existing_variable_nodes=(
                existing_variable_nodes
            ),
            collision_policy=(
                COLLISION_POLICY_REPLACE
            ),
        )
    )

    active_variable = (
        result.variable_nodes[
            OPENPLC_ADDRESS
        ]
    )

    resolved_binding = (
        result.resolved_bindings[0]
    )

    checks = [
        (
            "project namespace resolved",
            namespace_index > 0,
        ),
        (
            "target is Variable",
            target_node_class
            == ua.NodeClass.Variable,
        ),
        (
            "target DataType is Float",
            target_data_type
            == ua.NodeId(
                ua.ObjectIds.Float
            ),
        ),
        (
            "target is scalar",
            target_value_rank
            in {
                ua.ValueRank.Scalar,
                -1,
            },
        ),
        (
            "target initial value is 12.5",
            target_value == 12.5,
        ),
        (
            "one binding resolved",
            len(
                result.resolved_bindings
            )
            == 1,
        ),
        (
            "replacement counted",
            result.replacement_count
            == 1,
        ),
        (
            "no new address created",
            result.new_binding_count
            == 0,
        ),
        (
            "resolved address is correct",
            resolved_binding.address
            == OPENPLC_ADDRESS,
        ),
        (
            "replaced node is legacy node",
            resolved_binding.replaced_node
            is legacy_variable,
        ),
        (
            "active node is PADIM target",
            active_variable.node.nodeid
            == target_node.nodeid,
        ),
        (
            "active array index is zero",
            active_variable.arr == 0,
        ),
        (
            "active element index is fourteen",
            active_variable.elem == 14,
        ),
        (
            "active IEC type is REAL",
            active_variable.datatype
            == "REAL",
        ),
        (
            "active node is readonly",
            active_variable.access_mode
            == "readonly",
        ),
        (
            "input map was not mutated",
            existing_variable_nodes[
                OPENPLC_ADDRESS
            ]
            is legacy_variable,
        ),
    ]

    passed = print_checks(
        "Real PADIM binding checks:",
        checks,
    )

    print()
    print(
        "Target NodeId:",
        target_node.nodeid,
    )

    print(
        "Legacy NodeId:",
        legacy_node.nodeid,
    )

    print(
        "Active NodeId:",
        active_variable.node.nodeid,
    )

    print(
        "Address:",
        (
            active_variable.arr,
            active_variable.elem,
        ),
    )

    print(
        "Access mode:",
        active_variable.access_mode,
    )

    if not passed:
        raise SystemExit(
            "Real PADIM binding "
            "resolution failed"
        )

    print()
    print(
        "Real PADIM binding "
        "resolution passed"
    )


if __name__ == "__main__":
    asyncio.run(main())
