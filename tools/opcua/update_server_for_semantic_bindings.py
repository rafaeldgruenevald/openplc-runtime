from __future__ import annotations

import hashlib
import shutil
from pathlib import Path


REPOSITORY_ROOT = Path.cwd()

SERVER_PATH = (
    REPOSITORY_ROOT
    / "core"
    / "src"
    / "drivers"
    / "plugins"
    / "python"
    / "opcua"
    / "server.py"
)

BACKUP_PATH = (
    REPOSITORY_ROOT
    / "evidence"
    / "padim-stack"
    / "server.before-semantic-binding.py"
)

HASH_PATH = (
    REPOSITORY_ROOT
    / "evidence"
    / "padim-stack"
    / "server-after-semantic-binding.sha256"
)

EXPECTED_BASELINE_SHA256 = (
    "8ed51fbbcbc3bc860b42815276875fa2"
    "b9cd8192e1724dc7cf8730dcbadcd49a"
)

RELATIVE_IMPORT_MARKER = (
    "    from .nodeset_loader import import_nodesets\n"
)

RELATIVE_IMPORT_REPLACEMENT = (
    "    from .nodeset_loader import import_nodesets\n"
    "    from .imported_node_bindings import (\n"
    "        COLLISION_POLICY_REPLACE,\n"
    "        ImportedBindingResult,\n"
    "        load_and_resolve_imported_node_bindings,\n"
    "    )\n"
)

FALLBACK_IMPORT_MARKER = (
    "    from nodeset_loader import import_nodesets\n"
)

FALLBACK_IMPORT_REPLACEMENT = (
    "    from nodeset_loader import import_nodesets\n"
    "    from imported_node_bindings import (\n"
    "        COLLISION_POLICY_REPLACE,\n"
    "        ImportedBindingResult,\n"
    "        load_and_resolve_imported_node_bindings,\n"
    "    )\n"
)

ATTRIBUTE_MARKER = (
    "        # Synchronization manager "
    "(initialized after address space)\n"
    "        self.sync_manager: "
    "Optional[SynchronizationManager] = None\n"
)

ATTRIBUTE_REPLACEMENT = (
    "        # Semantic binding result "
    "(initialized after address space)\n"
    "        self.semantic_binding_result: Optional[\n"
    "            ImportedBindingResult\n"
    "        ] = None\n"
    "\n"
    "        # Synchronization manager "
    "(initialized after address space)\n"
    "        self.sync_manager: "
    "Optional[SynchronizationManager] = None\n"
)

RUN_MARKER = (
    "            # Register permission callbacks "
    "(AFTER address space, BEFORE start)\n"
    "            if not await self._register_callbacks():\n"
)

RUN_REPLACEMENT = (
    "            # Resolve imported semantic bindings after all NodeSets\n"
    "            # and legacy variables have been created, but before\n"
    "            # callbacks and synchronization are initialized.\n"
    "            if not await self._resolve_semantic_bindings():\n"
    "                log_error(\n"
    "                    \"Failed to resolve semantic OPC UA bindings\"\n"
    "                )\n"
    "                return\n"
    "\n"
    "            # Register permission callbacks "
    "(AFTER address space, BEFORE start)\n"
    "            if not await self._register_callbacks():\n"
)

METHOD_INSERTION_MARKER = (
    "    async def _initialize_sync_manager(self) -> bool:\n"
)

METHOD_CONTENT = '''    async def _resolve_semantic_bindings(self) -> bool:
        """
        Resolve configured semantic NodeSet bindings.

        Bindings are loaded after the configured NodeSets and legacy
        address space have been created. This allows imported semantic
        variables to replace legacy synchronization targets without
        creating duplicate nodes.

        The feature is optional. If OPENPLC_OPCUA_BINDINGS is absent or
        empty, the legacy variable mapping remains unchanged.

        Returns:
            True if no bindings are configured or every binding was
            resolved successfully.
        """
        binding_path = os.getenv(
            "OPENPLC_OPCUA_BINDINGS",
            "",
        ).strip()

        if not binding_path:
            log_debug(
                "No semantic OPC UA bindings configured"
            )
            return True

        if not self.server:
            log_error(
                "Cannot resolve semantic OPC UA bindings because "
                "the server is not initialized"
            )
            return False

        try:
            log_info(
                "Loading semantic OPC UA bindings from "
                f"{binding_path}"
            )

            result = (
                await load_and_resolve_imported_node_bindings(
                    server=self.server,
                    binding_path=binding_path,
                    existing_variable_nodes=(
                        self.variable_nodes
                    ),
                    collision_policy=(
                        COLLISION_POLICY_REPLACE
                    ),
                )
            )

            self.variable_nodes = (
                result.variable_nodes
            )

            self.semantic_binding_result = (
                result
            )

            log_info(
                "Semantic OPC UA bindings resolved: "
                f"{len(result.resolved_bindings)} total, "
                f"{result.new_binding_count} new, "
                f"{result.replacement_count} replaced"
            )

            for resolved in result.resolved_bindings:
                log_debug(
                    "Active semantic binding "
                    f"{resolved.binding.binding_id}: "
                    f"{resolved.address} -> "
                    f"{resolved.node_id}"
                )

            return True

        except Exception as exception:
            log_error(
                "Failed to resolve semantic OPC UA bindings "
                f"from {binding_path}: {exception}"
            )
            traceback.print_exc()
            return False

'''

UPDATED_IMPORT_FRAGMENT = (
    "load_and_resolve_imported_node_bindings"
)

UPDATED_METHOD_FRAGMENT = (
    "async def _resolve_semantic_bindings"
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


def require_server() -> None:
    if SERVER_PATH.is_file():
        return

    raise FileNotFoundError(
        f"Server source does not exist: "
        f"{SERVER_PATH}"
    )


def read_server() -> str:
    return SERVER_PATH.read_text(
        encoding="utf-8",
    )


def already_updated(
    content: str,
) -> bool:
    return (
        content.count(
            UPDATED_METHOD_FRAGMENT
        )
        == 1
        and content.count(
            "OPENPLC_OPCUA_BINDINGS"
        )
        >= 1
        and content.count(
            UPDATED_IMPORT_FRAGMENT
        )
        >= 2
        and content.count(
            "await self._resolve_semantic_bindings()"
        )
        == 1
    )


def validate_original(
    content: str,
) -> None:
    if already_updated(content):
        print(
            "Server already contains the semantic "
            "binding integration"
        )
        return

    actual_sha256 = calculate_sha256(
        SERVER_PATH
    )

    if actual_sha256 != EXPECTED_BASELINE_SHA256:
        raise RuntimeError(
            "Unexpected server.py baseline SHA-256. "
            f"Expected {EXPECTED_BASELINE_SHA256}, "
            f"found {actual_sha256}"
        )

    checks = [
        (
            "relative import marker exists once",
            content.count(
                RELATIVE_IMPORT_MARKER
            )
            == 1,
        ),
        (
            "fallback import marker exists once",
            content.count(
                FALLBACK_IMPORT_MARKER
            )
            == 1,
        ),
        (
            "sync-manager attribute marker exists once",
            content.count(
                ATTRIBUTE_MARKER
            )
            == 1,
        ),
        (
            "run insertion marker exists once",
            content.count(
                RUN_MARKER
            )
            == 1,
        ),
        (
            "method insertion marker exists once",
            content.count(
                METHOD_INSERTION_MARKER
            )
            == 1,
        ),
        (
            "semantic binding method is absent",
            UPDATED_METHOD_FRAGMENT
            not in content,
        ),
        (
            "binding environment variable is absent",
            "OPENPLC_OPCUA_BINDINGS"
            not in content,
        ),
    ]

    failed = False

    print(
        "Pre-update server validation:"
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
            "server.py is not in the expected "
            "pre-update state"
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

        if (
            backup_sha256
            != EXPECTED_BASELINE_SHA256
        ):
            raise RuntimeError(
                "Existing server backup does not "
                "match the approved baseline: "
                f"{backup_sha256}"
            )

        print(
            "Approved server backup already exists:",
            BACKUP_PATH,
        )
        return

    shutil.copy2(
        SERVER_PATH,
        BACKUP_PATH,
    )

    print(
        "Server backup written:",
        BACKUP_PATH,
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

    if occurrences != 1:
        raise RuntimeError(
            f"Expected one {label} marker, "
            f"found {occurrences}"
        )

    return content.replace(
        old,
        new,
        1,
    )


def update_content(
    content: str,
) -> str:
    if already_updated(content):
        return content

    updated = replace_once(
        content,
        RELATIVE_IMPORT_MARKER,
        RELATIVE_IMPORT_REPLACEMENT,
        "relative import",
    )

    updated = replace_once(
        updated,
        FALLBACK_IMPORT_MARKER,
        FALLBACK_IMPORT_REPLACEMENT,
        "fallback import",
    )

    updated = replace_once(
        updated,
        ATTRIBUTE_MARKER,
        ATTRIBUTE_REPLACEMENT,
        "semantic result attribute",
    )

    updated = replace_once(
        updated,
        RUN_MARKER,
        RUN_REPLACEMENT,
        "run integration",
    )

    updated = replace_once(
        updated,
        METHOD_INSERTION_MARKER,
        (
            METHOD_CONTENT
            + METHOD_INSERTION_MARKER
        ),
        "semantic binding method insertion",
    )

    return updated


def validate_updated(
    content: str,
) -> None:
    compile(
        content,
        str(SERVER_PATH),
        "exec",
    )

    resolve_position = content.index(
        "await self._resolve_semantic_bindings()"
    )

    callback_position = content.index(
        "await self._register_callbacks()"
    )

    sync_position = content.index(
        "await self._initialize_sync_manager()"
    )

    checks = [
        (
            "relative resolver import exists",
            content.count(
                "from .imported_node_bindings import"
            )
            == 1,
        ),
        (
            "fallback resolver import exists",
            content.count(
                "from imported_node_bindings import"
            )
            == 1,
        ),
        (
            "resolver loader appears three times",
            content.count(
                UPDATED_IMPORT_FRAGMENT
            )
            == 3,
        ),
        (
            "semantic result attribute exists",
            content.count(
                "self.semantic_binding_result"
            )
            == 2,
        ),
        (
            "semantic binding method exists once",
            content.count(
                UPDATED_METHOD_FRAGMENT
            )
            == 1,
        ),
        (
            "binding environment variable exists once",
            content.count(
                "OPENPLC_OPCUA_BINDINGS"
            )
            == 2,
        ),
        (
            "semantic resolution called once",
            content.count(
                "await self._resolve_semantic_bindings()"
            )
            == 1,
        ),
        (
            "resolution occurs before callbacks",
            resolve_position
            < callback_position,
        ),
        (
            "resolution occurs before sync manager",
            resolve_position
            < sync_position,
        ),
        (
            "replace policy is used",
            "COLLISION_POLICY_REPLACE"
            in content,
        ),
        (
            "legacy address-space creation preserved",
            content.count(
                "async def _create_address_space"
            )
            == 1,
        ),
        (
            "sync-manager method preserved",
            content.count(
                "async def _initialize_sync_manager"
            )
            == 1,
        ),
        (
            "server entry point preserved",
            content.count(
                "async def run(self)"
            )
            == 1,
        ),
    ]

    failed = False

    print()
    print(
        "Updated server validation:"
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
            "Updated server validation failed"
        )


def write_server(
    content: str,
) -> None:
    SERVER_PATH.write_text(
        content,
        encoding="utf-8",
    )


def write_hash_manifest() -> None:
    digest = calculate_sha256(
        SERVER_PATH
    )

    relative_path = (
        SERVER_PATH.relative_to(
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
        "Updated server SHA-256:",
        digest,
    )
    print(
        "Hash manifest:",
        HASH_PATH,
    )


def main() -> None:
    require_server()

    original = read_server()

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
        write_server(
            updated
        )

    written = read_server()

    if written != updated:
        raise RuntimeError(
            "Written server differs from the "
            "validated updated content"
        )

    validate_updated(
        written
    )

    write_hash_manifest()

    print()
    print(
        "Semantic binding server integration passed"
    )


if __name__ == "__main__":
    main()
