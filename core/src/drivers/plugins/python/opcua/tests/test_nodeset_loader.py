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
