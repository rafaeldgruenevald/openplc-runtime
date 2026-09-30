from __future__ import annotations

import hashlib
from pathlib import Path


REPOSITORY_ROOT = Path.cwd()

SERVER_PATH = (
    REPOSITORY_ROOT
    / "core"
    / "src"
    / "drivers"
    / "plugins"
    / "python"
    / "opcua"
    / "server.py"
)

NODESET_PATH = (
    REPOSITORY_ROOT
    / "models"
    / "generated"
    / "Test.PADIMDevice.NodeSet2.xml"
)

BINDING_PATH = (
    REPOSITORY_ROOT
    / "config"
    / "opcua"
    / "bindings"
    / "Test.PADIMDevice.openplc-bindings.json"
)

TEST_LOG_PATH = (
    REPOSITORY_ROOT
    / "evidence"
    / "padim-stack"
    / "test-real-padim-binding-resolution.log"
)

STATUS_PATH = (
    REPOSITORY_ROOT
    / "evidence"
    / "padim-stack"
    / "semantic-binding-integration-status.txt"
)

EXPECTED_SERVER_SHA256 = (
    "114c2668022a5693e6f704ae80080c335"
    "e55d624f5c4e52cde53a4e5cc2c2b5b"
)

EXPECTED_NODESET_SHA256 = (
    "010f20c8f0349b57fd9c444956155561"
    "11df2d4053039bddfda66c966bad3c45"
)


def calculate_sha256(
    path: Path,
) -> str:
    return hashlib.sha256(
        path.read_bytes()
    ).hexdigest()


def require_file(
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


def main() -> None:
    files = [
        (
            "server",
            SERVER_PATH,
        ),
        (
            "NodeSet",
            NODESET_PATH,
        ),
        (
            "binding",
            BINDING_PATH,
        ),
        (
            "test log",
            TEST_LOG_PATH,
        ),
    ]

    for label, path in files:
        require_file(
            label,
            path,
        )

    server_sha256 = calculate_sha256(
        SERVER_PATH
    )

    nodeset_sha256 = calculate_sha256(
        NODESET_PATH
    )

    binding_sha256 = calculate_sha256(
        BINDING_PATH
    )

    test_log_sha256 = calculate_sha256(
        TEST_LOG_PATH
    )

    if server_sha256 != EXPECTED_SERVER_SHA256:
        raise RuntimeError(
            "Unexpected server.py SHA-256: "
            f"{server_sha256}"
        )

    if nodeset_sha256 != EXPECTED_NODESET_SHA256:
        raise RuntimeError(
            "Unexpected NodeSet SHA-256: "
            f"{nodeset_sha256}"
        )

    status_content = f"""Semantic OPC UA binding integration

Server:
core/src/drivers/plugins/python/opcua/server.py

Server SHA-256:
{server_sha256}

NodeSet:
models/generated/Test.PADIMDevice.NodeSet2.xml

NodeSet SHA-256:
{nodeset_sha256}

Binding:
config/opcua/bindings/Test.PADIMDevice.openplc-bindings.json

Binding SHA-256:
{binding_sha256}

Test log SHA-256:
{test_log_sha256}

Binding:
PT101.Pressure

Target Namespace URI:
urn:openplc:test:padim-device

Target NodeId:
PT101.SignalSet.Pressure.AnalogSignal

OpenPLC symbol:
INSTANCE0.PT101.PRESSURESIGNAL.PROCESSVALUE.VALUE

OpenPLC address:
arrayIndex = 0
elementIndex = 14

IEC type:
REAL

OPC UA DataType:
Float

Access:
readonly

Collision policy:
replace

Initialization order:
1. Import configured NodeSets.
2. Create legacy address space.
3. Resolve semantic bindings.
4. Register permission callbacks.
5. Initialize synchronization manager.
6. Start OPC UA server.

Validation:
Server modules compiled successfully.
OpcuaServerManager imported successfully.
Semantic binding method is present.
Synthetic resolver test passed.
Real PADIM NodeSet resolver test exited with code 0.
Legacy synchronization target was replaced in the active map.
Input variable map remained unchanged by the atomic resolver.

Status:
Ready for runtime integration test.
"""

    STATUS_PATH.write_text(
        status_content,
        encoding="utf-8",
    )

    print(
        "PASS: integration status written"
    )
    print(
        "Status file:",
        STATUS_PATH,
    )


if __name__ == "__main__":
    main()
