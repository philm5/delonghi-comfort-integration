"""Build installable release archives without changing the versioned source."""

import argparse
import json
from pathlib import Path
import re
from zipfile import ZIP_DEFLATED, ZipFile

ROOT = Path(__file__).resolve().parents[1]
DOMAIN = "delonghi_comfort"
INTEGRATION = ROOT / "custom_components" / DOMAIN


def integration_files():
    """Yield integration files, excluding interpreter and editor artifacts."""
    for path in sorted(INTEGRATION.rglob("*")):
        relative = path.relative_to(INTEGRATION)
        if (
            path.is_file()
            and not any(part.startswith(".") or part == "__pycache__" for part in relative.parts)
            and path.suffix not in {".pyc", ".pyo"}
        ):
            yield path


def build_release(output_dir: Path, tag: str | None = None) -> tuple[Path, Path]:
    """Create a manual-install ZIP and a complete package for one version."""
    manifest = json.loads((INTEGRATION / "manifest.json").read_text())
    version = manifest["version"]
    if not re.fullmatch(r"\d+\.\d+\.\d+", version):
        raise ValueError(f"Invalid release version: {version}")
    if tag is not None and tag.removeprefix("v") != version:
        raise ValueError(f"Tag {tag} does not match manifest version {version}")

    output_dir.mkdir(parents=True, exist_ok=True)
    integration_zip = output_dir / f"{DOMAIN}.zip"
    complete_zip = output_dir / f"delonghi-comfort-integration-v{version}.zip"
    files = list(integration_files())
    with ZipFile(integration_zip, "w", ZIP_DEFLATED) as archive:
        for path in files:
            archive.write(path, path.relative_to(INTEGRATION.parent))
    with ZipFile(complete_zip, "w", ZIP_DEFLATED) as archive:
        for path in files:
            archive.write(path, path.relative_to(ROOT))
        for name in ("README.md", "CHANGELOG.md", "UPGRADE.md", "LICENSE", "NOTICE", "hacs.json"):
            archive.write(ROOT / name, name)
    return integration_zip, complete_zip


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--tag", help="Require this tag to match manifest.json")
    parser.add_argument("--output-dir", type=Path, default=ROOT / "dist")
    args = parser.parse_args()
    for artifact in build_release(args.output_dir, args.tag):
        print(artifact)
