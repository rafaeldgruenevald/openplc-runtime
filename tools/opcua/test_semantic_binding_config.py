from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from types import ModuleType
from typing import Any


REPOSITORY_ROOT = Path.cwd()

MODULE_PATH = (
    REPOSITORY_ROOT
    / "core"
    / "src"
    / "drivers"
    / "plugins"
    / "python"
    / "opcua"
    / "semantic_binding_config.py"
)

BINDING_PATH = (
    REPOSITORY_ROOT
    / "config"
    / "opcua"
    / "bindings"
    / "Test.PADIMDevice.openplc-bindings.json"
)

MODULE_NAME = (
    "openplc_semantic_binding_config_test"
)


def load_module_from_path(
    module_name: str,
    module_path: Path,
) -> ModuleType:
    if not module_path.is_file():
        raise FileNotFoundError(
            f"Module file does not exist: "
            f"{module_path}"
        )

    specification = (
        importlib.util.spec_from_file_location(
            module_name,
            module_path,
        )
    )

    if specification is None:
        raise RuntimeError(
            "Could not create module specification "
            f"for {module_path}"
        )

    loader = specification.loader

    if loader is None:
        raise RuntimeError(
            "Module specification does not provide "
            f"a loader for {module_path}"
        )

    module = (
        importlib.util.module_from_spec(
            specification
        )
    )

    
     # Dataclasses inspect sys.modules while processing
     # type metadata. Register the module before executing
     # it, matching normal Python import behavior.
    sys.modules[module_name] = module

    try:
        loader.exec_module(module)
    except Exception:
        sys.modules.pop(
            module_name,
            None,
        )
        raise

    return module


def check(
    results: list[tuple[str, bool]],
    name: str,
    condition: Any,
) -> None:
    results.append(
        (
            name,
            bool(condition),
        )
    )


def expect_value_error(
    name: str,
    callback: Any,
    expected_fragment: str,
) -> tuple[str, bool]:
    try:
        callback()
    except ValueError as exception:
        message = str(exception)

        passed = (
            expected_fragment
            in message
        )

        if not passed:
            print()
            print(
                "Unexpected validation message:"
            )
            print(" ", message)

        return (
            name,
            passed,
        )

    return (
        name,
        False,
    )


def test_valid_binding(
    module: ModuleType,
) -> list[tuple[str, bool]]:
    config = (
        module.load_semantic_binding_config(
            BINDING_PATH
        )
    )

    binding = config.bindings[0]

    results: list[tuple[str, bool]] = []

    check(
        results,
        "schema version",
        config.schema_version == "1.0",
    )

    check(
        results,
        "project id",
        config.project.project_id
        == "padim-pressure-test",
    )

    check(
        results,
        "project namespace",
        config.project.namespace_uri
        == "urn:openplc:test:padim-device",
    )

    check(
        results,
        "runtime type",
        config.runtime.runtime_type
        == "openplc",
    )

    check(
        results,
        "runtime version",
        config.runtime.version
        == "4.0.0",
    )

    check(
        results,
        "binding count",
        len(config.bindings) == 1,
    )

    check(
        results,
        "binding id",
        binding.binding_id
        == "PT101.Pressure",
    )

    check(
        results,
        "target namespace",
        binding.target.namespace_uri
        == "urn:openplc:test:padim-device",
    )

    check(
        results,
        "target identifier type",
        binding.target.identifier_type
        == "String",
    )

    check(
        results,
        "target identifier",
        binding.target.identifier
        == (
            "PT101.SignalSet."
            "Pressure.AnalogSignal"
        ),
    )

    check(
        results,
        "source kind",
        binding.source.kind
        == "openplc-debug-leaf",
    )

    check(
        results,
        "canonical symbol",
        binding.source.symbol
        == (
            "INSTANCE0.PT101."
            "PRESSURESIGNAL."
            "PROCESSVALUE.VALUE"
        ),
    )

    check(
        results,
        "debug address",
        binding.source.address
        == (0, 14),
    )

    check(
        results,
        "array index",
        binding.source.array_index == 0,
    )

    check(
        results,
        "element index",
        binding.source.element_index == 14,
    )

    check(
        results,
        "source datatype",
        binding.source.datatype
        == "REAL",
    )

    check(
        results,
        "source size",
        binding.source.size == 4,
    )

    check(
        results,
        "IEC binding type",
        binding.types.iec == "REAL",
    )

    check(
        results,
        "OPC UA binding type",
        binding.types.opcua == "Float",
    )

    check(
        results,
        "read enabled",
        binding.access.read is True,
    )

    check(
        results,
        "write disabled",
        binding.access.write is False,
    )

    check(
        results,
        "readonly access mode",
        binding.access.access_mode
        == "readonly",
    )

    check(
        results,
        "update mode",
        binding.update.mode
        == "subscription-aware",
    )

    check(
        results,
        "update interval",
        binding.update.interval_ms == 100,
    )

    return results


def test_invalid_configurations(
    module: ModuleType,
) -> list[tuple[str, bool]]:
    valid_root = {
        "schemaVersion": "1.0",
        "project": {
            "id": "test-project",
            "namespaceUri": (
                "urn:openplc:test:model"
            ),
        },
        "runtime": {
            "type": "openplc",
            "version": "4.0.0",
        },
        "bindings": [
            {
                "id": "Test.Value",
                "nodeId": {
                    "namespaceUri": (
                        "urn:openplc:test:model"
                    ),
                    "identifierType": "String",
                    "identifier": "Test.Value",
                },
                "source": {
                    "kind": (
                        "openplc-debug-leaf"
                    ),
                    "symbol": (
                        "INSTANCE0.TEST.VALUE"
                    ),
                    "arrayIndex": 0,
                    "elementIndex": 1,
                    "datatype": "REAL",
                    "size": 4,
                },
                "types": {
                    "iec": "REAL",
                    "opcUa": "Float",
                },
                "access": {
                    "read": True,
                    "write": False,
                },
                "update": {
                    "mode": (
                        "subscription-aware"
                    ),
                    "intervalMs": 100,
                },
            }
        ],
    }

    tests: list[tuple[str, bool]] = []

    wrong_schema = {
        **valid_root,
        "schemaVersion": "2.0",
    }

    tests.append(
        expect_value_error(
            "reject unsupported schema",
            lambda: (
                module.SemanticBindingConfig
                .from_dict(
                    wrong_schema
                )
            ),
            "Unsupported semantic binding",
        )
    )

    wrong_runtime = {
        **valid_root,
        "runtime": {
            "type": "codesys",
            "version": "1.0",
        },
    }

    tests.append(
        expect_value_error(
            "reject wrong runtime",
            lambda: (
                module.SemanticBindingConfig
                .from_dict(
                    wrong_runtime
                )
            ),
            "Unsupported runtime type",
        )
    )

    wrong_size = {
        **valid_root,
        "bindings": [
            {
                **valid_root["bindings"][0],
                "source": {
                    **valid_root[
                        "bindings"
                    ][0]["source"],
                    "size": 8,
                },
            }
        ],
    }

    tests.append(
        expect_value_error(
            "reject invalid REAL size",
            lambda: (
                module.SemanticBindingConfig
                .from_dict(
                    wrong_size
                )
            ),
            "expected 4",
        )
    )

    wrong_opcua_type = {
        **valid_root,
        "bindings": [
            {
                **valid_root["bindings"][0],
                "types": {
                    "iec": "REAL",
                    "opcUa": "Double",
                },
            }
        ],
    }

    tests.append(
        expect_value_error(
            "reject incompatible OPC UA type",
            lambda: (
                module.SemanticBindingConfig
                .from_dict(
                    wrong_opcua_type
                )
            ),
            "requires OPC UA type Float",
        )
    )

    wrong_namespace = {
        **valid_root,
        "bindings": [
            {
                **valid_root["bindings"][0],
                "nodeId": {
                    **valid_root[
                        "bindings"
                    ][0]["nodeId"],
                    "namespaceUri": (
                        "urn:other:model"
                    ),
                },
            }
        ],
    }

    tests.append(
        expect_value_error(
            "reject target namespace mismatch",
            lambda: (
                module.SemanticBindingConfig
                .from_dict(
                    wrong_namespace
                )
            ),
            "project namespace",
        )
    )

    access_disabled = {
        **valid_root,
        "bindings": [
            {
                **valid_root["bindings"][0],
                "access": {
                    "read": False,
                    "write": False,
                },
            }
        ],
    }

    tests.append(
        expect_value_error(
            "reject disabled binding",
            lambda: (
                module.SemanticBindingConfig
                .from_dict(
                    access_disabled
                )
            ),
            "at least one access direction",
        )
    )

    return tests


def print_results(
    title: str,
    results: list[tuple[str, bool]],
) -> bool:
    print()
    print(title)

    failed = False

    for name, passed in results:
        print(
            "  PASS" if passed else "  FAIL",
            name,
        )

        if not passed:
            failed = True

    return not failed


def main() -> None:
    print("Semantic binding parser test")
    print("Module path:", MODULE_PATH)
    print("Binding path:", BINDING_PATH)

    module = load_module_from_path(
        MODULE_NAME,
        MODULE_PATH,
    )

    valid_results = test_valid_binding(
        module
    )

    invalid_results = (
        test_invalid_configurations(
            module
        )
    )

    valid_passed = print_results(
        "Valid binding checks:",
        valid_results,
    )

    invalid_passed = print_results(
        "Invalid binding checks:",
        invalid_results,
    )

    if not valid_passed or not invalid_passed:
        raise SystemExit(
            "Semantic binding parser test failed"
        )

    print()
    print(
        "Semantic binding parser passed"
    )


if __name__ == "__main__":
    main()
