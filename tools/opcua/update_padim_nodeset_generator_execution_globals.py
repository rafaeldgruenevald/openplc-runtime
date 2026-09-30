from __future__ import annotations

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
    / (
        "build_padim_device_nodeset."
        "before_execution_globals.py"
    )
)

HASH_PATH = (
    REPOSITORY_ROOT
    / "evidence"
    / "padim-stack"
    / (
        "build-padim-device-nodeset-"
        "after-execution-globals.sha256"
    )
)

OLD_EXECUTION_GLOBALS = (
    '    execution_globals = {\n'
    '        "__name__": "__main__",\n'
    '        "__file__": str(BASELINE_PATH),\n'
    '        "__package__": None,\n'
    '    }'
)

NEW_EXECUTION_GLOBALS = (
    '    execution_globals = {\n'
    '        "__name__": "__main__",\n'
    '        "__file__": str(BASELINE_PATH),\n'
    '        "__package__": None,\n'
    '        "calculate_sha256": calculate_sha256,\n'
    '    }'
)

EXPORTED_GLOBAL_FRAGMENT = (
    '"calculate_sha256": calculate_sha256'
)


def calculate_file_sha256(
    path: Path,
) -> str:
    digest = hashlib.sha256()

    with path.open("rb") as file_handle:
        while True:
            data = file_handle.read(
                1024 * 1024
            )

            if not data:
                break

            digest.update(data)

    return digest.hexdigest()


def require_generator() -> None:
    if GENERATOR_PATH.is_file():
        return

    raise FileNotFoundError(
        f"Generator does not exist: "
        f"{GENERATOR_PATH}"
    )


def read_generator() -> str:
    return GENERATOR_PATH.read_text(
        encoding="utf-8",
    )


def already_updated(
    content: str,
) -> bool:
    return (
        content.count(
            EXPORTED_GLOBAL_FRAGMENT
        )
        == 1
        and NEW_EXECUTION_GLOBALS
        in content
    )


def validate_original(
    content: str,
) -> None:
    if already_updated(content):
        print(
            "Generator already exports "
            "calculate_sha256 to the "
            "instrumented baseline"
        )
        return

    checks = [
        (
            "old execution globals block exists once",
            content.count(
                OLD_EXECUTION_GLOBALS
            )
            == 1,
        ),
        (
            "calculate_sha256 function exists",
            (
                "def calculate_sha256("
                in content
            ),
        ),
        (
            "calculate_sha256 is not exported yet",
            EXPORTED_GLOBAL_FRAGMENT
            not in content,
        ),
        (
            "19-node update remains present",
            content.count(
                "EXPECTED_PROJECT_NODE_COUNT = 19"
            )
            == 2,
        ),
        (
            "PADIMDevices remains expected",
            "PADIMDevices" in content,
        ),
        (
            "devices folder remains export root",
            "pt101=devices_folder"
            in content,
        ),
        (
            "model version remains injected",
            "PROJECT_MODEL_VERSION"
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
            calculate_file_sha256(
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
        calculate_file_sha256(
            BACKUP_PATH
        ),
    )


def update_content(
    content: str,
) -> str:
    if already_updated(content):
        return content

    updated = content.replace(
        OLD_EXECUTION_GLOBALS,
        NEW_EXECUTION_GLOBALS,
        1,
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
            "calculate_sha256 exported once",
            content.count(
                EXPORTED_GLOBAL_FRAGMENT
            )
            == 1,
        ),
        (
            "new execution globals block exists",
            NEW_EXECUTION_GLOBALS
            in content,
        ),
        (
            "old execution globals block removed",
            OLD_EXECUTION_GLOBALS
            not in content,
        ),
        (
            "calculate_sha256 function preserved",
            (
                "def calculate_sha256("
                in content
            ),
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
            "pt101=devices_folder"
            in content,
        ),
        (
            "model version preserved",
            "PROJECT_MODEL_VERSION"
            in content,
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
            "Execution-globals generator "
            "update validation failed"
        )


def write_generator(
    content: str,
) -> None:
    GENERATOR_PATH.write_text(
        content,
        encoding="utf-8",
    )


def write_hash_manifest() -> None:
    digest = calculate_file_sha256(
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
        "Execution-globals generator "
        "update passed"
    )


if __name__ == "__main__":
    main()
