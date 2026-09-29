from __future__ import annotations

from pathlib import Path


REPOSITORY_ROOT = Path.cwd()

ASTERISK = chr(42)

EVIDENCE_DIRECTORY = (
    REPOSITORY_ROOT
    / "evidence"
    / "padim-stack"
)

BASELINE_DIRECTORY = (
    EVIDENCE_DIRECTORY
    / "runtime-baseline"
)

ACCIDENTAL_FILES = [
    EVIDENCE_DIRECTORY
    / "runtime",
    EVIDENCE_DIRECTORY
    / (
        "address-s"
        + ASTERISK
        + "ace-structure.txt"
    ),
    EVIDENCE_DIRECTORY
    / (
        "server-s"
        + ASTERISK
        + "ructure.txt"
    ),
]

REQUIRED_FILES = [
    BASELINE_DIRECTORY
    / "server.py",
    BASELINE_DIRECTORY
    / "synchronization.py",
    BASELINE_DIRECTORY
    / "opcua_types.py",
    BASELINE_DIRECTORY
    / "opcua_config_model.py",
    BASELINE_DIRECTORY
    / "nodeset_loader.py",
    BASELINE_DIRECTORY
    / "address_space.py",
    EVIDENCE_DIRECTORY
    / "server-structure.txt",
    EVIDENCE_DIRECTORY
    / "synchronization-structure.txt",
    EVIDENCE_DIRECTORY
    / "address-space-structure.txt",
    EVIDENCE_DIRECTORY
    / "opcua-config-model-structure.txt",
]


def verify_required_files() -> None:
    missing_files = [
        path
        for path in REQUIRED_FILES
        if not path.is_file()
    ]

    if not missing_files:
        print(
            "PASS: all required baseline files exist"
        )
        return

    print(
        "FAIL: required baseline files are missing"
    )

    for path in missing_files:
        print(
            " ",
            path,
        )

    raise SystemExit(1)


def describe_accidental_files() -> None:
    print()
    print("Accidental evidence files:")

    for path in ACCIDENTAL_FILES:
        print(
            " ",
            path,
            "exists=",
            path.exists(),
            "file=",
            path.is_file(),
        )


def remove_accidental_files() -> None:
    print()
    print("Accidental evidence cleanup:")

    for path in ACCIDENTAL_FILES:
        if not path.exists():
            print(
                "  ABSENT",
                path,
            )
            continue

        if not path.is_file():
            print(
                "  SKIPPED, not a regular file:",
                path,
            )
            continue

        path.unlink()

        print(
            "  REMOVED",
            path,
        )


def verify_cleanup() -> None:
    remaining_files = [
        path
        for path in ACCIDENTAL_FILES
        if path.exists()
    ]

    print()

    if not remaining_files:
        print(
            "PASS: accidental evidence files removed"
        )
        return

    print(
        "FAIL: accidental evidence files remain"
    )

    for path in remaining_files:
        print(
            " ",
            path,
        )

    raise SystemExit(1)


def main() -> None:
    verify_required_files()
    describe_accidental_files()
    remove_accidental_files()
    verify_cleanup()


if __name__ == "__main__":
    main()

