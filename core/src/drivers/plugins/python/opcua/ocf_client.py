# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Autonomy®

"""
OCF client of the DCN (O-PAS Part 4).

A DCN takes the signals other DCNs publish through this client, which the
program reads as ordinary variables (the OCFB_IN of the AML). For each
configured input it

  1. asks the GDS which node the alias stands for (OPC 10000-17 FindAlias on
     the TagVariables category) and which server holds it,
  2. asks the GDS where that server is (FindApplications -> discovery URL),
  3. reads the node every period and soft-writes the value into the PLC
     variable (debug_write), as the runtime's debugger would.

Nothing is cached across a failure: when the source disappears the client
resolves the alias again, so a DCN that moved is found again through the GDS.
The GDS is reached over a secure channel with the certificate of this DCN's
own OPC UA server (the GDS answers FindAlias and FindApplications to any
session, it asks for a role only to register).
"""

import asyncio
import time
from typing import Any, Callable, Dict, List, Optional, Tuple

from asyncua import Client, ua
from asyncua.common.utils import Buffer
from asyncua.ua import ua_binary as binary

try:
    from .opcua_logging import log_debug, log_info, log_warn
    from .opcua_memory import debug_write_value
except ImportError:
    from opcua_logging import log_debug, log_info, log_warn
    from opcua_memory import debug_write_value

GDS_NAMESPACE = "http://opcfoundation.org/UA/GDS/"
GDS_DIRECTORY = 141

BACKOFF_FIRST_S = 1.0
BACKOFF_MAX_S = 10.0


def decode_application_record(body: bytes) -> Tuple[str, List[str]]:
    """(ApplicationUri, DiscoveryUrls) of an ApplicationRecordDataType in its
    binary encoding (OPC 10000-12 §6.5.2). The data type dictionary of the GDS
    is not needed to read the two fields."""
    data = Buffer(body)

    binary.nodeid_from_binary(data)  # ApplicationId
    uri = binary.unpack_uatype(ua.VariantType.String, data)
    binary.unpack_uatype(ua.VariantType.Int32, data)  # ApplicationType
    binary.unpack_uatype_array(ua.VariantType.LocalizedText, data)
    binary.unpack_uatype(ua.VariantType.String, data)  # ProductUri
    urls = binary.unpack_uatype_array(ua.VariantType.String, data) or []

    return uri, list(urls)


class Source:
    """Where an alias is served: the endpoint of the server and the node."""

    def __init__(self, server_uri: str, endpoint: str, namespace_uri: str, node_id: Any):
        self.server_uri = server_uri
        self.endpoint = endpoint
        self.namespace_uri = namespace_uri
        self.node_id = node_id


class OcfClient:

    def __init__(
        self,
        config,
        runtime_args: Any,
        application_uri: str,
        certificate: str,
        private_key: str,
        writer: Callable[..., bool] = debug_write_value,
    ):
        self.config = config
        self.runtime_args = runtime_args
        self.application_uri = application_uri
        self.certificate = certificate
        self.private_key = private_key
        self.writer = writer
        self._tasks: List[asyncio.Task] = []
        # alias -> {"connected": bool, "server": str, "last_ok": float}
        self.state: Dict[str, Dict[str, Any]] = {}

    # -- lifecycle ----------------------------------------------------------

    async def run(self) -> None:
        if not self.config.inputs:
            return

        log_info(
            f"OCF client: {len(self.config.inputs)} input(s) through the GDS at {self.config.gds_url}"
        )

        self._tasks = [
            asyncio.create_task(self._input_loop(item))
            for item in self.config.inputs
        ]

        await asyncio.gather(*self._tasks, return_exceptions=True)

    async def stop(self) -> None:
        for task in self._tasks:
            task.cancel()

        await asyncio.gather(*self._tasks, return_exceptions=True)

        self._tasks = []

    # -- one input ----------------------------------------------------------

    async def _input_loop(self, item) -> None:
        state = self.state.setdefault(item.alias, {"connected": False})

        delay = BACKOFF_FIRST_S

        while True:
            try:
                source = await self._resolve(item.alias)

                async with Client(source.endpoint, timeout=10) as client:
                    index = await client.get_namespace_index(source.namespace_uri)

                    node = client.get_node(
                        ua.NodeId(source.node_id.Identifier, index, source.node_id.NodeIdType)
                    )

                    state.update(connected=True, server=source.server_uri)

                    log_info(
                        f"OCF input {item.alias}: reading {source.node_id.Identifier} from "
                        f"{source.server_uri} ({source.endpoint})"
                    )

                    delay = BACKOFF_FIRST_S

                    while True:
                        value = await node.read_data_value()

                        if value.StatusCode.is_good() and value.Value is not None:
                            self.writer(
                                self.runtime_args,
                                item.array_index,
                                item.element_index,
                                item.datatype,
                                value.Value.Value,
                            )

                            state["last_ok"] = time.monotonic()

                        await asyncio.sleep(self.config.period_ms / 1000.0)

            except asyncio.CancelledError:
                raise

            except Exception as error:
                if state.get("connected"):
                    log_warn(f"OCF input {item.alias}: lost the source ({error}); resolving it again")
                else:
                    log_debug(f"OCF input {item.alias}: not available yet ({error})")

                state["connected"] = False

                await asyncio.sleep(delay)

                delay = min(delay * 2, BACKOFF_MAX_S)

    # -- the GDS ------------------------------------------------------------

    async def _gds_session(self) -> Client:
        client = Client(self.config.gds_url, timeout=10)

        client.application_uri = self.application_uri

        await client.set_security_string(
            f"Basic256Sha256,SignAndEncrypt,{self.certificate},{self.private_key}"
        )

        return client

    async def _resolve(self, alias: str) -> Source:
        async with await self._gds_session() as gds:
            servers = await gds.get_node(
                ua.NodeId(ua.ObjectIds.Server_ServerArray)
            ).read_value()

            category = gds.get_node(ua.NodeId(ua.ObjectIds.TagVariables))

            found = await category.call_method(
                ua.QualifiedName("FindAlias", 0),
                alias,
                ua.NodeId(ua.ObjectIds.AliasFor),
            )

            candidates = []

            for entry in found or []:
                if entry.AliasName.Name != alias:
                    continue

                for target in entry.ReferencedNodes:
                    server_uri = (
                        servers[target.ServerIndex]
                        if target.ServerIndex < len(servers)
                        else ""
                    )

                    # the alias of this very DCN is not an input
                    if server_uri and server_uri != self.application_uri:
                        candidates.append((server_uri, target))

            if not candidates:
                raise LookupError(f"the GDS knows no other server that publishes {alias!r}")

            if len(candidates) > 1:
                log_warn(
                    f"OCF input {alias}: {len(candidates)} servers publish it, using "
                    f"{candidates[0][0]}"
                )

            server_uri, target = candidates[0]

            index = await gds.get_namespace_index(GDS_NAMESPACE)

            directory = gds.get_node(ua.NodeId(GDS_DIRECTORY, index))

            records = await directory.call_method(
                ua.QualifiedName("FindApplications", index), server_uri
            )

            for record in records or []:
                body = record.Body if isinstance(record, ua.ExtensionObject) else record

                uri, urls = decode_application_record(body)

                if uri == server_uri and urls:
                    return Source(server_uri, urls[0], target.NamespaceUri, target)

            raise LookupError(f"the GDS has no discovery URL for {server_uri}")
