from __future__ import annotations

import hashlib
import shutil
from pathlib import Path


REPOSITORY_ROOT = Path.cwd()

READER_PATH = (
    REPOSITORY_ROOT
    / "tools"
    / "opcua"
    / "read_runtime_padim_pressure.py"
)

BACKUP_PATH = (
    REPOSITORY_ROOT
    / "evidence"
    / "padim-stack"
    / "read_runtime_padim_pressure.before_access_api.py"
)

HASH_PATH = (
    REPOSITORY_ROOT
    / "evidence"
    / "padim-stack"
    / "read-runtime-padim-pressure-script.sha256"
)

REPLACEMENTS = [
    (
        "await analog_signal.read_access_level()",
        "await analog_signal.get_access_level()",
        "AccessLevel API",
    ),
    (
        (
            "await analog_signal\n"
            "            .read_user_access_level()"
        ),
        (
            "await analog_signal\n"
            "            .get_user_access_level()"
        ),
        "UserAccessLevel API",
    ),
]


def calculate_sha256(
    path: Path,
) -> str:
    return hashlib.sha256(
        path.read_bytes()
    ).hexdigest()


def require_reader() -> None:
    if READER_PATH.is_file():
        return

    raise FileNotFoundError(
        f"Runtime reader does not exist: "
        f"{READER_PATH}"
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
        READER_PATH,
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
    updated = content

    for old, new, label in REPLACEMENTS:
        old_count = updated.count(
            old
        )

        new_count = updated.count(
            new
        )

        if old_count == 1 and new_count == 0:
            updated = updated.replace(
                old,
                new,
                1,
            )

            print(
                "Updated:",
                label,
            )

        elif old_count == 0 and new_count == 1:
            print(
                "Already updated:",
                label,
            )

        else:
            raise RuntimeError(
                f"Unexpected {label} state: "
                f"old={old_count}, "
                f"new={new_count}"
            )

    return updated


def validate_updated(
    content: str,
) -> None:
    compile(
        content,
        str(READER_PATH),
        "exec",
    )

    checks = [
        (
            "get_access_level is used",
            content.count(
                "get_access_level()"
            )
            == 1,
        ),
        (
            "get_user_access_level is used",
            content.count(
                "get_user_access_level()"
            )
            == 1,
        ),
        (
            "read_access_level was removed",
            "read_access_level()"
            not in content,
        ),
        (
            "read_user_access_level was removed",
            "read_user_access_level()"
            not in content,
        ),
        (
            "runtime success marker preserved",
            (
                "Runtime PADIM read passed"
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
        (
            "main call preserved",
            "asyncio.run(main())"
            in content,
        ),
    ]

    failed = False

    print()
    print(
        "Updated reader validation:"
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
            "Updated runtime reader "
            "validation failed"
        )


def write_hash_manifest() -> None:
    digest = calculate_sha256(
        READER_PATH
    )

    relative_path = (
        READER_PATH.relative_to(
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
        "Updated reader SHA-256:",
        digest,
    )
    print(
        "Hash manifest:",
        HASH_PATH,
    )


def main() -> None:
    require_reader()

    original = READER_PATH.read_text(
        encoding="utf-8",
    )

    create_backup()

    updated = update_content(
        original
    )

    validate_updated(
        updated
    )

    READER_PATH.write_text(
        updated,
        encoding="utf-8",
    )

    written = READER_PATH.read_text(
        encoding="utf-8",
    )

    if written != updated:
        raise RuntimeError(
            "Written reader differs from "
            "validated content"
        )

    validate_updated(
        written
    )

    write_hash_manifest()

    print()
    print(
        "Runtime PADIM reader access API "
        "update passed"
    )


if __name__ == "__main__":
    main()

