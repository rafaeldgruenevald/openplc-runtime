# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Autonomy®

"""
Push certificate management on the server of the DCN (OPC 10000-12 §7.7,
ServerConfiguration; the Global Certificate Management Server Facet that O-PAS
Part 4 OCF-F-001 requires).

A certificate manager (the configuration service, with a certificate the GDS
signs) asks the DCN for a signing request, gets it signed and pushes the
certificate back:

  1. CreateSigningRequest: the DCN makes a new key pair (or takes its current
     key) and returns a PKCS#10 request for its ApplicationUri and host names;
     the private key never leaves the DCN.
  2. UpdateCertificate: the signed certificate (and its issuers) is checked
     against the pending key, the ApplicationUri and its validity period.
  3. ApplyChanges: the credentials are written to the certificate store (a
     folder that outlives a new program) and the server restarts with them.

Only a caller with the engineer role may call these methods
(OpenPLCRoleRuleset). The trust list (TrustList object) is not managed here:
the trusted certificates still come with the program.
"""

import asyncio
import datetime
import ipaddress
import os
import tempfile
from pathlib import Path
from typing import Callable, List, Optional, Tuple

from asyncua import ua
from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.x509.oid import NameOID

try:
    from .opcua_logging import log_info, log_warn
except ImportError:
    from opcua_logging import log_info, log_warn

CREATE_SIGNING_REQUEST = ua.ObjectIds.ServerConfiguration_CreateSigningRequest
UPDATE_CERTIFICATE = ua.ObjectIds.ServerConfiguration_UpdateCertificate
APPLY_CHANGES = ua.ObjectIds.ServerConfiguration_ApplyChanges
GET_REJECTED_LIST = ua.ObjectIds.ServerConfiguration_GetRejectedList

# Methods only the certificate manager may call.
PUSH_METHODS = frozenset(
    ua.NodeId(i) for i in (CREATE_SIGNING_REQUEST, UPDATE_CERTIFICATE, APPLY_CHANGES, GET_REJECTED_LIST)
)

DEFAULT_GROUP = ua.NodeId(ua.ObjectIds.ServerConfiguration_CertificateGroups_DefaultApplicationGroup)
CERTIFICATE_TYPES = {
    ua.NodeId(ua.ObjectIds.ApplicationCertificateType),
    ua.NodeId(ua.ObjectIds.RsaMinApplicationCertificateType),
    ua.NodeId(ua.ObjectIds.RsaSha256ApplicationCertificateType),
}

CERTIFICATE_FILE = "server_cert.pem"
KEY_FILE = "server_key.pem"
ISSUERS_FILE = "issuers.pem"

KEY_SIZE = 2048

# How long ApplyChanges waits before the restart, so its answer gets out.
RESTART_DELAY_S = 0.5

NAME_ATTRIBUTES = {
    "CN": NameOID.COMMON_NAME,
    "O": NameOID.ORGANIZATION_NAME,
    "OU": NameOID.ORGANIZATIONAL_UNIT_NAME,
    "DC": NameOID.DOMAIN_COMPONENT,
    "C": NameOID.COUNTRY_NAME,
    "L": NameOID.LOCALITY_NAME,
    "ST": NameOID.STATE_OR_PROVINCE_NAME,
}


class PushError(Exception):
    """A refused request, with the StatusCode the method answers."""

    def __init__(self, code: int, message: str):
        super().__init__(message)
        self.code = code


def parse_subject(text: str) -> x509.Name:
    """'CN=DCN01, O=OPAS' (or separated by '/') as an X.509 name."""
    parts = [p.strip() for p in text.replace("/", ",").split(",") if p.strip()]
    attributes = []

    for part in parts:
        key, sep, value = part.partition("=")
        oid = NAME_ATTRIBUTES.get(key.strip().upper())

        if not sep or oid is None or not value.strip():
            raise PushError(ua.StatusCodes.BadInvalidArgument, f"subject name part {part!r} not understood")

        attributes.append(x509.NameAttribute(oid, value.strip()))

    if not attributes:
        raise PushError(ua.StatusCodes.BadInvalidArgument, "empty subject name")

    return x509.Name(attributes)


def application_uris(certificate: x509.Certificate) -> List[str]:
    try:
        names = certificate.extensions.get_extension_for_class(x509.SubjectAlternativeName).value
    except x509.ExtensionNotFound:
        return []

    return names.get_values_for_type(x509.UniformResourceIdentifier)


def signing_request(key, subject: x509.Name, application_uri: str, alternative: List[x509.GeneralName]) -> bytes:
    """A DER PKCS#10 request for ``application_uri`` and the other names of the server."""
    names = [x509.UniformResourceIdentifier(application_uri)]
    names += [n for n in alternative if not isinstance(n, x509.UniformResourceIdentifier)]

    request = (
        x509.CertificateSigningRequestBuilder()
        .subject_name(subject)
        .add_extension(x509.SubjectAlternativeName(names), critical=False)
        .sign(key, hashes.SHA256())
    )

    return request.public_bytes(serialization.Encoding.DER)


def pushed_credentials(store: Optional[str], application_uri: str) -> Optional[Tuple[str, str]]:
    """(certificate, key) PEM files a certificate manager pushed, when they are for
    this ApplicationUri and valid now; None otherwise (the program's are used)."""
    if not store:
        return None

    folder = Path(store)
    certificate_file, key_file = folder / CERTIFICATE_FILE, folder / KEY_FILE

    if not (certificate_file.exists() and key_file.exists()):
        return None

    try:
        certificate = x509.load_pem_x509_certificate(certificate_file.read_bytes())
    except ValueError as error:
        log_warn(f"OPC UA: the pushed certificate in {folder} cannot be read ({error}); not used")
        return None

    if application_uri not in application_uris(certificate):
        log_warn(f"OPC UA: the pushed certificate in {folder} is not for {application_uri}; not used")
        return None

    now = datetime.datetime.now(datetime.timezone.utc)

    if not certificate.not_valid_before_utc <= now <= certificate.not_valid_after_utc:
        log_warn(f"OPC UA: the pushed certificate in {folder} is outside its validity period; not used")
        return None

    return str(certificate_file), str(key_file)


def write_private(path: Path, data: bytes, mode: int = 0o600) -> None:
    """Replace ``path`` atomically, readable only by the runtime."""
    fd, temporary = tempfile.mkstemp(dir=path.parent, prefix=f".{path.name}.")

    try:
        with os.fdopen(fd, "wb") as handle:
            handle.write(data)

        os.chmod(temporary, mode)
        os.replace(temporary, path)
    except BaseException:
        Path(temporary).unlink(missing_ok=True)
        raise


class CertificatePush:
    """The ServerConfiguration methods of one server."""

    def __init__(
        self,
        application_uri: str,
        store: Optional[str],
        current: Callable[[], Optional[Tuple[str, str]]],
        on_apply: Callable[[], None],
        hosts: Optional[List[str]] = None,
    ):
        self.application_uri = application_uri
        # names the clients reach the server by, added to the signing request
        self.hosts = list(hosts or [])
        self.store = Path(store) if store else None
        # (certificate, key) PEM files the server presents now
        self.current = current
        self.on_apply = on_apply
        self._pending_key = None
        self._update: Optional[Tuple[bytes, bytes, List[bytes]]] = None

    async def link(self, server) -> None:
        for method, call in (
            (CREATE_SIGNING_REQUEST, self.create_signing_request),
            (UPDATE_CERTIFICATE, self.update_certificate),
            (APPLY_CHANGES, self.apply_changes),
            (GET_REJECTED_LIST, self.get_rejected_list),
        ):
            server.link_method(server.get_node(ua.NodeId(method)), call)

    # -- the methods (asyncua passes Variants, a StatusCode is the refusal) --

    async def create_signing_request(self, parent, group, kind, subject, regenerate, nonce):
        try:
            return [ua.Variant(self._signing_request(group.Value, kind.Value, subject.Value, regenerate.Value),
                               ua.VariantType.ByteString)]
        except PushError as error:
            log_warn(f"OPC UA CreateSigningRequest refused: {error}")
            return ua.StatusCode(error.code)

    async def update_certificate(self, parent, group, kind, certificate, issuers, key_format, key):
        try:
            self._accept(group.Value, kind.Value, certificate.Value, issuers.Value or [], key.Value)
            return [ua.Variant(True, ua.VariantType.Boolean)]
        except PushError as error:
            log_warn(f"OPC UA UpdateCertificate refused: {error}")
            return ua.StatusCode(error.code)

    async def apply_changes(self, parent):
        try:
            self._apply()
        except PushError as error:
            log_warn(f"OPC UA ApplyChanges refused: {error}")
            return ua.StatusCode(error.code)

        # answer first, then restart with the new certificate
        asyncio.get_running_loop().call_later(RESTART_DELAY_S, self.on_apply)
        return []

    async def get_rejected_list(self, parent):
        return [ua.Variant([], ua.VariantType.ByteString)]

    # -- the work ------------------------------------------------------------

    def _check_target(self, group, kind) -> None:
        if self.store is None:
            raise PushError(ua.StatusCodes.BadNotSupported, "no certificate store configured (security.certificate_store)")

        if group is not None and not group.is_null() and group != DEFAULT_GROUP:
            raise PushError(ua.StatusCodes.BadInvalidArgument, f"certificate group {group} not managed")

        if kind is not None and not kind.is_null() and kind not in CERTIFICATE_TYPES:
            raise PushError(ua.StatusCodes.BadInvalidArgument, f"certificate type {kind} not supported")

    def _current_certificate(self) -> Tuple[Optional[x509.Certificate], Optional[object]]:
        files = self.current()

        if not files:
            return None, None

        certificate_file, key_file = files
        certificate = x509.load_pem_x509_certificate(Path(certificate_file).read_bytes())
        key = serialization.load_pem_private_key(Path(key_file).read_bytes(), password=None)

        return certificate, key

    def _signing_request(self, group, kind, subject, regenerate) -> bytes:
        self._check_target(group, kind)

        try:
            certificate, key = self._current_certificate()
        except (OSError, ValueError) as error:
            raise PushError(ua.StatusCodes.BadInternalError, f"current certificate unreadable ({error})") from error

        if regenerate or key is None:
            key = rsa.generate_private_key(public_exponent=65537, key_size=KEY_SIZE)

        if subject:
            name = parse_subject(subject)
        elif certificate is not None:
            name = certificate.subject
        else:
            name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, self.application_uri)])

        alternative: List[x509.GeneralName] = []

        if certificate is not None:
            try:
                alternative = list(certificate.extensions.get_extension_for_class(x509.SubjectAlternativeName).value)
            except x509.ExtensionNotFound:
                pass

        for host in self.hosts:
            try:
                entry = x509.IPAddress(ipaddress.ip_address(host))
            except ValueError:
                entry = x509.DNSName(host)
            if entry not in alternative:
                alternative.append(entry)

        self._pending_key = key
        self._update = None

        log_info(f"OPC UA: signing request made for {self.application_uri} (new key: {bool(regenerate)})")

        return signing_request(key, name, self.application_uri, alternative)

    def _accept(self, group, kind, certificate_der: bytes, issuers: List[bytes], private_key: bytes) -> None:
        self._check_target(group, kind)

        if private_key:
            raise PushError(ua.StatusCodes.BadNotSupported, "a private key from outside is not taken: ask for a signing request")

        if self._pending_key is None:
            raise PushError(ua.StatusCodes.BadInvalidState, "no signing request pending")

        try:
            certificate = x509.load_der_x509_certificate(certificate_der)
            list(certificate.extensions)
            issuer_certificates = [x509.load_der_x509_certificate(i) for i in issuers]
        except ValueError as error:
            raise PushError(ua.StatusCodes.BadCertificateInvalid, f"certificate cannot be read ({error})") from error

        public = serialization.PublicFormat.SubjectPublicKeyInfo
        der = serialization.Encoding.DER

        if certificate.public_key().public_bytes(der, public) != self._pending_key.public_key().public_bytes(der, public):
            raise PushError(ua.StatusCodes.BadCertificateInvalid, "certificate is not for the key of the signing request")

        if self.application_uri not in application_uris(certificate):
            raise PushError(ua.StatusCodes.BadCertificateUriInvalid, f"certificate is not for {self.application_uri}")

        now = datetime.datetime.now(datetime.timezone.utc)

        if not certificate.not_valid_before_utc <= now <= certificate.not_valid_after_utc:
            raise PushError(ua.StatusCodes.BadCertificateTimeInvalid, "certificate outside its validity period")

        key_pem = self._pending_key.private_bytes(
            serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8, serialization.NoEncryption()
        )
        issuers_pem = b"".join(i.public_bytes(serialization.Encoding.PEM) for i in issuer_certificates)

        self._update = (certificate.public_bytes(serialization.Encoding.PEM), key_pem, issuers_pem)

        log_info(f"OPC UA: certificate for {self.application_uri} accepted, waiting for ApplyChanges")

    def _apply(self) -> None:
        if self.store is None:
            raise PushError(ua.StatusCodes.BadNotSupported, "no certificate store configured (security.certificate_store)")

        if self._update is None:
            raise PushError(ua.StatusCodes.BadNothingToDo, "no certificate update pending")

        certificate_pem, key_pem, issuers_pem = self._update

        self.store.mkdir(parents=True, exist_ok=True)
        os.chmod(self.store, 0o700)

        write_private(self.store / KEY_FILE, key_pem)
        write_private(self.store / CERTIFICATE_FILE, certificate_pem, 0o644)
        write_private(self.store / ISSUERS_FILE, issuers_pem, 0o644)

        self._update = None
        self._pending_key = None

        log_info(f"OPC UA: new certificate stored in {self.store}; restarting the server with it")
