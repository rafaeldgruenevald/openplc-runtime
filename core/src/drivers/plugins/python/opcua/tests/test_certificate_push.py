"""Tests for the push certificate management of the server (OPC 10000-12
ServerConfiguration): the signing request, the checks on the certificate pushed
back, where it is kept, who may call, and the methods over a real session."""

import asyncio
import datetime
import socket
import stat
import sys
from pathlib import Path
from types import SimpleNamespace

from asyncua import Client, Server, ua
from asyncua.server.user_managers import UserRole
from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.x509.oid import NameOID

OPCUA_DIR = Path(__file__).resolve().parents[1]

if str(OPCUA_DIR) not in sys.path:
    sys.path.insert(0, str(OPCUA_DIR))

import certificate_push  # noqa: E402
from certificate_push import CertificatePush, pushed_credentials  # noqa: E402

URI = "urn:opas:dcn:Test:DCN01"
NOW = datetime.datetime.now(datetime.timezone.utc)


def key():
    return rsa.generate_private_key(public_exponent=65537, key_size=2048)


def name(text):
    return x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, text)])


CA_KEY = key()
CA = (
    x509.CertificateBuilder().subject_name(name("Test CA")).issuer_name(name("Test CA"))
    .public_key(CA_KEY.public_key()).serial_number(1)
    .not_valid_before(NOW - datetime.timedelta(days=1)).not_valid_after(NOW + datetime.timedelta(days=30))
    .add_extension(x509.BasicConstraints(ca=True, path_length=None), critical=True)
    .sign(CA_KEY, hashes.SHA256())
)


def issue(public_key, uri=URI, days=30, start=None):
    start = start or NOW - datetime.timedelta(minutes=1)
    return (
        x509.CertificateBuilder().subject_name(name("DCN01")).issuer_name(CA.subject)
        .public_key(public_key).serial_number(x509.random_serial_number())
        .not_valid_before(start).not_valid_after(start + datetime.timedelta(days=days))
        .add_extension(x509.SubjectAlternativeName(
            [x509.UniformResourceIdentifier(uri), x509.DNSName("dcn01.local")]), critical=False)
        .sign(CA_KEY, hashes.SHA256())
    )


def pem(certificate):
    return certificate.public_bytes(serialization.Encoding.PEM)


def der(certificate):
    return certificate.public_bytes(serialization.Encoding.DER)


def key_pem(private):
    return private.private_bytes(serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8,
                                 serialization.NoEncryption())


def current_pair(folder):
    """The certificate the program gave the server: (certificate, key) files."""
    private = key()
    certificate_file, key_file = folder / "program_cert.pem", folder / "program_key.pem"
    certificate_file.write_bytes(pem(issue(private.public_key())))
    key_file.write_bytes(key_pem(private))
    return str(certificate_file), str(key_file)


class Push:
    """A CertificatePush on files of a temporary folder, counting the restarts."""

    def __init__(self, tmp_path, store=True):
        self.restarts = 0
        self.current = current_pair(tmp_path)
        self.store = tmp_path / "store"
        self.push = CertificatePush(URI, str(self.store) if store else None, lambda: self.current, self.restart)

    def restart(self):
        self.restarts += 1


def run(coroutine):
    return asyncio.run(coroutine)


def v(value, kind):
    return ua.Variant(value, kind)


def request(push, regenerate=True, subject=""):
    out = run(push.create_signing_request(
        None, v(ua.NodeId(), ua.VariantType.NodeId), v(ua.NodeId(), ua.VariantType.NodeId),
        v(subject, ua.VariantType.String), v(regenerate, ua.VariantType.Boolean),
        v(b"", ua.VariantType.ByteString)))
    return out if isinstance(out, ua.StatusCode) else x509.load_der_x509_csr(out[0].Value)


def update(push, certificate_der, private=b""):
    return run(push.update_certificate(
        None, v(ua.NodeId(), ua.VariantType.NodeId), v(ua.NodeId(), ua.VariantType.NodeId),
        v(certificate_der, ua.VariantType.ByteString), v([der(CA)], ua.VariantType.ByteString),
        v("", ua.VariantType.String), v(private, ua.VariantType.ByteString)))


def test_the_signing_request_is_for_the_application_and_its_hosts(tmp_path):
    push = Push(tmp_path).push

    csr = request(push)

    names = csr.extensions.get_extension_for_class(x509.SubjectAlternativeName).value
    assert names.get_values_for_type(x509.UniformResourceIdentifier) == [URI]
    assert names.get_values_for_type(x509.DNSName) == ["dcn01.local"]
    assert csr.is_signature_valid


def test_a_new_key_is_made_unless_the_current_one_is_asked_for(tmp_path):
    bench = Push(tmp_path)
    current = x509.load_pem_x509_certificate(Path(bench.current[0]).read_bytes()).public_key()

    def same(a, b):
        f = (serialization.Encoding.DER, serialization.PublicFormat.SubjectPublicKeyInfo)
        return a.public_bytes(*f) == b.public_bytes(*f)

    assert not same(request(bench.push, regenerate=True).public_key(), current)
    assert same(request(bench.push, regenerate=False).public_key(), current)


def test_a_certificate_for_the_pending_key_is_applied_and_kept(tmp_path, monkeypatch):
    monkeypatch.setattr(certificate_push, "RESTART_DELAY_S", 0)
    bench = Push(tmp_path)
    csr = request(bench.push)

    assert update(bench.push, der(issue(csr.public_key())))[0].Value is True

    async def apply():
        result = await bench.push.apply_changes(None)
        await asyncio.sleep(0.05)  # the restart comes after the answer
        return result

    assert run(apply()) == []
    assert bench.restarts == 1
    assert stat.S_IMODE((bench.store / "server_key.pem").stat().st_mode) == 0o600
    assert pushed_credentials(str(bench.store), URI) == (
        str(bench.store / "server_cert.pem"), str(bench.store / "server_key.pem"))


def test_a_certificate_for_another_key_is_refused(tmp_path):
    bench = Push(tmp_path)
    request(bench.push)

    assert update(bench.push, der(issue(key().public_key()))) == ua.StatusCode(ua.StatusCodes.BadCertificateInvalid)


def test_a_certificate_for_another_application_is_refused(tmp_path):
    bench = Push(tmp_path)
    csr = request(bench.push)

    assert update(bench.push, der(issue(csr.public_key(), uri="urn:other"))) == ua.StatusCode(
        ua.StatusCodes.BadCertificateUriInvalid)


def test_a_certificate_outside_its_validity_is_refused(tmp_path):
    bench = Push(tmp_path)
    csr = request(bench.push)
    expired = issue(csr.public_key(), start=NOW - datetime.timedelta(days=10), days=1)

    assert update(bench.push, der(expired)) == ua.StatusCode(ua.StatusCodes.BadCertificateTimeInvalid)


def test_a_private_key_from_outside_is_not_taken(tmp_path):
    bench = Push(tmp_path)
    csr = request(bench.push)

    assert update(bench.push, der(issue(csr.public_key())), private=b"key") == ua.StatusCode(
        ua.StatusCodes.BadNotSupported)


def test_without_a_certificate_store_push_is_not_supported(tmp_path):
    assert request(Push(tmp_path, store=False).push) == ua.StatusCode(ua.StatusCodes.BadNotSupported)


def test_apply_without_an_update_has_nothing_to_do(tmp_path):
    assert run(Push(tmp_path).push.apply_changes(None)) == ua.StatusCode(ua.StatusCodes.BadNothingToDo)


def test_a_pushed_certificate_of_another_application_is_not_used(tmp_path):
    store = tmp_path / "store"
    store.mkdir()
    private = key()
    (store / "server_key.pem").write_bytes(key_pem(private))
    (store / "server_cert.pem").write_bytes(pem(issue(private.public_key(), uri="urn:other")))

    assert pushed_credentials(str(store), URI) is None
    assert pushed_credentials(None, URI) is None


def test_only_an_administrator_may_call_the_push_methods():
    from opcua_security import OpenPLCRoleRuleset

    ruleset = OpenPLCRoleRuleset()
    call = ua.NodeId(ua.ObjectIds.CallRequest_Encoding_DefaultBinary)

    def body(method):
        return SimpleNamespace(Parameters=SimpleNamespace(
            MethodsToCall=[SimpleNamespace(MethodId=ua.NodeId(method))]))

    viewer, admin = SimpleNamespace(role=UserRole.User), SimpleNamespace(role=UserRole.Admin)
    signing = body(certificate_push.CREATE_SIGNING_REQUEST)

    assert ruleset.check_validity(viewer, call, signing) is False
    assert ruleset.check_validity(admin, call, signing) is True
    assert ruleset.check_validity(viewer, call, body(ua.ObjectIds.Server_GetMonitoredItems)) is True


def free_port():
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def test_the_methods_answer_over_a_session(tmp_path, monkeypatch):
    """A manager's round trip on a real server: signing request, the signed
    certificate pushed back, ApplyChanges."""
    monkeypatch.setattr(certificate_push, "RESTART_DELAY_S", 0)
    bench = Push(tmp_path)

    async def round_trip():
        port = free_port()
        server = Server()
        await server.init()
        server.set_endpoint(f"opc.tcp://127.0.0.1:{port}/")
        await bench.push.link(server)

        async with server:
            async with Client(f"opc.tcp://127.0.0.1:{port}/") as client:
                configuration = client.get_node(ua.NodeId(ua.ObjectIds.ServerConfiguration))
                csr_der = await configuration.call_method(
                    ua.NodeId(certificate_push.CREATE_SIGNING_REQUEST),
                    ua.Variant(ua.NodeId(), ua.VariantType.NodeId), ua.Variant(ua.NodeId(), ua.VariantType.NodeId),
                    ua.Variant("", ua.VariantType.String), ua.Variant(True, ua.VariantType.Boolean),
                    ua.Variant(b"", ua.VariantType.ByteString))
                certificate = issue(x509.load_der_x509_csr(csr_der).public_key())
                required = await configuration.call_method(
                    ua.NodeId(certificate_push.UPDATE_CERTIFICATE),
                    ua.Variant(ua.NodeId(), ua.VariantType.NodeId), ua.Variant(ua.NodeId(), ua.VariantType.NodeId),
                    ua.Variant(der(certificate), ua.VariantType.ByteString),
                    ua.Variant([der(CA)], ua.VariantType.ByteString),
                    ua.Variant("", ua.VariantType.String), ua.Variant(b"", ua.VariantType.ByteString))
                await configuration.call_method(ua.NodeId(certificate_push.APPLY_CHANGES))
                await asyncio.sleep(0.05)
                return required, certificate

    required, certificate = run(round_trip())

    assert required is True
    assert bench.restarts == 1
    assert (bench.store / "server_cert.pem").read_bytes() == pem(certificate)


def test_a_pushed_certificate_replaces_the_one_of_the_strategy(tmp_path):
    from opcua_security import OpcuaSecurityManager

    store = tmp_path / "store"
    store.mkdir()
    private = key()
    (store / "server_key.pem").write_bytes(key_pem(private))
    (store / "server_cert.pem").write_bytes(pem(issue(private.public_key())))

    config = SimpleNamespace(
        server=SimpleNamespace(application_uri=URI, security_profiles=[]),
        security=SimpleNamespace(server_certificate_strategy="auto_self_signed",
                                 server_certificate_custom=None, server_private_key_custom=None,
                                 trusted_client_certificates=[], peer_role=None,
                                 certificate_store=str(store)),
    )

    manager = OpcuaSecurityManager(config, str(tmp_path))

    assert manager.credential_files() == (str(store / "server_cert.pem"), str(store / "server_key.pem"))
