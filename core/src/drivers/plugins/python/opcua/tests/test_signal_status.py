"""A bound node is served with the StatusCode the program keeps for its signal
(MetaData.Status), when the binding names that leaf."""

import sys
from pathlib import Path
from typing import Dict, Optional

import pytest
from asyncua import ua

OPCUA_DIR = Path(__file__).resolve().parents[1]

if str(OPCUA_DIR) not in sys.path:
    sys.path.insert(0, str(OPCUA_DIR))

import semantic_binding_config as config  # noqa: E402
import synchronization  # noqa: E402
from opcua_types import VariableNode  # noqa: E402

NAMESPACE = "urn:test:model"


def leaf(elem: int, datatype: str = "REAL", size: int = 4) -> Dict[str, object]:
    return {
        "kind": "openplc-debug-leaf",
        "symbol": f"PT101.X{elem}",
        "arrayIndex": 0,
        "elementIndex": elem,
        "datatype": datatype,
        "size": size,
    }


def binding(status: Optional[Dict[str, object]]) -> Dict[str, object]:
    data: Dict[str, object] = {
        "id": "PT101.Value",
        "nodeId": {"namespaceUri": NAMESPACE, "identifierType": "String", "identifier": "PT101"},
        "source": leaf(1),
        "types": {"iec": "REAL", "opcUa": "Float"},
        "access": {"read": True, "write": False},
        "update": {"mode": "poll", "intervalMs": 100},
    }
    if status is not None:
        data["status"] = status
    return data


def test_the_status_leaf_is_optional():
    assert config.SemanticBinding.from_dict(binding(None)).status is None


def test_the_status_leaf_is_parsed():
    parsed = config.SemanticBinding.from_dict(binding(leaf(2, "UDINT")))

    assert parsed.status.address == (0, 2)


def test_a_status_leaf_must_hold_a_status_code():
    with pytest.raises(ValueError, match="UDINT or DWORD"):
        config.SemanticBinding.from_dict(binding(leaf(2, "REAL")))


class FakeRuntime:
    def __init__(self, values: Dict[tuple, Optional[object]]):
        self.values = values

    def __call__(self, args, arr, elem, datatype):
        return self.values.get((arr, elem))


def read(monkeypatch, values, status_address=(0, 2)):
    monkeypatch.setattr(synchronization, "debug_read_value", FakeRuntime(values))

    node = VariableNode(
        node=None, arr=0, elem=1, datatype="REAL", access_mode="readonly",
        status_address=status_address,
    )

    manager = synchronization.SynchronizationManager(args=None, variable_nodes={}, server=None)

    return manager._make_read_callback(0, 1, node)(None, None)


def test_a_good_signal_is_served_good(monkeypatch):
    value = read(monkeypatch, {(0, 1): 4.5, (0, 2): 0})

    assert value.StatusCode_.is_good()
    assert value.Value.Value == 4.5


def test_an_uncertain_signal_keeps_its_value(monkeypatch):
    value = read(monkeypatch, {(0, 1): 4.5, (0, 2): ua.StatusCodes.UncertainLastUsableValue})

    assert value.StatusCode_.value == ua.StatusCodes.UncertainLastUsableValue
    assert value.Value.Value == 4.5


def test_a_bad_signal_is_served_bad_without_a_value(monkeypatch):
    value = read(monkeypatch, {(0, 1): 4.5, (0, 2): ua.StatusCodes.BadNoCommunication})

    assert value.StatusCode_.value == ua.StatusCodes.BadNoCommunication
    assert value.Value is None or value.Value.Value is None


def test_an_unreadable_status_is_bad_no_data(monkeypatch):
    value = read(monkeypatch, {(0, 1): 4.5})

    assert value.StatusCode_.value == ua.StatusCodes.BadNoDataAvailable


def test_without_a_status_leaf_a_readable_node_is_good(monkeypatch):
    value = read(monkeypatch, {(0, 1): 4.5, (0, 2): ua.StatusCodes.BadNoCommunication}, None)

    assert value.StatusCode_.is_good()
