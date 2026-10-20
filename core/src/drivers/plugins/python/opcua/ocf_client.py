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
     variable (debug_write), as the runtime's debugger would, and the
     StatusCode into the signal's MetaData.Status when the input has one.

The status says what the program can trust: the source's own StatusCode while
the source answers, BadNoCommunication while it does not. The value is then
left as it was, so a block can hold its last usable value.

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

# OPC 10000-4 StatusCodes written into MetaData.Status.
STATUS_GOOD = 0x00000000
STATUS_BAD_NO_COMMUNICATION = 0x80310000

BACKOFF_FIRST_S = 1.0
BACKOFF_MAX_S = 10.0

# Without ocf.stale_ms, a value is stale after this many periods (at least 1 s).
STALE_PERIODS = 5
STALE_MIN_MS = 1000

# A secure session (two handshakes) needs more than one stale period.
CONNECT_MIN_S = 5.0


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
        validator: Optional[Callable[..., Any]] = None,
    ):
        self.config = config
        self.runtime_args = runtime_args
        self.application_uri = application_uri
        self.certificate = certificate
        self.private_key = private_key
        self.writer = writer
        # Checks the certificate of the server on the other end: it must be
        # in the trust list or issued by one of its CAs.
        self.validator = validator
        self._tasks: List[asyncio.Task] = []
        # alias -> {"connected": bool, "server": str, "last_ok": float}
        self.state: Dict[str, Dict[str, Any]] = {}

    @property
    def stale_s(self) -> float:
        """How long a value may go without a fresh read before it is Bad."""
        stale_ms = getattr(self.config, "stale_ms", None)

        if not stale_ms:
            stale_ms = max(STALE_MIN_MS, STALE_PERIODS * self.config.period_ms)

        return stale_ms / 1000.0

    @property
    def connect_s(self) -> float:
        """How long connecting to a source may take."""
        return max(self.stale_s, CONNECT_MIN_S)

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

                client = await self._peer_session(source.endpoint)

                try:
                    await asyncio.wait_for(client.connect(), self.connect_s)

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
                        # A source that stops answering is Bad after stale_s,
                        # not after the request timeout.
                        try:
                            value = await asyncio.wait_for(
                                node.read_data_value(raise_on_bad_status=False), self.stale_s
                            )
                        except Exception:
                            # Bad at once: closing the session waits for the peer.
                            self._write_status(item, STATUS_BAD_NO_COMMUNICATION)
                            raise

                        self._deliver(item, value)

                        if value.StatusCode.is_good():
                            state["last_ok"] = time.monotonic()

                        await asyncio.sleep(self.config.period_ms / 1000.0)
                finally:
                    await self._close(client)

            except asyncio.CancelledError:
                raise

            except Exception as error:
                if isinstance(error, asyncio.TimeoutError):
                    error = f"no answer in {self.stale_s:.1f} s"

                if state.get("connected"):
                    log_warn(f"OCF input {item.alias}: lost the source ({error}); resolving it again")
                else:
                    log_debug(f"OCF input {item.alias}: not available yet ({error})")

                state["connected"] = False

                self._write_status(item, STATUS_BAD_NO_COMMUNICATION)

                await asyncio.sleep(delay)

                delay = min(delay * 2, BACKOFF_MAX_S)

    async def _close(self, client: Client) -> None:
        """Close the session; a peer that does not answer is left behind."""
        try:
            await asyncio.wait_for(client.disconnect(), self.stale_s)
        except asyncio.CancelledError:
            raise
        except Exception as error:
            log_debug(f"OCF: closing the session with a silent peer ({error})")

    def _deliver(self, item, value: ua.DataValue) -> None:
        """Write what the source sent: the value when it has one that is not
        Bad, and its StatusCode."""
        status = value.StatusCode.value if value.StatusCode is not None else STATUS_GOOD

        has_value = value.Value is not None and value.Value.Value is not None

        if has_value and not value.StatusCode.is_bad():
            self.writer(
                self.runtime_args,
                item.array_index,
                item.element_index,
                item.datatype,
                value.Value.Value,
            )

        self._write_status(item, status)

    def _write_status(self, item, status: int) -> None:
        leaf = getattr(item, "status", None)

        if leaf is None:
            return

        if not self.writer(
            self.runtime_args, leaf.array_index, leaf.element_index, leaf.datatype, status
        ):
            log_debug(f"OCF input {item.alias}: could not write the status 0x{status:08X}")

    # -- the GDS ------------------------------------------------------------

    async def _secure_client(self, url: str) -> Client:
        client = Client(url, timeout=10)

        client.application_uri = self.application_uri

        await client.set_security_string(
            f"Basic256Sha256,SignAndEncrypt,{self.certificate},{self.private_key}"
        )

        if self.validator is not None:
            client.certificate_validator = self.validator

        return client

    async def _gds_session(self) -> Client:
        return await self._secure_client(self.config.gds_url)

    async def _peer_session(self, url: str) -> Client:
        if getattr(self.config, "secure", False):
            return await self._secure_client(url)

        return Client(url, timeout=10)

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
                    # a target without a server index is a node of the GDS itself
                    if not hasattr(target, "ServerIndex"):
                        continue

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
