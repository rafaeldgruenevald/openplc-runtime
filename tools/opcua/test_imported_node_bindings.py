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
    COLLISION_POLICY_REJECT,
    COLLISION_POLICY_REPLACE,
    load_and_resolve_imported_node_bindings,
)
from opcua.opcua_types import VariableNode


BINDING_PATH = (
    REPOSITORY_ROOT
    / "config"
    / "opcua"
    / "bindings"
    / "Test.PADIMDevice.openplc-bindings.json"
)

PROJECT_NAMESPACE_URI = (
    "urn:openplc:test:padim-device"
)

TARGET_IDENTIFIER = (
    "PT101.SignalSet."
    "Pressure.AnalogSignal"
)


async def create_target_node(
    server: Server,
    namespace_index: int,
):
    return await server.nodes.objects.add_variable(
        ua.NodeId(
            TARGET_IDENTIFIER,
            namespace_index,
        ),
        ua.QualifiedName(
            "AnalogSignal",
            namespace_index,
        ),
        ua.Variant(
            12.5,
            ua.VariantType.Float,
        ),
        datatype=ua.VariantType.Float,
    )


async def create_legacy_node(
    server: Server,
    namespace_index: int,
):
    return await server.nodes.objects.add_variable(
        ua.NodeId(
            "Legacy.Pressure",
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
        datatype=ua.VariantType.Float,
    )


def print_checks(
    title,
    checks,
):
    print()
    print(title)

    failed = False

    for name, passed in checks:
        print(
            "  PASS" if passed else "  FAIL",
            name,
        )

        if not passed:
            failed = True

    return not failed


async def main():
    server = Server()
    await server.init()

    project_index = (
        await server.register_namespace(
            PROJECT_NAMESPACE_URI
        )
    )

    target_node = await create_target_node(
        server,
        project_index,
    )

    legacy_node = await create_legacy_node(
        server,
        project_index,
    )

    legacy_variable_node = VariableNode(
        node=legacy_node,
        arr=0,
        elem=14,
        datatype="REAL",
        access_mode="readwrite",
        is_array_element=False,
    )

    existing_nodes = {
        (
            0,
            14,
        ): legacy_variable_node,
    }

    result = (
        await load_and_resolve_imported_node_bindings(
            server=server,
            binding_path=BINDING_PATH,
            existing_variable_nodes=(
                existing_nodes
            ),
            collision_policy=(
                COLLISION_POLICY_REPLACE
            ),
        )
    )

    resolved = result.resolved_bindings[0]
    active_node = result.variable_nodes[
        (
            0,
            14,
        )
    ]

    replace_checks = [
        (
            "one binding resolved",
            len(
                result.resolved_bindings
            )
            == 1,
        ),
        (
            "replacement counted",
            result.replacement_count == 1,
        ),
        (
            "no new address counted",
            result.new_binding_count == 0,
        ),
        (
            "namespace resolved",
            resolved.namespace_index
            == project_index,
        ),
        (
            "target NodeId resolved",
            resolved.node.nodeid
            == target_node.nodeid,
        ),
        (
            "target address preserved",
            resolved.address == (0, 14),
        ),
        (
            "target datatype is REAL",
            active_node.datatype == "REAL",
        ),
        (
            "target is readonly",
            active_node.access_mode
            == "readonly",
        ),
        (
            "active node is imported target",
            active_node.node.nodeid
            == target_node.nodeid,
        ),
        (
            "legacy node was replaced",
            resolved.replaced_node
            is legacy_variable_node,
        ),
        (
            "input map was not mutated",
            existing_nodes[(0, 14)]
            is legacy_variable_node,
        ),
    ]

    replace_passed = print_checks(
        "Replace policy:",
        replace_checks,
    )

    reject_passed = False

    try:
        await load_and_resolve_imported_node_bindings(
            server=server,
            binding_path=BINDING_PATH,
            existing_variable_nodes=(
                existing_nodes
            ),
            collision_policy=(
                COLLISION_POLICY_REJECT
            ),
        )
    except ValueError as exception:
        reject_passed = (
            "collides with an existing"
            in str(exception)
        )

    reject_checks = [
        (
            "reject policy detects collision",
            reject_passed,
        ),
    ]

    reject_policy_passed = print_checks(
        "Reject policy:",
        reject_checks,
    )

    if (
        not replace_passed
        or not reject_policy_passed
    ):
        raise SystemExit(
            "Imported-node binding test failed"
        )

    print()
    print(
        "Imported-node binding test passed"
    )


if __name__ == "__main__":
    asyncio.run(main())
