from __future__ import annotations

import ast
import hashlib
import re
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
    / (
        "build_padim_device_nodeset."
        "before_root_folder.py"
    )
)

HASH_PATH = (
    REPOSITORY_ROOT
    / "evidence"
    / "padim-stack"
    / (
        "build-padim-device-nodeset-"
        "after-root-folder.sha256"
    )
)

OLD_COUNT_DEFINITION = (
    "EXPECTED_PROJECT_NODE_COUNT = 18"
)

NEW_COUNT_DEFINITION = (
    "EXPECTED_PROJECT_NODE_COUNT = 19"
)

EXPECTED_COUNT_OCCURRENCES = 2

ROOT_FOLDER_IDENTIFIER = (
    "PADIMDevices"
)

SIGNAL_TAG_IDENTIFIER = (
    "PT101.SignalSet.Pressure.SignalTag"
)

ANALOG_SIGNAL_IDENTIFIER = (
    "PT101.SignalSet.Pressure."
    "AnalogSignal"
)

ENGINEERING_UNITS_IDENTIFIER = (
    "PT101.SignalSet.Pressure."
    "AnalogSignal.EngineeringUnits"
)

EU_RANGE_IDENTIFIER = (
    "PT101.SignalSet.Pressure."
    "AnalogSignal.EURange"
)

TEXTUAL_TYPE_TERM = (
    "PressureMeasurementVariableType"
)

IDENTIFIER_SET_START_PATTERN = re.compile(
    r"PROJECT_NODE_IDENTIFIERS\s*=\s*\{\s*"
    r'("PT101"\s*,)'
)

EXPORT_ROOT_PATTERN = re.compile(
    r"(?P<indent>[ \t]*)"
    r"pt101"
    r"(?P<before_equals>[ \t]*)"
    r"="
    r"(?P<after_equals>[ \t]*)"
    r"pt101"
    r"(?P<suffix>[ \t]*,)"
)

UPDATED_EXPORT_ROOT_PATTERN = re.compile(
    r"(?P<indent>[ \t]*)"
    r"pt101"
    r"(?P<before_equals>[ \t]*)"
    r"="
    r"(?P<after_equals>[ \t]*)"
    r"devices_folder"
    r"(?P<suffix>[ \t]*,)"
)

TEXTUAL_TERM_LINE_PATTERN = re.compile(
    r"^[ \t]*"
    r'["\']PressureMeasurementVariableType["\']'
    r"[ \t]*,[ \t]*\n",
    re.MULTILINE,
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


def extract_identifier_sets(
    content: str,
) -> list[set[str]]:
    tree = ast.parse(
        content,
        filename=str(GENERATOR_PATH),
    )

    identifier_sets = []

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

        identifier_sets.append(
            {
                item
                for item in value
                if isinstance(
                    item,
                    str,
                )
            }
        )

    return identifier_sets


def combined_identifiers(
    content: str,
) -> set[str]:
    result = set()

    for identifiers in extract_identifier_sets(
        content
    ):
        result.update(
            identifiers
        )

    return result


def already_updated(
    content: str,
) -> bool:
    identifiers = combined_identifiers(
        content
    )

    return (
        content.count(
            NEW_COUNT_DEFINITION
        )
        == EXPECTED_COUNT_OCCURRENCES
        and OLD_COUNT_DEFINITION
        not in content
        and ROOT_FOLDER_IDENTIFIER
        in identifiers
        and bool(
            UPDATED_EXPORT_ROOT_PATTERN.search(
                content
            )
        )
        and not bool(
            EXPORT_ROOT_PATTERN.search(
                content
            )
        )
        and not bool(
            TEXTUAL_TERM_LINE_PATTERN.search(
                content
            )
        )
    )


def validate_original(
    content: str,
) -> None:
    if already_updated(content):
        print(
            "Generator already includes the "
            "root-folder update"
        )
        return

    identifiers = combined_identifiers(
        content
    )

    old_export_matches = list(
        EXPORT_ROOT_PATTERN.finditer(
            content
        )
    )

    identifier_start_matches = list(
        IDENTIFIER_SET_START_PATTERN
        .finditer(
            content
        )
    )

    textual_term_matches = list(
        TEXTUAL_TERM_LINE_PATTERN.finditer(
            content
        )
    )

    checks = [
        (
            "18-node count occurs twice",
            content.count(
                OLD_COUNT_DEFINITION
            )
            == EXPECTED_COUNT_OCCURRENCES,
        ),
        (
            "19-node count is absent",
            NEW_COUNT_DEFINITION
            not in content,
        ),
        (
            "one identifier set starts with PT101",
            len(
                identifier_start_matches
            )
            == 1,
        ),
        (
            "one export call uses PT101 root",
            len(old_export_matches) == 1,
        ),
        (
            (
                "one textual type-name "
                "validation exists"
            ),
            len(textual_term_matches) == 1,
        ),
        (
            "identifier set contains 18 nodes",
            len(identifiers) == 18,
        ),
        (
            "SignalTag is expected",
            SIGNAL_TAG_IDENTIFIER
            in identifiers,
        ),
        (
            "root folder is not yet expected",
            ROOT_FOLDER_IDENTIFIER
            not in identifiers,
        ),
    ]

    failed = False

    print("Pre-update generator validation:")

    for name, passed in checks:
        print(
            "  PASS" if passed else "  FAIL",
            name,
        )

        if not passed:
            failed = True

    print(
        "  PT101 export-root matches:",
        len(old_export_matches),
    )
    print(
        "  Identifier-set starts:",
        len(identifier_start_matches),
    )
    print(
        "  Textual type checks:",
        len(textual_term_matches),
    )
    print(
        "  Identifier count:",
        len(identifiers),
    )

    if failed:
        raise RuntimeError(
            "Generator is not in the expected "
            "pre-update state"
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


def update_node_counts(
    content: str,
) -> str:
    return content.replace(
        OLD_COUNT_DEFINITION,
        NEW_COUNT_DEFINITION,
    )


def update_identifier_set(
    content: str,
) -> str:
    replacement_count = 0

    def replacement(
        match: re.Match[str],
    ) -> str:
        nonlocal replacement_count

        replacement_count += 1

        return (
            "PROJECT_NODE_IDENTIFIERS = {\n"
            '    "PADIMDevices",\n'
            "    "
            + match.group(1)
        )

    updated = (
        IDENTIFIER_SET_START_PATTERN.sub(
            replacement,
            content,
            count=1,
        )
    )

    if replacement_count != 1:
        raise RuntimeError(
            "Could not add PADIMDevices to "
            "PROJECT_NODE_IDENTIFIERS"
        )

    return updated


def update_export_root(
    content: str,
) -> str:
    replacement_count = 0

    def replacement(
        match: re.Match[str],
    ) -> str:
        nonlocal replacement_count

        replacement_count += 1

        return (
            match.group("indent")
            + "pt101"
            + match.group("before_equals")
            + "="
            + match.group("after_equals")
            + "devices_folder"
            + match.group("suffix")
        )

    updated = EXPORT_ROOT_PATTERN.sub(
        replacement,
        content,
        count=1,
    )

    if replacement_count != 1:
        raise RuntimeError(
            "Could not change the export root "
            "from PT101 to PADIMDevices"
        )

    return updated


def remove_textual_type_check(
    content: str,
) -> str:
    updated, replacement_count = (
        TEXTUAL_TERM_LINE_PATTERN.subn(
            "",
            content,
            count=1,
        )
    )

    if replacement_count != 1:
        raise RuntimeError(
            "Could not remove the textual "
            "PressureMeasurementVariableType check"
        )

    return updated


def update_content(
    content: str,
) -> str:
    if already_updated(content):
        return content

    updated = update_node_counts(
        content
    )

    updated = update_identifier_set(
        updated
    )

    updated = update_export_root(
        updated
    )

    updated = remove_textual_type_check(
        updated
    )

    return updated


def validate_updated(
    content: str,
) -> None:
    compile(
        content,
        str(GENERATOR_PATH),
        "exec",
    )

    identifiers = combined_identifiers(
        content
    )

    identifier_sets = extract_identifier_sets(
        content
    )

    old_export_matches = list(
        EXPORT_ROOT_PATTERN.finditer(
            content
        )
    )

    new_export_matches = list(
        UPDATED_EXPORT_ROOT_PATTERN
        .finditer(
            content
        )
    )

    textual_term_matches = list(
        TEXTUAL_TERM_LINE_PATTERN.finditer(
            content
        )
    )

    critical_identifiers = {
        ROOT_FOLDER_IDENTIFIER,
        "PT101",
        SIGNAL_TAG_IDENTIFIER,
        ANALOG_SIGNAL_IDENTIFIER,
        ENGINEERING_UNITS_IDENTIFIER,
        EU_RANGE_IDENTIFIER,
    }

    checks = [
        (
            "19-node count occurs twice",
            content.count(
                NEW_COUNT_DEFINITION
            )
            == EXPECTED_COUNT_OCCURRENCES,
        ),
        (
            "18-node count removed",
            OLD_COUNT_DEFINITION
            not in content,
        ),
        (
            "one identifier set found",
            len(identifier_sets) == 1,
        ),
        (
            "root folder is expected",
            ROOT_FOLDER_IDENTIFIER
            in identifiers,
        ),
        (
            "identifier count is 19",
            len(identifiers) == 19,
        ),
        (
            "critical identifiers preserved",
            critical_identifiers
            .issubset(
                identifiers
            ),
        ),
        (
            "one export call uses devices folder",
            len(new_export_matches) == 1,
        ),
        (
            "old PT101 export root removed",
            len(old_export_matches) == 0,
        ),
        (
            "textual type check removed",
            len(textual_term_matches) == 0,
        ),
        (
            "model version update preserved",
            (
                "PROJECT_MODEL_VERSION"
                in content
            ),
        ),
        (
            "entry point preserved",
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
        "  Identifier count:",
        len(identifiers),
    )
    print(
        "  New export-root matches:",
        len(new_export_matches),
    )
    print(
        "  Old export-root matches:",
        len(old_export_matches),
    )
    print(
        "  Textual type checks:",
        len(textual_term_matches),
    )

    if failed:
        missing = (
            critical_identifiers
            - identifiers
        )

        if missing:
            print(
                "  Missing critical identifiers:",
                sorted(missing),
            )

        raise RuntimeError(
            "Root-folder generator update "
            "validation failed"
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
    print(
        "Updated generator SHA-256:",
        digest,
    )
    print(
        "Hash manifest:",
        HASH_PATH,
    )


def main() -> None:
    require_generator()

    original = read_generator()

    validate_original(
        original
    )

    was_updated = already_updated(
        original
    )

    if not was_updated:
        create_backup()

    updated = update_content(
        original
    )

    validate_updated(
        updated
    )

    if not was_updated:
        write_generator(
            updated
        )

    written = read_generator()

    if written != updated:
        raise RuntimeError(
            "Written generator differs from "
            "the validated content"
        )

    validate_updated(
        written
    )

    write_hash_manifest()

    print()
    print(
        "Root-folder generator update passed"
    )


if __name__ == "__main__":
    main()
