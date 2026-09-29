from __future__ import annotations

import ast
import hashlib
import shutil
from pathlib import Path


REPOSITORY_ROOT = Path.cwd()

TEST_PATH = (
    REPOSITORY_ROOT
    / "tools"
    / "opcua"
    / "test_real_padim_binding_resolution.py"
)

BACKUP_PATH = (
    REPOSITORY_ROOT
    / "evidence"
    / "padim-stack"
    / (
        "test_real_padim_binding_resolution."
        "before_tail_restore.py"
    )
)

HASH_PATH = (
    REPOSITORY_ROOT
    / "evidence"
    / "padim-stack"
    / (
        "test-real-padim-binding-resolution-"
        "script.sha256"
    )
)

EXPECTED_CURRENT_SHA256 = (
    "1f07db2c3f168c759bb4de40f54f2308"
    "75a559edda7d5d302a2903a44ef8b51a"
)

TRUNCATED_SUFFIX = '''    print(
        "Address:",
        (
            active_variable.arr,
            active_variable.elem,
        ),
    )

    print()
'''

RESTORED_SUFFIX = '''    print(
        "Address:",
        (
            active_variable.arr,
            active_variable.elem,
        ),
    )

    print(
        "Access mode:",
        active_variable.access_mode,
    )

    if not passed:
        raise SystemExit(
            "Real PADIM binding "
            "resolution failed"
        )

    print()
    print(
        "Real PADIM binding "
        "resolution passed"
    )


if __name__ == "__main__":
    asyncio.run(main())
'''

FAILURE_SOURCE_FRAGMENT = (
    '"Real PADIM binding "\n'
    '            "resolution failed"'
)

SUCCESS_SOURCE_FRAGMENT = (
    '"Real PADIM binding "\n'
    '        "resolution passed"'
)

FAILURE_RUNTIME_TEXT = (
    "Real PADIM binding resolution failed"
)

SUCCESS_RUNTIME_TEXT = (
    "Real PADIM binding resolution passed"
)


def calculate_sha256(
    path: Path,
) -> str:
    return hashlib.sha256(
        path.read_bytes()
    ).hexdigest()


def require_test_file() -> None:
    if TEST_PATH.is_file():
        return

    raise FileNotFoundError(
        f"Test file does not exist: {TEST_PATH}"
    )


def read_test() -> str:
    return TEST_PATH.read_text(
        encoding="utf-8",
    )


def collect_string_constants(
    content: str,
) -> set[str]:
    tree = ast.parse(
        content,
        filename=str(TEST_PATH),
    )

    return {
        node.value
        for node in ast.walk(tree)
        if isinstance(
            node,
            ast.Constant,
        )
        and isinstance(
            node.value,
            str,
        )
    }


def is_restored(
    content: str,
) -> bool:
    string_constants = (
        collect_string_constants(
            content
        )
    )

    return (
        SUCCESS_RUNTIME_TEXT
        in string_constants
        and FAILURE_RUNTIME_TEXT
        in string_constants
        and content.count(
            'if __name__ == "__main__":'
        )
        == 1
        and content.count(
            "asyncio.run(main())"
        )
        == 1
        and content.rstrip().endswith(
            "asyncio.run(main())"
        )
    )


def validate_original(
    content: str,
) -> None:
    if is_restored(content):
        print(
            "Test already contains the "
            "complete restored tail"
        )
        return

    actual_sha256 = calculate_sha256(
        TEST_PATH
    )

    if actual_sha256 != EXPECTED_CURRENT_SHA256:
        raise RuntimeError(
            "Unexpected test file SHA-256. "
            f"Expected {EXPECTED_CURRENT_SHA256}, "
            f"found {actual_sha256}"
        )

    normalized = (
        content.rstrip()
        + "\n"
    )

    checks = [
        (
            "asyncio import exists",
            "import asyncio" in content,
        ),
        (
            "main coroutine exists",
            "async def main()" in content,
        ),
        (
            "checks list exists",
            "checks = [" in content,
        ),
        (
            "print_checks is called",
            (
                "passed = print_checks("
                in content
            ),
        ),
        (
            "file ends at expected truncated suffix",
            normalized.endswith(
                TRUNCATED_SUFFIX
            ),
        ),
        (
            "failure source fragment is absent",
            FAILURE_SOURCE_FRAGMENT
            not in content,
        ),
        (
            "success source fragment is absent",
            SUCCESS_SOURCE_FRAGMENT
            not in content,
        ),
        (
            "entry point is absent",
            (
                'if __name__ == "__main__":'
                not in content
            ),
        ),
        (
            "asyncio main call is absent",
            "asyncio.run(main())"
            not in content,
        ),
    ]

    failed = False

    print(
        "Pre-restoration test validation:"
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
            "Test is not in the expected "
            "truncated state"
        )


def create_backup() -> None:
    BACKUP_PATH.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    if BACKUP_PATH.exists():
        backup_sha256 = calculate_sha256(
            BACKUP_PATH
        )

        if backup_sha256 != EXPECTED_CURRENT_SHA256:
            raise RuntimeError(
                "Existing backup does not match "
                "the approved truncated file: "
                f"{backup_sha256}"
            )

        print(
            "Approved backup already exists:",
            BACKUP_PATH,
        )
        print(
            "Backup SHA-256:",
            backup_sha256,
        )
        return

    shutil.copy2(
        TEST_PATH,
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


def restore_tail(
    content: str,
) -> str:
    if is_restored(content):
        return content

    normalized = (
        content.rstrip()
        + "\n"
    )

    if not normalized.endswith(
        TRUNCATED_SUFFIX
    ):
        raise RuntimeError(
            "Test file does not end with the "
            "expected truncated suffix"
        )

    prefix = normalized[
        :-len(TRUNCATED_SUFFIX)
    ]

    return (
        prefix
        + RESTORED_SUFFIX
    )


def validate_restored(
    content: str,
) -> None:
    compile(
        content,
        str(TEST_PATH),
        "exec",
    )

    string_constants = (
        collect_string_constants(
            content
        )
    )

    checks = [
        (
            "main coroutine exists once",
            content.count(
                "async def main()"
            )
            == 1,
        ),
        (
            "print_checks result is preserved",
            content.count(
                "passed = print_checks("
            )
            == 1,
        ),
        (
            "access mode output exists",
            content.count(
                '"Access mode:"'
            )
            == 1,
        ),
        (
            "two failed-check guards exist",
            content.count(
                "if not passed:"
            )
            == 2,
        ),
        (
            "failure source fragment exists",
            FAILURE_SOURCE_FRAGMENT
            in content,
        ),
        (
            "success source fragment exists",
            SUCCESS_SOURCE_FRAGMENT
            in content,
        ),
        (
            "failure runtime string exists",
            FAILURE_RUNTIME_TEXT
            in string_constants,
        ),
        (
            "success runtime string exists",
            SUCCESS_RUNTIME_TEXT
            in string_constants,
        ),
        (
            "entry point exists once",
            content.count(
                'if __name__ == "__main__":'
            )
            == 1,
        ),
        (
            "asyncio main call exists once",
            content.count(
                "asyncio.run(main())"
            )
            == 1,
        ),
        (
            "file ends with main call",
            content.rstrip().endswith(
                "asyncio.run(main())"
            ),
        ),
    ]

    failed = False

    print()
    print(
        "Restored test validation:"
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
            "Restored test validation failed"
        )


def write_test(
    content: str,
) -> None:
    TEST_PATH.write_text(
        content,
        encoding="utf-8",
    )


def write_hash_manifest() -> None:
    digest = calculate_sha256(
        TEST_PATH
    )

    relative_path = (
        TEST_PATH.relative_to(
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
        "Restored test SHA-256:",
        digest,
    )
    print(
        "Hash manifest:",
        HASH_PATH,
    )


def main() -> None:
    require_test_file()

    original = read_test()

    validate_original(
        original
    )

    was_restored = is_restored(
        original
    )

    if not was_restored:
        create_backup()

    restored = restore_tail(
        original
    )

    validate_restored(
        restored
    )

    if not was_restored:
        write_test(
            restored
        )

    written = read_test()

    if written != restored:
        raise RuntimeError(
            "Written test differs from the "
            "validated restored content"
        )

    validate_restored(
        written
    )

    write_hash_manifest()

    print()
    print(
        "Real PADIM binding test "
        "tail restoration passed"
    )


if __name__ == "__main__":
    main()
