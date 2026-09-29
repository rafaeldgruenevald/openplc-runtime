import asyncio
import os

from asyncua import Server, ua


DI_MODEL = os.environ["DI_MODEL_PATH"]
IRDI_MODEL = os.environ["IRDI_MODEL_PATH"]
PADIM_MODEL = os.environ["PADIM_MODEL_PATH"]

INSTANCE_URI = "urn:openplc:test:padim-device"


async def import_model(
    server,
    name,
    path,
):
    print(f"Importing {name}: {path}")

    nodes = await server.import_xml(
        path=path,
        strict_mode=True,
        auto_load_definitions=True,
    )

    print(
        f"Imported {name}: "
        f"{len(nodes or [])} nodes"
    )


async def collect_project_nodes(
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

    return collected


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

    project_index = await server.register_namespace(
        INSTANCE_URI
    )

    print()
    print("Project namespace index:", project_index)

    folder = await server.nodes.objects.add_folder(
        ua.NodeId(
            "CollectionTest",
            project_index,
        ),
        ua.QualifiedName(
            "CollectionTest",
            project_index,
        ),
    )

    child_object = await folder.add_object(
        ua.NodeId(
            "CollectionTest.Child",
            project_index,
        ),
        ua.QualifiedName(
            "Child",
            project_index,
        ),
    )

    variable = await child_object.add_variable(
        ua.NodeId(
            "CollectionTest.Child.Value",
            project_index,
        ),
        ua.QualifiedName(
            "Value",
            project_index,
        ),
        ua.Variant(
            12.5,
            ua.VariantType.Float,
        ),
    )

    nodes = await collect_project_nodes(
        folder,
        project_index,
    )

    nodes.sort(
        key=lambda node: node.nodeid.to_string()
    )

    print()
    print("Collected nodes:", len(nodes))

    for node in nodes:
        print()
        print("NodeId:", node.nodeid)
        print(
            "BrowseName:",
            await node.read_browse_name(),
        )
        print(
            "NodeClass:",
            await node.read_node_class(),
        )

    collected_ids = {
        node.nodeid.to_string()
        for node in nodes
    }

    expected_ids = {
        folder.nodeid.to_string(),
        child_object.nodeid.to_string(),
        variable.nodeid.to_string(),
    }

    passed = collected_ids == expected_ids

    print()
    print(
        "PASS" if passed else "FAIL",
        "recursive project-node collection",
    )

    if not passed:
        print(
            "Missing:",
            sorted(
                expected_ids - collected_ids
            ),
        )
        print(
            "Unexpected:",
            sorted(
                collected_ids - expected_ids
            ),
        )

        raise SystemExit(1)


if __name__ == "__main__":
    asyncio.run(main())
