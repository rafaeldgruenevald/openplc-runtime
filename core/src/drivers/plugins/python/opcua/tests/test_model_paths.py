"""Tests for the safe resolution of semantic model files."""

import os
import sys
from pathlib import Path

import pytest

OPCUA_DIR = Path(__file__).resolve().parents[1]

if str(OPCUA_DIR) not in sys.path:
    sys.path.insert(0, str(OPCUA_DIR))

import model_paths  # noqa: E402


@pytest.fixture
def generated(tmp_path, monkeypatch) -> Path:
    root = tmp_path / "generated"
    (root / "models").mkdir(parents=True)
    monkeypatch.setenv(model_paths.GENERATED_DIR_ENV, str(root))
    return root.resolve()


def resolve(raw: str, root: Path, suffixes=(".xml",)) -> Path:
    return model_paths.resolve_model_file(raw, roots=(root,), suffixes=suffixes)


def test_relative_path_is_taken_from_the_generated_directory(generated):
    model = generated / "models" / "a.xml"
    model.write_text("<x/>")

    assert resolve("models/a.xml", generated) == model


def test_absolute_path_inside_a_root_is_accepted(generated):
    model = generated / "models" / "a.xml"
    model.write_text("<x/>")

    assert resolve(str(model), generated) == model


def test_parent_traversal_is_rejected(generated, tmp_path):
    (tmp_path / "secret.xml").write_text("<x/>")

    with pytest.raises(ValueError, match="outside"):
        resolve("../secret.xml", generated)


def test_symlink_escaping_the_root_is_rejected(generated, tmp_path):
    outside = tmp_path / "outside.xml"
    outside.write_text("<x/>")
    os.symlink(outside, generated / "models" / "link.xml")

    with pytest.raises(ValueError, match="outside"):
        resolve("models/link.xml", generated)


def test_absolute_path_elsewhere_is_rejected(generated):
    with pytest.raises(ValueError, match="outside"):
        resolve("/etc/passwd", generated)


def test_empty_path_is_rejected(generated):
    with pytest.raises(ValueError):
        resolve("  ", generated)


def test_missing_file_is_reported(generated):
    with pytest.raises(FileNotFoundError):
        resolve("models/missing.xml", generated)


def test_directory_is_rejected(generated):
    with pytest.raises(ValueError, match="regular file"):
        resolve("models", generated)


def test_wrong_extension_is_rejected(generated):
    (generated / "models" / "a.txt").write_text("x")

    with pytest.raises(ValueError, match="extension"):
        resolve("models/a.txt", generated)


def test_json_suffix_can_be_requested(generated):
    (generated / "models" / "b.json").write_text("{}")

    resolved = resolve("models/b.json", generated, suffixes=(".json",))

    assert resolved.name == "b.json"


def test_oversized_file_is_rejected(generated, monkeypatch):
    (generated / "models" / "big.xml").write_text("x" * 20)
    monkeypatch.setattr(model_paths, "MAX_MODEL_FILE_BYTES", 10)

    with pytest.raises(ValueError, match="larger"):
        resolve("models/big.xml", generated)


def test_generated_root_defaults_to_core_generated(monkeypatch):
    monkeypatch.delenv(model_paths.GENERATED_DIR_ENV, raising=False)

    assert model_paths.generated_root().name == "generated"
    assert model_paths.generated_root().parent.name == "core"
