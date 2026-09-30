from __future__ import annotations

import hashlib
from pathlib import Path


REPOSITORY_ROOT = Path.cwd()

NODESET_PATH = (
    REPOSITORY_ROOT
    / "models"
    / "generated"
    / "Test.PADIMDevice.NodeSet2.xml"
)

VALIDATION_LOG_PATH = (
    REPOSITORY_ROOT
    / "evidence"
    / "padim-stack"
    / "validate-padim-device-nodeset.log"
)

PARENT_LOG_PATH = (
    REPOSITORY_ROOT
    / "evidence"
    / "padim-stack"
    / "padim-nodeset-parent-inspection.log"
)

STATUS_PATH = (
    REPOSITORY_ROOT
    / "evidence"
    / "padim-stack"
    / "padim-device-nodeset-status.txt"
)

EXPECTED_NODESET_SHA256 = (
    "010f20c8f0349b57fd9c444956155561"
    "11df2d4053039bddfda66c966bad3c45"
)

STATUS_CONTENT = """PADIM PT101 project NodeSet

File:
models/generated/Test.PADIMDevice.NodeSet2.xml

Project namespace:
urn:openplc:test:padim-device

Project model version:
1.0.0

SHA-256:
010f20c8f0349b57fd9c44495615556111df2d4053039bddfda66c966bad3c45

Project nodes:
19

Root hierarchy:
Objects
└── PADIMDevices
    └── PT101

Required models:
DI 1.05.0
IRDI 1.02.0
PADIM 1.02.0

Semantic hierarchy:
PT101 : PADIMType
SignalSet : SignalSetType
Pressure : AnalogSignalType
AnalogSignal : PressureMeasurementVariableType
SignalTag : PADIM SignalTag declaration

AnalogSignal:
Value: 12.5
DataType: Float
Unit: bar
Range: 0.0 to 16.0

Validation:
Generator exit code was 0.
Generator completed without traceback.
XML structure inspection passed.
All ParentNodeId references resolved.
NodeSet reimport validation passed.
Semantic TypeDefinition validation passed.
Metadata validation passed.
Structured-value validation passed.

Status:
Approved project NodeSet.
"""


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


def require_nonempty_file(
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


def require_log_result(
    path: Path,
    expected_text: str,
) -> None:
    content = path.read_text(
        encoding="utf-8",
        errors="replace",
    )

    if expected_text not in content:
        raise RuntimeError(
            "Expected result is missing from "
            f"{path}: {expected_text!r}"
        )


def main() -> None:
    require_nonempty_file(
        "PADIM project NodeSet",
        NODESET_PATH,
    )

    require_nonempty_file(
        "NodeSet validation log",
        VALIDATION_LOG_PATH,
    )

    require_nonempty_file(
        "Parent inspection log",
        PARENT_LOG_PATH,
    )

    actual_sha256 = calculate_sha256(
        NODESET_PATH
    )

    if actual_sha256 != EXPECTED_NODESET_SHA256:
        raise RuntimeError(
            "Unexpected NodeSet SHA-256. "
            f"Expected {EXPECTED_NODESET_SHA256}, "
            f"found {actual_sha256}"
        )

    require_log_result(
        VALIDATION_LOG_PATH,
        (
            "Complete PADIM PT101 NodeSet "
            "import validation passed"
        ),
    )

    require_log_result(
        PARENT_LOG_PATH,
        (
            "PASS: all ParentNodeId "
            "references are resolvable"
        ),
    )

    STATUS_PATH.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    STATUS_PATH.write_text(
        STATUS_CONTENT,
        encoding="utf-8",
    )

    written_content = STATUS_PATH.read_text(
        encoding="utf-8",
    )

    if written_content != STATUS_CONTENT:
        raise RuntimeError(
            "Written status content differs "
            "from the approved content"
        )

    print(
        "PASS: PADIM NodeSet status written"
    )
    print(
        "Status file:",
        STATUS_PATH,
    )
    print(
        "NodeSet SHA-256:",
        actual_sha256,
    )


if __name__ == "__main__":
    main()
