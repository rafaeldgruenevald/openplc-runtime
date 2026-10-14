"""Tests for composite (structured) semantic bindings."""

import sys
from datetime import datetime
from pathlib import Path
from types import SimpleNamespace
from typing import Dict, List, Optional

import pytest
from asyncua import ua

OPCUA_DIR = Path(__file__).resolve().parents[1]

if str(OPCUA_DIR) not in sys.path:
    sys.path.insert(0, str(OPCUA_DIR))

import semantic_binding_config as config  # noqa: E402
import synchronization  # noqa: E402

NAMESPACE = "urn:test:model"


def leaf(arr: int, elem: int, datatype: str = "REAL", size: int = 4) -> Dict[str, object]:
    return {
        "symbol": f"INSTANCE0.X{elem}",
        "arrayIndex": arr,
        "elementIndex": elem,
        "datatype": datatype,
        "size": size,
    }


def scalar(identifier: str, elem: int) -> Dict[str, object]:
    return {
        "id": identifier,
        "nodeId": {
            "namespaceUri": NAMESPACE,
            "identifierType": "String",
            "identifier": identifier,
        },
        "source": {"kind": "openplc-debug-leaf", **leaf(0, elem)},
        "types": {"iec": "REAL", "opcUa": "Float"},
        "access": {"read": True, "write": False},
        "update": {"mode": "poll", "intervalMs": 100},
    }


def composite(identifier: str = "PT101.Range", **overrides: object) -> Dict[str, object]:
    data: Dict[str, object] = {
        "id": identifier,
        "nodeId": {
            "namespaceUri": NAMESPACE,
            "identifierType": "String",
            "identifier": identifier,
        },
        "structure": "Range",
        "fields": {"Low": leaf(0, 10), "High": leaf(0, 11)},
    }
    data.update(overrides)
    return data


def document(composites: Optional[List[Dict[str, object]]]) -> Dict[str, object]:
    data: Dict[str, object] = {
        "schemaVersion": "1.0",
        "project": {"id": "p", "namespaceUri": NAMESPACE},
        "runtime": {"type": "openplc", "version": "4.3.1"},
        "bindings": [scalar("PT101.Value", 1)],
    }
    if composites is not None:
        data["compositeBindings"] = composites
    return data


def test_a_document_without_composites_still_loads():
    parsed = config.SemanticBindingConfig.from_dict(document(None))

    assert parsed.composite_bindings == []


def test_a_range_composite_is_parsed():
    parsed = config.SemanticBindingConfig.from_dict(document([composite()]))

    binding = parsed.composite_bindings[0]

    assert binding.structure == "Range"
    assert binding.fields["Low"].address == (0, 10)
    assert binding.fields["High"].address == (0, 11)
    assert binding.target.identifier == "PT101.Range"


def test_lreal_fields_are_accepted():
    data = composite(fields={"Low": leaf(0, 10, "LREAL", 8), "High": leaf(0, 11, "LREAL", 8)})

    parsed = config.SemanticBindingConfig.from_dict(document([data]))

    assert parsed.composite_bindings[0].fields["High"].datatype == "LREAL"


@pytest.mark.parametrize(
    "overrides, message",
    [
        ({"structure": "EUInformation"}, "Unsupported composite structure"),
        ({"fields": {"Low": leaf(0, 10)}}, "needs exactly the fields"),
        (
            {"fields": {"Low": leaf(0, 10), "High": leaf(0, 11), "Mid": leaf(0, 12)}},
            "needs exactly the fields",
        ),
        (
            {"fields": {"Low": leaf(0, 10, "INT", 2), "High": leaf(0, 11)}},
            "must be REAL or LREAL",
        ),
    ],
)
def test_invalid_composites_are_rejected(overrides, message):
    with pytest.raises(ValueError, match=message):
        config.SemanticBindingConfig.from_dict(document([composite(**overrides)]))


def test_a_composite_cannot_reuse_a_scalar_target():
    with pytest.raises(ValueError, match="Duplicate imported NodeId"):
        config.SemanticBindingConfig.from_dict(document([composite("PT101.Value")]))


def test_a_composite_must_target_the_project_namespace():
    other = composite()
    other["nodeId"] = {**other["nodeId"], "namespaceUri": "urn:other"}

    with pytest.raises(ValueError, match="project namespace"):
        config.SemanticBindingConfig.from_dict(document([other]))


def test_an_invalid_composite_names_its_index():
    with pytest.raises(ValueError, match="composite binding at index 1"):
        config.SemanticBindingConfig.from_dict(
            document([composite(), composite("PT102.Range", structure="Nope")])
        )


class FakeRuntime:
    """Replaces the debug_read thunk: leaf address -> value."""

    def __init__(self, values: Dict[tuple, Optional[float]]):
        self.values = values

    def __call__(self, args, arr, elem, datatype):
        return self.values.get((arr, elem))


def make_manager(monkeypatch, values):
    monkeypatch.setattr(synchronization, "debug_read_value", FakeRuntime(values))

    parsed = config.SemanticBindingConfig.from_dict(document([composite()]))

    resolved = SimpleNamespace(
        binding=parsed.composite_bindings[0],
        node=SimpleNamespace(nodeid=ua.NodeId("PT101.Range", 2)),
    )

    manager = synchronization.SynchronizationManager(
        args=None, variable_nodes={}, server=None, composite_nodes=[resolved]
    )

    return manager, resolved


def test_the_callback_builds_a_range_from_the_live_leaves(monkeypatch):
    manager, resolved = make_manager(monkeypatch, {(0, 10): 0.0, (0, 11): 16.0})

    data_value = manager._make_composite_callback(resolved)(None, None)

    assert data_value.StatusCode_.is_good()

    assert data_value.Value.VariantType == ua.VariantType.ExtensionObject
    assert data_value.Value.Value.Low == 0.0
    assert data_value.Value.Value.High == 16.0
    assert isinstance(data_value.SourceTimestamp, datetime)


def test_the_range_follows_the_plc(monkeypatch):
    values = {(0, 10): 0.0, (0, 11): 16.0}

    manager, resolved = make_manager(monkeypatch, values)

    callback = manager._make_composite_callback(resolved)

    values[(0, 11)] = 25.0

    assert callback(None, None).Value.Value.High == 25.0


def test_a_missing_leaf_is_reported_bad(monkeypatch):
    manager, resolved = make_manager(monkeypatch, {(0, 10): 0.0, (0, 11): None})

    data_value = manager._make_composite_callback(resolved)(None, None)

    assert data_value.StatusCode_.value == ua.StatusCodes.BadNoDataAvailable
    assert data_value.Value.Value is None


def test_hooks_are_not_installed_without_an_address_space(monkeypatch):
    manager, _ = make_manager(monkeypatch, {})

    # server is None: nothing to hook, and no exception
    manager._register_composite_hooks()
