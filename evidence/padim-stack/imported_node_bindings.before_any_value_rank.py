"""
Imported OPC UA node binding resolution.

This module connects OPC UA Variable nodes that already exist because
they were imported from a project NodeSet to OpenPLC STruC++ debug
leaves.

The module does not create semantic OPC UA nodes. The project NodeSet
is responsible for:

- NodeId identity;
- BrowseName hierarchy;
- TypeDefinition;
- OPC UA DataType;
- engineering units;
- ranges;
- semantic metadata.

This module is responsible only for:

- loading the runtime-specific binding configuration;
- resolving namespace URIs to runtime namespace indexes;
- locating imported nodes;
- validating NodeClass and DataType;
- creating VariableNode adapters for SynchronizationManager;
- applying an explicit collision policy for OpenPLC debug addresses.

The first implementation supports string NodeIds and scalar variables.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Optional, Tuple

from asyncua import Server, ua
from asyncua.common.node import Node

try:
    from .opcua_logging import (
        log_debug,
        log_error,
        log_info,
        log_warn,
    )
    from .opcua_types import VariableNode
    from .semantic_binding_config import (
        SemanticBinding,
        SemanticBindingConfig,
        load_semantic_binding_config,
    )
except ImportError:
    from opcua_logging import (
        log_debug,
        log_error,
        log_info,
        log_warn,
    )
    from opcua_types import VariableNode
    from semantic_binding_config import (
        SemanticBinding,
        SemanticBindingConfig,
        load_semantic_binding_config,
    )


Address = Tuple[int, int]

COLLISION_POLICY_REJECT = "reject"
COLLISION_POLICY_REPLACE = "replace"

SUPPORTED_COLLISION_POLICIES = frozenset(
    {
        COLLISION_POLICY_REJECT,
        COLLISION_POLICY_REPLACE,
    }
)

OPCUA_DATA_TYPE_NODE_IDS = {
    "Boolean": ua.NodeId(
        ua.ObjectIds.Boolean
    ),
    "SByte": ua.NodeId(
        ua.ObjectIds.SByte
    ),
    "Byte": ua.NodeId(
        ua.ObjectIds.Byte
    ),
    "Int16": ua.NodeId(
        ua.ObjectIds.Int16
    ),
    "UInt16": ua.NodeId(
        ua.ObjectIds.UInt16
    ),
    "Int32": ua.NodeId(
        ua.ObjectIds.Int32
    ),
    "UInt32": ua.NodeId(
        ua.ObjectIds.UInt32
    ),
    "Int64": ua.NodeId(
        ua.ObjectIds.Int64
    ),
    "UInt64": ua.NodeId(
        ua.ObjectIds.UInt64
    ),
    "Float": ua.NodeId(
        ua.ObjectIds.Float
    ),
    "Double": ua.NodeId(
        ua.ObjectIds.Double
    ),
    "String": ua.NodeId(
        ua.ObjectIds.String
    ),
    "DateTime": ua.NodeId(
        ua.ObjectIds.DateTime
    ),
}


@dataclass(frozen=True)
class ResolvedImportedBinding:
    """
    One validated imported node and its OpenPLC adapter.
    """

    binding: SemanticBinding
    namespace_index: int
    node: Node
    variable_node: VariableNode
    replaced_node: Optional[VariableNode]

    @property
    def address(self) -> Address:
        return self.binding.source.address

    @property
    def node_id(self) -> ua.NodeId:
        return self.node.nodeid


@dataclass(frozen=True)
class ImportedBindingResult:
    """
    Result of resolving and merging imported bindings.
    """

    config: SemanticBindingConfig
    variable_nodes: Dict[
        Address,
        VariableNode,
    ]
    resolved_bindings: List[
        ResolvedImportedBinding
    ]

    @property
    def replacement_count(self) -> int:
        return sum(
            1
            for item in self.resolved_bindings
            if item.replaced_node is not None
        )

    @property
    def new_binding_count(self) -> int:
        return sum(
            1
            for item in self.resolved_bindings
            if item.replaced_node is None
        )


def _expected_data_type_node_id(
    opcua_type: str,
) -> ua.NodeId:
    try:
        return OPCUA_DATA_TYPE_NODE_IDS[
            opcua_type
        ]
    except KeyError as exception:
        raise ValueError(
            "Unsupported OPC UA DataType in "
            f"semantic binding: {opcua_type!r}"
        ) from exception


def _build_target_node_id(
    binding: SemanticBinding,
    namespace_index: int,
) -> ua.NodeId:
    identifier_type = (
        binding.target.identifier_type
    )

    if identifier_type != "String":
        raise ValueError(
            "Unsupported imported NodeId "
            f"identifier type: {identifier_type!r}"
        )

    return ua.NodeId(
        binding.target.identifier,
        namespace_index,
    )


async def _resolve_namespace_index(
    server: Server,
    namespace_uri: str,
) -> int:
    try:
        namespace_index = (
            await server.get_namespace_index(
                namespace_uri
            )
        )
    except Exception as exception:
        raise ValueError(
            "Imported binding namespace is not "
            "registered in the OPC UA server: "
            f"{namespace_uri!r}"
        ) from exception

    if (
        not isinstance(namespace_index, int)
        or namespace_index <= 0
    ):
        raise ValueError(
            "Imported binding namespace resolved "
            "to an invalid namespace index: "
            f"{namespace_uri!r} -> "
            f"{namespace_index!r}"
        )

    return namespace_index


async def _validate_target_node(
    node: Node,
    binding: SemanticBinding,
) -> None:
    try:
        node_class = (
            await node.read_node_class()
        )
    except Exception as exception:
        raise ValueError(
            f"Binding {binding.binding_id!r} "
            "target node does not exist or cannot "
            f"be read: {node.nodeid}"
        ) from exception

    if node_class != ua.NodeClass.Variable:
        raise ValueError(
            f"Binding {binding.binding_id!r} "
            "target must be an OPC UA Variable, "
            f"but {node.nodeid} has NodeClass "
            f"{node_class}"
        )

    try:
        actual_data_type = (
            await node.read_data_type()
        )
    except Exception as exception:
        raise ValueError(
            f"Binding {binding.binding_id!r} "
            "target DataType could not be read: "
            f"{node.nodeid}"
        ) from exception

    expected_data_type = (
        _expected_data_type_node_id(
            binding.types.opcua
        )
    )

    if actual_data_type != expected_data_type:
        raise ValueError(
            f"Binding {binding.binding_id!r} "
            "target has incompatible DataType: "
            f"actual={actual_data_type}, "
            f"expected={expected_data_type} "
            f"for {binding.types.opcua}"
        )

    try:
        value_rank = await node.read_value_rank()
    except Exception as exception:
        raise ValueError(
            f"Binding {binding.binding_id!r} "
            "target ValueRank could not be read: "
            f"{node.nodeid}"
        ) from exception

    scalar_value_ranks = {
        ua.ValueRank.Scalar,
        -1,
    }

    if value_rank not in scalar_value_ranks:
        raise ValueError(
            f"Binding {binding.binding_id!r} "
            "currently supports only scalar nodes, "
            f"but {node.nodeid} has ValueRank "
            f"{value_rank}"
        )


async def _create_variable_node(
    server: Server,
    binding: SemanticBinding,
) -> Tuple[int, Node, VariableNode]:
    namespace_index = (
        await _resolve_namespace_index(
            server,
            binding.target.namespace_uri,
        )
    )

    node_id = _build_target_node_id(
        binding,
        namespace_index,
    )

    node = server.get_node(
        node_id
    )

    await _validate_target_node(
        node,
        binding,
    )

    variable_node = VariableNode(
        node=node,
        arr=binding.source.array_index,
        elem=binding.source.element_index,
        datatype=binding.source.datatype,
        access_mode=(
            binding.access.access_mode
        ),
        is_array_element=False,
        array_index=None,
        array_length=None,
    )

    return (
        namespace_index,
        node,
        variable_node,
    )


def _validate_collision_policy(
    collision_policy: str,
) -> None:
    if (
        collision_policy
        not in SUPPORTED_COLLISION_POLICIES
    ):
        raise ValueError(
            "Unsupported imported binding "
            f"collision policy: "
            f"{collision_policy!r}; supported "
            f"policies: "
            f"{sorted(SUPPORTED_COLLISION_POLICIES)}"
        )


async def resolve_imported_node_bindings(
    server: Server,
    config: SemanticBindingConfig,
    existing_variable_nodes: Dict[
        Address,
        VariableNode,
    ],
    collision_policy: str = (
        COLLISION_POLICY_REPLACE
    ),
) -> ImportedBindingResult:
    """
    Resolve imported nodes and merge them into the sync mapping.

    The operation is atomic from the caller's perspective. A copy of
    existing_variable_nodes is created and returned only after every
    binding has been validated successfully.

    With collision_policy="replace", a semantic imported node replaces
    the legacy synchronization target for the same OpenPLC debug
    address. The legacy OPC UA node remains in the AddressSpace but is
    no longer part of the active synchronization map.

    With collision_policy="reject", any occupied debug address causes
    the full operation to fail.
    """

    if server is None:
        raise ValueError(
            "OPC UA server is required"
        )

    _validate_collision_policy(
        collision_policy
    )

    merged_variable_nodes = dict(
        existing_variable_nodes
    )

    resolved_bindings: List[
        ResolvedImportedBinding
    ] = []

    binding_addresses = set()

    for binding in config.bindings:
        address = binding.source.address

        if address in binding_addresses:
            raise ValueError(
                "Duplicate OpenPLC address within "
                "semantic binding configuration: "
                f"{address}"
            )

        binding_addresses.add(
            address
        )

        (
            namespace_index,
            node,
            variable_node,
        ) = await _create_variable_node(
            server,
            binding,
        )

        replaced_node = (
            merged_variable_nodes.get(
                address
            )
        )

        if (
            replaced_node is not None
            and collision_policy
            == COLLISION_POLICY_REJECT
        ):
            raise ValueError(
                f"Binding {binding.binding_id!r} "
                "collides with an existing OPC UA "
                "sync node at OpenPLC address "
                f"{address}: "
                f"{replaced_node.node.nodeid}"
            )

        resolved_binding = (
            ResolvedImportedBinding(
                binding=binding,
                namespace_index=(
                    namespace_index
                ),
                node=node,
                variable_node=variable_node,
                replaced_node=replaced_node,
            )
        )

        resolved_bindings.append(
            resolved_binding
        )

        merged_variable_nodes[
            address
        ] = variable_node

    result = ImportedBindingResult(
        config=config,
        variable_nodes=(
            merged_variable_nodes
        ),
        resolved_bindings=(
            resolved_bindings
        ),
    )

    log_info(
        "Resolved "
        f"{len(result.resolved_bindings)} "
        "imported semantic OPC UA binding(s): "
        f"{result.new_binding_count} new, "
        f"{result.replacement_count} replaced"
    )

    for item in result.resolved_bindings:
        if item.replaced_node is None:
            log_debug(
                "Imported semantic binding "
                f"{item.binding.binding_id}: "
                f"{item.address} -> "
                f"{item.node_id}"
            )
            continue

        log_warn(
            "Imported semantic binding "
            f"{item.binding.binding_id} replaced "
            "the active synchronization target "
            f"for address {item.address}: "
            f"{item.replaced_node.node.nodeid} -> "
            f"{item.node_id}"
        )

    return result


async def load_and_resolve_imported_node_bindings(
    server: Server,
    binding_path: str | Path,
    existing_variable_nodes: Dict[
        Address,
        VariableNode,
    ],
    collision_policy: str = (
        COLLISION_POLICY_REPLACE
    ),
) -> ImportedBindingResult:
    """
    Load one semantic binding JSON file and resolve its nodes.
    """

    config = load_semantic_binding_config(
        binding_path
    )

    return await resolve_imported_node_bindings(
        server=server,
        config=config,
        existing_variable_nodes=(
            existing_variable_nodes
        ),
        collision_policy=collision_policy,
    )
