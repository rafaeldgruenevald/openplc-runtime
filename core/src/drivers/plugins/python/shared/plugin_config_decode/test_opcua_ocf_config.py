"""Tests for the ocf section (the OCF client of the DCN) of the OPC UA configuration."""

import os
import sys

import pytest

current_dir = os.path.dirname(os.path.abspath(__file__))
if current_dir not in sys.path:
    sys.path.insert(0, current_dir)


class TestOcfConfig:
    """ocf section of opcua.json."""

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

    GOOD = {
        "gds": {"url": "opc.tcp://gds:62541/OpasGds"},
        "period_ms": 200,
        "inputs": [
            {
                "alias": "PT101",
                "target": {
                    "symbol": "PT101.VALUE",
                    "arrayIndex": 1,
                    "elementIndex": 16,
                    "datatype": "REAL",
                    "size": 4,
                },
            }
        ],
    }

    def test_absent_section_means_no_ocf_client(self):
        from opcua_config_model import OpcuaConfig

        assert OpcuaConfig.from_dict(self._base()).ocf is None

    def test_the_gds_the_period_and_the_inputs_are_parsed(self):
        from opcua_config_model import OpcuaConfig

        ocf = OpcuaConfig.from_dict(self._base(ocf=self.GOOD)).ocf

        assert ocf.gds_url == "opc.tcp://gds:62541/OpasGds"
        assert ocf.period_ms == 200
        assert [(i.alias, i.array_index, i.element_index, i.datatype) for i in ocf.inputs] == [
            ("PT101", 1, 16, "REAL")
        ]

    def test_the_period_defaults_to_100_ms(self):
        from opcua_config_model import OpcuaConfig

        data = dict(self.GOOD)
        del data["period_ms"]

        assert OpcuaConfig.from_dict(self._base(ocf=data)).ocf.period_ms == 100

    @pytest.mark.parametrize(
        "mutate",
        [
            lambda d: d.pop("gds"),
            lambda d: d["gds"].update(url=""),
            lambda d: d.update(period_ms=1),
            lambda d: d.update(inputs="PT101"),
            lambda d: d["inputs"][0].update(alias=""),
            lambda d: d["inputs"][0].pop("target"),
            lambda d: d["inputs"][0]["target"].update(arrayIndex="1"),
            lambda d: d["inputs"][0]["target"].update(datatype=""),
        ],
    )
    def test_invalid_sections_are_rejected(self, mutate):
        import copy

        from opcua_config_model import OpcuaConfig

        data = copy.deepcopy(self.GOOD)

        mutate(data)

        with pytest.raises(ValueError):
            OpcuaConfig.from_dict(self._base(ocf=data))
