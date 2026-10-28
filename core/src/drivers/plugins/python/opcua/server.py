# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Autonomy®

"""
OPC UA Server Manager.

This module provides the main server orchestration for the OPC UA plugin.
It coordinates all server components and manages the server lifecycle.
"""

import asyncio
import os
import sys
import traceback
from datetime import datetime
from typing import Optional, Dict, Any

from asyncua import Server, ua

# Add directories to path for module access
_current_dir = os.path.dirname(os.path.abspath(__file__))
_parent_dir = os.path.dirname(_current_dir)
if _current_dir not in sys.path:
    sys.path.insert(0, _current_dir)
if _parent_dir not in sys.path:
    sys.path.insert(0, _parent_dir)

# Import local modules (handle both package and direct loading)
try:
    from .opcua_logging import log_info, log_warn, log_error, log_debug
    from .opcua_security import OpcuaSecurityManager
    from .opcua_endpoints_config import normalize_endpoint_url, suggest_client_endpoints
    from .address_space import AddressSpaceBuilder
    from .synchronization import SynchronizationManager
    from .user_manager import OpenPLCUserManager
    from .callbacks import PermissionCallbackHandler
    from .opcua_types import VariableNode
    from .model_paths import generated_root, resolve_model_file
    from .nodeset_loader import ALLOWED_MODEL_ROOT, import_nodesets
    from .imported_node_bindings import (
        COLLISION_POLICY_REPLACE,
        ImportedBindingResult,
        load_and_resolve_imported_node_bindings,
    )
except ImportError:
    from opcua_logging import log_info, log_warn, log_error, log_debug
    from opcua_security import OpcuaSecurityManager
    from opcua_endpoints_config import normalize_endpoint_url, suggest_client_endpoints
    from address_space import AddressSpaceBuilder
    from synchronization import SynchronizationManager
    from user_manager import OpenPLCUserManager
    from callbacks import PermissionCallbackHandler
    from opcua_types import VariableNode
    from model_paths import generated_root, resolve_model_file
    from nodeset_loader import ALLOWED_MODEL_ROOT, import_nodesets
    from imported_node_bindings import (
        COLLISION_POLICY_REPLACE,
        ImportedBindingResult,
        load_and_resolve_imported_node_bindings,
    )

from shared import SafeBufferAccess
from shared.plugin_config_decode.opcua_config_model import OpcuaConfig

from asyncua.crypto.validator import CertificateValidator

try:
    from .certificate_push import CertificatePush, apply_pushed_trust_list, trust_list_of
    from .ocf_client import OcfClient
    from .opcua_security import PEER_TRUST_OPTIONS
except ImportError:
    from certificate_push import CertificatePush, apply_pushed_trust_list, trust_list_of
    from ocf_client import OcfClient
    from opcua_security import PEER_TRUST_OPTIONS

class OpcuaServerManager:
    """
    Manages the OPC-UA server lifecycle and coordinates components.

    Responsibilities:
    - Server initialization and configuration
    - Security setup (certificates, policies)
    - Component orchestration (address space, sync, callbacks)
    - Main run loop
    - Graceful shutdown

    Usage:
        manager = OpcuaServerManager(config, buffer_accessor, plugin_dir)
        await manager.run()  # Blocks until stop() is called
        await manager.stop()
    """

    def __init__(
        self,
        config: OpcuaConfig,
        buffer_accessor: SafeBufferAccess,
        plugin_dir: str
    ):
        """
        Initialize the server manager.

        Args:
            config: Typed OpcuaConfig instance
            buffer_accessor: SafeBufferAccess for PLC memory operations
            plugin_dir: Directory path for certificates and resources
        """
        self.config = config
        self.buffer_accessor = buffer_accessor
        self.plugin_dir = plugin_dir

        # A trust list the certificate manager pushed replaces the program's
        # (before the security and user managers read it)
        apply_pushed_trust_list(self.config)

        # Server state
        self.server: Optional[Server] = None
        self.running = False
        self.namespace_idx: Optional[int] = None

        # Security manager
        self.security_manager = OpcuaSecurityManager(config, plugin_dir)

        # User manager for authentication
        self.user_manager = OpenPLCUserManager(config)

        # Client endpoint suggestions (populated after setup)
        self._client_endpoints: Dict[str, str] = {}

        # Address space builder (initialized in _create_address_space)
        self.address_space_builder: Optional[AddressSpaceBuilder] = None

        # Node mappings (populated by address space builder).
        # Variables are keyed by (arr, elem) tuples — the same
        # address the runtime's debug_read / debug_write thunks take.
        self.variable_nodes: Dict[Any, VariableNode] = {}
        self.node_permissions: Dict[str, Any] = {}
        self.nodeid_to_variable: Dict[Any, str] = {}

        # Semantic binding result (initialized after address space)
        self.semantic_binding_result: Optional[
            ImportedBindingResult
        ] = None

        # Synchronization manager (initialized after address space)
        self.sync_manager: Optional[SynchronizationManager] = None

        # Permission callback handler (initialized after address space)
        self.callback_handler: Optional[PermissionCallbackHandler] = None

        # OCF client (signals taken from other DCNs, found through the GDS)
        self.ocf_client: Optional[OcfClient] = None
        self._ocf_task: Optional[asyncio.Task] = None

        # Push certificate management; a new certificate needs a new server
        self.certificate_push: Optional[CertificatePush] = None
        self.restart_requested = False
        self.start_failed = False

        # The listening sockets are open: they must be closed before a new server binds
        self._server_started = False

    async def run(self) -> None:
        """
        Initialize, start, and run the server.

        This is the main entry point that:
        1. Sets up the server with security
        2. Creates address space (Phase 2)
        3. Starts the server
        4. Runs the sync loop (Phase 3)

        Blocks until stop() is called or an error occurs.
        """
        try:
            log_info("OpcuaServerManager starting...")

            # Setup server
            if not await self._setup_server():
                log_error("Failed to setup server")
                return

            await self._link_certificate_push()

            if not await self._import_configured_nodesets():
                log_warn("Failed to import OPC UA NodeSets")
                return

            # Create address space (nodes)
            if not await self._create_address_space():
                log_error("Failed to create address space")
                return

            # Resolve imported semantic bindings after all NodeSets
            # and legacy variables have been created, but before
            # callbacks and synchronization are initialized.
            if not await self._resolve_semantic_bindings():
                log_error(
                    "Failed to resolve semantic OPC UA bindings"
                )
                return

            # Register permission callbacks (AFTER address space, BEFORE start)
            if not await self._register_callbacks():
                log_warn("Failed to register permission callbacks - continuing without access control")

            # Initialize synchronization manager
            if not await self._initialize_sync_manager():
                log_error("Failed to initialize sync manager")
                return

            # Start server
            if not await self._start_server():
                log_error("Failed to start server")
                self.start_failed = True
                return

            # The OCF client runs next to the server
            self._start_ocf_client()

            # Run main loop
            log_debug("Server running, entering main loop...")
            await self._main_loop()

        except Exception as e:
            log_error(f"Error in server manager: {e}")
            traceback.print_exc()
        finally:
            await self._cleanup()

    async def _link_certificate_push(self) -> None:
        """OPC 10000-12 push: a certificate manager may renew this server's
        certificate (ServerConfiguration methods)."""
        self.certificate_push = CertificatePush(
            self.config.server.application_uri,
            getattr(self.config.security, "certificate_store", None),
            self.security_manager.credential_files,
            self._restart_for_new_certificate,
            getattr(self.config.security, "certificate_hosts", None),
            lambda: trust_list_of(
                [entry["pem"] for entry in self.config.security.trusted_client_certificates],
                getattr(self.config.security, "trusted_crls", None) or [],
            ),
        )

        await self.certificate_push.link(self.server)

    def _restart_for_new_certificate(self) -> None:
        """ApplyChanges: end this run; the plugin starts a new server, which
        loads the pushed certificate."""
        self.restart_requested = True
        self.running = False

    async def stop(self) -> None:
        """
        Stop the server gracefully.

        Sets running flag to False and waits for main loop to exit.
        """
        log_debug("Stop requested...")
        self.running = False

    async def _setup_server(self) -> bool:
        """
        Configure and initialize the asyncua Server.

        Order of operations (critical for asyncua):
        1. Create Server instance
        2. Set endpoint URL (BEFORE init)
        3. Set server name (BEFORE init)
        4. Configure security (BEFORE init)
        5. Call server.init()
        6. Register namespace (AFTER init)
        7. Set build info (AFTER init)

        Returns:
            True if setup successful, False otherwise
        """
        try:
            # Create server with user manager for authentication
            self.server = Server(user_manager=self.user_manager)

            # Normalize and set endpoint URL (BEFORE init)
            try:
                normalized_endpoint = normalize_endpoint_url(
                    self.config.server.endpoint_url
                )
                self.server.set_endpoint(normalized_endpoint)
                self._client_endpoints = suggest_client_endpoints(normalized_endpoint)
                log_debug(f"Server endpoint set to: {normalized_endpoint}")
            except Exception as e:
                log_warn(f"Endpoint normalization failed, using raw URL: {e}")
                self.server.set_endpoint(self.config.server.endpoint_url)

            # Set server name and URIs (BEFORE init)
            self.server.set_server_name(self.config.server.name)
            self.server.application_uri = self.config.server.application_uri

            # Configure security (BEFORE init)
            await self.security_manager.setup_server_security(
                self.server,
                self.config.server.security_profiles,
                app_uri=self.config.server.application_uri
            )

            # Setup certificate validation for client certificates (BEFORE init)
            if self.config.security.trusted_client_certificates:
                await self.security_manager.setup_certificate_validation(
                    self.server,
                    self.config.security.trusted_client_certificates
                )

            # Initialize the server
            await self.server.init()
            log_debug("OPC-UA server initialized")

            # init() resets the application URI to asyncua's default, and a plain
            # attribute assignment before it has no effect: the endpoints and the
            # ServerArray announce whatever set_application_uri() was given last.
            # The certificate was made for the configured URI, and clients (and a
            # GDS reading this server) refuse an endpoint that names another one.
            await self.server.set_application_uri(self.config.server.application_uri)

            # init() also wrote the default URI into ServerArray[0], which is how
            # a GDS names the server an alias belongs to (OPC 10000-17).
            await self.server.get_node(
                ua.NodeId(ua.ObjectIds.Server_ServerArray)
            ).write_value([self.config.server.application_uri], ua.VariantType.String)

            # Register namespace (AFTER init)
            self.namespace_idx = await self.server.register_namespace(
                self.config.address_space.namespace_uri
            )
            log_debug(
                f"Registered namespace: {self.config.address_space.namespace_uri} "
                f"(index: {self.namespace_idx})"
            )

            # Set build info (AFTER init)
            await self.server.set_build_info(
                product_uri=self.config.server.product_uri,
                manufacturer_name="Autonomy Logic",
                product_name="OpenPLC Runtime",
                software_version="1.0.0",
                build_number="1.0.0.0",
                build_date=datetime.now()
            )

            log_debug("OPC-UA server setup completed successfully")
            return True

        except Exception as e:
            log_error(f"Failed to setup OPC-UA server: {e}")
            traceback.print_exc()
            return False

    async def _import_configured_nodesets(self) -> bool:
        """
        Import optional NodeSet XML models.

        The paths come from the semantic_model section of opcua.json
        (relative to the extracted program). The OPENPLC_OPCUA_NODESETS
        environment variable, with paths separated by the platform path
        separator, remains as a development fallback.
        """

        if not self.server:
            log_error(
                "Cannot import NodeSets because the OPC-UA server "
                "is not initialized"
            )
            return False

        semantic_model = getattr(self.config, "semantic_model", None)

        if semantic_model is not None and semantic_model.nodesets:
            paths = list(semantic_model.nodesets)
        else:
            raw_value = os.getenv(
                "OPENPLC_OPCUA_NODESETS",
                "",
            ).strip()

            paths = [
                item.strip()
                for item in raw_value.split(os.pathsep)
                if item.strip()
            ]

        if not paths:
            log_debug(
                "No optional OPC UA NodeSets configured"
            )
            return True

        log_info(
            f"Found {len(paths)} configured OPC UA "
            "NodeSet file(s)"
        )

        try:
            results = await import_nodesets(
                server=self.server,
                raw_paths=paths,
            )

            log_info(
                f"Successfully imported {len(results)} "
                "configured OPC UA NodeSet file(s)"
            )

            return True

        except Exception as exc:
            log_error(
                "Failed to import configured OPC UA NodeSets: "
                f"{exc}"
            )
            traceback.print_exc()
            return False

    async def _start_server(self) -> bool:
        """
        Start the OPC-UA server.

        Returns:
            True if server started successfully, False otherwise
        """
        try:
            if not self.server:
                log_error("Server not initialized")
                return False

            await self.server.start()
            self.running = True
            self._server_started = True

            log_info(f"OPC-UA server started on {self.config.server.endpoint_url}")

            # Print alternative endpoints for client connection
            if self._client_endpoints:
                log_debug("Alternative client endpoints:")
                for scenario, endpoint in self._client_endpoints.items():
                    if endpoint:
                        log_debug(f"  {scenario}: {endpoint}")

            return True

        except Exception as e:
            log_error(f"Failed to start OPC-UA server: {e}")
            traceback.print_exc()
            return False

    async def _main_loop(self) -> None:
        """
        Main server loop with bidirectional synchronization.

        Runs the sync manager's unified sync loop which handles:
        1. OPC-UA → Runtime (client writes to PLC)
        2. Runtime → OPC-UA (PLC values to clients)
        """
        cycle_time = self.config.cycle_time_ms / 1000.0

        if self.sync_manager:
            # Run the sync manager's loop (blocks until stopped)
            await self.sync_manager.run(
                is_running=lambda: self.running,
                cycle_time_seconds=cycle_time
            )
        else:
            # Fallback: simple keepalive loop (no sync)
            log_warn("No sync manager - running without synchronization")
            while self.running:
                try:
                    await asyncio.sleep(cycle_time)
                except asyncio.CancelledError:
                    log_debug("Main loop cancelled")
                    break

    def _start_ocf_client(self) -> None:
        """Start the OCF client when the config has inputs. It needs the
        certificate of this server to open a secure channel to the GDS; without
        it the inputs cannot be served, which is reported, not fatal."""
        ocf = getattr(self.config, "ocf", None)

        if ocf is None or not ocf.inputs:
            return

        credentials = self.security_manager.credential_files()

        if credentials is None:
            log_error(
                "OCF client not started: the server certificate and key are "
                "needed for the channel to the GDS (strategy auto_self_signed, "
                "or a custom certificate and key)"
            )
            return

        certificate, private_key = credentials

        self._ocf_task = asyncio.create_task(
            self._run_ocf_client(ocf, certificate, private_key)
        )

    async def _run_ocf_client(self, ocf, certificate: str, private_key: str) -> None:
        # The servers the client reaches are held to the same trust list as
        # the clients this server accepts.
        validator = None

        trusted = self.config.security.trusted_client_certificates

        if trusted:
            pems = [item["pem"] if isinstance(item, dict) else item for item in trusted]

            trust_store = await self.security_manager.create_trust_store(pems)

            if trust_store is not None:
                validator = CertificateValidator(
                    PEER_TRUST_OPTIONS, trust_store=trust_store
                )

        self.ocf_client = OcfClient(
            ocf,
            self.buffer_accessor.runtime_args,
            self.config.server.application_uri,
            certificate,
            private_key,
            validator=validator,
        )

        await self.ocf_client.run()

    async def _stop_ocf_client(self) -> None:
        if self.ocf_client is not None:
            await self.ocf_client.stop()

        if self._ocf_task is not None:
            self._ocf_task.cancel()
            await asyncio.gather(self._ocf_task, return_exceptions=True)

        self.ocf_client = None
        self._ocf_task = None

    def _force_close(self) -> None:
        """Close the listening socket and abort the connections of a server whose
        stop() is still waiting on its clients: a new server must be able to bind
        the port (a restart after ApplyChanges), and connections nobody reads
        pile up otherwise."""
        bserver = getattr(self.server, "bserver", None)
        listener = getattr(bserver, "_server", None)

        if listener is not None:
            listener.close()

        iserver = getattr(self.server, "iserver", None)

        for transport in list(getattr(iserver, "asyncio_transports", None) or []):
            try:
                transport.abort()
            except Exception as e:  # noqa: BLE001 - a transport already gone
                log_debug(f"aborting a connection: {e}")

    async def _cleanup(self) -> None:
        """
        Clean up resources.

        Stops the server and releases resources. asyncua's server.stop()
        can block while it waits for connected clients to disconnect
        gracefully (a UAExpert client left running across an editor
        Stop press is the classic case). Cap that with a short timeout
        so the editor's Stop button feels responsive — any clients
        that don't disconnect in 1.5s are dropped when the listening
        sockets close.
        """
        try:
            await self._stop_ocf_client()

            # running is already False when stop() or a restart ended the loop:
            # what matters is whether the server bound its sockets
            if self.server and self._server_started:
                try:
                    await asyncio.wait_for(self.server.stop(), timeout=1.5)
                    log_info("OPC-UA server stopped")
                except asyncio.TimeoutError:
                    log_warn("OPC-UA server.stop() did not finish in 1.5s; "
                             "closing its socket and connections")
                    self._force_close()

            self.running = False
            self.server = None

            # Clean up security manager resources (temp directories, etc.)
            if self.security_manager:
                self.security_manager.cleanup()

        except Exception as e:
            log_error(f"Error during cleanup: {e}")

    # -------------------------------------------------------------------------
    # Address Space Creation
    # -------------------------------------------------------------------------

    async def _create_address_space(self) -> bool:
        """
        Create OPC-UA nodes from configuration.

        Uses AddressSpaceBuilder to create all variable nodes
        and stores the resulting mappings for synchronization.

        Returns:
            True if address space created successfully
        """
        try:
            self.address_space_builder = AddressSpaceBuilder(
                self.server,
                self.namespace_idx,
                self.config
            )

            if not await self.address_space_builder.build():
                return False

            # Copy mappings from builder for easy access
            self.variable_nodes = self.address_space_builder.variable_nodes
            self.node_permissions = self.address_space_builder.node_permissions
            self.nodeid_to_variable = self.address_space_builder.nodeid_to_variable

            log_debug(f"Address space created with {len(self.variable_nodes)} nodes")
            return True

        except Exception as e:
            log_error(f"Failed to create address space: {e}")
            traceback.print_exc()
            return False

    async def _resolve_semantic_bindings(self) -> bool:
        """
        Resolve configured semantic NodeSet bindings.

        Bindings are loaded after the configured NodeSets and legacy
        address space have been created. This allows imported semantic
        variables to replace legacy synchronization targets without
        creating duplicate nodes.

        The feature is optional. If neither the semantic_model section
        of opcua.json nor OPENPLC_OPCUA_BINDINGS names a file, the legacy
        variable mapping remains unchanged.

        Returns:
            True if no bindings are configured or every binding was
            resolved successfully.
        """
        semantic_model = getattr(self.config, "semantic_model", None)

        binding_path = (
            semantic_model.bindings
            if semantic_model is not None and semantic_model.bindings
            else os.getenv(
                "OPENPLC_OPCUA_BINDINGS",
                "",
            ).strip()
        )

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
            binding_path = str(
                resolve_model_file(
                    binding_path,
                    roots=(generated_root(), ALLOWED_MODEL_ROOT),
                    suffixes=(".json",),
                )
            )

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

    async def _initialize_sync_manager(self) -> bool:
        """
        Initialize the synchronization manager.

        Creates the sync manager and initializes its metadata cache
        for optimized memory access. Passes server reference for
        optimized subscription notifications via write_attribute_value.

        Returns:
            True if initialization successful
        """
        try:
            # SyncManager talks to the runtime's debug_* C function
            # pointers directly via the underlying ctypes struct.
            # buffer_accessor.runtime_args exposes that struct.
            self.sync_manager = SynchronizationManager(
                args=self.buffer_accessor.runtime_args,
                variable_nodes=self.variable_nodes,
                server=self.server,
                composite_nodes=(
                    self.semantic_binding_result.resolved_composites
                    if self.semantic_binding_result is not None
                    else []
                ),
            )

            if not await self.sync_manager.initialize():
                log_warn("Sync manager initialization failed - sync may be limited")
                # Don't fail completely - sync manager can still work with batch ops

            log_debug("Synchronization manager initialized")
            return True

        except Exception as e:
            log_error(f"Failed to initialize sync manager: {e}")
            traceback.print_exc()
            return False

    async def _register_callbacks(self) -> bool:
        """
        Register permission callbacks for access control.

        Creates the callback handler and registers it with the server.
        Must be called AFTER address space creation and BEFORE server start.

        Returns:
            True if callbacks registered successfully
        """
        try:
            # Only register callbacks if we have nodes with permissions
            if not self.node_permissions:
                log_debug("No node permissions configured - skipping callback registration")
                return True

            self.callback_handler = PermissionCallbackHandler(
                node_permissions=self.node_permissions,
                nodeid_to_variable=self.nodeid_to_variable
            )

            if not await self.callback_handler.register(self.server):
                log_warn("Callback registration returned False")
                return False

            log_debug("Permission callback handler initialized")
            return True

        except Exception as e:
            log_error(f"Failed to register callbacks: {e}")
            traceback.print_exc()
            return False

    # -------------------------------------------------------------------------
    # Debug/Diagnostic Methods
    # -------------------------------------------------------------------------

    async def debug_endpoints(self) -> None:
        """Debug method to verify endpoint configuration."""
        try:
            log_debug("=== ENDPOINT VERIFICATION ===")
            endpoints = await self.server.get_endpoints()
            log_debug(f"Total endpoints created: {len(endpoints)}")

            for i, endpoint in enumerate(endpoints):
                log_debug(f"Endpoint {i+1}:")
                log_debug(f"  URL: {endpoint.EndpointUrl}")
                log_debug(f"  Security Policy: {endpoint.SecurityPolicyUri}")
                log_debug(f"  Security Mode: {endpoint.SecurityMode}")
                log_debug(f"  User Tokens: {len(endpoint.UserIdentityTokens)}")

            log_debug("=== END ENDPOINT VERIFICATION ===")
        except Exception as e:
            log_error(f"Error during endpoint verification: {e}")
