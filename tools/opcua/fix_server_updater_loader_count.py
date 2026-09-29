from __future__ import annotations

import hashlib
from pathlib import Path


REPOSITORY_ROOT = Path.cwd()

UPDATER_PATH = (
    REPOSITORY_ROOT
    / "tools"
    / "opcua"
    / "update_server_for_semantic_bindings.py"
)

HASH_PATH = (
    REPOSITORY_ROOT
    / "evidence"
    / "padim-stack"
    / "server-updater-after-loader-count-fix.sha256"
)

OLD_VALIDATION_BLOCK = (
    '        (\n'
    '            "resolver loader imported twice",\n'
    '            content.count(\n'
    '                UPDATED_IMPORT_FRAGMENT\n'
    '            )\n'
    '            == 4,\n'
    '        ),'
)

NEW_VALIDATION_BLOCK = (
    '        (\n'
    '            "resolver loader appears three times",\n'
    '            content.count(\n'
    '                UPDATED_IMPORT_FRAGMENT\n'
    '            )\n'
    '            == 3,\n'
    '        ),'
)


def calculate_sha256(
    path: Path,
) -> str:
    return hashlib.sha256(
        path.read_bytes()
    ).hexdigest()


def main() -> None:
    if not UPDATER_PATH.is_file():
        raise FileNotFoundError(
            f"Missing updater: {UPDATER_PATH}"
        )

    content = UPDATER_PATH.read_text(
        encoding="utf-8",
    )

    old_count = content.count(
        OLD_VALIDATION_BLOCK
    )

    new_count = content.count(
        NEW_VALIDATION_BLOCK
    )

    if old_count == 0 and new_count == 1:
        print(
            "Updater already contains the "
            "correct loader count"
        )
        updated = content

    elif old_count == 1 and new_count == 0:
        updated = content.replace(
            OLD_VALIDATION_BLOCK,
            NEW_VALIDATION_BLOCK,
            1,
        )

    else:
        raise RuntimeError(
            "Unexpected updater state: "
            f"old block count={old_count}, "
            f"new block count={new_count}"
        )

    compile(
        updated,
        str(UPDATER_PATH),
        "exec",
    )

    checks = [
        (
            "old validation removed",
            OLD_VALIDATION_BLOCK
            not in updated,
        ),
        (
            "new validation exists once",
            updated.count(
                NEW_VALIDATION_BLOCK
            )
            == 1,
        ),
        (
            "loader expectation is three",
            (
                '"resolver loader appears '
                'three times"'
            )
            in updated,
        ),
        (
            "server baseline validation preserved",
            "EXPECTED_BASELINE_SHA256"
            in updated,
        ),
        (
            "server write function preserved",
            "def write_server("
            in updated,
        ),
        (
            "entry point preserved",
            (
                'if __name__ == "__main__":'
                in updated
            ),
        ),
    ]

    failed = False

    print("Updater correction validation:")

    for name, passed in checks:
        print(
            "  PASS" if passed else "  FAIL",
            name,
        )

        if not passed:
            failed = True

    if failed:
        raise RuntimeError(
            "Updater correction validation failed"
        )

    UPDATER_PATH.write_text(
        updated,
        encoding="utf-8",
    )

    written = UPDATER_PATH.read_text(
        encoding="utf-8",
    )

    if written != updated:
        raise RuntimeError(
            "Written updater differs from "
            "validated content"
        )

    digest = calculate_sha256(
        UPDATER_PATH
    )

    relative_path = (
        UPDATER_PATH.relative_to(
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
        "PASS: server updater loader count fixed"
    )
    print(
        "Updater SHA-256:",
        digest,
    )
    print(
        "Manifest:",
        HASH_PATH,
    )


if __name__ == "__main__":
    main()
