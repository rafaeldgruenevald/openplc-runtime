from __future__ import annotations

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
        "before_remove_external_validation.py"
    )
)

HASH_PATH = (
    REPOSITORY_ROOT
    / "evidence"
    / "padim-stack"
    / (
        "build-padim-device-nodeset-"
        "after-remove-external-validation.sha256"
    )
)

EXTERNAL_VALIDATION_PATTERN = re.compile(
    r"\n"
    r"    validate_generated_nodeset\(\n"
    r"        OUTPUT_PATH\n"
    r"    \)\n"
)

EXPECTED_EXTERNAL_CALL_COUNT = 1

REQUIRED_GENERATOR_FRAGMENTS = [
    "EXPECTED_PROJECT_NODE_COUNT = 19",
    "PADIMDevices",
    "pt101=devices_folder",
    "PROJECT_MODEL_VERSION",
    (
        '"calculate_sha256": '
        "calculate_sha256"
    ),
    (
        "PADIM PT101 NodeSet "
        "build passed"
    ),
]


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


def external_call_count(
    content: str,
) -> int:
    return len(
        list(
            EXTERNAL_VALIDATION_PATTERN
            .finditer(content)
        )
    )


def already_updated(
    content: str,
) -> bool:
    return (
        external_call_count(content) == 0
        and all(
            fragment in content
            for fragment in (
                REQUIRED_GENERATOR_FRAGMENTS
            )
        )
    )


def validate_original(
    content: str,
) -> None:
    if already_updated(content):
        print(
            "Generator already has no redundant "
            "external validation call"
        )
        return

    calls = external_call_count(
        content
    )

    checks = [
        (
            "one external validation call exists",
            calls
            == EXPECTED_EXTERNAL_CALL_COUNT,
        ),
        (
            "validation function remains injected",
            (
                "def validate_generated_nodeset("
                in content
            ),
        ),
        (
            "internal validation call remains",
            (
                "    validate_generated_nodeset(\n"
                "        output_path\n"
                "    )"
            )
            in content,
        ),
        (
            "19-node count preserved",
            content.count(
                "EXPECTED_PROJECT_NODE_COUNT = 19"
            )
            == 2,
        ),
        (
            "PADIMDevices preserved",
            "PADIMDevices" in content,
        ),
        (
            "devices folder export root preserved",
            "pt101=devices_folder" in content,
        ),
        (
            "calculate_sha256 export preserved",
            (
                '"calculate_sha256": '
                "calculate_sha256"
            )
            in content,
        ),
    ]

    failed = False

    print(
        "Pre-update generator validation:"
    )

    for name, passed in checks:
        print(
            "  PASS" if passed else "  FAIL",
            name,
        )

        if not passed:
            failed = True

    print(
        "  External validation calls:",
        calls,
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


def update_content(
    content: str,
) -> str:
    if already_updated(content):
        return content

    updated, replacement_count = (
        EXTERNAL_VALIDATION_PATTERN.subn(
            "\n",
            content,
            count=1,
        )
    )

    if replacement_count != 1:
        raise RuntimeError(
            "Could not remove exactly one "
            "external validation call"
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

    checks = [
        (
            "external validation call removed",
            external_call_count(content)
            == 0,
        ),
        (
            "validation function preserved",
            (
                "def validate_generated_nodeset("
                in content
            ),
        ),
        (
            "internal validation call preserved",
            (
                "    validate_generated_nodeset(\n"
                "        output_path\n"
                "    )"
            )
            in content,
        ),
        (
            "19-node count preserved",
            content.count(
                "EXPECTED_PROJECT_NODE_COUNT = 19"
            )
            == 2,
        ),
        (
            "PADIMDevices preserved",
            "PADIMDevices" in content,
        ),
        (
            "devices folder export root preserved",
            "pt101=devices_folder" in content,
        ),
        (
            "model version preserved",
            "PROJECT_MODEL_VERSION" in content,
        ),
        (
            "calculate_sha256 export preserved",
            (
                '"calculate_sha256": '
                "calculate_sha256"
            )
            in content,
        ),
        (
            "entry point preserved",
            (
                'if __name__ == "__main__":'
                in content
            ),
        ),
        (
            "success marker preserved",
            (
                "PADIM PT101 NodeSet "
                "build passed"
            )
            in content,
        ),
    ]

    failed = False

    print()
    print(
        "Updated generator validation:"
    )

    for name, passed in checks:
        print(
            "  PASS" if passed else "  FAIL",
            name,
        )

        if not passed:
            failed = True

    if failed:
        raise RuntimeError(
            "Removal of external validation "
            "did not produce a valid generator"
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
            "the validated updated content"
        )

    validate_updated(
        written
    )

    write_hash_manifest()

    print()
    print(
        "External validation removal passed"
    )


if __name__ == "__main__":
    main()
