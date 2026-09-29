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
    / "build_padim_device_nodeset.before_model_version.py"
)

HASH_PATH = (
    REPOSITORY_ROOT
    / "evidence"
    / "padim-stack"
    / "build-padim-device-nodeset-after-model-version.sha256"
)

OLD_INJECTED_BLOCK = (
    '        "PROJECT_MODEL_URI = INSTANCE_URI\\n"\n'
    '        "NODESET_XML_NAMESPACE = (\\n"'
)

NEW_INJECTED_BLOCK = (
    '        "PROJECT_MODEL_URI = INSTANCE_URI\\n"\n'
    '        "PROJECT_MODEL_VERSION = \\"1.0.0\\"\\n"\n'
    '        "NODESET_XML_NAMESPACE = (\\n"'
)

MODEL_VERSION_SOURCE_FRAGMENT = (
    '        "PROJECT_MODEL_VERSION = '
    '\\"1.0.0\\"\\n"'
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


def is_already_updated(
    content: str,
) -> bool:
    return (
        content.count(
            MODEL_VERSION_SOURCE_FRAGMENT
        )
        == 1
    )


def validate_original_content(
    content: str,
) -> None:
    if is_already_updated(content):
        print(
            "Generator already injects "
            "PROJECT_MODEL_VERSION"
        )
        return

    old_block_count = content.count(
        OLD_INJECTED_BLOCK
    )

    if old_block_count != 1:
        raise RuntimeError(
            "Expected exactly one injected model "
            "URI block, found "
            f"{old_block_count}"
        )

    if (
        "PROJECT_MODEL_VERSION = "
        '"1.0.0"'
        not in content
    ):
        raise RuntimeError(
            "The outer generator does not define "
            "PROJECT_MODEL_VERSION"
        )

    if (
        "EXPECTED_PROJECT_NODE_COUNT = 18"
        not in content
    ):
        raise RuntimeError(
            "The generator does not contain the "
            "approved 18-node update"
        )

    if (
        "PT101.SignalSet.Pressure."
        not in content
        or "SignalTag"
        not in content
    ):
        raise RuntimeError(
            "The generator does not contain the "
            "SignalTag update"
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
    if is_already_updated(content):
        return content

    return content.replace(
        OLD_INJECTED_BLOCK,
        NEW_INJECTED_BLOCK,
        1,
    )


def validate_updated_content(
    content: str,
) -> None:
    compile(
        content,
        str(GENERATOR_PATH),
        "exec",
    )

    checks = [
        (
            "model version injected once",
            content.count(
                MODEL_VERSION_SOURCE_FRAGMENT
            )
            == 1,
        ),
        (
            "old injected block removed",
            OLD_INJECTED_BLOCK
            not in content,
        ),
        (
            "new injected block exists",
            NEW_INJECTED_BLOCK
            in content,
        ),
        (
            "outer model version preserved",
            (
                'PROJECT_MODEL_VERSION = "1.0.0"'
                in content
            ),
        ),
        (
            "18-node count preserved",
            content.count(
                "EXPECTED_PROJECT_NODE_COUNT = 18"
            )
            == 2,
        ),
        (
            "SignalTag update preserved",
            (
                '"PT101.SignalSet.Pressure."\n'
                '        "SignalTag"'
            )
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
    print("Updated generator validation:")

    for name, passed in checks:
        print(
            "  PASS" if passed else "  FAIL",
            name,
        )

        if not passed:
            failed = True

    if failed:
        raise RuntimeError(
            "Model-version generator update "
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

    already_updated = is_already_updated(
        original_content
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
        "Model-version generator update passed"
    )


if __name__ == "__main__":
    main()
