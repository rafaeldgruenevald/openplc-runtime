"""A discovery-only None endpoint lists the secure endpoints and opens no session."""

import asyncio
import sys
from pathlib import Path

import pytest
from asyncua import Client, Server, ua

OPCUA_DIR = Path(__file__).resolve().parents[1]

if str(OPCUA_DIR) not in sys.path:
    sys.path.insert(0, str(OPCUA_DIR))

import opcua_security  # noqa: E402


@pytest.fixture(autouse=True)
def restore_asyncua(monkeypatch):
    """The guard patches asyncua for the whole process: undo it after each
    test so other servers in the suite still accept None sessions."""
    from asyncua.server.uaprocessor import UaProcessor

    monkeypatch.setattr(UaProcessor, "_process_message", UaProcessor._process_message)
    monkeypatch.setattr(opcua_security, "_sessions_refused_on_none", False)


def test_discovery_works_and_a_session_is_refused_on_the_none_channel():
    async def main():
        opcua_security.refuse_sessions_on_unsecured_channels()

        server = Server()
        await server.init()
        server.set_endpoint("opc.tcp://127.0.0.1:48421/discovery-test")
        server.set_security_policy([ua.SecurityPolicyType.NoSecurity])

        async with server:
            client = Client("opc.tcp://127.0.0.1:48421/discovery-test", timeout=5)

            # discovery answers on the unsecured channel
            endpoints = await client.connect_and_get_server_endpoints()

            assert endpoints

            # a session does not
            with pytest.raises(ua.UaStatusCodeError) as refused:
                async with Client("opc.tcp://127.0.0.1:48421/discovery-test", timeout=5):
                    pass

            assert "BadSecurityPolicyRejected" in str(refused.value)

    asyncio.run(main())


def test_the_profile_flag_is_only_for_the_none_endpoint():
    from shared.plugin_config_decode.opcua_config_model import SecurityProfile

    ok = SecurityProfile.from_dict(
        {
            "name": "d", "enabled": True, "security_policy": "None",
            "security_mode": "None", "auth_methods": ["Anonymous"], "discovery_only": True,
        }
    )

    assert ok.discovery_only

    with pytest.raises(ValueError):
        SecurityProfile.from_dict(
            {
                "name": "d", "enabled": True, "security_policy": "Basic256Sha256",
                "security_mode": "Sign", "auth_methods": ["Anonymous"], "discovery_only": True,
            }
        )
