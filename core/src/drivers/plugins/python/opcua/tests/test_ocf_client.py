"""Tests for the OCF client of the DCN: what it reads from a source it was
pointed at and writes into the PLC, and the GDS record it decodes."""

import asyncio
import dataclasses
import sys
import time
from pathlib import Path
from types import SimpleNamespace

from asyncua import Server, ua
from cryptography import x509
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


SERVERS = ["urn:gds", "urn:dcn:1", "urn:dcn:2"]


def expanded(text, server_index=None):
    return dataclasses.replace(ua.ExpandedNodeId.from_string(text), ServerIndex=server_index)


def verbose(name, nodes, uris):
    return b"".join([
        binary.struct_to_binary(ua.QualifiedName(name, 0)),
        binary.pack_uatype(ua.VariantType.Int32, len(nodes)),
        *[binary.nodeid_to_binary(node) for node in nodes],
        binary.pack_uatype_array(ua.VariantType.String, uris),
    ])


class FakeCategory:
    """The TagVariables category of a GDS: FindAliasVerbose answers with entries in
    their binary encoding unless the GDS has no such method."""

    def __init__(self, entries, find_alias=None):
        self.entries = entries
        self.find_alias = find_alias

    async def call_method(self, method, *args):
        if method.Name == "FindAliasVerbose":
            if self.entries is None:
                raise ua.UaStatusCodeError(ua.StatusCodes.BadMethodInvalid)
            return [ua.ExtensionObject(Body=body) for body in self.entries]
        return self.find_alias


def test_an_alias_verbose_entry_is_decoded():
    node = expanded("nsu=urn:x;s=PT101", 2)

    name, nodes, uris = ocf_client.decode_alias_verbose(verbose("PT101", [node], ["urn:dcn:2"]))

    assert name == "PT101"
    assert [(n.Identifier, n.NamespaceUri, n.ServerIndex) for n in nodes] == [("PT101", "urn:x", 2)]
    assert uris == ["urn:dcn:2"]


def test_an_alias_added_to_the_gds_keeps_its_server():
    # AddAliasesToCategory: the target has no server index, only the verbose answer names the server
    category = FakeCategory([
        verbose("PT101", [expanded("nsu=urn:codesys;b=AQAAAA==")], ["urn:nx3008"]),
        verbose("CV101", [expanded("nsu=urn:x;s=CV101", 1)], ["urn:dcn:1"]),
        verbose("LOCAL", [expanded("nsu=urn:x;s=Here")], [""]),
    ])

    found = asyncio.run(ocf_client.alias_targets(category, "%", SERVERS))

    assert [(name, uri) for name, _, uri in found] == [
        ("PT101", "urn:nx3008"), ("CV101", "urn:dcn:1"), ("LOCAL", ""),
    ]


def test_a_gds_without_find_alias_verbose_is_asked_with_find_alias():
    entry = SimpleNamespace(
        AliasName=ua.QualifiedName("PT101", 0),
        ReferencedNodes=[expanded("nsu=urn:x;s=PT101", 2), ua.NodeId("Here", 1)],
    )
    category = FakeCategory(None, find_alias=[entry])

    found = asyncio.run(ocf_client.alias_targets(category, "PT101", SERVERS))

    # the second target has no server index: a node of the GDS itself
    assert [uri for _, _, uri in found] == ["urn:dcn:2", ""]


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


STATUS = SimpleNamespace(array_index=1, element_index=17, datatype="UDINT")


def config_with_status(period_ms=20):
    cfg = config(period_ms)
    cfg.inputs[0].status = STATUS
    return cfg


def test_the_status_of_the_source_is_written_into_the_signal_status():
    writes = []

    def writer(args, arr, elem, datatype, value):
        writes.append((arr, elem, datatype, value))
        return True

    async def test(value, index):
        node_id = SimpleNamespace(Identifier="Dev.PT101", NodeIdType=ua.NodeIdType.String)

        client = FakeClient(
            "opc.tcp://127.0.0.1:48420/ocf-test", "urn:test:source", node_id,
            config_with_status(), None, "urn:me", "c", "k", writer=writer,
        )

        task = asyncio.create_task(client.run())

        await asyncio.sleep(0.5)

        # the source reports its sensor failed: the status arrives, the value
        # that came with it does not
        await value.write_value(
            ua.DataValue(
                ua.Variant(99.0, ua.VariantType.Float),
                ua.StatusCode(ua.StatusCodes.BadSensorFailure),
            )
        )

        await asyncio.sleep(0.3)

        await client.stop()

        task.cancel()

        values = [w[3] for w in writes if w[:3] == (1, 16, "REAL")]
        statuses = [w[3] for w in writes if w[:3] == (1, 17, "UDINT")]

        assert values and 99.0 not in values
        assert statuses[0] == ocf_client.STATUS_GOOD
        assert statuses[-1] == ua.StatusCodes.BadSensorFailure

    run_with_source(test)


def test_a_source_that_does_not_answer_is_bad_no_communication(monkeypatch):
    monkeypatch.setattr(ocf_client, "BACKOFF_FIRST_S", 0.05)

    writes = []

    def writer(args, arr, elem, datatype, value):
        writes.append((arr, elem, datatype, value))
        return True

    async def main():
        node_id = SimpleNamespace(Identifier="Dev.PT101", NodeIdType=ua.NodeIdType.String)

        client = FakeClient(
            "opc.tcp://127.0.0.1:1/none", "urn:test:source", node_id,
            config_with_status(), None, "urn:me", "c", "k", writer=writer,
        )

        task = asyncio.create_task(client.run())

        await asyncio.sleep(0.5)

        await client.stop()

        task.cancel()

        assert writes
        assert all(w == (1, 17, "UDINT", ocf_client.STATUS_BAD_NO_COMMUNICATION) for w in writes)

    asyncio.run(main())


def test_an_input_without_a_status_leaf_writes_only_the_value(monkeypatch):
    monkeypatch.setattr(ocf_client, "BACKOFF_FIRST_S", 0.05)

    writes = []

    async def main():
        node_id = SimpleNamespace(Identifier="Dev.PT101", NodeIdType=ua.NodeIdType.String)

        client = FakeClient(
            "opc.tcp://127.0.0.1:1/none", "urn:test:source", node_id,
            config(), None, "urn:me", "c", "k", writer=lambda *a: writes.append(a) or True,
        )

        task = asyncio.create_task(client.run())

        await asyncio.sleep(0.3)

        await client.stop()

        task.cancel()

        assert writes == []

    asyncio.run(main())


def test_a_source_that_stops_answering_is_bad_after_stale_ms(monkeypatch):
    from asyncua.common.node import Node

    writes = []

    def writer(args, arr, elem, datatype, value):
        writes.append((time.monotonic(), elem, value))
        return True

    async def test(value, index):
        node_id = SimpleNamespace(Identifier="Dev.PT101", NodeIdType=ua.NodeIdType.String)

        cfg = config_with_status()
        cfg.stale_ms = 300

        client = FakeClient(
            "opc.tcp://127.0.0.1:48420/ocf-test", "urn:test:source", node_id,
            cfg, None, "urn:me", "c", "k", writer=writer,
        )

        task = asyncio.create_task(client.run())

        await asyncio.sleep(0.5)

        # the source is still connected but answers nothing: neither reads
        # nor the closing of the session
        async def hang(self, *args, **kwargs):
            await asyncio.sleep(30)

        monkeypatch.setattr(Node, "read_data_value", hang)
        monkeypatch.setattr(ocf_client.Client, "disconnect", hang)

        frozen = time.monotonic()

        await asyncio.sleep(0.8)

        await client.stop()

        task.cancel()

        bad = [t for t, elem, v in writes if elem == 17 and v == ocf_client.STATUS_BAD_NO_COMMUNICATION]

        assert bad, "the status never became BadNoCommunication"
        assert bad[0] - frozen < 0.6

    run_with_source(test)


def test_the_stale_time_defaults_to_a_few_periods():
    client = ocf_client.OcfClient(config(period_ms=100), None, "urn:me", "c", "k")

    assert client.stale_s == 1.0

    client = ocf_client.OcfClient(config(period_ms=500), None, "urn:me", "c", "k")

    assert client.stale_s == 2.5


# -- the certificate of a server is checked before any session ---------------

def self_signed(ca_flag=0xFF):
    """A DER certificate with a critical BasicConstraints CA:TRUE, pathlen 0; ca_flag
    0x01 encodes the BOOLEAN outside DER, as the NX3008 firmware does."""
    import datetime

    from cryptography.hazmat.primitives import hashes, serialization
    from cryptography.hazmat.primitives.asymmetric import rsa
    from cryptography.x509.oid import NameOID

    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, "peer")])
    now = datetime.datetime.now(datetime.timezone.utc)
    der = (
        x509.CertificateBuilder()
        .subject_name(name).issuer_name(name).public_key(key.public_key())
        .serial_number(1).not_valid_before(now).not_valid_after(now + datetime.timedelta(days=1))
        .add_extension(x509.BasicConstraints(ca=True, path_length=0), critical=True)
        .sign(key, hashes.SHA256())
        .public_bytes(serialization.Encoding.DER)
    )
    return der.replace(b"\x30\x06\x01\x01\xff\x02\x01\x00", b"\x30\x06\x01\x01" + bytes([ca_flag]) + b"\x02\x01\x00")


def endpoint(certificate, policy=ocf_client.SECURE_POLICY_URI, mode=ua.MessageSecurityMode.SignAndEncrypt):
    description = ua.EndpointDescription()
    description.SecurityPolicyUri = policy
    description.SecurityMode = mode
    description.ServerCertificate = certificate
    description.Server = ua.ApplicationDescription(ApplicationUri="urn:peer")
    return description


class EndpointsOnly:
    """A server reached only for GetEndpoints; a session would be a test failure."""

    endpoints = []

    def __init__(self, url, timeout=None):
        self.url = url

    async def connect_and_get_server_endpoints(self):
        return EndpointsOnly.endpoints


class Validator:
    def __init__(self, trusted):
        self.trusted = trusted
        self.seen = []

    async def __call__(self, certificate, application):
        self.seen.append(application.ApplicationUri)
        if not self.trusted:
            raise ua.UaStatusCodeError(ua.StatusCodes.BadCertificateUntrusted)


def checker(monkeypatch, endpoints, validator):
    monkeypatch.setattr(ocf_client, "Client", EndpointsOnly)
    EndpointsOnly.endpoints = endpoints
    config = SimpleNamespace(period_ms=100, stale_ms=None, inputs=[], gds_url="opc.tcp://gds")
    return ocf_client.OcfClient(config, None, "urn:me", "cert.pem", "key.pem", validator=validator)


def check(client, url="opc.tcp://peer:4840"):
    return asyncio.run(client._check_server(url))


def test_a_certificate_that_cannot_be_read_is_refused_without_a_session(monkeypatch):
    client = checker(monkeypatch, [endpoint(self_signed(ca_flag=0x01))], Validator(True))

    try:
        check(client)
    except ocf_client.PeerRefused as error:
        assert "opc.tcp://peer:4840" in str(error)
    else:
        raise AssertionError("an unreadable certificate was accepted")


def test_a_certificate_the_trust_list_does_not_vouch_for_is_refused(monkeypatch):
    validator = Validator(False)
    client = checker(monkeypatch, [endpoint(self_signed())], validator)

    try:
        check(client)
    except ocf_client.PeerRefused as error:
        assert "not trusted" in str(error)
    else:
        raise AssertionError("an untrusted certificate was accepted")

    assert validator.seen == ["urn:peer"]


def test_a_trusted_certificate_lets_the_session_go_on(monkeypatch):
    validator = Validator(True)
    insecure = endpoint(self_signed(), policy="http://opcfoundation.org/UA/SecurityPolicy#None",
                        mode=ua.MessageSecurityMode.None_)

    check(checker(monkeypatch, [insecure, endpoint(self_signed())], validator))

    assert validator.seen == ["urn:peer"]


def test_a_server_without_a_secure_endpoint_is_refused(monkeypatch):
    insecure = endpoint(self_signed(), policy="http://opcfoundation.org/UA/SecurityPolicy#None",
                        mode=ua.MessageSecurityMode.None_)

    try:
        check(checker(monkeypatch, [insecure], Validator(True)))
    except ocf_client.PeerRefused as error:
        assert "no Basic256Sha256" in str(error)
    else:
        raise AssertionError("a server without a secure endpoint was accepted")


def test_the_leaf_is_taken_from_a_certificate_with_its_chain():
    leaf = self_signed()

    assert ocf_client.first_certificate(leaf + self_signed()) == leaf
    assert ocf_client.first_certificate(leaf) == leaf


def test_sessions_ask_for_a_short_timeout():
    config = SimpleNamespace(period_ms=100, stale_ms=None, inputs=[], secure=False)
    client = ocf_client.OcfClient(config, None, "urn:me", "cert.pem", "key.pem")

    session = asyncio.run(client._peer_session("opc.tcp://peer:4840"))

    assert session.session_timeout == ocf_client.SESSION_TIMEOUT_MS
