"""Tests for the semantic_model section of the OPC UA configuration."""

import os
import sys

import pytest

current_dir = os.path.dirname(os.path.abspath(__file__))
if current_dir not in sys.path:
    sys.path.insert(0, current_dir)


class TestSemanticModelConfig:
    """semantic_model section of opcua.json."""

    def _base(self, **extra):
        data = {
            "server": {
                "name": "n",
                "application_uri": "urn:a",
                "product_uri": "urn:p",
                "endpoint_url": "opc.tcp://0.0.0.0:4840/x",
                "security_profiles": [
                    {
                        "name": "insecure",
                        "enabled": True,
                        "security_policy": "None",
                        "security_mode": "None",
                        "auth_methods": ["Anonymous"],
                    }
                ],
            },
            "security": {
                "server_certificate_strategy": "auto_self_signed",
                "server_certificate_custom": None,
                "server_private_key_custom": None,
                "trusted_client_certificates": [],
            },
            "users": [],
            "address_space": {
                "namespace_uri": "urn:openplc:opcua:namespace",
                "variables": [],
                "structures": [],
                "arrays": [],
            },
            "format_version": 2,
        }
        data.update(extra)
        return data

    def test_absent_section_means_no_semantic_model(self):
        from opcua_config_model import OpcuaConfig

        assert OpcuaConfig.from_dict(self._base()).semantic_model is None

    def test_nodesets_and_bindings_are_parsed(self):
        from opcua_config_model import OpcuaConfig

        config = OpcuaConfig.from_dict(
            self._base(
                semantic_model={
                    "nodesets": ["models/a.xml", "models/b.xml"],
                    "bindings": "conf/opcua_bindings.json",
                }
            )
        )

        assert config.semantic_model.nodesets == ["models/a.xml", "models/b.xml"]
        assert config.semantic_model.bindings == "conf/opcua_bindings.json"

    def test_bindings_are_optional(self):
        from opcua_config_model import OpcuaConfig

        config = OpcuaConfig.from_dict(
            self._base(semantic_model={"nodesets": ["models/a.xml"]})
        )

        assert config.semantic_model.bindings is None

    @pytest.mark.parametrize(
        "section",
        [
            "text",
            {"nodesets": "models/a.xml"},
            {"nodesets": [""]},
            {"nodesets": [1]},
            {"nodesets": [], "bindings": ""},
            {"nodesets": [], "bindings": 3},
        ],
    )
    def test_invalid_sections_are_rejected(self, section):
        from opcua_config_model import OpcuaConfig

        with pytest.raises(ValueError):
            OpcuaConfig.from_dict(self._base(semantic_model=section))
