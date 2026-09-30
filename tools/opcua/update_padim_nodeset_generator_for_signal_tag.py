from __future__ import annotations

import ast
import hashlib
import shutil
from pathlib import Path


REPOSITORY_ROOT = Path.cwd()

GENERATOR_PATH = (
    REPOSITORY_ROOT
    / "tools"
    / "opcua"
    / "build_padim_device_nodeset.py"
)

BACKUP_PATH = (
    REPOSITORY_ROOT
    / "evidence"
    / "padim-stack"
    / "build_padim_device_nodeset.before_signal_tag.py"
)

HASH_PATH = (
    REPOSITORY_ROOT
    / "evidence"
    / "padim-stack"
    / "build-padim-device-nodeset-after-signal-tag.sha256"
)

OLD_COUNT_DEFINITION = (
    "EXPECTED_PROJECT_NODE_COUNT = 17"
)

NEW_COUNT_DEFINITION = (
    "EXPECTED_PROJECT_NODE_COUNT = 18"
)

EXPECTED_OLD_COUNT_OCCURRENCES = 2
EXPECTED_NEW_COUNT_OCCURRENCES = 2

EXISTING_IDENTIFIER_BLOCK = (
    '    "PT101.SignalSet.Pressure",\n'
    '    (\n'
    '        "PT101.SignalSet.Pressure."\n'
    '        "AnalogSignal"\n'
    '    ),'
)

UPDATED_IDENTIFIER_BLOCK = (
    '    "PT101.SignalSet.Pressure",\n'
    '    (\n'
    '        "PT101.SignalSet.Pressure."\n'
    '        "SignalTag"\n'
    '    ),\n'
    '    (\n'
    '        "PT101.SignalSet.Pressure."\n'
    '        "AnalogSignal"\n'
    '    ),'
)

SIGNAL_TAG_SOURCE_FRAGMENT = (
    '"PT101.SignalSet.Pressure."\n'
    '        "SignalTag"'
)

ANALOG_SIGNAL_SOURCE_FRAGMENT = (
    '"PT101.SignalSet.Pressure."\n'
    '        "AnalogSignal"'
)

ENGINEERING_UNITS_SOURCE_FRAGMENT = (
    '"PT101.SignalSet.Pressure."\n'
    '        "AnalogSignal.EngineeringUnits"'
)

EU_RANGE_SOURCE_FRAGMENT = (
    '"PT101.SignalSet.Pressure."\n'
    '        "AnalogSignal.EURange"'
)

EXPECTED_RUNTIME_IDENTIFIERS = {
    "PT101.SignalSet.Pressure.SignalTag",
    "PT101.SignalSet.Pressure.AnalogSignal",
    (
        "PT101.SignalSet.Pressure."
        "AnalogSignal.EngineeringUnits"
    ),
    (
        "PT101.SignalSet.Pressure."
        "AnalogSignal.EURange"
    ),
}


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


def require_generator() -> None:
    if GENERATOR_PATH.is_file():
        return

    raise FileNotFoundError(
        "NodeSet generator does not exist: "
        f"{GENERATOR_PATH}"
    )


def read_generator() -> str:
    return GENERATOR_PATH.read_text(
        encoding="utf-8",
    )


def source_is_already_updated(
    content: str,
) -> bool:
    return (
        content.count(
            NEW_COUNT_DEFINITION
        )
        == EXPECTED_NEW_COUNT_OCCURRENCES
        and OLD_COUNT_DEFINITION
        not in content
        and content.count(
            SIGNAL_TAG_SOURCE_FRAGMENT
        )
        == 1
    )


def validate_original_content(
    content: str,
) -> None:
    if source_is_already_updated(
        content
    ):
        print(
            "Generator already includes SignalTag "
            "and expects 18 project nodes"
        )
        return

    old_count_occurrences = content.count(
        OLD_COUNT_DEFINITION
    )

    if (
        old_count_occurrences
        != EXPECTED_OLD_COUNT_OCCURRENCES
    ):
        raise RuntimeError(
            "Expected exactly "
            f"{EXPECTED_OLD_COUNT_OCCURRENCES} "
            "old project-node count definitions, "
            f"found {old_count_occurrences}"
        )

    new_count_occurrences = content.count(
        NEW_COUNT_DEFINITION
    )

    if new_count_occurrences != 0:
        raise RuntimeError(
            "Generator contains a partial count "
            "update. Found "
            f"{new_count_occurrences} occurrence(s) "
            "of the new count definition"
        )

    block_occurrences = content.count(
        EXISTING_IDENTIFIER_BLOCK
    )

    if block_occurrences != 1:
        raise RuntimeError(
            "Expected exactly one insertion block "
            "for SignalTag, found "
            f"{block_occurrences}"
        )

    signal_tag_occurrences = content.count(
        SIGNAL_TAG_SOURCE_FRAGMENT
    )

    if signal_tag_occurrences != 0:
        raise RuntimeError(
            "SignalTag already appears in the "
            "project identifier set, but the count "
            "definitions remain inconsistent"
        )


def create_backup() -> None:
    BACKUP_PATH.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    if BACKUP_PATH.exists():
        print(
            "Backup already exists:",
            BACKUP_PATH,
        )
        print(
            "Backup SHA-256:",
            calculate_sha256(
                BACKUP_PATH
            ),
        )
        return

    shutil.copy2(
        GENERATOR_PATH,
        BACKUP_PATH,
    )

    print(
        "Backup written:",
        BACKUP_PATH,
    )

    print(
        "Backup SHA-256:",
        calculate_sha256(
            BACKUP_PATH
        ),
    )


def update_content(
    content: str,
) -> str:
    if source_is_already_updated(
        content
    ):
        return content

    updated = content.replace(
        OLD_COUNT_DEFINITION,
        NEW_COUNT_DEFINITION,
    )

    updated = updated.replace(
        EXISTING_IDENTIFIER_BLOCK,
        UPDATED_IDENTIFIER_BLOCK,
        1,
    )

    return updated


def compile_updated_source(
    content: str,
) -> None:
    compile(
        content,
        str(GENERATOR_PATH),
        "exec",
    )


def extract_literal_project_identifiers(
    content: str,
) -> set[str]:
    tree = ast.parse(
        content,
        filename=str(GENERATOR_PATH),
    )

    identifiers = set()

    for node in ast.walk(tree):
        if not isinstance(
            node,
            ast.Assign,
        ):
            continue

        target_names = {
            target.id
            for target in node.targets
            if isinstance(
                target,
                ast.Name,
            )
        }

        if (
            "PROJECT_NODE_IDENTIFIERS"
            not in target_names
        ):
            continue

        try:
            value = ast.literal_eval(
                node.value
            )
        except (
            ValueError,
            TypeError,
        ):
            continue

        if not isinstance(
            value,
            set,
        ):
            continue

        identifiers.update(
            item
            for item in value
            if isinstance(
                item,
                str,
            )
        )

    return identifiers


def validate_updated_content(
    content: str,
) -> None:
    compile_updated_source(
        content
    )

    runtime_identifiers = (
        extract_literal_project_identifiers(
            content
        )
    )

    checks = [
        (
            "expected node count occurs twice",
            content.count(
                NEW_COUNT_DEFINITION
            )
            == EXPECTED_NEW_COUNT_OCCURRENCES,
        ),
        (
            "old node count removed",
            OLD_COUNT_DEFINITION
            not in content,
        ),
        (
            "SignalTag source fragment included once",
            content.count(
                SIGNAL_TAG_SOURCE_FRAGMENT
            )
            == 1,
        ),
        (
            "AnalogSignal source fragment preserved",
            content.count(
                ANALOG_SIGNAL_SOURCE_FRAGMENT
            )
            >= 1,
        ),
        (
            "EngineeringUnits source fragment preserved",
            content.count(
                ENGINEERING_UNITS_SOURCE_FRAGMENT
            )
            >= 1,
        ),
        (
            "EURange source fragment preserved",
            content.count(
                EU_RANGE_SOURCE_FRAGMENT
            )
            >= 1,
        ),
        (
            "runtime identifier set found",
            bool(runtime_identifiers),
        ),
        (
            "SignalTag runtime identifier present",
            (
                "PT101.SignalSet.Pressure.SignalTag"
                in runtime_identifiers
            ),
        ),
        (
            "all critical runtime identifiers present",
            EXPECTED_RUNTIME_IDENTIFIERS
            .issubset(
                runtime_identifiers
            ),
        ),
        (
            "runtime identifier count is 18",
            len(runtime_identifiers) == 18,
        ),
        (
            "generator entry point preserved",
            (
                'if __name__ == "__main__":'
                in content
            ),
        ),
    ]

    failed = False

    print()
    print("Updated generator validation:")

    for name, passed in checks:
        print(
            "  PASS" if passed else "  FAIL",
            name,
        )

        if not passed:
            failed = True

    print(
        "  Runtime identifier count:",
        len(runtime_identifiers),
    )

    if failed:
        missing_identifiers = (
            EXPECTED_RUNTIME_IDENTIFIERS
            - runtime_identifiers
        )

        if missing_identifiers:
            print(
                "  Missing runtime identifiers:",
                sorted(
                    missing_identifiers
                ),
            )

        raise RuntimeError(
            "Updated generator validation failed"
        )


def write_generator(
    content: str,
) -> None:
    GENERATOR_PATH.write_text(
        content,
        encoding="utf-8",
    )


def write_hash_manifest() -> None:
    digest = calculate_sha256(
        GENERATOR_PATH
    )

    relative_path = (
        GENERATOR_PATH.relative_to(
            REPOSITORY_ROOT
        )
    )

    HASH_PATH.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    HASH_PATH.write_text(
        f"{digest}  {relative_path}\n",
        encoding="utf-8",
    )

    print()
    print("Updated generator:")
    print(
        " ",
        GENERATOR_PATH,
    )
    print(
        "SHA-256:",
        digest,
    )
    print(
        "Hash manifest:",
        HASH_PATH,
    )


def main() -> None:
    require_generator()

    original_content = read_generator()

    validate_original_content(
        original_content
    )

    already_updated = (
        source_is_already_updated(
            original_content
        )
    )

    if not already_updated:
        create_backup()

    updated_content = update_content(
        original_content
    )

    validate_updated_content(
        updated_content
    )

    if not already_updated:
        write_generator(
            updated_content
        )

    written_content = read_generator()

    if written_content != updated_content:
        raise RuntimeError(
            "Generator content differs from the "
            "validated updated content"
        )

    validate_updated_content(
        written_content
    )

    write_hash_manifest()

    print()
    print(
        "SignalTag generator update passed"
    )


if __name__ == "__main__":
    main()
