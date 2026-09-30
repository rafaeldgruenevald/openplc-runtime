from __future__ import annotations

import hashlib
import shutil
from pathlib import Path


REPOSITORY_ROOT = Path.cwd()

RESOLVER_PATH = (
    REPOSITORY_ROOT
    / "core"
    / "src"
    / "drivers"
    / "plugins"
    / "python"
    / "opcua"
    / "imported_node_bindings.py"
)

TEST_PATH = (
    REPOSITORY_ROOT
    / "tools"
    / "opcua"
    / "test_real_padim_binding_resolution.py"
)

RESOLVER_BACKUP_PATH = (
    REPOSITORY_ROOT
    / "evidence"
    / "padim-stack"
    / "imported_node_bindings.before_any_value_rank.py"
)

TEST_BACKUP_PATH = (
    REPOSITORY_ROOT
    / "evidence"
    / "padim-stack"
    / (
        "test_real_padim_binding_resolution."
        "before_any_value_rank.py"
    )
)

RESOLVER_HASH_PATH = (
    REPOSITORY_ROOT
    / "evidence"
    / "padim-stack"
    / "imported-node-bindings-after-any-value-rank.sha256"
)

TEST_HASH_PATH = (
    REPOSITORY_ROOT
    / "evidence"
    / "padim-stack"
    / (
        "test-real-padim-binding-resolution-"
        "script.sha256"
    )
)

EXPECTED_RESOLVER_SHA256 = (
    "d53a529a2da828b24dea5907b837ae2c"
    "e03dd800ee23fa481cfdff561cf9dd02"
)

EXPECTED_TEST_SHA256 = (
    "01994f83c73805a193c43585ae11c2c5"
    "b621ce08b11a1ec56ee1f9ef9e971d1a"
)

OLD_RESOLVER_BLOCK = '''    scalar_value_ranks = {
        ua.ValueRank.Scalar,
        -1,
    }

    if value_rank not in scalar_value_ranks:
'''

NEW_RESOLVER_BLOCK = '''    scalar_compatible_value_ranks = {
        ua.ValueRank.Scalar,
        ua.ValueRank.Any,
        -1,
        -2,
    }

    if (
        value_rank
        not in scalar_compatible_value_ranks
    ):
'''

OLD_RESOLVER_ERROR = '''            "currently supports only scalar nodes, "
            f"but {node.nodeid} has ValueRank "
            f"{value_rank}"
'''

NEW_RESOLVER_ERROR = '''            "currently supports only scalar-compatible "
            "nodes, but "
            f"{node.nodeid} has ValueRank "
            f"{value_rank}"
'''

OLD_TEST_CHECK = '''        (
            "target is scalar",
            target_value_rank
            in {
                ua.ValueRank.Scalar,
                -1,
            },
        ),
'''

NEW_TEST_CHECK = '''        (
            "target ValueRank is scalar-compatible",
            target_value_rank
            in {
                ua.ValueRank.Scalar,
                ua.ValueRank.Any,
                -1,
                -2,
            },
        ),
'''


def calculate_sha256(
    path: Path,
) -> str:
    return hashlib.sha256(
        path.read_bytes()
    ).hexdigest()


def require_file(
    label: str,
    path: Path,
) -> None:
    if not path.is_file():
        raise FileNotFoundError(
            f"{label} does not exist: {path}"
        )


def create_backup(
    source_path: Path,
    backup_path: Path,
    expected_sha256: str,
) -> None:
    backup_path.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    if backup_path.exists():
        backup_sha256 = calculate_sha256(
            backup_path
        )

        if backup_sha256 != expected_sha256:
            raise RuntimeError(
                "Existing backup has unexpected "
                f"SHA-256: {backup_path} "
                f"{backup_sha256}"
            )

        print(
            "Approved backup already exists:",
            backup_path,
        )

        return

    shutil.copy2(
        source_path,
        backup_path,
    )

    print(
        "Backup written:",
        backup_path,
    )


def replace_once(
    content: str,
    old: str,
    new: str,
    label: str,
) -> str:
    occurrences = content.count(
        old
    )

    if occurrences == 0 and new in content:
        print(
            f"{label} is already updated"
        )

        return content

    if occurrences != 1:
        raise RuntimeError(
            f"Expected one {label} block, "
            f"found {occurrences}"
        )

    return content.replace(
        old,
        new,
        1,
    )


def write_hash_manifest(
    path: Path,
    manifest_path: Path,
) -> None:
    digest = calculate_sha256(
        path
    )

    relative_path = path.relative_to(
        REPOSITORY_ROOT
    )

    manifest_path.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    manifest_path.write_text(
        f"{digest}  {relative_path}\n",
        encoding="utf-8",
    )

    print(
        "SHA-256:",
        digest,
        path,
    )


def validate_resolver(
    content: str,
) -> None:
    compile(
        content,
        str(RESOLVER_PATH),
        "exec",
    )

    checks = [
        (
            "scalar-compatible set exists",
            "scalar_compatible_value_ranks"
            in content,
        ),
        (
            "ValueRank Scalar is accepted",
            "ua.ValueRank.Scalar"
            in content,
        ),
        (
            "ValueRank Any is accepted",
            "ua.ValueRank.Any"
            in content,
        ),
        (
            "numeric Scalar rank is accepted",
            "-1" in content,
        ),
        (
            "numeric Any rank is accepted",
            "-2" in content,
        ),
        (
            "old scalar set removed",
            "scalar_value_ranks = {"
            not in content,
        ),
        (
            "NodeClass validation preserved",
            (
                "target must be an OPC UA Variable"
                in content
            ),
        ),
        (
            "DataType validation preserved",
            (
                "target has incompatible DataType"
                in content
            ),
        ),
        (
            "collision policy preserved",
            "COLLISION_POLICY_REPLACE"
            in content,
        ),
    ]

    failed = False

    print()
    print("Resolver validation:")

    for name, passed in checks:
        print(
            "  PASS" if passed else "  FAIL",
            name,
        )

        if not passed:
            failed = True

    if failed:
        raise RuntimeError(
            "Resolver validation failed"
        )


def validate_test(
    content: str,
) -> None:
    compile(
        content,
        str(TEST_PATH),
        "exec",
    )

    checks = [
        (
            "scalar-compatible check exists",
            (
                "target ValueRank is "
                "scalar-compatible"
            )
            in content,
        ),
        (
            "test accepts ValueRank Any",
            "ua.ValueRank.Any"
            in content,
        ),
        (
            "success marker preserved",
            (
                '"Real PADIM binding "\n'
                '        "resolution passed"'
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
            "main call preserved",
            "asyncio.run(main())"
            in content,
        ),
    ]

    failed = False

    print()
    print("Real binding test validation:")

    for name, passed in checks:
        print(
            "  PASS" if passed else "  FAIL",
            name,
        )

        if not passed:
            failed = True

    if failed:
        raise RuntimeError(
            "Real binding test validation failed"
        )


def main() -> None:
    require_file(
        "binding resolver",
        RESOLVER_PATH,
    )

    require_file(
        "real binding test",
        TEST_PATH,
    )

    resolver_sha256 = calculate_sha256(
        RESOLVER_PATH
    )

    test_sha256 = calculate_sha256(
        TEST_PATH
    )

    resolver_is_updated = (
        NEW_RESOLVER_BLOCK
        in RESOLVER_PATH.read_text(
            encoding="utf-8",
        )
    )

    test_is_updated = (
        NEW_TEST_CHECK
        in TEST_PATH.read_text(
            encoding="utf-8",
        )
    )

    if (
        not resolver_is_updated
        and resolver_sha256
        != EXPECTED_RESOLVER_SHA256
    ):
        raise RuntimeError(
            "Unexpected resolver SHA-256: "
            f"{resolver_sha256}"
        )

    if (
        not test_is_updated
        and test_sha256
        != EXPECTED_TEST_SHA256
    ):
        raise RuntimeError(
            "Unexpected test SHA-256: "
            f"{test_sha256}"
        )

    if not resolver_is_updated:
        create_backup(
            RESOLVER_PATH,
            RESOLVER_BACKUP_PATH,
            EXPECTED_RESOLVER_SHA256,
        )

    if not test_is_updated:
        create_backup(
            TEST_PATH,
            TEST_BACKUP_PATH,
            EXPECTED_TEST_SHA256,
        )

    resolver_content = (
        RESOLVER_PATH.read_text(
            encoding="utf-8",
        )
    )

    resolver_content = replace_once(
        resolver_content,
        OLD_RESOLVER_BLOCK,
        NEW_RESOLVER_BLOCK,
        "resolver ValueRank",
    )

    resolver_content = replace_once(
        resolver_content,
        OLD_RESOLVER_ERROR,
        NEW_RESOLVER_ERROR,
        "resolver error message",
    )

    test_content = TEST_PATH.read_text(
        encoding="utf-8",
    )

    test_content = replace_once(
        test_content,
        OLD_TEST_CHECK,
        NEW_TEST_CHECK,
        "test ValueRank",
    )

    validate_resolver(
        resolver_content
    )

    validate_test(
        test_content
    )

    RESOLVER_PATH.write_text(
        resolver_content,
        encoding="utf-8",
    )

    TEST_PATH.write_text(
        test_content,
        encoding="utf-8",
    )

    validate_resolver(
        RESOLVER_PATH.read_text(
            encoding="utf-8",
        )
    )

    validate_test(
        TEST_PATH.read_text(
            encoding="utf-8",
        )
    )

    write_hash_manifest(
        RESOLVER_PATH,
        RESOLVER_HASH_PATH,
    )

    write_hash_manifest(
        TEST_PATH,
        TEST_HASH_PATH,
    )

    print()
    print(
        "ValueRank Any compatibility "
        "update passed"
    )


if __name__ == "__main__":
    main()
