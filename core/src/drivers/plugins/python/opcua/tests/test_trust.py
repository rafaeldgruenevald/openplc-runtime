"""A DCN trusts the certificates in its list and the ones a CA of the list issued, and nothing else."""

import asyncio
import datetime
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest
from asyncua import ua
from asyncua.crypto.truststore import TrustStore
from asyncua.crypto.validator import CertificateValidator
from asyncua.ua.uaerrors import UaError
from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.x509.oid import ExtendedKeyUsageOID, NameOID

OPCUA_DIR = Path(__file__).resolve().parents[1]

if str(OPCUA_DIR) not in sys.path:
    sys.path.insert(0, str(OPCUA_DIR))

import opcua_security  # noqa: E402

URI = "urn:opas:dcn:test:DCN01"


def key():
    return rsa.generate_private_key(public_exponent=65537, key_size=2048)


def name(cn):
    return x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, cn)])


def certificate(subject_key, subject, issuer_key=None, issuer=None, ca=False, uri=URI):
    now = datetime.datetime.now(datetime.timezone.utc)

    builder = (
        x509.CertificateBuilder()
        .subject_name(name(subject))
        .issuer_name(name(issuer or subject))
        .public_key(subject_key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(now - datetime.timedelta(minutes=1))
        .not_valid_after(now + datetime.timedelta(days=30))
        .add_extension(x509.BasicConstraints(ca=ca, path_length=None), critical=True)
        .add_extension(
            x509.KeyUsage(
                digital_signature=True, content_commitment=True, key_encipherment=not ca,
                data_encipherment=not ca, key_agreement=False, key_cert_sign=ca,
                crl_sign=ca, encipher_only=False, decipher_only=False,
            ),
            critical=True,
        )
    )

    if not ca:
        builder = builder.add_extension(
            x509.SubjectAlternativeName([x509.UniformResourceIdentifier(uri), x509.DNSName("localhost")]),
            critical=False,
        ).add_extension(
            x509.ExtendedKeyUsage([ExtendedKeyUsageOID.CLIENT_AUTH, ExtendedKeyUsageOID.SERVER_AUTH]),
            critical=False,
        )

    return builder.sign(issuer_key or subject_key, hashes.SHA256())


def store(tmp_path, *certs):
    folder = tmp_path / "trusted"
    folder.mkdir()

    for i, cert in enumerate(certs):
        (folder / f"trusted{i}.der").write_bytes(cert.public_bytes(serialization.Encoding.DER))

    trust = TrustStore([folder], [])

    asyncio.run(trust.load())

    return trust


def validate(trust, cert):
    validator = CertificateValidator(opcua_security.PEER_TRUST_OPTIONS, trust_store=trust)

    app = ua.ApplicationDescription()
    app.ApplicationUri = URI
    # a GDS that reads the aliases presents itself as a server
    app.ApplicationType = ua.ApplicationType.Server

    asyncio.run(validator.validate(cert, app))


@pytest.fixture
def ca():
    ca_key = key()
    return ca_key, certificate(ca_key, "OPAS CA", ca=True)


def test_a_certificate_issued_by_a_trusted_ca_is_accepted(tmp_path, ca):
    ca_key, ca_cert = ca

    leaf = certificate(key(), "DCN01", ca_key, "OPAS CA")

    validate(store(tmp_path, ca_cert), leaf)


def test_a_certificate_nobody_trusts_is_refused(tmp_path, ca):
    _, ca_cert = ca

    stranger = certificate(key(), "stranger")

    with pytest.raises(UaError):
        validate(store(tmp_path, ca_cert), stranger)


def test_a_certificate_issued_by_another_ca_is_refused(tmp_path, ca):
    _, ca_cert = ca

    other_key = key()

    leaf = certificate(key(), "DCN01", other_key, "Other CA")

    with pytest.raises(UaError):
        validate(store(tmp_path, ca_cert), leaf)


def test_a_certificate_in_the_list_is_accepted(tmp_path):
    leaf = certificate(key(), "tool")

    validate(store(tmp_path, leaf), leaf)


def manager(tmp_path, **security):
    config = SimpleNamespace(
        security=SimpleNamespace(
            server_certificate_strategy=security.pop("strategy", "custom"),
            server_certificate_custom=security.get("cert"),
            server_private_key_custom=security.get("key"),
            trusted_client_certificates=[],
        ),
        server=SimpleNamespace(application_uri=URI),
    )

    return opcua_security.OpcuaSecurityManager(config, str(tmp_path / "plugin"))


def test_custom_credentials_are_found_inside_the_program(tmp_path, monkeypatch):
    generated = tmp_path / "generated"
    (generated / "conf" / "pki").mkdir(parents=True)
    (generated / "conf" / "pki" / "server_cert.pem").write_text("c")
    (generated / "conf" / "pki" / "server_key.pem").write_text("k")

    monkeypatch.setenv("OPENPLC_GENERATED_DIR", str(generated))

    files = manager(
        tmp_path, cert="conf/pki/server_cert.pem", key="conf/pki/server_key.pem"
    ).credential_files()

    assert files == (
        str(generated / "conf/pki/server_cert.pem"),
        str(generated / "conf/pki/server_key.pem"),
    )


def test_custom_credentials_outside_the_program_are_refused(tmp_path, monkeypatch):
    generated = tmp_path / "generated"
    generated.mkdir()
    (tmp_path / "evil.pem").write_text("x")

    monkeypatch.setenv("OPENPLC_GENERATED_DIR", str(generated))

    assert manager(tmp_path, cert="../evil.pem", key="../evil.pem").credential_files() is None


def test_the_trust_store_of_the_security_manager_trusts_what_it_was_given(tmp_path):
    # the manager hands the store a folder of the PEM certificates of the config
    ca_key = key()
    ca_cert = certificate(ca_key, "OPAS CA", ca=True)
    leaf = certificate(key(), "DCN01", ca_key, "OPAS CA")
    stranger = certificate(key(), "stranger")

    pem = ca_cert.public_bytes(serialization.Encoding.PEM).decode()

    security = manager(tmp_path)

    trust = asyncio.run(security.create_trust_store([pem]))

    assert trust.validate(leaf)
    assert not trust.validate(stranger)


def test_a_pem_certificate_and_key_are_loaded_into_the_server(tmp_path, monkeypatch):
    # custom credentials as the adapter ships them: PEM files
    from asyncua import Server

    k = key()
    cert = certificate(k, "DCN01")

    generated = tmp_path / "generated" / "conf" / "pki"
    generated.mkdir(parents=True)
    (generated / "server_cert.pem").write_bytes(cert.public_bytes(serialization.Encoding.PEM))
    (generated / "server_key.pem").write_bytes(
        k.private_bytes(
            serialization.Encoding.PEM,
            serialization.PrivateFormat.PKCS8,
            serialization.NoEncryption(),
        )
    )

    monkeypatch.setenv("OPENPLC_GENERATED_DIR", str(tmp_path / "generated"))

    security = manager(
        tmp_path, cert="conf/pki/server_cert.pem", key="conf/pki/server_key.pem"
    )

    loaded = []

    async def load():
        server = Server()
        await server.init()

        original = server.load_certificate

        async def spy(data, *args, **kwargs):
            loaded.append(data)
            return await original(data, *args, **kwargs)

        server.load_certificate = spy

        await security._setup_server_certificates_for_asyncua(server, URI)

    asyncio.run(load())

    # handed over as DER, whatever the file holds
    assert len(loaded) == 1
    assert x509.load_der_x509_certificate(loaded[0]).subject == cert.subject
