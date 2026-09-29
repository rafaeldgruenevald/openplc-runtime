from __future__ import annotations

import hashlib
import re
import shutil
from pathlib import Path


REPOSITORY_ROOT = Path.cwd()

EVIDENCE_ROOT = (
    REPOSITORY_ROOT
    / "evidence"
    / "padim-stack"
)

BASELINE_DIRECTORY = (
    EVIDENCE_ROOT
    / "runtime-baseline"
)

SOURCE_FILES = {
    "server.py": (
        REPOSITORY_ROOT
        / "core"
        / "src"
        / "drivers"
        / "plugins"
        / "python"
        / "opcua"
        / "server.py"
    ),
    "synchronization.py": (
        REPOSITORY_ROOT
        / "core"
        / "src"
        / "drivers"
        / "plugins"
        / "python"
        / "opcua"
        / "synchronization.py"
    ),
    "opcua_types.py": (
        REPOSITORY_ROOT
        / "core"
        / "src"
        / "drivers"
        / "plugins"
        / "python"
        / "opcua"
        / "opcua_types.py"
    ),
    "opcua_config_model.py": (
        REPOSITORY_ROOT
        / "core"
        / "src"
        / "drivers"
        / "plugins"
        / "python"
        / "shared"
        / "plugin_config_decode"
        / "opcua_config_model.py"
    ),
    "nodeset_loader.py": (
        REPOSITORY_ROOT
        / "core"
        / "src"
        / "drivers"
        / "plugins"
        / "python"
        / "opcua"
        / "nodeset_loader.py"
    ),
    "address_space.py": (
        REPOSITORY_ROOT
        / "core"
        / "src"
        / "drivers"
        / "plugins"
        / "python"
        / "opcua"
        / "address_space.py"
    ),
}

STRUCTURE_OUTPUTS = {
    "server.py": (
        EVIDENCE_ROOT
        / "server-structure.txt"
    ),
    "synchronization.py": (
        EVIDENCE_ROOT
        / "synchronization-structure.txt"
    ),
    "address_space.py": (
        EVIDENCE_ROOT
        / "address-space-structure.txt"
    ),
    "opcua_config_model.py": (
        EVIDENCE_ROOT
        / "opcua-config-model-structure.txt"
    ),
}

FULL_TEXT_OUTPUTS = {
    "server.py": (
        EVIDENCE_ROOT
        / "current-server.py.txt"
    ),
    "synchronization.py": (
        EVIDENCE_ROOT
        / "current-synchronization.py.txt"
    ),
    "opcua_types.py": (
        EVIDENCE_ROOT
        / "current-opcua-types.py.txt"
    ),
    "opcua_config_model.py": (
        EVIDENCE_ROOT
        / "current-opcua-config-model.py.txt"
    ),
    "address_space.py": (
        EVIDENCE_ROOT
        / "current-address-space.py.txt"
    ),
    "nodeset_loader.py": (
        EVIDENCE_ROOT
        / "current-nodeset-loader.py.txt"
    ),
}

DEFINITION_PATTERN = re.compile(
    r"^(class |    async def |    def )"
)


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


def verify_sources() -> None:
    missing_files = []

    for destination_name, source_path in (
        SOURCE_FILES.items()
    ):
        if not source_path.is_file():
            missing_files.append(
                (
                    destination_name,
                    source_path,
                )
            )

    if not missing_files:
        return

    print("Missing source files:")

    for destination_name, source_path in (
        missing_files
    ):
        print(
            f"  {destination_name}: "
            f"{source_path}"
        )

    raise SystemExit(1)


def reset_baseline_directory() -> None:
    EVIDENCE_ROOT.mkdir(
        parents=True,
        exist_ok=True,
    )

    if BASELINE_DIRECTORY.exists():
        shutil.rmtree(
            BASELINE_DIRECTORY
        )

    BASELINE_DIRECTORY.mkdir(
        parents=True,
        exist_ok=True,
    )


def copy_baseline_files() -> None:
    print()
    print("Copying baseline files:")

    for destination_name, source_path in (
        SOURCE_FILES.items()
    ):
        destination_path = (
            BASELINE_DIRECTORY
            / destination_name
        )

        shutil.copy2(
            source_path,
            destination_path,
        )

        print(
            f"  {source_path}"
            f" -> {destination_path}"
        )


def write_hash_manifest() -> Path:
    manifest_path = (
        EVIDENCE_ROOT
        / "runtime-baseline.sha256"
    )

    entries = []

    for destination_name in sorted(
        SOURCE_FILES
    ):
        baseline_path = (
            BASELINE_DIRECTORY
            / destination_name
        )

        digest = calculate_sha256(
            baseline_path
        )

        relative_path = (
            baseline_path.relative_to(
                REPOSITORY_ROOT
            )
        )

        entries.append(
            f"{digest}  {relative_path}"
        )

    manifest_path.write_text(
        "\n".join(entries) + "\n",
        encoding="utf-8",
    )

    return manifest_path


def write_structure_files() -> None:
    print()
    print("Writing structure summaries:")

    for source_name, output_path in (
        STRUCTURE_OUTPUTS.items()
    ):
        source_path = (
            SOURCE_FILES[source_name]
        )

        source_lines = source_path.read_text(
            encoding="utf-8",
        ).splitlines()

        definitions = []

        for line_number, line in enumerate(
            source_lines,
            start=1,
        ):
            if not DEFINITION_PATTERN.match(
                line
            ):
                continue

            definitions.append(
                f"{line_number}:{line}"
            )

        output_path.write_text(
            "\n".join(definitions) + "\n",
            encoding="utf-8",
        )

        print(
            f"  {output_path}: "
            f"{len(definitions)} definitions"
        )


def write_full_text_snapshots() -> None:
    print()
    print("Writing full source snapshots:")

    for source_name, output_path in (
        FULL_TEXT_OUTPUTS.items()
    ):
        source_path = (
            SOURCE_FILES[source_name]
        )

        source_content = (
            source_path.read_text(
                encoding="utf-8",
            )
        )

        output_path.write_text(
            source_content,
            encoding="utf-8",
        )

        print(
            f"  {output_path}: "
            f"{len(source_content.splitlines())}"
            f" lines"
        )


def validate_copies() -> None:
    print()
    print("Validating copied files:")

    failed = False

    for destination_name, source_path in (
        SOURCE_FILES.items()
    ):
        baseline_path = (
            BASELINE_DIRECTORY
            / destination_name
        )

        source_digest = calculate_sha256(
            source_path
        )

        baseline_digest = (
            calculate_sha256(
                baseline_path
            )
        )

        matches = (
            source_digest
            == baseline_digest
        )

        print(
            "  PASS" if matches else "  FAIL",
            destination_name,
        )

        if not matches:
            failed = True

    if failed:
        raise SystemExit(
            "Baseline validation failed"
        )


def print_summary(
    manifest_path: Path,
) -> None:
    print()
    print("Runtime baseline capture completed")
    print(
        "Baseline directory:",
        BASELINE_DIRECTORY,
    )
    print(
        "Hash manifest:",
        manifest_path,
    )
    print(
        "Files captured:",
        len(SOURCE_FILES),
    )


def main() -> None:
    verify_sources()
    reset_baseline_directory()
    copy_baseline_files()

    manifest_path = (
        write_hash_manifest()
    )

    write_structure_files()
    write_full_text_snapshots()
    validate_copies()
    print_summary(manifest_path)


if __name__ == "__main__":
    main()
