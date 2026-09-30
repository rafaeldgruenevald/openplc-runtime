from __future__ import annotations

import hashlib
import json
from pathlib import Path


REPOSITORY_ROOT = Path.cwd()

EVIDENCE_DIRECTORY = (
    REPOSITORY_ROOT
    / "evidence"
    / "padim-stack"
)

OUTPUT_PATH = (
    EVIDENCE_DIRECTORY
    / "runtime-binding-context.txt"
)

REQUIRED_SOURCE_FILES = [
    (
        "OPC UA server",
        REPOSITORY_ROOT
        / "core"
        / "src"
        / "drivers"
        / "plugins"
        / "python"
        / "opcua"
        / "server.py",
    ),
    (
        "Synchronization manager",
        REPOSITORY_ROOT
        / "core"
        / "src"
        / "drivers"
        / "plugins"
        / "python"
        / "opcua"
        / "synchronization.py",
    ),
    (
        "OPC UA internal types",
        REPOSITORY_ROOT
        / "core"
        / "src"
        / "drivers"
        / "plugins"
        / "python"
        / "opcua"
        / "opcua_types.py",
    ),
    (
        "Address-space builder",
        REPOSITORY_ROOT
        / "core"
        / "src"
        / "drivers"
        / "plugins"
        / "python"
        / "opcua"
        / "address_space.py",
    ),
    (
        "NodeSet loader",
        REPOSITORY_ROOT
        / "core"
        / "src"
        / "drivers"
        / "plugins"
        / "python"
        / "opcua"
        / "nodeset_loader.py",
    ),
    (
        "OPC UA configuration model",
        REPOSITORY_ROOT
        / "core"
        / "src"
        / "drivers"
        / "plugins"
        / "python"
        / "shared"
        / "plugin_config_decode"
        / "opcua_config_model.py",
    ),
]

OPTIONAL_JSON_FILES = [
    (
        "Resolved semantic binding",
        REPOSITORY_ROOT
        / "config"
        / "opcua"
        / "bindings"
        / "Test.PADIMDevice.openplc-bindings.json",
    ),
    (
        "Current generated OPC UA configuration",
        EVIDENCE_DIRECTORY
        / "current-opcua-config.json",
    ),
    (
        "Current generated debug map",
        EVIDENCE_DIRECTORY
        / "debug-map.json",
    ),
]

OPTIONAL_TEXT_FILES = [
    (
        "Server structure",
        EVIDENCE_DIRECTORY
        / "server-structure.txt",
    ),
    (
        "Synchronization structure",
        EVIDENCE_DIRECTORY
        / "synchronization-structure.txt",
    ),
    (
        "Address-space structure",
        EVIDENCE_DIRECTORY
        / "address-space-structure.txt",
    ),
    (
        "Configuration-model structure",
        EVIDENCE_DIRECTORY
        / "opcua-config-model-structure.txt",
    ),
    (
        "Runtime baseline hashes",
        EVIDENCE_DIRECTORY
        / "runtime-baseline.sha256",
    ),
    (
        "Debug API usage",
        EVIDENCE_DIRECTORY
        / "debug-api-usage.txt",
    ),
    (
        "Runtime communication",
        EVIDENCE_DIRECTORY
        / "runtime-communication.txt",
    ),
    (
        "Existing OPC UA implementation",
        EVIDENCE_DIRECTORY
        / "existing-opcua-implementation.txt",
    ),
    (
        "PLC library loading",
        EVIDENCE_DIRECTORY
        / "plc-library-loading.txt",
    ),
    (
        "Container startup",
        EVIDENCE_DIRECTORY
        / "openplc-container-startup.txt",
    ),
]


def calculate_sha256(path: Path) -> str:
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


def relative_path(path: Path) -> str:
    try:
        return str(
            path.relative_to(
                REPOSITORY_ROOT
            )
        )
    except ValueError:
        return str(path)


def append_heading(
    output: list[str],
    level: int,
    title: str,
) -> None:
    output.append(
        f"{'#' * level} {title}"
    )
    output.append("")


def append_text_file(
    output: list[str],
    title: str,
    path: Path,
    required: bool,
) -> None:
    append_heading(
        output,
        2,
        title,
    )

    output.append(
        f"Path: {relative_path(path)}"
    )

    if not path.is_file():
        output.append(
            "Status: missing"
        )
        output.append("")

        if required:
            raise FileNotFoundError(path)

        return

    content = path.read_text(
        encoding="utf-8",
        errors="replace",
    )

    output.append(
        f"SHA-256: {calculate_sha256(path)}"
    )
    output.append(
        f"Lines: {len(content.splitlines())}"
    )
    output.append("")
    output.append("BEGIN FILE CONTENT")
    output.append(content.rstrip())
    output.append("END FILE CONTENT")
    output.append("")


def append_json_file(
    output: list[str],
    title: str,
    path: Path,
) -> None:
    append_heading(
        output,
        2,
        title,
    )

    output.append(
        f"Path: {relative_path(path)}"
    )

    if not path.is_file():
        output.append(
            "Status: missing"
        )
        output.append("")
        return

    raw_content = path.read_text(
        encoding="utf-8",
        errors="replace",
    )

    output.append(
        f"SHA-256: {calculate_sha256(path)}"
    )

    try:
        data = json.loads(
            raw_content
        )
    except json.JSONDecodeError as exception:
        output.append(
            "Status: invalid JSON"
        )
        output.append(
            f"Error: {exception}"
        )
        output.append("")
        output.append("BEGIN FILE CONTENT")
        output.append(raw_content.rstrip())
        output.append("END FILE CONTENT")
        output.append("")
        return

    normalized_content = json.dumps(
        data,
        indent=2,
        ensure_ascii=False,
        sort_keys=False,
    )

    output.append(
        "Status: valid JSON"
    )
    output.append("")
    output.append("BEGIN JSON CONTENT")
    output.append(
        normalized_content
    )
    output.append("END JSON CONTENT")
    output.append("")


def verify_required_sources() -> None:
    missing_sources = [
        path
        for _, path in REQUIRED_SOURCE_FILES
        if not path.is_file()
    ]

    if not missing_sources:
        print(
            "PASS: all required sources exist"
        )
        return

    print(
        "FAIL: required source files are missing"
    )

    for path in missing_sources:
        print(
            " ",
            path,
        )

    raise SystemExit(1)


def build_context() -> str:
    output: list[str] = []

    append_heading(
        output,
        1,
        "OpenPLC OPC UA Runtime Binding Context",
    )

    output.extend(
        [
            (
                "This file contains the exact runtime "
                "sources and artifacts required to implement "
                "semantic NodeSet bindings."
            ),
            "",
        ]
    )

    append_heading(
        output,
        2,
        "Implementation objective",
    )

    output.extend(
        [
            "1. Load standardized and project NodeSets.",
            (
                "2. Resolve imported OPC UA variables by "
                "Namespace URI and NodeId."
            ),
            (
                "3. Bind imported nodes to OpenPLC "
                "debug leaves."
            ),
            (
                "4. Reuse the existing synchronization "
                "manager."
            ),
            (
                "5. Avoid creating duplicate OPC UA nodes."
            ),
            (
                "6. Preserve future CODESYS export support."
            ),
            "",
        ]
    )

    append_heading(
        output,
        2,
        "First binding target",
    )

    output.extend(
        [
            (
                "OPC UA node: "
                "PT101.SignalSet.Pressure.AnalogSignal"
            ),
            (
                "IEC symbol: "
                "INSTANCE0.PT101.PRESSURESIGNAL."
                "PROCESSVALUE.VALUE"
            ),
            "OpenPLC debug array index: 0",
            "OpenPLC debug element index: 14",
            "IEC type: REAL",
            "OPC UA DataType: Float",
            "Initial direction: PLC to OPC UA",
            "",
        ]
    )

    append_heading(
        output,
        1,
        "Required runtime sources",
    )

    for title, path in REQUIRED_SOURCE_FILES:
        append_text_file(
            output,
            title,
            path,
            required=True,
        )

    append_heading(
        output,
        1,
        "Generated JSON artifacts",
    )

    for title, path in OPTIONAL_JSON_FILES:
        append_json_file(
            output,
            title,
            path,
        )

    append_heading(
        output,
        1,
        "Supporting evidence",
    )

    for title, path in OPTIONAL_TEXT_FILES:
        append_text_file(
            output,
            title,
            path,
            required=False,
        )

    return "\n".join(output) + "\n"


def validate_output(
    content: str,
) -> None:
    required_titles = [
        "OPC UA server",
        "Synchronization manager",
        "OPC UA internal types",
        "Address-space builder",
        "NodeSet loader",
        "OPC UA configuration model",
    ]

    failed = False

    for title in required_titles:
        present = title in content

        print(
            "PASS" if present else "FAIL",
            "context contains",
            title,
        )

        if not present:
            failed = True

    if failed:
        raise SystemExit(
            "Context validation failed"
        )


def main() -> None:
    print(
        "Repository root:",
        REPOSITORY_ROOT,
    )

    verify_required_sources()

    EVIDENCE_DIRECTORY.mkdir(
        parents=True,
        exist_ok=True,
    )

    content = build_context()

    validate_output(content)

    OUTPUT_PATH.write_text(
        content,
        encoding="utf-8",
    )

    if not OUTPUT_PATH.is_file():
        raise SystemExit(
            "FAIL: output file was not created"
        )

    output_size = OUTPUT_PATH.stat().st_size

    if output_size == 0:
        raise SystemExit(
            "FAIL: output file is empty"
        )

    print()
    print(
        "Runtime binding context written:"
    )
    print(
        " ",
        OUTPUT_PATH,
    )
    print(
        "Size:",
        output_size,
        "bytes",
    )
    print(
        "Lines:",
        len(content.splitlines()),
    )
    print(
        "SHA-256:",
        calculate_sha256(
            OUTPUT_PATH
        ),
    )


if __name__ == "__main__":
    main()

