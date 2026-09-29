"""
Semantic OPC UA binding configuration.

This module parses the runtime-specific binding artifact that connects
OPC UA variables imported from project NodeSets to OpenPLC debug leaves.

The semantic NodeSet remains independent from the runtime. This file
contains only the OpenPLC-side resolution contract:

    imported OPC UA NodeId
        ->
    OpenPLC debug leaf (array index, element index, datatype and size)

The first implementation intentionally supports PLC-to-OPC-UA bindings.
Write support is represented by the configuration model but remains
disabled until the read path has been validated end to end.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List


SUPPORTED_SCHEMA_VERSION = "1.0"
SUPPORTED_RUNTIME_TYPE = "openplc"
SUPPORTED_IDENTIFIER_TYPES = frozenset(
    {
        "String",
    }
)
SUPPORTED_SOURCE_KINDS = frozenset(
    {
        "openplc-debug-leaf",
    }
)
SUPPORTED_UPDATE_MODES = frozenset(
    {
        "subscription-aware",
        "poll",
    }
)

IEC_TYPE_SIZES = {
    "BOOL": 1,
    "SINT": 1,
    "USINT": 1,
    "BYTE": 1,
    "INT": 2,
    "UINT": 2,
    "WORD": 2,
    "DINT": 4,
    "UDINT": 4,
    "DWORD": 4,
    "REAL": 4,
    "LINT": 8,
    "ULINT": 8,
    "LWORD": 8,
    "LREAL": 8,
    "TIME": 8,
    "DATE": 8,
    "TOD": 8,
    "DT": 8,
}

IEC_TO_OPCUA_TYPE = {
    "BOOL": "Boolean",
    "SINT": "SByte",
    "USINT": "Byte",
    "BYTE": "Byte",
    "INT": "Int16",
    "UINT": "UInt16",
    "WORD": "UInt16",
    "DINT": "Int32",
    "UDINT": "UInt32",
    "DWORD": "UInt32",
    "REAL": "Float",
    "LINT": "Int64",
    "ULINT": "UInt64",
    "LWORD": "UInt64",
    "LREAL": "Double",
    "STRING": "String",
    "WSTRING": "String",
    "TIME": "Int64",
    "DATE": "DateTime",
    "TOD": "Int64",
    "DT": "DateTime",
}


def _require_dict(
    value: Any,
    field_name: str,
) -> Dict[str, Any]:
    if not isinstance(value, dict):
        raise ValueError(
            f"{field_name} must be an object"
        )

    return value


def _require_list(
    value: Any,
    field_name: str,
) -> List[Any]:
    if not isinstance(value, list):
        raise ValueError(
            f"{field_name} must be an array"
        )

    return value


def _require_string(
    data: Dict[str, Any],
    field_name: str,
) -> str:
    if field_name not in data:
        raise ValueError(
            f"Missing required field: {field_name}"
        )

    value = data[field_name]

    if not isinstance(value, str):
        raise ValueError(
            f"{field_name} must be a string"
        )

    value = value.strip()

    if not value:
        raise ValueError(
            f"{field_name} cannot be empty"
        )

    return value


def _require_integer(
    data: Dict[str, Any],
    field_name: str,
    minimum: int = 0,
) -> int:
    if field_name not in data:
        raise ValueError(
            f"Missing required field: {field_name}"
        )

    value = data[field_name]

    if (
        not isinstance(value, int)
        or isinstance(value, bool)
    ):
        raise ValueError(
            f"{field_name} must be an integer"
        )

    if value < minimum:
        raise ValueError(
            f"{field_name} must be greater than "
            f"or equal to {minimum}"
        )

    return value


def _require_boolean(
    data: Dict[str, Any],
    field_name: str,
) -> bool:
    if field_name not in data:
        raise ValueError(
            f"Missing required field: {field_name}"
        )

    value = data[field_name]

    if not isinstance(value, bool):
        raise ValueError(
            f"{field_name} must be a boolean"
        )

    return value


@dataclass(frozen=True)
class SemanticProject:
    """Identity of the generated semantic project model."""

    project_id: str
    namespace_uri: str

    @classmethod
    def from_dict(
        cls,
        data: Dict[str, Any],
    ) -> "SemanticProject":
        return cls(
            project_id=_require_string(
                data,
                "id",
            ),
            namespace_uri=_require_string(
                data,
                "namespaceUri",
            ),
        )


@dataclass(frozen=True)
class RuntimeTarget:
    """Runtime family and version targeted by the binding."""

    runtime_type: str
    version: str

    @classmethod
    def from_dict(
        cls,
        data: Dict[str, Any],
    ) -> "RuntimeTarget":
        runtime_type = _require_string(
            data,
            "type",
        )

        if runtime_type != SUPPORTED_RUNTIME_TYPE:
            raise ValueError(
                "Unsupported runtime type: "
                f"{runtime_type!r}; expected "
                f"{SUPPORTED_RUNTIME_TYPE!r}"
            )

        return cls(
            runtime_type=runtime_type,
            version=_require_string(
                data,
                "version",
            ),
        )


@dataclass(frozen=True)
class ImportedNodeTarget:
    """Stable identity of a node imported from a project NodeSet."""

    namespace_uri: str
    identifier_type: str
    identifier: str

    @classmethod
    def from_dict(
        cls,
        data: Dict[str, Any],
    ) -> "ImportedNodeTarget":
        identifier_type = _require_string(
            data,
            "identifierType",
        )

        if (
            identifier_type
            not in SUPPORTED_IDENTIFIER_TYPES
        ):
            raise ValueError(
                "Unsupported NodeId identifier type: "
                f"{identifier_type!r}; supported types: "
                f"{sorted(SUPPORTED_IDENTIFIER_TYPES)}"
            )

        return cls(
            namespace_uri=_require_string(
                data,
                "namespaceUri",
            ),
            identifier_type=identifier_type,
            identifier=_require_string(
                data,
                "identifier",
            ),
        )


@dataclass(frozen=True)
class OpenPLCDebugLeaf:
    """Resolved OpenPLC STruC++ debug-table leaf."""

    kind: str
    symbol: str
    array_index: int
    element_index: int
    datatype: str
    size: int

    @classmethod
    def from_dict(
        cls,
        data: Dict[str, Any],
    ) -> "OpenPLCDebugLeaf":
        kind = _require_string(
            data,
            "kind",
        )

        if kind not in SUPPORTED_SOURCE_KINDS:
            raise ValueError(
                "Unsupported binding source kind: "
                f"{kind!r}; supported kinds: "
                f"{sorted(SUPPORTED_SOURCE_KINDS)}"
            )

        datatype = _require_string(
            data,
            "datatype",
        ).upper()

        if datatype not in IEC_TO_OPCUA_TYPE:
            raise ValueError(
                "Unsupported IEC datatype: "
                f"{datatype!r}"
            )

        size = _require_integer(
            data,
            "size",
            minimum=1,
        )

        expected_size = IEC_TYPE_SIZES.get(
            datatype
        )

        if (
            expected_size is not None
            and size != expected_size
        ):
            raise ValueError(
                f"Invalid size {size} for IEC datatype "
                f"{datatype}; expected {expected_size}"
            )

        array_index = _require_integer(
            data,
            "arrayIndex",
            minimum=0,
        )

        if array_index > 255:
            raise ValueError(
                "arrayIndex must fit the runtime "
                "uint8 address component"
            )

        element_index = _require_integer(
            data,
            "elementIndex",
            minimum=0,
        )

        if element_index > 65535:
            raise ValueError(
                "elementIndex must fit the runtime "
                "uint16 address component"
            )

        return cls(
            kind=kind,
            symbol=_require_string(
                data,
                "symbol",
            ),
            array_index=array_index,
            element_index=element_index,
            datatype=datatype,
            size=size,
        )

    @property
    def address(self) -> tuple[int, int]:
        return (
            self.array_index,
            self.element_index,
        )


@dataclass(frozen=True)
class BindingTypes:
    """IEC and OPC UA types expected by one binding."""

    iec: str
    opcua: str

    @classmethod
    def from_dict(
        cls,
        data: Dict[str, Any],
    ) -> "BindingTypes":
        iec_type = _require_string(
            data,
            "iec",
        ).upper()

        if iec_type not in IEC_TO_OPCUA_TYPE:
            raise ValueError(
                "Unsupported IEC binding type: "
                f"{iec_type!r}"
            )

        opcua_type = _require_string(
            data,
            "opcUa",
        )

        expected_opcua_type = (
            IEC_TO_OPCUA_TYPE[iec_type]
        )

        if opcua_type != expected_opcua_type:
            raise ValueError(
                f"IEC type {iec_type} requires OPC UA "
                f"type {expected_opcua_type}, not "
                f"{opcua_type}"
            )

        return cls(
            iec=iec_type,
            opcua=opcua_type,
        )


@dataclass(frozen=True)
class BindingAccess:
    """Allowed synchronization directions."""

    read: bool
    write: bool

    @classmethod
    def from_dict(
        cls,
        data: Dict[str, Any],
    ) -> "BindingAccess":
        read_enabled = _require_boolean(
            data,
            "read",
        )

        write_enabled = _require_boolean(
            data,
            "write",
        )

        if not read_enabled and not write_enabled:
            raise ValueError(
                "A binding must enable at least one "
                "access direction"
            )

        return cls(
            read=read_enabled,
            write=write_enabled,
        )

    @property
    def access_mode(self) -> str:
        if self.write:
            return "readwrite"

        return "readonly"


@dataclass(frozen=True)
class BindingUpdate:
    """Update strategy for subscriptions and cyclic pushes."""

    mode: str
    interval_ms: int

    @classmethod
    def from_dict(
        cls,
        data: Dict[str, Any],
    ) -> "BindingUpdate":
        mode = _require_string(
            data,
            "mode",
        )

        if mode not in SUPPORTED_UPDATE_MODES:
            raise ValueError(
                "Unsupported update mode: "
                f"{mode!r}; supported modes: "
                f"{sorted(SUPPORTED_UPDATE_MODES)}"
            )

        return cls(
            mode=mode,
            interval_ms=_require_integer(
                data,
                "intervalMs",
                minimum=1,
            ),
        )


@dataclass(frozen=True)
class SemanticBinding:
    """One imported OPC UA node to OpenPLC leaf binding."""

    binding_id: str
    target: ImportedNodeTarget
    source: OpenPLCDebugLeaf
    types: BindingTypes
    access: BindingAccess
    update: BindingUpdate

    @classmethod
    def from_dict(
        cls,
        data: Dict[str, Any],
    ) -> "SemanticBinding":
        target_data = _require_dict(
            data.get("nodeId"),
            "nodeId",
        )

        source_data = _require_dict(
            data.get("source"),
            "source",
        )

        types_data = _require_dict(
            data.get("types"),
            "types",
        )

        access_data = _require_dict(
            data.get("access"),
            "access",
        )

        update_data = _require_dict(
            data.get("update"),
            "update",
        )

        binding = cls(
            binding_id=_require_string(
                data,
                "id",
            ),
            target=ImportedNodeTarget.from_dict(
                target_data
            ),
            source=OpenPLCDebugLeaf.from_dict(
                source_data
            ),
            types=BindingTypes.from_dict(
                types_data
            ),
            access=BindingAccess.from_dict(
                access_data
            ),
            update=BindingUpdate.from_dict(
                update_data
            ),
        )

        binding.validate_consistency()

        return binding

    def validate_consistency(self) -> None:
        if (
            self.source.datatype
            != self.types.iec
        ):
            raise ValueError(
                f"Binding {self.binding_id!r} has "
                "inconsistent IEC types: source uses "
                f"{self.source.datatype}, types.iec uses "
                f"{self.types.iec}"
            )


@dataclass(frozen=True)
class SemanticBindingConfig:
    """Complete semantic binding artifact."""

    schema_version: str
    project: SemanticProject
    runtime: RuntimeTarget
    bindings: List[SemanticBinding]

    @classmethod
    def from_dict(
        cls,
        data: Dict[str, Any],
    ) -> "SemanticBindingConfig":
        schema_version = _require_string(
            data,
            "schemaVersion",
        )

        if (
            schema_version
            != SUPPORTED_SCHEMA_VERSION
        ):
            raise ValueError(
                "Unsupported semantic binding "
                f"schemaVersion {schema_version!r}; "
                f"expected {SUPPORTED_SCHEMA_VERSION!r}"
            )

        project_data = _require_dict(
            data.get("project"),
            "project",
        )

        runtime_data = _require_dict(
            data.get("runtime"),
            "runtime",
        )

        bindings_data = _require_list(
            data.get("bindings"),
            "bindings",
        )

        if not bindings_data:
            raise ValueError(
                "bindings cannot be empty"
            )

        bindings = []

        for index, binding_data in enumerate(
            bindings_data
        ):
            try:
                parsed_binding = (
                    SemanticBinding.from_dict(
                        _require_dict(
                            binding_data,
                            (
                                "bindings"
                                f"[{index}]"
                            ),
                        )
                    )
                )
            except ValueError as exception:
                raise ValueError(
                    f"Invalid binding at index "
                    f"{index}: {exception}"
                ) from exception

            bindings.append(
                parsed_binding
            )

        config = cls(
            schema_version=schema_version,
            project=SemanticProject.from_dict(
                project_data
            ),
            runtime=RuntimeTarget.from_dict(
                runtime_data
            ),
            bindings=bindings,
        )

        config.validate_consistency()

        return config

    def validate_consistency(self) -> None:
        identifiers = set()
        addresses = set()

        for binding in self.bindings:
            if (
                binding.target.namespace_uri
                != self.project.namespace_uri
            ):
                raise ValueError(
                    f"Binding {binding.binding_id!r} "
                    "targets namespace "
                    f"{binding.target.namespace_uri!r}, "
                    "but the project namespace is "
                    f"{self.project.namespace_uri!r}"
                )

            target_key = (
                binding.target.namespace_uri,
                binding.target.identifier_type,
                binding.target.identifier,
            )

            if target_key in identifiers:
                raise ValueError(
                    "Duplicate imported NodeId target "
                    f"in binding {binding.binding_id!r}"
                )

            identifiers.add(
                target_key
            )

            address = binding.source.address

            if address in addresses:
                raise ValueError(
                    "Duplicate OpenPLC debug address "
                    f"{address} in binding "
                    f"{binding.binding_id!r}"
                )

            addresses.add(
                address
            )


def load_semantic_binding_config(
    path: str | Path,
) -> SemanticBindingConfig:
    """Load and validate one semantic binding JSON file."""

    binding_path = Path(path).expanduser().resolve()

    if not binding_path.exists():
        raise FileNotFoundError(
            "Semantic binding file does not exist: "
            f"{binding_path}"
        )

    if not binding_path.is_file():
        raise ValueError(
            "Semantic binding path is not a regular "
            f"file: {binding_path}"
        )

    if binding_path.suffix.lower() != ".json":
        raise ValueError(
            "Semantic binding file must use the "
            f".json extension: {binding_path}"
        )

    try:
        raw_data = json.loads(
            binding_path.read_text(
                encoding="utf-8",
            )
        )
    except json.JSONDecodeError as exception:
        raise ValueError(
            "Invalid semantic binding JSON in "
            f"{binding_path}: {exception}"
        ) from exception

    return SemanticBindingConfig.from_dict(
        _require_dict(
            raw_data,
            "root",
        )
    )
