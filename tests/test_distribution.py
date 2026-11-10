"""Validate the Marketplace contract and the delivered manual-install archives."""

import json
from pathlib import Path
from zipfile import ZipFile

from awesomeversion import AwesomeVersion
from homeassistant.components.marketplace.repositories.integration import (
    _check_loadable_manifest,
)
from homeassistant.components.marketplace.utils.validate import REPOSITORY_MANIFEST_VALUES
import pytest

from scripts.build_release import DOMAIN, INTEGRATION, ROOT, build_release


def test_marketplace_metadata_is_usable():
    metadata = json.loads((ROOT / "hacs.json").read_text())
    # Core ignores unknown or wrongly typed keys; reject them in our repository.
    for key, value in metadata.items():
        assert key in REPOSITORY_MANIFEST_VALUES
        assert REPOSITORY_MANIFEST_VALUES[key](value) == value
    assert metadata["name"]
    assert AwesomeVersion(metadata["homeassistant"]) >= AwesomeVersion("2026.11.0")
    _check_loadable_manifest(INTEGRATION, DOMAIN)


def test_manifest_uses_core_dependencies_and_a_valid_category():
    import homeassistant

    manifest = json.loads((INTEGRATION / "manifest.json").read_text())
    categories = json.loads(
        (Path(homeassistant.__file__).parent / "generated/integration_categories.json").read_text()
    )
    assert set(manifest["categories"]) <= {category["slug"] for category in categories}
    assert manifest["requirements"] == []
    assert manifest["issue_tracker"].endswith("filmackay/delonghi-comfort-integration/issues")


def test_archives_include_installable_code_without_caches(tmp_path):
    before = (INTEGRATION / "manifest.json").read_bytes()
    manifest = json.loads(before)
    integration_zip, complete_zip = build_release(tmp_path, f"v{manifest['version']}")
    for filename, prefix in ((integration_zip, DOMAIN), (complete_zip, f"custom_components/{DOMAIN}")):
        with ZipFile(filename) as archive:
            names = archive.namelist()
            assert f"{prefix}/__init__.py" in names
            assert f"{prefix}/exceptions.py" in names
            assert f"{prefix}/translations/en.json" in names
            assert json.loads(archive.read(f"{prefix}/manifest.json")) == manifest
            assert not any("__pycache__" in name or name.endswith((".pyc", ".pyo")) for name in names)
    with ZipFile(complete_zip) as archive:
        assert {"hacs.json", "README.md", "LICENSE", "NOTICE", "UPGRADE.md"} <= set(archive.namelist())
    assert (INTEGRATION / "manifest.json").read_bytes() == before


def test_mismatched_release_tag_is_rejected(tmp_path):
    with pytest.raises(ValueError, match="does not match manifest"):
        build_release(tmp_path, "v9999.0.0")
    assert list(tmp_path.iterdir()) == []
