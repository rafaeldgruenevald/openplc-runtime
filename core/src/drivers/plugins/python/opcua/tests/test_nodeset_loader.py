"""Tests for optional OPC UA NodeSet loading."""

import sys
from pathlib import Path

import pytest


OPCUA_DIR = Path(__file__).resolve().parents[1]

if str(OPCUA_DIR) not in sys.path:
    sys.path.insert(0, str(OPCUA_DIR))


import nodeset_loader


def test_rejects_empty_path():
    with pytest.raises(ValueError):
        nodeset_loader.validate_nodeset_path("")


def test_rejects_path_outside_allowed_root():
    with pytest.raises(ValueError):
        nodeset_loader.validate_nodeset_path("/etc/passwd")


def test_rejects_missing_file(tmp_path, monkeypatch):
    model_root = tmp_path / "models"
    model_root.mkdir()

    monkeypatch.setattr(
        nodeset_loader,
        "ALLOWED_MODEL_ROOT",
        model_root.resolve(),
    )

    with pytest.raises(FileNotFoundError):
        nodeset_loader.validate_nodeset_path(
            str(model_root / "missing.xml")
        )


def test_rejects_non_xml_extension(tmp_path, monkeypatch):
    model_root = tmp_path / "models"
    model_root.mkdir()

    model_file = model_root / "model.txt"
    model_file.write_text("not xml", encoding="utf-8")

    monkeypatch.setattr(
        nodeset_loader,
        "ALLOWED_MODEL_ROOT",
        model_root.resolve(),
    )

    with pytest.raises(ValueError):
        nodeset_loader.validate_nodeset_path(
            str(model_file)
        )


def test_accepts_xml_below_allowed_root(
    tmp_path,
    monkeypatch,
):
    model_root = tmp_path / "models"
    model_root.mkdir()

    model_file = model_root / "model.xml"
    model_file.write_text(
        "<UANodeSet />",
        encoding="utf-8",
    )

    monkeypatch.setattr(
        nodeset_loader,
        "ALLOWED_MODEL_ROOT",
        model_root.resolve(),
    )

    result = nodeset_loader.validate_nodeset_path(
        str(model_file)
    )

    assert result == model_file.resolve()


GROUP_TYPE_NODESET = """<?xml version="1.0" encoding="utf-8"?>
<UANodeSet xmlns="http://opcfoundation.org/UA/2011/03/UANodeSet.xsd">
  <NamespaceUris><Uri>urn:test</Uri></NamespaceUris>
  <UAObjectType NodeId="ns=1;i=1005" BrowseName="1:FunctionalGroupType"/>
  <UAObjectType NodeId="ns=1;i=2000" BrowseName="1:OtherType"/>
  <UAObject NodeId="ns=1;i=73" BrowseName="1:Configuration">
    <References><Reference ReferenceType="HasTypeDefinition">ns=1;i=1005</Reference></References>
  </UAObject>
  <UAObject NodeId="ns=1;i=74" BrowseName="1:Referenced">
    <References><Reference ReferenceType="HasTypeDefinition">ns=1;i=1005</Reference></References>
  </UAObject>
  <UAObject NodeId="ns=1;i=75" BrowseName="1:HasParent" ParentNodeId="ns=1;i=74">
    <References><Reference ReferenceType="HasTypeDefinition">ns=1;i=1005</Reference></References>
  </UAObject>
  <UAObject NodeId="ns=1;i=76" BrowseName="1:OtherKind">
    <References><Reference ReferenceType="HasTypeDefinition">ns=1;i=2000</Reference></References>
  </UAObject>
  <UAObject NodeId="ns=1;i=77" BrowseName="1:Holder">
    <References><Reference ReferenceType="Organizes">ns=1;i=74</Reference></References>
  </UAObject>
</UANodeSet>
"""

NO_GROUP_TYPE_NODESET = """<?xml version="1.0" encoding="utf-8"?>
<UANodeSet xmlns="http://opcfoundation.org/UA/2011/03/UANodeSet.xsd">
  <UAObject NodeId="ns=1;i=73" BrowseName="1:Configuration"/>
</UANodeSet>
"""


def test_only_unreferenced_parentless_group_instances_are_skipped(tmp_path):
    path = tmp_path / "a.xml"
    path.write_text(GROUP_TYPE_NODESET)

    xml_text, skipped = nodeset_loader.prepare_nodeset(path)

    # 74 is referenced, 75 has a parent, 76 is another type, 77 is no group
    assert skipped == ["ns=1;i=73"]

    assert 'NodeId="ns=1;i=73"' not in xml_text
    assert 'NodeId="ns=1;i=74"' in xml_text
    assert 'NodeId="ns=1;i=76"' in xml_text


def test_a_file_with_nothing_to_skip_is_imported_as_it_is(tmp_path):
    path = tmp_path / "b.xml"
    path.write_text(NO_GROUP_TYPE_NODESET)

    assert nodeset_loader.prepare_nodeset(path) == (None, [])


def test_the_file_on_disk_is_never_modified(tmp_path):
    path = tmp_path / "c.xml"
    path.write_text(GROUP_TYPE_NODESET)

    nodeset_loader.prepare_nodeset(path)

    assert path.read_text() == GROUP_TYPE_NODESET
