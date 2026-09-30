from __future__ import annotations

import hashlib
from pathlib import Path


REPOSITORY_ROOT = Path.cwd()

OUTPUT_PATH = (
    REPOSITORY_ROOT
    / "evidence"
    / "padim-stack"
    / "server-binding-context.txt"
)

FILES = [
    (
        "server.py",
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
        "opcua_types.py",
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
        "synchronization.py",
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
        "address_space.py",
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
        "nodeset_loader.py",
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
        "semantic_binding_config.py",
        REPOSITORY_ROOT
        / "core"
        / "src"
        / "drivers"
        / "plugins"
        / "python"
        / "opcua"
        / "semantic_binding_config.py",
    ),
    (
        "imported_node_bindings.py",
        REPOSITORY_ROOT
        / "core"
        / "src"
        / "drivers"
        / "plugins"
        / "python"
        / "opcua"
        / "imported_node_bindings.py",
    ),
]


def calculate_sha256(
    path: Path,
) -> str:
    digest = hashlib.sha256(
        path.read_bytes()
    )

    return digest.hexdigest()


def main() -> None:
    output = [
        "OpenPLC OPC UA server binding context",
        "",
    ]

    for label, path in FILES:
        if not path.is_file():
            raise FileNotFoundError(
                f"Missing source file: {path}"
            )

        content = path.read_text(
            encoding="utf-8",
            errors="replace",
        )

        output.extend(
            [
                "=" * 80,
                label,
                "=" * 80,
                f"Path: {path}",
                (
                    "SHA-256: "
                    + calculate_sha256(path)
                ),
                (
                    "Lines: "
                    + str(
                        len(
                            content.splitlines()
                        )
                    )
                ),
                "",
                content.rstrip(),
                "",
            ]
        )

    final_content = (
        "\n".join(output)
        + "\n"
    )

    OUTPUT_PATH.write_text(
        final_content,
        encoding="utf-8",
    )

    print(
        "PASS: server binding context written"
    )
    print(
        "Output:",
        OUTPUT_PATH,
    )
    print(
        "Lines:",
        len(
            final_content.splitlines()
        ),
    )
    print(
        "SHA-256:",
        calculate_sha256(
            OUTPUT_PATH
        ),
    )


if __name__ == "__main__":
    main()
