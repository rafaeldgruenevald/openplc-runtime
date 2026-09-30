from __future__ import annotations

import hashlib
from pathlib import Path


REPOSITORY_ROOT = Path.cwd()

RESTORER_PATH = (
    REPOSITORY_ROOT
    / "tools"
    / "opcua"
    / "restore_real_padim_binding_test_tail.py"
)

HASH_PATH = (
    REPOSITORY_ROOT
    / "evidence"
    / "padim-stack"
    / (
        "restore-real-padim-binding-test-tail-"
        "after-count-fix.sha256"
    )
)

OLD_VALIDATION_BLOCK = '''        (
            "failed checks terminate the test",
            content.count(
                "if not passed:"
            )
            == 1,
        ),'''

NEW_VALIDATION_BLOCK = '''        (
            "two failed-check guards exist",
            content.count(
                "if not passed:"
            )
            == 2,
        ),'''


def calculate_sha256(
    path: Path,
) -> str:
    return hashlib.sha256(
        path.read_bytes()
    ).hexdigest()


def main() -> None:
    if not RESTORER_PATH.is_file():
        raise FileNotFoundError(
            f"Missing restorer: {RESTORER_PATH}"
        )

    content = RESTORER_PATH.read_text(
        encoding="utf-8",
    )

    old_count = content.count(
        OLD_VALIDATION_BLOCK
    )

    new_count = content.count(
        NEW_VALIDATION_BLOCK
    )

    if old_count == 1 and new_count == 0:
        updated = content.replace(
            OLD_VALIDATION_BLOCK,
            NEW_VALIDATION_BLOCK,
            1,
        )

    elif old_count == 0 and new_count == 1:
        print(
            "Restorer already has the correct "
            "failed-check count"
        )

        updated = content

    else:
        raise RuntimeError(
            "Unexpected restorer state: "
            f"old block count={old_count}, "
            f"new block count={new_count}"
        )

    compile(
        updated,
        str(RESTORER_PATH),
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
            "expected count is two",
            (
                '"if not passed:"\n'
                "            )\n"
                "            == 2,"
            )
            in updated,
        ),
        (
            "tail restoration function preserved",
            "def restore_tail("
            in updated,
        ),
        (
            "AST string validation preserved",
            "collect_string_constants("
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

    print(
        "Restorer correction validation:"
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
            "Restorer correction validation "
            "failed"
        )

    RESTORER_PATH.write_text(
        updated,
        encoding="utf-8",
    )

    written = RESTORER_PATH.read_text(
        encoding="utf-8",
    )

    if written != updated:
        raise RuntimeError(
            "Written restorer differs from "
            "validated content"
        )

    digest = calculate_sha256(
        RESTORER_PATH
    )

    relative_path = (
        RESTORER_PATH.relative_to(
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
        "PASS: restorer failed-check "
        "count corrected"
    )
    print(
        "Restorer SHA-256:",
        digest,
    )
    print(
        "Manifest:",
        HASH_PATH,
    )


if __name__ == "__main__":
    main()
