"""Tests for the OCF client of the DCN: what it reads from a source it was
pointed at and writes into the PLC, and the GDS record it decodes."""

import asyncio
import sys
from pathlib import Path
from types import SimpleNamespace

from asyncua import Server, ua
from asyncua.ua import ua_binary as binary

OPCUA_DIR = Path(__file__).resolve().parents[1]

if str(OPCUA_DIR) not in sys.path:
    sys.path.insert(0, str(OPCUA_DIR))

import ocf_client  # noqa: E402


def record(uri, urls):
    return b"".join([
        binary.nodeid_to_binary(ua.NodeId()),
        binary.pack_uatype(ua.VariantType.String, uri),
        binary.pack_uatype(ua.VariantType.Int32, 0),
        binary.pack_uatype_array(ua.VariantType.LocalizedText, [ua.LocalizedText("x")]),
        binary.pack_uatype(ua.VariantType.String, "urn:p"),
        binary.pack_uatype_array(ua.VariantType.String, urls),
        binary.pack_uatype_array(ua.VariantType.String, ["ALIAS"]),
    ])


def test_the_application_record_of_the_gds_is_decoded():
    uri, urls = ocf_client.decode_application_record(
        record("urn:dcn:2", ["opc.tcp://a:4840", "opc.tcp://b:4840"])
    )

    assert uri == "urn:dcn:2"
    assert urls == ["opc.tcp://a:4840", "opc.tcp://b:4840"]


class FakeClient(ocf_client.OcfClient):
    """An OCF client whose GDS answer is fixed: the alias is served by the
    server the test started."""

    def __init__(self, endpoint, namespace_uri, node_id, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.answer = ocf_client.Source("urn:src", endpoint, namespace_uri, node_id)
        self.resolved = []

    async def _resolve(self, alias):
        self.resolved.append(alias)
        return self.answer


def run_with_source(test):
    async def main():
        server = Server()
        await server.init()
        server.set_endpoint("opc.tcp://127.0.0.1:48420/ocf-test")
        index = await server.register_namespace("urn:test:source")
        value = await server.nodes.objects.add_variable(
            ua.NodeId("Dev.PT101", index, ua.NodeIdType.String), "PT101", 3.5, ua.VariantType.Float
        )
        async with server:
            await test(value, index)

    asyncio.run(main())


def config(period_ms=20):
    return SimpleNamespace(
        gds_url="opc.tcp://unused",
        period_ms=period_ms,
        inputs=[SimpleNamespace(alias="PT101", array_index=1, element_index=16, datatype="REAL")],
    )


def test_the_value_of_the_source_is_written_into_the_plc_variable():
    writes = []

    def writer(args, arr, elem, datatype, value):
        writes.append((args, arr, elem, datatype, value))
        return True

    async def test(value, index):
        node_id = SimpleNamespace(Identifier="Dev.PT101", NodeIdType=ua.NodeIdType.String)

        client = FakeClient(
            "opc.tcp://127.0.0.1:48420/ocf-test", "urn:test:source", node_id,
            config(), "ARGS", "urn:me", "c", "k", writer=writer,
        )

        task = asyncio.create_task(client.run())

        await asyncio.sleep(0.5)

        await value.write_value(ua.Variant(7.25, ua.VariantType.Float))

        await asyncio.sleep(0.3)

        await client.stop()

        task.cancel()

        assert writes, "nothing was written"
        assert writes[0][:4] == ("ARGS", 1, 16, "REAL")
        assert writes[0][4] == 3.5
        assert writes[-1][4] == 7.25
        assert client.state["PT101"]["connected"]
        assert client.resolved == ["PT101"]

    run_with_source(test)


def test_a_source_that_is_gone_is_resolved_again(monkeypatch):
    monkeypatch.setattr(ocf_client, "BACKOFF_FIRST_S", 0.05)

    async def main():
        node_id = SimpleNamespace(Identifier="Dev.PT101", NodeIdType=ua.NodeIdType.String)

        # nothing listens there: every attempt fails and the alias is resolved
        # again each time
        client = FakeClient(
            "opc.tcp://127.0.0.1:1/none", "urn:test:source", node_id,
            config(), None, "urn:me", "c", "k", writer=lambda *a: True,
        )

        task = asyncio.create_task(client.run())

        await asyncio.sleep(1.0)

        await client.stop()

        task.cancel()

        assert len(client.resolved) >= 2
        assert not client.state["PT101"]["connected"]

    asyncio.run(main())
